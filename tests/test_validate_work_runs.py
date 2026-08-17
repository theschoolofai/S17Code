"""The validator has to be able to run before anything it says can matter.

`validate_work` is the capability that exists to disprove a premature "it
works". Two tests already cover it: one asserts it is registered in the right
capability families, the other asserts its brief is suitably hostile and forbids
editing. Both pass on a worker that cannot execute at all, which is what this
one is here to stop.
"""
from __future__ import annotations

import pytest

from s17code.core.live_graph import TaskSpec
from s17code.workers import RunContext
from s17code.workers.special import run_validate_work


class _Runtime:
    """A stand-in for the child run the validator spawns."""

    def __init__(self) -> None:
        self.called_with: dict = {}

    async def run(self, **kwargs):
        self.called_with = kwargs
        return {
            "run_id": "child-1",
            "status": "completed",
            "answer": '{"passed": false, "summary": "one test still fails",'
                      ' "findings": [{"what": "test_empty fails", "evidence":'
                      ' "exit 1", "reproduced": true, "severity": "blocker"}]}',
        }


@pytest.fixture
def ctx() -> tuple[RunContext, _Runtime]:
    runtime = _Runtime()
    return RunContext(run_id="parent", runtime=runtime, llm=None, scope=None,
                      registry=None, ledger=None), runtime


async def test_validate_work_can_actually_be_called(ctx) -> None:
    """It reaches for `os` on its first line, and `os` was never imported.

        if int(os.getenv("_S17_VALIDATION_DEPTH", "0")) >= 1:

    `os` is used three times in workers/special.py and appears in no import, so
    every call raised `NameError: name 'os' is not defined` before the child run
    was reached. The capability had never executed once.

    The existing tests do not catch it because neither of them calls the worker.
    This one does, and asserts nothing more interesting than that it returns.
    """
    context, _ = ctx
    task = TaskSpec(id="v", skill="validate_work",
                    input={"requirement": "the suite passes", "paths": ["src/calc.py"]})

    report = await run_validate_work(context, task)

    assert report["passed"] is False
    assert report["blockers"] == 1
    assert report["reproduced_any"] is True
    assert report["validator_run_id"] == "child-1"


async def test_the_child_may_run_things_but_not_repair_them(ctx) -> None:
    """A validator that can fix what it grades will grade what it can fix."""
    context, runtime = ctx
    await run_validate_work(
        context, TaskSpec(id="v", skill="validate_work",
                          input={"requirement": "the suite passes"}))

    allowed = runtime.called_with["allowed_side_effects"]
    assert allowed == {"run_command", "create_file"}
    assert "edit_code" not in allowed


async def test_the_requirement_and_paths_reach_the_child(ctx) -> None:
    """The child gets the brief and the files, and no build history."""
    context, runtime = ctx
    await run_validate_work(
        context, TaskSpec(id="v", skill="validate_work",
                          input={"requirement": "average([]) must return 0",
                                 "paths": ["src/calc.py"]}))

    goal = runtime.called_with["prompt"]
    assert "average([]) must return 0" in goal
    assert "src/calc.py" in goal
