"""The wall must refuse, never fall over.

`POST /v1/validate` advertises that it adjudicates any surface JSON, including
hostile ones. Three one-line bodies used to return HTTP 500 instead:

    {"$bind": 5}                 TypeError  — regex matched against an int
    {"components": [1, 2, 3]}    AttributeError — .get() on an int
    {"components": "evil"}       AttributeError — iterating a string's characters

A 500 is not a refusal. It is the wall reporting that the attacker broke the
thing that judges attackers, and a control whose failure mode is a stack trace
is worse than no control, because it still looks like one from the outside.

Four more holes were open beside them, and each is asserted below by the
specific shape that walked through it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from s17code.ui.catalog import COMPONENTS                # noqa: E402
from s17code.ui.fixtures import load_injections          # noqa: E402
from s17code.ui.routes import router as ui_router        # noqa: E402
from s17code.ui.validator import Invariant, validate_surface  # noqa: E402


def scaffold(evil: dict | int) -> dict:
    """The standard corpus shape: one safe sibling beside the hostile node.

    `accepted == ["root", "ok"]` afterwards is the observable proof that one
    poisoned component does not blank the screen.
    """
    return {"root": "root", "dataModel": {"title": "Dashboard", "w": 5}, "components": [
        {"id": "root", "type": "Column", "children": ["ok", "evil"]},
        {"id": "ok", "type": "Text", "variant": "heading", "text": {"$bind": "/title"}},
        evil,
    ]}


class TestNeverRaises:
    """validate_surface is pointed at hostile input; it must return, not throw."""

    @pytest.mark.parametrize("surface", [
        None, 7, "evil", [], ["a"],
        {"components": "evil"},
        {"components": 5},
        {"components": [1, 2, 3]},
        {"components": [None]},
        {"components": [{"id": "a", "type": "Text", "text": {"$bind": 5}}]},
        {"components": [{"id": "a", "type": "Text", "text": {"$bind": None}}]},
        {"components": [{"id": "a", "type": "Text", "text": {}}]},
        {},
    ])
    def test_malformed_surface_returns_a_rejection(self, surface):
        result = validate_surface(surface)

        assert isinstance(result.accepted, list)
        if surface not in ({}, {"components": []}):
            assert not result.ok or result.accepted == []


class TestClosedHoles:
    def test_nonstring_pointer_is_rejected_not_a_typeerror(self):
        result = validate_surface(scaffold(
            {"id": "evil", "type": "Text", "text": {"$bind": 5}}))

        assert Invariant.DATA_NOT_CODE in {r.invariant for r in result.rejections}
        assert [c["id"] for c in result.accepted] == ["root", "ok"]

    def test_binding_carrying_an_extra_key_is_rejected(self):
        """`isinstance(dict) and "$bind" in value` let every other key ride along."""
        result = validate_surface(scaffold(
            {"id": "evil", "type": "Text", "text": {"$bind": "/title", "onclick": "steal()"}}))

        assert not result.ok
        assert [c["id"] for c in result.accepted] == ["root", "ok"]

    def test_markup_on_a_number_prop_is_rejected(self):
        """The check used to run only for text|binding kinds.

        A property's kind says what it MEANS, not what a hostile agent will put
        in it.
        """
        result = validate_surface(scaffold(
            {"id": "evil", "type": "Slider", "label": "w", "value": {"$bind": "/w"},
             "min": 0, "max": "<img src=x onerror=alert(1)>"}))

        assert any(r.reason == "value carries markup" for r in result.rejections)

    def test_structure_on_a_non_bindable_text_prop_is_rejected(self):
        """The markup check is isinstance(str)-guarded, so a dict sails past it."""
        result = validate_surface(scaffold(
            {"id": "evil", "type": "Image", "src": "/logo.png", "alt": {"$bind": "/title"}}))

        assert any("must be a scalar" in r.reason for r in result.rejections)

    def test_a_bindable_text_prop_still_accepts_a_binding(self):
        """The ordering trap.

        client/index.html:103 resolves `Card.title`, so tightening text props
        without declaring it bindable would reject Cards that render correctly
        — and read as the validator being broken rather than the catalog being
        out of date.
        """
        result = validate_surface({"root": "c", "dataModel": {"t": "hi"}, "components": [
            {"id": "c", "type": "Card", "title": {"$bind": "/t"}, "children": []}]})

        assert result.ok, [r.as_dict() for r in result.rejections]

    def test_a_bindable_prop_still_refuses_an_arbitrary_dict(self):
        result = validate_surface({"root": "c", "components": [
            {"id": "c", "type": "Card", "title": {"evil": "x"}, "children": []}]})

        assert not result.ok

    def test_non_dict_component_is_named_by_index(self):
        result = validate_surface(scaffold(7))

        assert any("index 2" in r.component_id for r in result.rejections)
        assert [c["id"] for c in result.accepted] == ["root", "ok"]


class TestEndpoint:
    @pytest.fixture()
    def client(self) -> TestClient:
        # /v1/validate needs no runtime: it adjudicates a surface handed to it,
        # which is exactly why it can be pointed at one this service never made.
        app = FastAPI()
        app.include_router(ui_router)
        return TestClient(app)

    @pytest.mark.parametrize("body", [
        {"surface": {"components": [{"id": "a", "type": "Text", "text": {"$bind": 5}}]}},
        {"surface": {"components": [1, 2, 3]}},
        {"surface": {"components": "evil"}},
        {"surface": {}},
        {"surface": {"root": "x", "components": []}},
    ])
    def test_endpoint_never_returns_500(self, client, body):
        """The claim the endpoint makes about itself, asserted."""
        response = client.post("/v1/validate", json=body)

        assert response.status_code < 500, response.text
        assert "rejections" in response.json()

    def test_every_fixture_is_rejected_by_its_named_invariant(self, client):
        for case in load_injections()["cases"]:
            response = client.post("/v1/validate", json={"surface": case["surface"]})

            assert response.status_code == 200, case["name"]
            payload = response.json()
            assert not payload["ok"], case["name"]
            assert case["expect_invariant"] in {r["invariant"] for r in payload["rejections"]}, \
                (case["name"], payload["rejections"])

    def test_the_safe_sibling_survives_every_attack(self, client):
        """One poisoned node must not blank the screen."""
        for case in load_injections()["cases"]:
            if "expect_accepted" not in case:
                continue
            response = client.post("/v1/validate", json={"surface": case["surface"]})

            assert response.json()["accepted"] == case["expect_accepted"], case["name"]


class TestCatalogRendererDrift:
    """The check the fork lost when it forked before `gallery.py` existed.

    A ComponentSpec with no renderer does not fail anything today — it surfaces
    as a red `[skipped unknown type: X]` marker in a browser, which is a bug
    report written in the worst possible place.
    """

    def test_every_catalog_type_has_a_renderer_in_the_client(self):
        client_source = (Path(__file__).parent.parent / "s17code" / "ui" / "client"
                         / "index.html").read_text(encoding="utf-8")

        # Renderers take whatever arguments they need — `Divider:()=>`,
        # `Image:(c)=>`, `Card:(c,ctx)=>` — so match the shape, not one arity.
        # The first draft of this test asserted `(c,ctx)` and reported Divider
        # and Image as missing when both render perfectly, which is the failure
        # mode a drift check must not have: crying wolf trains people to
        # disable it, and then the real drift lands unannounced.
        missing = [name for name in COMPONENTS
                   if not re.search(rf"\b{re.escape(name)}\s*:\s*\([^)]*\)\s*=>", client_source)]

        assert not missing, f"catalog types with no renderer: {missing}"
