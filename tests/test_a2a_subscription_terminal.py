"""A subscription that ends is not the same as a task that finished.

`test_official_subscription_resumes_waiting_graph_and_maps_cancel` failed about
one run in six, in isolation, with `assert 2 == 3` — the bridge returned a task
in TASK_STATE_WORKING where the test expected TASK_STATE_COMPLETED. Two defects
produce that, one on each side of the wire.

Server: `SubscribeToTask` yields a snapshot and then re-reads `task.state` to
decide whether to continue. `task` is shared and mutable, so a task that
completes in the gap between the yield and the check ends the stream with a
non-terminal event as its last word.

Client: `GraphA2ARemote.wait` keeps the last event it happened to see and returns
it as final, with no check that it is terminal. `dispatch_waiting` then writes an
`a2a_task_completed` event carrying `state: working` and resumes the waiting
graph node — a run continuing on a remote task nobody observed finish, with a
journal that says it finished.
"""
from __future__ import annotations

import asyncio

import pytest
from a2a.types import a2a_pb2 as p

from s17code.core.a2a.official import (
    DurablePushConfigs,
    GraphA2ARemote,
    OfficialA2AServicer,
)
from s17code.core.a2a.server import TERMINAL, A2ADemoServer, TaskState


def card():
    return {
        "name": "terminal", "description": "subscription fixture", "version": "1.0.0",
        "supportedInterfaces": [{"url": "http://a2a.test/1.0", "protocolBinding": "GRPC",
                                 "protocolVersion": "1.0"}],
        "capabilities": {"streaming": True, "pushNotifications": False},
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
        "skills": [{"id": "s", "name": "s", "description": "s", "tags": ["s"]}],
    }


class _Context:
    """Enough gRPC context for a servicer with no credentials configured."""

    @staticmethod
    def invocation_metadata():
        return ()

    async def abort(self, code, details):  # pragma: no cover - not reached here
        raise AssertionError(f"aborted: {code} {details}")


class _Stream:
    """A subscription whose last event is whatever the caller scripted."""

    def __init__(self, tasks):
        self._tasks = list(tasks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._tasks:
            raise StopAsyncIteration
        return p.StreamResponse(task=self._tasks.pop(0))


class _Stub:
    def __init__(self, tasks):
        self._tasks = tasks

    def SubscribeToTask(self, request):  # noqa: N802 - gRPC stub spelling
        return _Stream(self._tasks)


def _pb(state) -> p.Task:
    return p.Task(id="t1", context_id="c1", status=p.TaskStatus(state=state))


async def test_wait_refuses_a_stream_that_ended_without_a_terminal_state():
    """The client half. Returning this task is what resumed the graph early."""
    remote = GraphA2ARemote(_Stub([_pb(p.TASK_STATE_SUBMITTED), _pb(p.TASK_STATE_WORKING)]))

    with pytest.raises(RuntimeError, match="without reaching a terminal state|non-terminal"):
        await remote.wait("t1")


async def test_wait_accepts_a_stream_that_ended_terminal():
    remote = GraphA2ARemote(_Stub([_pb(p.TASK_STATE_WORKING), _pb(p.TASK_STATE_COMPLETED)]))
    final = await remote.wait("t1")
    assert final.status.state == p.TASK_STATE_COMPLETED


async def test_wait_refuses_an_empty_stream():
    remote = GraphA2ARemote(_Stub([]))
    with pytest.raises(RuntimeError):
        await remote.wait("t1")


async def test_the_last_event_is_terminal_even_when_the_task_completes_mid_stream(tmp_path):
    """The server half, driven deterministically rather than by racing.

    The task is flipped to COMPLETED after the first event has been delivered,
    which is exactly the window the old loop condition read.
    """
    core = A2ADemoServer(card())
    servicer = OfficialA2AServicer(core, DurablePushConfigs(tmp_path / "push.sqlite"))
    sent = await core.send({"message": {"messageId": "m", "parts": [{"kind": "text", "text": "hi"}]}})
    task = core.tasks[sent["id"]]
    task.state = TaskState.WORKING

    stream = servicer.SubscribeToTask(p.SubscribeToTaskRequest(id=task.id), _Context())
    seen = [await stream.__anext__()]
    task.state = TaskState.COMPLETED          # completes in the gap the old check read
    async for event in stream:
        seen.append(event)

    assert seen[-1].task.status.state == p.TASK_STATE_COMPLETED, (
        "the stream's last word must be the terminal state, not whatever "
        f"preceded it: {[e.task.status.state for e in seen]}"
    )


async def test_a_task_already_terminal_still_yields_one_terminal_event(tmp_path):
    core = A2ADemoServer(card())
    servicer = OfficialA2AServicer(core, DurablePushConfigs(tmp_path / "push.sqlite"))
    sent = await core.send({"message": {"messageId": "m", "parts": [{"kind": "text", "text": "hi"}]}})
    task = core.tasks[sent["id"]]
    task.state = TaskState.COMPLETED

    seen = [event async for event in
            servicer.SubscribeToTask(p.SubscribeToTaskRequest(id=task.id), _Context())]

    assert len(seen) == 1
    assert seen[0].task.status.state == p.TASK_STATE_COMPLETED


def test_the_terminal_set_is_not_redefined_by_hand():
    """`server.py` already exports TERMINAL; official.py spelled it out again."""
    import inspect

    from s17code.core.a2a import official

    source = inspect.getsource(official.OfficialA2AServicer.SubscribeToTask)
    assert "TaskState.FAILED" not in source, (
        "SubscribeToTask should use the shared TERMINAL set, not its own copy"
    )
    assert TERMINAL == {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}


async def test_wait_does_not_spin_forever_on_a_stalled_stream():
    """A stream that never ends must not hang the graph indefinitely."""

    class _Endless:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(0)
            return p.StreamResponse(task=_pb(p.TASK_STATE_WORKING))

    class _EndlessStub:
        def SubscribeToTask(self, request):  # noqa: N802
            return _Endless()

    with pytest.raises((RuntimeError, TimeoutError, asyncio.TimeoutError)):
        await asyncio.wait_for(GraphA2ARemote(_EndlessStub()).wait("t1", max_events=50), timeout=10)
