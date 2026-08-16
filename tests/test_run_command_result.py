"""`run_command` has to hand back something the graph can store.

Session 17's whole argument is that a failing test is evidence rather than an
error, and that the exit code is what the next attempt reads. That requires the
exit code to survive the trip from the subprocess into the graph.

It does not. `run_command_worker` returns the `CommandResult` dataclass rather
than the dict its own annotation promises, so the journal cannot serialise it
and every verification node fails with a `TypeError` instead of a result.

The second test here is the one that makes it dangerous rather than merely
broken: `_stuck_verification` reads a missing `exit_code` as a pass, so a run
whose judge is failing every time looks, to the loop control, like a run whose
judge keeps succeeding. The circuit breaker never counts, and the run continues
believing it is being graded.
"""
from __future__ import annotations

import json

import pytest

from s17code.coding.exec import CommandResult
from s17code.core.live_graph import TaskSpec
from s17code.workers.coding import run_command_worker


class _Context:
    """Minimal RunContext stand-in: the worker only asks for the workspace."""

    def __init__(self, workspace):
        self._workspace = workspace
        self.ledger = None

    def workspace(self):
        return self._workspace


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("S17_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("S17_ALLOWED_COMMANDS", "python,git,pytest")
    from s17code.coding.workspace import Workspace

    return Workspace.from_env()


async def test_worker_returns_json_serialisable_output(workspace):
    """The graph journals every node result as JSON. A dataclass cannot go in."""
    task = TaskSpec("verify", "run_command", {"command": "git status"}, {})
    result = await run_command_worker(_Context(workspace), task)

    assert not isinstance(result, CommandResult), (
        "the worker returned the dataclass; the journal cannot serialise it"
    )
    json.dumps(result)  # must not raise


async def test_exit_code_survives_into_the_result(workspace):
    """A non-zero exit is the evidence the next attempt reads."""
    task = TaskSpec("verify", "run_command",
                    {"command": "git rev-parse --verify no-such-ref"}, {})
    result = await run_command_worker(_Context(workspace), task)

    assert isinstance(result, dict)
    assert result["exit_code"] != 0
    assert result["ok"] is False


async def test_successful_command_reports_zero(workspace):
    # Not `git status`: the workspace fixture is a bare tmp directory, and git
    # exits 128 there. The point is a command that genuinely succeeds.
    task = TaskSpec("verify", "run_command", {"command": "python --version"}, {})
    result = await run_command_worker(_Context(workspace), task)

    assert result["exit_code"] == 0
    assert result["ok"] is True
    assert "command" in result


def _planner(max_repeat_failures: int = 4):
    from s17code.planner import GeneralAgentPlanner

    planner = object.__new__(GeneralAgentPlanner)
    planner.max_repeat_failures = max_repeat_failures

    class _Registry:
        @staticmethod
        def family(name):
            return {"run_command"} if name == "verify" else set()

    planner.registry = _Registry()
    return planner


def _snapshot(nodes: dict):
    return type("Snapshot", (), {"nodes": nodes})()


def test_a_verification_that_cannot_run_counts_toward_the_ceiling():
    """A node that failed outright is a failure, not an absence of one.

    `_stuck_verification` only inspects nodes in state `succeeded`, so a
    verification command that raises — a worker error, a serialisation failure,
    a missing binary — is skipped entirely. The run then repeats it forever:
    the one control designed to stop a thrashing loop cannot see the failures
    that are doing the thrashing.
    """
    failing = {
        "state": "failed",
        "skill": "run_command",
        "input": {"command": "uv run pytest -q"},
        "result": {"error": "TypeError: Object of type CommandResult is not JSON serializable"},
    }
    stuck = _planner()._stuck_verification(_snapshot({f"n{i}": dict(failing) for i in range(4)}))

    assert stuck is not None, (
        "four verification nodes failed to run and the run was not stopped"
    )
    assert stuck[0] == "uv run pytest -q"
    assert stuck[1] >= 4


def test_a_passing_verification_still_forgives_earlier_failures():
    """The existing contract: a pass clears whatever went before it."""
    command = "uv run pytest -q"
    nodes = {
        "n0": {"state": "succeeded", "skill": "run_command",
               "input": {"command": command}, "result": {"exit_code": 1}},
        "n1": {"state": "failed", "skill": "run_command",
               "input": {"command": command}, "result": {"error": "boom"}},
        "n2": {"state": "succeeded", "skill": "run_command",
               "input": {"command": command}, "result": {"exit_code": 0}},
    }
    assert _planner(max_repeat_failures=2)._stuck_verification(_snapshot(nodes)) is None


def test_a_verifier_with_no_exit_code_is_not_a_failure():
    """`validate_work` is in the verify family and returns findings, not a code.

    It must keep counting as a pass, or every run that validates its work would
    walk into the circuit breaker.
    """
    nodes = {
        f"n{i}": {"state": "succeeded", "skill": "run_command",
                  "input": {"command": "validate"}, "result": {"findings": []}}
        for i in range(6)
    }
    assert _planner()._stuck_verification(_snapshot(nodes)) is None
