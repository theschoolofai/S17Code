"""The shipped app viewer starts a run, and the page never holds a token.

`app.html` POSTed `/v1/agent/runs` with a Content-Type and nothing else. That
route is bearer-gated and fails closed, so the viewer answered 503 with the
token unset and 401 with it set: broken under every configuration.

The obvious repair is the dangerous one. `S17_CONTROL_TOKEN` is a server-side
secret and it unlocks `budget`, `principal` and `allowed_side_effects`; putting
it in served HTML would fix the 401 and hand the authority the control plane
exists to protect to every tab - and to any prompt-injected surface, because
`setStatus()` writes model-derived text through `innerHTML`.

So the page gets no credential at all. Loading `/app` mints a per-process
session and returns it as an HttpOnly cookie, and the page posts to `/app/runs`,
a route that is off by default, narrower than the control plane, and cannot be
read by script. These tests pin both halves: the viewer works, and nothing about
`/v1/agent/runs` got looser to make that true.
"""
from __future__ import annotations

import json

import conftest
import pytest

import s17code.routes as agent_route
from s17code.core.memory.embeddings import DeterministicEmbedder

VIEWER_ENV = "S17_APP_VIEWER"
VIEWER_COOKIE = "s17_app_viewer"
GOAL = "Teach me for IIT JEE. Ask me which subject to study."


@pytest.fixture
def browser(monkeypatch):
    """A client with NO Authorization header - the thing a browser actually is.

    The shared `app_client` fixture attaches the control token to every request,
    which would hide the entire bug: the viewer's problem is that it has no
    bearer and can never be given one.
    """
    from fastapi.testclient import TestClient

    from s17code.main import app

    monkeypatch.setenv(VIEWER_ENV, "1")
    with TestClient(app) as client:
        client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
        yield client


@pytest.fixture
def fake_planner(monkeypatch):
    """Plan one terminal node and answer it, so a run reaches a real outcome."""

    async def fake(_app, prompt: str, system: str):
        if "evidence-readiness critic" in system:
            return {"text": json.dumps({"ready": True, "missing": [], "reason": "complete"}),
                    "provider": "fake", "model": "critic"}
        if "decision core of a live-graph agent" in system:
            context = json.loads(prompt)
            return {"text": json.dumps({"add": [{"id": "answer", "capability": "answer_with_evidence",
                    "arguments": {"query": context["goal"]}, "depends_on": []}],
                    "cancel": [], "finish": False, "reason": "answer directly"}),
                    "provider": "fake", "model": "planner"}
        return {"text": "an answer", "provider": "fake", "model": "fake"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake)


class TestThePageCarriesNoSecret:
    def test_the_served_page_never_contains_the_control_token(self, browser) -> None:
        page = browser.get("/app")

        assert page.status_code == 200
        assert conftest.CONTROL_TOKEN not in page.text

    def test_the_page_does_not_call_the_bearer_gated_control_plane(self, browser) -> None:
        """A page that cannot hold a bearer must not be pointed at a route that
        demands one; that combination is the bug, in one line of HTML."""
        page = browser.get("/app")

        assert 'fetch(API+"/v1/agent/runs"' not in page.text
        assert 'fetch(API+"/app/runs"' in page.text
        assert "Authorization" not in page.text

    def test_the_session_cookie_is_unreadable_by_the_page_and_by_other_sites(
        self, browser
    ) -> None:
        page = browser.get("/app")

        cookie = page.headers["set-cookie"]
        assert cookie.startswith(f"{VIEWER_COOKIE}=")
        assert "HttpOnly" in cookie          # setStatus() writes innerHTML
        assert "SameSite=strict" in cookie   # no other origin can spend here
        assert "Path=/app" in cookie         # rides on no other route


class TestTheViewerCanStartARun:
    def test_a_run_starts_with_no_bearer_anywhere(self, browser, fake_planner) -> None:
        browser.get("/app")  # the page load is what mints the session

        started = browser.post("/app/runs", json={"prompt": GOAL})

        assert started.status_code == 200, started.text
        assert started.json()["run_id"]

    def test_the_browser_cannot_name_the_authority_the_token_protects(
        self, browser, fake_planner
    ) -> None:
        """Scope, response mode and the side-effect grant are the server's to
        choose. A body that tries to claim them changes nothing."""
        browser.get("/app")

        started = browser.post("/app/runs", json={
            "prompt": GOAL, "allowed_side_effects": ["send_email"],
            "budget": 1000.0, "principal": "somebody-else", "tenant_id": "attacker",
        })

        assert started.status_code == 200, started.text
        context = browser.app.state.runtime.graph.context(started.json()["run_id"])
        assert context["allowed_side_effects"] == []
        assert context["respond_as"] == "ui"
        assert context["scope"]["tenant_id"] == "local"


class TestItFailsClosed:
    def test_both_viewer_routes_refuse_when_the_flag_is_not_set(
        self, browser, monkeypatch
    ) -> None:
        """The default install ships the viewer off, and says so."""
        monkeypatch.delenv(VIEWER_ENV, raising=False)

        page = browser.get("/app")
        started = browser.post("/app/runs", json={"prompt": GOAL})

        assert page.status_code == 503
        assert started.status_code == 503
        assert VIEWER_ENV in started.json()["detail"]

    def test_a_post_without_the_session_cookie_is_refused(self, browser) -> None:
        """No page load, no session - which is what a cross-site POST looks like."""
        started = browser.post("/app/runs", json={"prompt": GOAL})

        assert started.status_code == 401

    def test_a_guessed_cookie_is_refused(self, browser) -> None:
        """The session is 32 random bytes; a guess must fail, not be compared
        against an empty expectation."""
        browser.get("/app")
        browser.cookies.set(VIEWER_COOKIE, "s17_app_viewer")

        started = browser.post("/app/runs", json={"prompt": GOAL})

        assert started.status_code == 401


class TestTheControlPlaneIsUnchanged:
    def test_the_bearer_gate_still_refuses_a_browser(self, browser) -> None:
        """The viewer route must not have become a way around the gate."""
        body = {"prompt": GOAL, "tenant_id": "course"}
        browser.get("/app")  # even holding a valid viewer session

        assert browser.post("/v1/agent/runs", json=body).status_code == 401
        assert browser.post("/v1/agent/runs", json=body,
                            headers={"Authorization": "Bearer wrong"}).status_code == 401

    def test_the_bearer_gate_still_refuses_to_serve_with_no_token_configured(
        self, browser, monkeypatch
    ) -> None:
        monkeypatch.delenv("S17_CONTROL_TOKEN", raising=False)

        refused = browser.post("/v1/agent/runs", json={"prompt": GOAL, "tenant_id": "course"})

        assert refused.status_code == 503
        assert "S17_CONTROL_TOKEN" in refused.json()["detail"]
