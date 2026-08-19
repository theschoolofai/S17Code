"""The extracted workers must behave exactly like the closures they replaced.

Moving forty-eight closures out of a thousand-line function is mechanical, which
is precisely why it is dangerous: a worker that is subtly rewritten during the
move still passes every test that only checks the capability exists. During this
extraction `git_diff` was rewritten to shell out to `git diff` instead of using
the workspace's own diff, and the whole suite stayed green.
"""
from __future__ import annotations

import inspect

import pytest

from s17code.core.live_graph import TaskSpec
from s17code.core.memory import MemoryKind
from s17code.workers import RunContext, general, special
from s17code.workers import coding as workers


class _FakeSource:
    def __init__(self, uri: str) -> None:
        self.uri = uri


class _FakeRecord:
    """The three things `recall` reads off a memory record."""

    def __init__(self, id: str, text: str, uri: str) -> None:
        self.id, self.text = id, text
        self.kind = MemoryKind.FACT
        self.sources = [_FakeSource(uri)]
        self.metadata: dict = {}


class _FakeMemory:
    def __init__(self, records: list) -> None:
        self._records = records

    def recall(self, query, scope, *, limit, kinds):
        return list(self._records)


class _FakeRuntime:
    def __init__(self, records: list) -> None:
        self.memory = _FakeMemory(records)


async def _echo_llm(prompt: str, system: str) -> dict:
    return {"text": prompt[:80], "provider": "fake", "model": "fake-1"}


def test_git_workers_use_the_workspace_not_the_command_runner() -> None:
    """Routing these through run_command would subject them to the allowlist,
    the metacharacter check and an output cap, for no benefit."""
    for fn in (workers.git_diff_worker, workers.git_reset_worker):
        src = inspect.getsource(fn)
        assert "ctx.workspace()" in src
        assert "run_command(" not in src, f"{fn.__name__} must not shell out"


def test_every_worker_takes_a_context_and_a_task() -> None:
    for name in workers.__all__:
        fn = getattr(workers, name)
        params = list(inspect.signature(fn).parameters)
        assert params == ["ctx", "task"], f"{name} has {params}"
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


def test_the_context_cannot_be_mutated_by_a_worker() -> None:
    """A worker that could swap the registry could change what the run may do."""
    ctx = RunContext(run_id="r", runtime=None, llm=None, scope=None,
                     registry=None, ledger=None)
    with pytest.raises(Exception):
        ctx.run_id = "other"  # type: ignore[misc]


def test_the_context_carries_only_what_was_measured() -> None:
    """Eight fields, and the eighth is a correction.

    The first AST pass reported seven, because it filtered `prompt` out as a
    local name. It is not: the composer titles a surface with the run's goal,
    and it read that straight from the enclosing scope. The measurement was
    wrong, not the code.

    This assertion is exact on purpose. If it grows again, something is being
    dragged into the context instead of being passed to the one worker that
    needs it, which is how forty-eight closures happened the first time.
    """
    import dataclasses

    fields = {f.name for f in dataclasses.fields(RunContext)}
    assert fields == {"run_id", "runtime", "llm", "scope", "registry",
                      "ledger", "transport", "goal"}


def test_the_coding_workers_are_thin() -> None:
    """The rules live in coding/. A worker that grows logic has stolen it."""
    for name in workers.__all__:
        body = [l for l in inspect.getsource(getattr(workers, name)).splitlines()
                if l.strip() and not l.strip().startswith(("#", '"""', "'''"))]
        assert len(body) <= 12, f"{name} is {len(body)} lines; the rule belongs in coding/"


# --- Names left behind by the move -------------------------------------------
#
# The failure mode of an extraction is not a bad line, it is a name that stayed
# in the module it was moved out of. Both capabilities below are registered and
# routable, and both raise NameError on their first statement. Nothing caught it:
# the executor records a raising node as a failed *outcome* rather than letting
# the exception surface, and the existing tests assert only that the capability
# is registered and declares the right families.


async def test_a_validator_does_not_spawn_a_validator(monkeypatch) -> None:
    """The depth bound is the whole reason a validator may run commands at all."""
    monkeypatch.setenv("_S17_VALIDATION_DEPTH", "1")
    ctx = RunContext(run_id="r", runtime=None, llm=None, scope=None, registry=None, ledger=None)

    out = await special.run_validate_work(ctx, TaskSpec("v1", "validate_work", {"requirement": "x"}))

    assert out["skipped"] is True
    assert out["passed"] is True


async def test_the_retriever_reaches_scoped_memory() -> None:
    """`retriever` is a registered role. It has never returned a hit."""
    record = _FakeRecord("mem-1", "London is in England.", "doc://england")
    ctx = RunContext(run_id="r", runtime=_FakeRuntime([record]), llm=_echo_llm,
                     scope=None, registry=None, ledger=None)

    out = await general.run_retriever(ctx, TaskSpec("r1", "retriever", {"query": "where is London"}),
                                      inbound_id="inbound-1")

    assert [hit["id"] for hit in out["hits"]] == ["mem-1"]
    assert out["agent"] == "retriever"


async def test_the_retriever_does_not_cite_the_question_it_was_asked() -> None:
    """The inbound request is written to memory before planning starts. Letting
    it back in means the answer cites the asking of it as evidence."""
    inbound = _FakeRecord("inbound-1", "where is London", "api://agent/runs")
    other = _FakeRecord("mem-1", "London is in England.", "doc://england")
    ctx = RunContext(run_id="r", runtime=_FakeRuntime([inbound, other]), llm=_echo_llm,
                     scope=None, registry=None, ledger=None)

    out = await general.run_retriever(ctx, TaskSpec("r1", "retriever", {"query": "where is London"}),
                                      inbound_id="inbound-1")

    assert [hit["id"] for hit in out["hits"]] == ["mem-1"]
