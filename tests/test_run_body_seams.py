"""Two RunBody fields that AgentRuntime.run always accepted and HTTP never exposed.

Both are the same shape of bug: the runtime signature has the parameter, the
request model does not, so a capability that exists is unreachable over the API.

  run_id           without it you cannot learn a run's id until it is over, so
                   the SSE stream at /v1/runs/{id}/events can never attach to a
                   run you started — only replay one that finished.

  initial_evidence without it a caller wanting to hand a run context-as-data has
                   to inline it in the prompt, where nothing marks it untrusted.
                   The planner already has semantics for this
                   (planner.py:535 — "It cannot grant tool authority").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from s17code.routes import RunBody  # noqa: E402


class TestRunId:
    def test_run_body_accepts_a_client_supplied_run_id(self):
        body = RunBody(tenant_id="t", prompt="hello", run_id="run-chosen-by-caller")

        assert body.run_id == "run-chosen-by-caller"

    def test_run_id_is_optional_and_defaults_to_none(self):
        """Absent means the runtime mints one, exactly as before."""
        assert RunBody(tenant_id="t", prompt="hello").run_id is None


class TestInitialEvidence:
    def test_run_body_accepts_initial_evidence(self):
        turns = {"conversation": [{"question": "how long?", "answer": "12 months"}]}

        body = RunBody(tenant_id="t", prompt="and why?", initial_evidence=turns)

        assert body.initial_evidence == turns

    def test_initial_evidence_is_optional(self):
        assert RunBody(tenant_id="t", prompt="hello").initial_evidence is None


class TestBothReachTheRuntime:
    def test_the_runtime_signature_accepts_what_the_body_now_carries(self):
        """The fields are useless unless run() takes them — assert the contract."""
        import inspect

        from s17code.runtime import AgentRuntime

        parameters = inspect.signature(AgentRuntime.run).parameters
        assert "run_id" in parameters
        assert "initial_evidence" in parameters
