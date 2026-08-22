"""The two workers in `special.py`, both of which were broken in ways that hid.

`validate_work` is the nested-validator capability — a second agent with a fresh
context and a hostile brief, and the centrepiece of this session's verification
argument. It raised NameError on its very first statement, and the executor
turned that into a `task_failed` like any other, so the capability appeared to
merely fail rather than to be impossible.

`recall` silently returned less inside the graph than the same query returned
over HTTP. Nothing errored; a node just could not see the chunk offsets that
would let it point at what it had recalled.
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

from s17code.core.memory import MemoryKind
from s17code.workers import RunContext, special


class TestValidateWorkIsCallableAtAll:
    """Bug 7. Registered at runtime.py:463 and never once able to run."""

    def test_the_module_can_reach_os(self):
        """The whole bug in one line.

        `special.py` uses os.getenv and os.environ in three places and imported
        only json and typing, so the first statement of run_validate_work's body
        raised. A capability whose first line cannot execute has never executed.
        """
        assert hasattr(special, "os"), "special.py uses os in three places"

    async def test_the_depth_guard_returns_instead_of_raising(self, monkeypatch):
        """The reachable half of the worker, with no runtime needed.

        A validator must not spawn a validator, so at depth >= 1 the worker
        returns early. Before the import was added this raised NameError on the
        guard itself — which is to say it failed BEFORE deciding anything.
        """
        monkeypatch.setenv("_S17_VALIDATION_DEPTH", "1")
        ctx = RunContext(run_id="r", runtime=None, llm=None, scope=None,
                         registry=None, ledger=None)
        task = SimpleNamespace(id="t", skill="validate_work",
                               input={"requirement": "does it work", "paths": []})

        result = await special.run_validate_work(ctx, task)

        assert result["skipped"] is True
        assert result["passed"] is True
        assert result["findings"] == []

    def test_the_depth_guard_is_restored_after_a_run(self):
        """The env var is a process global; leaving it set would silently
        disable validation for every later run in the same process."""
        source = inspect.getsource(special.run_validate_work)

        assert "finally:" in source
        assert 'os.environ.pop("_S17_VALIDATION_DEPTH", None)' in source


class TestTheValidatorActuallyGetsItsBrief:
    """Bug 17. VALIDATOR_SYSTEM was imported here and never delivered.

    The child therefore ran as an ordinary agent. It was never told not to
    accept that code existing means code runs, never told to reproduce a defect
    before reporting it, and — decisively — never told to return the JSON that
    this worker's own caller parses. `summarise()` reads `findings`, `severity`
    and `reproduced` out of that JSON, so with the brief missing the parse fell
    through to the `passed: False` fallback every time.
    """

    @staticmethod
    def _spy_ctx(captured: list):
        class Runtime:
            async def run(self, **kwargs):
                captured.append(kwargs)
                return {"answer": '{"passed": true, "findings": [], "summary": "ok"}'}

        async def llm(prompt, system):
            captured.append(("llm", system))
            return {"text": "{}"}

        return RunContext(run_id="r", runtime=Runtime(), llm=llm, scope=None,
                          registry=None, ledger=None)

    @staticmethod
    def _task():
        return SimpleNamespace(id="t", skill="validate_work",
                               input={"requirement": "the button works", "paths": ["a.js"]})

    async def test_the_planner_persona_is_left_alone(self, monkeypatch):
        """The child still has to emit graph patches.

        A second "return JSON only" contract inside the planning prompt would
        fight the planner's own output contract, so the brief must not be
        appended there.
        """
        from s17code.coding.validate import VALIDATOR_SYSTEM

        captured: list = []
        ctx = self._spy_ctx(captured)
        monkeypatch.delenv("_S17_VALIDATION_DEPTH", raising=False)
        await special.run_validate_work(ctx, self._task())
        child_llm = captured[0]["llm"]

        await child_llm("plan this", "You are the planner. Return graph patches.")

        forwarded = [entry for entry in captured if isinstance(entry, tuple) and entry[0] == "llm"]
        assert forwarded, "the child llm must forward to ctx.llm"
        assert VALIDATOR_SYSTEM not in forwarded[-1][1]

    async def test_the_brief_is_appended_to_the_answer_persona(self, monkeypatch):
        from s17code.coding.validate import VALIDATOR_SYSTEM
        from s17code.runtime import GROUNDED_ANSWER_SYSTEM

        captured: list = []
        ctx = self._spy_ctx(captured)
        monkeypatch.delenv("_S17_VALIDATION_DEPTH", raising=False)
        await special.run_validate_work(ctx, self._task())
        child_llm = captured[0]["llm"]

        await child_llm("answer this", GROUNDED_ANSWER_SYSTEM)

        forwarded = [entry for entry in captured if isinstance(entry, tuple) and entry[0] == "llm"]
        delivered = forwarded[-1][1]
        assert VALIDATOR_SYSTEM in delivered, "the validator brief never reached the answer call"
        # And the original persona survives, so the answer worker still knows to
        # treat evidence as data rather than as instructions.
        assert GROUNDED_ANSWER_SYSTEM in delivered

    async def test_the_validator_still_cannot_edit(self, monkeypatch):
        """A validator that can edit will eventually validate what it can edit."""
        captured: list = []
        monkeypatch.delenv("_S17_VALIDATION_DEPTH", raising=False)
        await special.run_validate_work(self._spy_ctx(captured), self._task())

        allowed = captured[0]["allowed_side_effects"]
        assert "edit_code" not in allowed
        assert allowed == {"run_command", "create_file"}


class TestRecallReturnsWhatTheHttpRouteReturns:
    """Bug 8. The same query, two answers, depending on who asked."""

    @staticmethod
    def _hit(hit_id: str, *, meta: dict):
        return SimpleNamespace(
            id=hit_id, kind=MemoryKind.DOCUMENT_CHUNK, text="a recalled span",
            sources=[SimpleNamespace(uri="src://doc1")], metadata=meta)

    @staticmethod
    def _ctx(hits):
        memory = SimpleNamespace(recall=lambda *a, **k: hits)
        return RunContext(run_id="run-1", runtime=SimpleNamespace(memory=memory),
                          llm=None, scope=None, registry=None, ledger=None)

    async def test_metadata_survives_into_the_graph(self):
        """Chunk offsets are what make a recalled span citable.

        Without them a node can quote a document but cannot say WHERE in it, so
        anything downstream that wants to anchor a citation has to fall back to
        matching the quote text instead of using the offsets it was entitled to.
        """
        meta = {"document_id": "doc1", "ordinal": 3, "heading": "Retention",
                "source_start_char": 120, "source_end_char": 240}
        ctx = self._ctx([self._hit("m1", meta=meta)])
        task = SimpleNamespace(id="t", skill="memory_recall", input={"query": "retention"})

        result = await special.recall(ctx, task, inbound_id="other")

        assert result["hits"][0]["metadata"] == meta

    async def test_the_other_fields_are_unchanged(self):
        ctx = self._ctx([self._hit("m1", meta={"ordinal": 0})])
        task = SimpleNamespace(id="t", skill="memory_recall", input={"query": "q"})

        hit = (await special.recall(ctx, task, inbound_id="other"))["hits"][0]

        assert hit["id"] == "m1"
        assert hit["kind"] == MemoryKind.DOCUMENT_CHUNK.value
        assert hit["text"] == "a recalled span"
        assert hit["sources"] == ["src://doc1"]

    async def test_a_hit_from_this_very_run_is_still_excluded(self):
        """Guard against the fix widening what comes back.

        An answer must not be able to recall itself as evidence, so hits whose
        metadata names this run are dropped. Now that metadata is passed through,
        it is worth pinning that it is still being READ for this.
        """
        ctx = self._ctx([self._hit("m1", meta={"run_id": "run-1"}),
                         self._hit("m2", meta={"run_id": "older"})])
        task = SimpleNamespace(id="t", skill="memory_recall", input={"query": "q"})

        result = await special.recall(ctx, task, inbound_id="none")

        assert [hit["id"] for hit in result["hits"]] == ["m2"]

    async def test_the_inbound_request_is_still_excluded(self):
        ctx = self._ctx([self._hit("inbound", meta={}), self._hit("m2", meta={})])
        task = SimpleNamespace(id="t", skill="memory_recall", input={"query": "q"})

        result = await special.recall(ctx, task, inbound_id="inbound")

        assert [hit["id"] for hit in result["hits"]] == ["m2"]


class TestRetrieverCanRunAtAll:
    """Bug 6. Registered, and never once executed.

    `run_retriever` was sorted into workers/general.py during the extraction of
    forty-eight closures, but its body calls `recall` — a name that module
    neither imports nor defines — with ONE argument, against a function that
    takes three. The arity is the proof: a rename could have worked once, but a
    one-into-three call never has.
    """

    def test_it_lives_beside_the_recall_it_needs(self):
        from s17code.workers import general

        assert not hasattr(general, "run_retriever"), (
            "it needs the same bound value as recall, so it belongs in special.py")
        assert hasattr(special, "run_retriever")

    def test_it_takes_the_bound_inbound_id(self):
        params = list(inspect.signature(special.run_retriever).parameters)

        assert params == ["ctx", "task", "inbound_id"]

    def test_it_actually_runs_and_returns_hits_plus_a_summary(self):
        """The whole bug: this call used to raise NameError before doing anything."""
        hit = SimpleNamespace(id="m1", kind=MemoryKind.DOCUMENT_CHUNK, text="recalled",
                              sources=[SimpleNamespace(uri="src://d")], metadata={"ordinal": 1})
        memory = SimpleNamespace(recall=lambda *a, **k: [hit])

        async def llm(prompt, system):
            return {"text": "a summary", "provider": "p", "model": "m"}

        ctx = RunContext(run_id="r", runtime=SimpleNamespace(memory=memory), llm=llm,
                         scope=None, registry=None, ledger=None, goal="what is retention")
        task = SimpleNamespace(id="t", skill="retriever", input={})

        result = asyncio.run(special.run_retriever(ctx, task, inbound_id="inbound"))

        assert result["text"] == "a summary"
        assert result["agent"] == "retriever"
        assert [h["id"] for h in result["hits"]] == ["m1"]

    def test_the_runtime_binds_it_with_an_inbound_id(self):
        """Bound like memory_recall, or the run can recall its own question."""
        source = (Path(__file__).resolve().parents[1] / "s17code" / "runtime.py").read_text(encoding="utf-8")

        assert 'partial(special.run_retriever, ctx, inbound_id=inbound_id)' in source
        assert 'partial(general.run_retriever' not in source


def test_the_graph_and_the_http_route_agree_on_a_hits_shape():
    """The asymmetry itself, pinned so it cannot drift apart again.

    routes.py builds the same structure for the HTTP caller. If one side gains a
    field the other should too, and a divergence should fail here rather than be
    discovered by someone wondering why a node cannot see what curl can.
    """
    from s17code import routes

    graph_side = inspect.getsource(special.recall)
    http_side = inspect.getsource(routes)

    for field in ('"id"', '"kind"', '"text"', '"sources"', '"metadata"'):
        assert field in graph_side, f"graph recall dropped {field}"
        assert field in http_side, f"http recall dropped {field}"
