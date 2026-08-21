"""The repeat-failure ceiling must count failed validations, not only commands."""
from __future__ import annotations

from s17code.capabilities import default_registry
from s17code.planner import GeneralAgentPlanner


class _Snapshot:
    def __init__(self, nodes): self.nodes, self.edges = nodes, []


def _validation_node(requirement: str, passed: bool) -> dict:
    return {"skill": "validate_work", "state": "succeeded",
            "input": {"requirement": requirement},
            "result": {"passed": passed, "blockers": 0 if passed else 2,
                       "findings": [], "summary": "ran it"}}


def _planner(**kwargs) -> GeneralAgentPlanner:
    async def never(p, s): raise AssertionError("no model call expected")
    return GeneralAgentPlanner(never, default_registry(), goal="x", **kwargs)


def test_repeated_failed_validations_stop_the_run() -> None:
    planner = _planner(max_repeat_failures=4)
    graph = _Snapshot({f"val{i}": _validation_node("the page shows the total", False)
                       for i in range(4)})
    stuck = planner._stuck_verification(graph)          # noqa: SLF001
    assert stuck is not None
    assert stuck[1] == 4


def test_three_failed_validations_are_still_iteration() -> None:
    planner = _planner(max_repeat_failures=4)
    graph = _Snapshot({f"val{i}": _validation_node("the page shows the total", False)
                       for i in range(3)})
    assert planner._stuck_verification(graph) is None   # noqa: SLF001


def test_a_passing_validation_forgives_earlier_failures() -> None:
    planner = _planner(max_repeat_failures=2)
    nodes = {f"val{i}": _validation_node("the page shows the total", False) for i in range(3)}
    nodes["val_ok"] = _validation_node("the page shows the total", True)
    assert planner._stuck_verification(_Snapshot(nodes)) is None   # noqa: SLF001