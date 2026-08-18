"""A caller must be able to watch the run it started.

`POST /v1/agent/runs` blocks for the whole run, so the id in its response
arrives after every event has already been emitted. There is no run listing
route, and the store hashes the id into its filename, so the id cannot be
recovered from the outside either. A browser therefore had no way to open
`GET /v1/runs/{run_id}/events` for its own run.

Letting the caller choose the id fixes that, and immediately raises two
questions the server has to answer rather than the client: what an acceptable
id looks like, and what happens when one is already taken.
"""
from __future__ import annotations

import json

from s17code.core.memory.embeddings import DeterministicEmbedder

SCOPE = {"tenant_id": "acme", "project_id": "proofs", "user_id": "reviewer"}
TASK = "Say something short."


async def _fake_llm(_app, prompt, _system):
    if "evidence-readiness critic" in _system:
        return {"text": json.dumps({"ready": True, "missing": [], "reason": "complete"}),
                "provider": "fake", "model": "critic"}
    if "decision core of a live-graph agent" in _system:
        context = json.loads(prompt)
        return {"text": json.dumps({"add": [{"id": "answer", "capability": "answer_with_evidence",
                "arguments": {"query": context["goal"]}, "depends_on": []}], "cancel": [],
                "finish": False, "reason": "answer directly"}), "provider": "fake", "model": "planner"}
    return {"text": "plain answer", "provider": "fake", "model": "fake"}


def _offline(app_client, monkeypatch):
    import s17code.routes as agent_route

    app_client.app.state.runtime.memory.embedder = DeterministicEmbedder(128)
    monkeypatch.setattr(agent_route, "gateway_text_llm", _fake_llm)


def test_the_run_uses_the_id_the_client_chose(app_client, monkeypatch):
    _offline(app_client, monkeypatch)

    response = app_client.post("/v1/agent/runs",
                               json={**SCOPE, "prompt": TASK, "run_id": "chosen-by-the-client"})

    assert response.status_code == 200
    assert response.json()["run_id"] == "chosen-by-the-client"
    # The point of the exercise: the stream for that id is servable.
    assert app_client.get("/v1/runs/chosen-by-the-client/snapshot").status_code == 200


def test_omitting_the_id_still_generates_one(app_client, monkeypatch):
    """Additive. A caller that does not care keeps the previous behaviour."""
    _offline(app_client, monkeypatch)

    body = app_client.post("/v1/agent/runs", json={**SCOPE, "prompt": TASK}).json()

    assert body["run_id"].startswith("run-")


def test_an_id_already_in_use_is_a_conflict(app_client, monkeypatch):
    """Not an overwrite, and not a silent join.

    graph.start() returns False for an id that already exists and the runtime
    ignored it, so a second run on a taken id would have proceeded against the
    first one's graph.
    """
    _offline(app_client, monkeypatch)
    app_client.app.state.runtime.graph.start("already-running")

    response = app_client.post("/v1/agent/runs",
                               json={**SCOPE, "prompt": TASK, "run_id": "already-running"})

    assert response.status_code == 409


def test_an_unusable_id_is_refused_before_anything_runs(app_client, monkeypatch):
    """The store hashes the id, so this is not traversal - it is hygiene.

    An id reaches URLs, logs and journal keys. Constrain it where it enters
    rather than at each of those.
    """
    _offline(app_client, monkeypatch)

    for bad in ["../escape", "has space", "", "x" * 65, "semi;colon"]:
        response = app_client.post("/v1/agent/runs", json={**SCOPE, "prompt": TASK, "run_id": bad})
        assert response.status_code == 422, f"{bad!r} was accepted"
