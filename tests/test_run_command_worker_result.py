"""The judge has to be able to report its verdict.

`run_command` is the capability the coding surface is built around: it decides
whether a change worked. Its worker is what the runtime actually calls, and it
returned the `CommandResult` dataclass rather than the dict every other worker
returns, so the outcome could not be serialized into the node's result and every
call failed after the command had already run.

`CommandResult.as_dict()` exists for exactly this and was not called. The
existing coding tests all exercise `run_command` the function, never the worker,
which is how it survived a suite that otherwise covers this surface closely.
"""
from __future__ import annotations

import json

import pytest

from s17code.coding import EditLedger
from s17code.core.live_graph.core import TaskSpec
from s17code.workers.coding import run_command_worker
from s17code.workers.context import RunContext


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("S17_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("S17_ALLOWED_COMMANDS", "python")
    # `python -c` is refused on purpose: it is a shell by another name. Real
    # verification writes a script and runs it, so the tests do the same.
    (tmp_path / "say_ok.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "fail.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    return RunContext(run_id="test-run", runtime=None, llm=None, scope=None,
                      registry=None, ledger=EditLedger())


async def test_the_worker_returns_a_serializable_dict(ctx) -> None:
    task = TaskSpec(id="verify", skill="run_command",
                    input={"command": ["python", "say_ok.py"], "timeout": 30})

    result = await run_command_worker(ctx, task)

    assert isinstance(result, dict), f"worker returned {type(result).__name__}, not a dict"
    # The runtime stores this in the node's result and streams it as JSON. A
    # dataclass here fails at that boundary, after the command has already run.
    json.dumps(result)


async def test_the_verdict_survives_the_round_trip(ctx) -> None:
    """Exit code and output are the entire point of the capability."""
    task = TaskSpec(id="verify", skill="run_command",
                    input={"command": ["python", "say_ok.py"], "timeout": 30})

    result = await run_command_worker(ctx, task)

    assert result["exit_code"] == 0
    assert result["ok"] is True
    assert "ok" in result["stdout"]
    assert result["timed_out"] is False
    assert isinstance(result["command"], str)


async def test_a_failing_command_reports_its_failure_rather_than_raising(ctx) -> None:
    """A failing test is evidence, not an error: the next attempt reads it."""
    task = TaskSpec(id="verify", skill="run_command",
                    input={"command": ["python", "fail.py"], "timeout": 30})

    result = await run_command_worker(ctx, task)

    assert result["exit_code"] == 3
    assert result["ok"] is False
    json.dumps(result)
