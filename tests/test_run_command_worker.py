from __future__ import annotations

import json
import pytest
from s17code.workers.coding import run_command_worker
from s17code.core.live_graph.core import RunContext, TaskSpec


@pytest.mark.asyncio
async def test_run_command_worker_returns_serializable_dict(repo) -> None:
    # 1. Setup mock run context and task spec
    class MockRuntime:
        def _skills(self):
            return None

    class MockRunContext:
        def __init__(self, workspace):
            self._workspace = workspace
            self.runtime = MockRuntime()
            self.run_id = "test-run-123"

        def workspace(self):
            return self._workspace

    ctx = MockRunContext(repo)
    task = TaskSpec(
        id="run-test",
        skill="run_command",
        input={"command": ["git", "status", "--porcelain"], "timeout": 10},
        metadata={}
    )

    # 2. Execute worker
    result = await run_command_worker(ctx, task)

    # 3. Assertions: Must return a dictionary
    assert isinstance(result, dict)
    assert "exit_code" in result
    assert "ok" in result
    assert "stdout" in result

    # 4. Assertions: Must be completely JSON-serializable
    serialized = json.dumps(result)
    assert serialized is not None
    loaded = json.loads(serialized)
    assert loaded["ok"] is True
