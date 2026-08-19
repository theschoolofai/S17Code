"""wait=false must return run_id before the run finishes so UIs can stream."""
from __future__ import annotations

import asyncio
import time


def test_wait_false_returns_run_id_before_finish(app_client, monkeypatch):
    """GET /v1/runs/{id}/snapshot must work while the run is still in flight.

    Before the fix, POST /v1/agent/runs awaited the entire graph, so clients
    never received a run_id early enough to open the AG-UI event stream.
    Graph registration now happens before embeddings/LLM I/O.
    """
    from s17code.main import app

    gate = {"go": False}

    async def gated_complete(prompt: str, system: str):
        for _ in range(500):
            if gate["go"]:
                break
            await asyncio.sleep(0.01)
        return {"text": "hello", "model": "test"}

    monkeypatch.setattr(app.state.gateway, "complete", gated_complete)
    # Avoid a live embedding HTTP call during the async prelude.
    monkeypatch.setattr(
        app.state.runtime.memory,
        "_embed_document",
        lambda text: [0.0] * 8,
    )

    response = app_client.post(
        "/v1/agent/runs",
        json={
            "tenant_id": "t",
            "project_id": "async-start",
            "prompt": "Say hello in one word.",
            "wait": False,
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "running"
    assert body["finished"] is False
    run_id = body["run_id"]
    assert run_id.startswith("run-")

    snap = app_client.get(f"/v1/runs/{run_id}/snapshot")
    assert snap.status_code == 200, snap.text

    gate["go"] = True
    for _ in range(200):
        journal = app_client.get(f"/v1/agent/runs/{run_id}")
        if journal.status_code == 200 and journal.json().get("finished"):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("async run did not finish")
