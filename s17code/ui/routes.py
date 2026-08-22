"""HTTP + SSE UI surface, folded into the agent runtime (carried forward from S14).

  GET  /v1/catalog                  the trusted component catalog
  GET  /v1/runs/{id}/surface        build + validate a declarative surface
  GET  /v1/runs/{id}/snapshot       the complete data model as one STATE_SNAPSHOT
  GET  /v1/runs/{id}/events         AG-UI event stream over SSE
  GET  /v1/runs/{id}/composed       the interface the agent composed for a run
  POST /v1/validate                 validate an arbitrary surface (injection wall)
  POST /v1/action                   a validated user action (approve/reject/rerun)
  GET  /s/{id}                      the render client, pointed at a run
  POST /app/runs                    the app viewer starts a run (opt-in, cookie)

The data source is the runtime's own graph, read in-process off
``request.app.state.runtime`` — the same attribute ``GET /v1/agent/runs/{id}``
reads. No HTTP hop, no second service.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from s17code import routes as agent_routes
from s17code.core.memory import MemoryScope

from .agui import run_data_model, state_snapshot, to_agui_event
from .catalog import catalog_manifest
from .hitl import PendingAction, decide_resume
from .surface import build_run_surface
from .validator import Invariant, Rejection, validate_surface

router = APIRouter()
_CLIENT = Path(__file__).parent / "client" / "index.html"

# --------------------------------------------------------------------------- #
# the app viewer's credential
#
# app.html is a browser page and a browser cannot hold S17_CONTROL_TOKEN. That
# token is this process's own secret and it unlocks `budget`, `principal` and
# `allowed_side_effects` on the control plane; baking it into served HTML would
# hand every tab the authority the whole design rests on. It would also be
# readable by script in the page, and this page has a script-injection sink:
# setStatus() writes through innerHTML (client/app.html:153, 159) and choose()
# feeds it a model-chosen Button label on every turn after the first, so a
# prompt-injected surface could post anything the page can read to a server of
# its choosing.
#
# So the viewer never holds a token. Loading /app mints a per-process session
# and returns it as an HttpOnly cookie, and the viewer posts to a route of its
# own that is narrower than the control plane and refuses to exist unless an
# operator turned it on. The default install is unchanged: the flag is off and
# both routes answer 503 naming the variable to set.
# --------------------------------------------------------------------------- #
APP_VIEWER_ENV = "S17_APP_VIEWER"
APP_VIEWER_BUDGET_ENV = "S17_APP_VIEWER_BUDGET"
APP_VIEWER_COOKIE = "s17_app_viewer"


def _require_app_viewer() -> None:
    """Fail closed in auth.py's shape: unset means refuse, never serve anyway.

    Enabling this is a real decision, not a default. /app/runs authenticates a
    browser session, not an operator, so anyone who can reach this port can load
    the page, be given a cookie and spend model tokens. It is a loopback
    development surface: bind to 127.0.0.1 and set S17_APP_VIEWER_BUDGET.
    """
    if os.getenv(APP_VIEWER_ENV, "").strip().lower() not in {"1", "true", "yes"}:
        raise HTTPException(
            503,
            f"{APP_VIEWER_ENV} is not enabled; the app viewer refuses to serve "
            f"without it (local development only - it starts runs without a "
            f"control-plane token)",
        )


def _viewer_session(request: Request) -> str:
    """One random session secret per process, minted on first use, never stored.

    A restart invalidates every outstanding cookie, which is the right blast
    radius for a credential a page hands to whoever can load it.
    """
    secret = getattr(request.app.state, "app_viewer_session", "")
    if not secret:
        secret = secrets.token_urlsafe(32)
        request.app.state.app_viewer_session = secret
    return secret


def _read_run(request: Request, run_id: str) -> dict:
    """Read one run from the runtime's in-process graph, in S13's journal shape.

    Mirrors S13's ``GET /v1/agent/runs/{id}``: ``{run_id, finished, nodes,
    edges, events}``. Events are ``Event(sequence, kind, node_id, payload)``
    dataclasses; convert to plain dicts so the UI builders see the same shape a
    recorded fixture carries.
    """
    runtime = request.app.state.runtime
    try:
        snapshot = runtime.graph.snapshot(run_id)
    except KeyError:
        raise HTTPException(404, "run not found") from None
    events = [
        {"sequence": e.sequence, "kind": e.kind, "node_id": e.node_id, "payload": e.payload}
        for e in runtime.graph.events(run_id)
    ]
    return {
        "run_id": run_id,
        "finished": snapshot.finished,
        "nodes": snapshot.nodes,
        "edges": snapshot.edges,
        "events": events,
    }


def _composed_result(node: dict) -> dict | None:
    """One node's compose result, but only when it carries something to render.

    A compose node can succeed and still hold nothing: the model's JSON failed
    to parse, or the validator rejected every component it proposed. Counting
    that as absent keeps the selection below honest — /composed answers with an
    interface a client can draw, or with 404, and never with an empty surface.
    """
    result = node.get("result")
    if not isinstance(result, dict):
        return None
    surface = result.get("surface")
    if not isinstance(surface, dict) or not surface.get("components"):
        return None
    return result


@router.get("/v1/catalog")
async def catalog():
    return catalog_manifest()


@router.get("/v1/runs/{run_id}/surface")
async def surface(run_id: str, request: Request):
    run = _read_run(request, run_id)
    built = build_run_surface(run)
    result = validate_surface(built)
    # The builder's own surface is always clean; validating it here proves the
    # service treats even its own output as untrusted before serving.
    return {
        "run_id": run_id,
        "surface": {"root": built["root"], "components": result.accepted, "dataModel": built["dataModel"]},
        "rejections": [r.as_dict() for r in result.rejections],
    }


@router.get("/v1/runs/{run_id}/snapshot")
async def snapshot(run_id: str, request: Request):
    """The COMPLETE current data model as a single AG-UI STATE_SNAPSHOT event.

    A client that reconnects fetches this once and is whole, instead of replaying
    the entire event tape. The data model is the fold of the run's own AG-UI
    stream (``run_data_model``), so it is byte-identical to what a full delta
    replay would produce. We also build the run's surface in-process so the
    caller learns how many components that state renders into.
    """
    run = _read_run(request, run_id)
    built = build_run_surface(run)  # in-process graph read, same source as /surface
    data_model = run_data_model(run)
    return {
        "run_id": run_id,
        "event": state_snapshot(data_model),
        "component_count": len(built["components"]),
    }


@router.get("/v1/runs/{run_id}/events")
async def events(run_id: str, request: Request, reconnect: int = 0, after: int = 0):
    run = _read_run(request, run_id)
    # On reconnect the stream leads with ONE STATE_SNAPSHOT carrying the full
    # current data model; the client rebuilds from that single frame rather than
    # folding every delta again. Normal (first-connect) streaming is unchanged.
    snap = run_data_model(run) if reconnect else None

    async def gen():
        cursor = after
        if snap is not None:
            yield f"data: {json.dumps(state_snapshot(snap, seq=cursor))}\n\n"
        while not await request.is_disconnected():
            current = _read_run(request, run_id)
            fresh = [event for event in current["events"] if event["sequence"] > cursor]
            for event in fresh:
                cursor = event["sequence"]
                yield f"id: {cursor}\ndata: {json.dumps(to_agui_event(event))}\n\n"
            if current["finished"]:
                yield f"data: {json.dumps({'type': 'RUN_FINISHED', 'seq': cursor + 1, 'source_kind': 'derived'})}\n\n"
                break
            if not fresh:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


class ValidateBody(BaseModel):
    surface: dict


@router.post("/v1/validate")
async def validate(body: ValidateBody):
    """Adjudicate any surface, including one this service did not produce.

    Defence in depth. `validate_surface` is written not to raise, and the
    try/except exists so that a future edit which breaks that promise degrades
    to a 422 rather than a 500. The distinction is the whole point of the
    endpoint: a 422 says "your surface is unacceptable", a 500 says "your
    surface broke the thing that judges surfaces", and only one of those is a
    wall doing its job.
    """
    try:
        result = validate_surface(body.surface)
    except Exception as error:  # noqa: BLE001 - a wall must never fall over
        return {
            "ok": False,
            "accepted": [],
            "rejections": [Rejection("<surface>", "surface", Invariant.CATALOG,
                                     f"surface could not be validated: "
                                     f"{type(error).__name__}").as_dict()],
        }
    return {
        "ok": result.ok,
        "accepted": [c.get("id") for c in result.accepted],
        "rejections": [r.as_dict() for r in result.rejections],
    }


class ActionBody(BaseModel):
    run_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)
    # In a live system the pending params come from the parked node in S13. For
    # the recorded demo the caller supplies them so the binding check is real.
    pending_params: dict = Field(default_factory=dict)
    pending_summary: str = ""


@router.post("/v1/action")
async def action(body: ActionBody, request: Request):
    try:
        node = request.app.state.runtime.graph.snapshot(body.run_id).nodes[body.node_id]
    except (KeyError, TypeError):
        raise HTTPException(404, "waiting graph node not found") from None
    if node.get("state") != "waiting" or not isinstance(node.get("wait"), dict):
        raise HTTPException(409, "graph node is not waiting for a decision")
    wait = node["wait"]
    # The binding comes from the durable node, never from client-supplied
    # pending_params. Event payload cannot rewrite what the agent asked.
    bound = wait.get("params") if isinstance(wait.get("params"), dict) else {}
    pending = PendingAction(body.run_id, body.node_id, str(wait.get("question", "")), bound)
    decision = decide_resume(pending, body.action, body.args)
    if not decision.allowed:
        # A tamper attempt is refused; the node stays waiting.
        raise HTTPException(409, decision.reason)
    completion = request.app.state.runtime.graph.complete_waiting(
        str(wait["handle"]), str(wait["event_type"]),
        {"action": body.action, "args": body.args}, success=body.action == "approve",
    )
    if completion is None:
        return {"resumed": False, "duplicate": True, "node_id": body.node_id}
    result = await request.app.state.runtime.run(
        prompt=None, scope=None,
        llm=lambda prompt, system: request.app.state.gateway.complete(prompt, system),
        source_uri=None, source_author=None, run_id=body.run_id, resume=True,
    )
    return {"resumed": True, "node_id": body.node_id, "reason": decision.reason, "run": result}


@router.get("/v1/runs/{run_id}/composed")
async def composed(run_id: str, request: Request):
    """The interface the agent COMPOSED for this run (the compose_surface node's
    output), re-validated. Distinct from /surface, which is the run's progress
    view. This is what a UI-only app renders."""
    run = _read_run(request, run_id)
    # Select the compose node by its SKILL, never by its id. S14 minted
    # TaskSpec("surface", ...) itself, so reading run["nodes"]["surface"] was a
    # fact about that runtime; here the planner names its own nodes and says so
    # outright ("IDs are labels, not semantics"), which left this endpoint
    # 404ing every run whose model did not happen to pick that one word.
    # terminal_skills is the same source compose.py and the runtime's own
    # terminal-node pick already read.
    terminal = request.app.state.runtime.registry.terminal_skills("ui")
    # sorted() is stable, so this reads "succeeded compose nodes in graph order,
    # then the rest": a run that repaired a weak first attempt leaves more than
    # one, and an attempt that came back empty must not hide the sibling that
    # renders.
    composers = sorted((node for node in run["nodes"].values()
                        if node.get("skill") in terminal),
                       key=lambda node: node.get("state") != "succeeded")
    res = next((candidate for candidate in map(_composed_result, composers)
                if candidate is not None), None)
    if res is None:
        raise HTTPException(404, "run has no composed interface (no compose_surface node)")
    surf = res["surface"]
    result = validate_surface(surf)
    return {
        "run_id": run_id,
        "finished": run["finished"],
        "surface": {"root": surf.get("root"), "components": result.accepted,
                    "dataModel": res.get("data_model") or surf.get("dataModel") or {}},
        "component_count": len(result.accepted),
        "clean": result.ok,
        "provider": res.get("provider"),
        "model": res.get("model"),
    }


@router.get("/s/{run_id}", response_class=HTMLResponse)
async def client(run_id: str):
    if not _CLIENT.exists():
        raise HTTPException(500, "render client missing")
    # Path.read_text() defaults to the platform's preferred encoding, which on
    # Windows is the ANSI codepage (cp1252), not UTF-8. These files contain
    # non-Latin-1 bytes, so the default decodes them wrongly or not at all:
    # GET /app raised UnicodeDecodeError and returned HTTP 500 on every Windows
    # install, and the other two mojibake'd silently. The encoding of a file we
    # ship is a fact about the file, not about the host reading it.
    return _CLIENT.read_text(encoding="utf-8").replace("__RUN_ID__", run_id)


@router.get("/console", response_class=HTMLResponse)
@router.get("/console/", response_class=HTMLResponse)
async def autonomy_console():
    """The operator page for a system nobody is watching.

    Session 9 of the lesson promises "a browser or operations page that
    reconnects with after=41". This is it: a projection of the durable event
    history, with the liveness beat as its loudest element, because a quiet
    console and a dead watcher must not render the same.

    Read-only on purpose. Every write path needs the control token and has no
    button here; an operator page that could create authority would be the very
    hole the control plane exists to close.
    """
    path = Path(__file__).parent / "client" / "console.html"
    if not path.exists():
        raise HTTPException(500, "autonomy console missing")
    return path.read_text(encoding="utf-8")


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/", response_class=HTMLResponse)
async def app_viewer(request: Request, response: Response):
    """A bare-minimal UI-only app shell: it starts a run, renders the composed
    interface, and turns a tap into the next turn. The protocol does the work.

    Serving the page is what mints the viewer session. The cookie is HttpOnly so
    the page's own script can never read it, SameSite=strict so no other site can
    make this browser spend, and scoped to /app so it rides on no other route of
    this origin.
    """
    _require_app_viewer()
    path = Path(__file__).parent / "client" / "app.html"
    if not path.exists():
        raise HTTPException(500, "app viewer missing")
    response.set_cookie(APP_VIEWER_COOKIE, _viewer_session(request),
                        httponly=True, samesite="strict", path="/app")
    return path.read_text(encoding="utf-8")


class AppRunBody(BaseModel):
    """Deliberately narrower than the control plane's RunBody.

    RunBody carries `budget`, `principal` and `allowed_side_effects` - the fields
    that decide what the agent may do and how much it may spend, and the reason
    that route is bearer-gated at all. A browser cannot name any of them here: it
    may ask for an interface, and that is the whole vocabulary.
    """

    prompt: str = Field(min_length=1, max_length=40_000)


@router.post("/app/runs")
async def app_viewer_run(body: AppRunBody, request: Request):
    """Start a run for the app viewer without the page ever holding a token.

    This is not a hole in the control plane: /v1/agent/runs is untouched and
    still refuses every tokenless caller. It is a second, strictly weaker
    capability that exists only while an operator asks for it. Scope, response
    mode and the empty side-effect grant are fixed here rather than accepted from
    the caller, so a run started from a browser can compose an interface and
    nothing else.
    """
    _require_app_viewer()
    supplied = request.cookies.get(APP_VIEWER_COOKIE, "")
    # Compared as bytes: compare_digest raises TypeError on a non-ASCII str, and
    # a hand-crafted cookie has to come back 401, not 500 out of the auth check.
    if not hmac.compare_digest(supplied.encode(), _viewer_session(request).encode()):
        raise HTTPException(401, "no app viewer session; load /app in this browser first")
    ceiling = os.getenv(APP_VIEWER_BUDGET_ENV, "").strip()
    try:
        return await request.app.state.runtime.run(
            prompt=body.prompt,
            scope=MemoryScope("local", "app-viewer", "viewer", "s17-app-viewer"),
            llm=lambda prompt, system: agent_routes.gateway_text_llm(request.app, prompt, system),
            source_uri="app://viewer/runs", source_author="app-viewer",
            respond_as="ui", allowed_side_effects=set(),
            budget=float(ceiling) if ceiling else None,
            transport=request.app.state.gateway,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
