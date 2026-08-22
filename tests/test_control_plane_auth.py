"""The control plane fails closed, on every write path, without exception.

A subscription carries `allowed_side_effects` and a budget: it is the object the
whole session's security argument rests on. An unauthenticated write there hands
an anonymous caller the authority to decide what the agent may do and how much it
may spend. Starting a run and resuming a parked node both spend money too.

The shape being guarded against is `if expected and not compare_digest(...)`,
which reads like a check and behaves like an open door whenever the variable is
unset — which is exactly the state a fresh checkout is in.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import conftest
import pytest
from s17code.core.live_graph import Deferred, GraphPatch, TaskSpec

WRITE_PATHS = [
    ("put", "/v1/agent/subscriptions/probe", {"id": "probe", "instruction": "watch", "tenant_id": "t"}),
    ("post", "/v1/agent/events", {"id": "e1", "source": "s", "type": "t",
                                  "occurred_at": "2026-08-05T09:00:00Z"}),
    ("post", "/v1/agent/runs", {"prompt": "hello", "tenant_id": "t"}),
    ("post", "/v1/agent/runs/run-1/resume", {}),
    # These four were missing from the list that the session's security
    # argument rests on. An unauthenticated POST here poisons memory, searches
    # another tenant, or approves a parked high-impact node.
    ("post", "/v1/agent/facts", {"tenant_id": "t", "text": "secret", "source_uri": "mem://x"}),
    ("post", "/v1/agent/documents", {"tenant_id": "t", "text": "doc", "source_uri": "mem://d"}),
    ("post", "/v1/agent/memory/search", {"tenant_id": "t", "query": "secret"}),
    ("post", "/v1/action", {"run_id": "r", "node_id": "n", "action": "approve"}),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITE_PATHS)
def test_a_write_path_refuses_to_serve_when_no_token_is_configured(
    app_client, monkeypatch, method, path, body
) -> None:
    monkeypatch.delenv("S17_CONTROL_TOKEN", raising=False)
    response = getattr(app_client, method)(path, json=body)
    assert response.status_code == 503
    assert "S17_CONTROL_TOKEN" in response.json()["detail"]


@pytest.mark.parametrize(("method", "path", "body"), WRITE_PATHS)
def test_a_write_path_rejects_the_wrong_token(app_client, method, path, body) -> None:
    response = getattr(app_client, method)(path, json=body,
                                           headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_the_right_token_is_accepted(app_client) -> None:
    response = app_client.put("/v1/agent/subscriptions/probe",
                              json={"id": "probe", "instruction": "watch", "tenant_id": "t"})
    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_the_completion_callback_has_its_own_token_and_also_fails_closed(
    app_client, monkeypatch
) -> None:
    """A remote job service may finish work; it may not write subscriptions."""
    body = {"handle": "job-1", "event_type": "job.completed", "success": True, "payload": {}}

    # The control token is not the completion token.
    denied = app_client.post("/v1/agent/completions", json=body)
    assert denied.status_code == 401

    accepted = app_client.post("/v1/agent/completions", json=body,
                               headers={"Authorization": f"Bearer {conftest.COMPLETION_TOKEN}"})
    # Unknown handle, but authenticated: the gate passed and the store answered.
    assert accepted.status_code == 200
    assert accepted.json()["duplicate_or_unknown"] is True

    monkeypatch.delenv("S17_COMPLETION_TOKEN", raising=False)
    unset = app_client.post("/v1/agent/completions", json=body,
                            headers={"Authorization": f"Bearer {conftest.COMPLETION_TOKEN}"})
    assert unset.status_code == 503


def test_read_only_observability_is_available_to_an_operator(app_client) -> None:
    """Liveness answers 503 when the watcher is silent, which is the alarm."""
    liveness = app_client.get("/v1/agent/liveness")
    assert liveness.status_code == 503
    assert liveness.json()["alive"] is False

    report = app_client.get("/v1/agent/report")
    assert report.status_code == 200
    assert report.json()["totals"]["events_seen"] == 0

    markdown = app_client.get("/v1/agent/report", params={"fmt": "markdown"})
    assert "Overnight report" in markdown.text
    assert "NOT ALIVE" in markdown.text


def test_the_operator_console_is_served_and_is_read_only(app_client) -> None:
    """§9 promises an operations page. It has to exist, and it has to be inert.

    The console reads the durable history and nothing else. A page that could
    create a subscription would be the exact hole the control plane exists to
    close, so it ships with no write path at all.
    """
    page = app_client.get("/console")
    assert page.status_code == 200
    body = page.text
    assert "autonomy console" in body.lower()

    # It reads the endpoints an operator needs...
    for endpoint in ("/v1/agent/liveness", "/v1/agent/refusals",
                     "/v1/agent/report", "/v1/agent/events/stream?after="):
        assert endpoint in body, f"console never calls {endpoint}"

    # ...and never writes. No method:POST/PUT/DELETE anywhere in the page.
    lowered = body.lower()
    for verb in ('method: "post"', "method:'post'", 'method: "put"',
                 'method: "delete"', "_method: post"):
        assert verb not in lowered, f"console contains a write call: {verb}"


def _park_approval(runtime, run_id: str = "hitl-park") -> str:
    runtime.graph.start(run_id, context={
        "prompt": "pay the invoice",
        "scope": {"tenant_id": "t", "project_id": None, "user_id": None,
                  "agent_id": None, "run_id": None},
        "source_uri": "api://agent/runs", "source_author": "api-user",
        "inbound_id": None, "respond_as": "text",
        "allowed_side_effects": ["request_approval"], "initial_evidence": {},
    })
    task = TaskSpec("approve", "request_approval",
                    {"question": "Send $9,000 to acct-9?", "choices": ["yes", "no"]})
    runtime.graph.apply_patch(run_id, GraphPatch(add=(task,), reason="needs a person"),
                              trigger_event=1)
    runtime.graph.mark_running(run_id, [task])
    runtime.graph.record_waiting(run_id, "approve", Deferred(
        "handle-1", "approval.received",
        {"question": "Send $9,000 to acct-9?", "choices": ["yes", "no"]},
    ).as_wait())
    return run_id


def test_an_anonymous_caller_cannot_approve_a_parked_node(app_client) -> None:
    """`POST /v1/action` used to be missing from WRITE_PATHS.

    `wait.params` was also missing on `request_approval`, so `args={}` matched
    the empty default and consumed the handle before the graph even resumed.
    """
    run_id = _park_approval(app_client.app.state.runtime)
    naked = TestClient(app_client.app)
    stolen = naked.post("/v1/action", json={
        "run_id": run_id, "node_id": "approve", "action": "approve", "args": {},
    })
    assert stolen.status_code in {401, 503}
    node = app_client.app.state.runtime.graph.snapshot(run_id).nodes["approve"]
    assert node["state"] == "waiting"


def test_empty_args_do_not_approve_a_node_that_never_stored_params(app_client) -> None:
    """Even a holder of the control token cannot approve unbound work."""
    run_id = _park_approval(app_client.app.state.runtime, run_id="hitl-unbound")
    response = app_client.post("/v1/action", json={
        "run_id": run_id, "node_id": "approve", "action": "approve", "args": {},
    })
    assert response.status_code == 409
    assert "bound" in response.json()["detail"]
    node = app_client.app.state.runtime.graph.snapshot(run_id).nodes["approve"]
    assert node["state"] == "waiting"


def test_an_anonymous_caller_cannot_poison_or_read_another_tenant_memory(app_client) -> None:
    naked = TestClient(app_client.app)
    poison = naked.post("/v1/agent/facts", json={
        "tenant_id": "victim", "text": "the override code is 0000",
        "source_uri": "http://evil.example/fact",
    })
    assert poison.status_code in {401, 503}
    probe = naked.post("/v1/agent/memory/search", json={
        "tenant_id": "victim", "query": "override code",
    })
    assert probe.status_code in {401, 503}
    # The authenticated control plane still sees an empty tenant: the write
    # never landed.
    hits = app_client.post("/v1/agent/memory/search", json={
        "tenant_id": "victim", "query": "override code",
    })
    assert hits.status_code == 200
    assert hits.json()["hits"] == []
