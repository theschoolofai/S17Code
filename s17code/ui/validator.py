"""The injection wall: three invariants, enforced deterministically.

Every surface an agent produces passes through :func:`validate_surface`
before it reaches the client. The wall does not ask a model to be careful.
It checks structure:

  1. Catalog invariant      every component ``type`` is in the catalog
  2. Data-not-code invariant no property smuggles markup, a handler, or a URL
  3. Event invariant         every action name is registered

A rejection is specific: it names the component, the offending field, and the
invariant it broke. The safe part of a surface still renders; only the
offending components are dropped, so a single poisoned node cannot blank the
screen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import COMPONENTS, REGISTERED_ACTIONS

# Markup / script / javascript-url smells. A ``text`` or ``binding`` value that
# matches is treated as an attempt to reach execution and is refused.
_MARKUP = re.compile(r"<[a-z!/][^>]*>|</[a-z]+>", re.I)
_JS_URL = re.compile(r"^\s*(javascript|data|vbscript):", re.I)
_HANDLER = re.compile(r"^on[a-z]+$", re.I)  # onclick, onerror, onload, ...
_POINTER = re.compile(r"^/[^\s]*$")  # a JSON Pointer: /rows, /pending/params


class Invariant:
    CATALOG = "catalog"
    DATA_NOT_CODE = "data-not-code"
    EVENT = "event"


@dataclass(frozen=True)
class Rejection:
    component_id: str
    field: str
    invariant: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "field": self.field,
            "invariant": self.invariant,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ValidationResult:
    accepted: list[dict]  # components that render
    rejections: list[Rejection]

    @property
    def ok(self) -> bool:
        return not self.rejections


def _looks_like_markup(value) -> bool:
    return isinstance(value, str) and bool(_MARKUP.search(value))


def _looks_like_js_url(value) -> bool:
    return isinstance(value, str) and bool(_JS_URL.match(value))


def validate_surface(surface: dict) -> ValidationResult:
    """Validate one surface (``{root, components:[...]}``) against the catalog.

    Never raises. This is the wall, and it is pointed at hostile input by
    design, so an input it cannot parse must come back as a *rejection* and not
    as an exception: an exception becomes a 500, a 500 is not a refusal, and a
    wall that falls over when pushed is not a wall. Three one-line bodies used
    to reach here and crash — a non-dict surface, a components list holding
    integers, and components as a bare string.
    """
    accepted: list[dict] = []
    rejections: list[Rejection] = []

    if not isinstance(surface, dict):
        return ValidationResult([], [Rejection(
            "<surface>", "surface", Invariant.CATALOG,
            f"surface must be an object, got {type(surface).__name__}")])

    components = surface.get("components", [])
    # A string is iterable, so `for comp in "evil"` would loop over characters
    # and fail one character at a time. Reject the shape, not its letters.
    if not isinstance(components, (list, tuple)):
        return ValidationResult([], [Rejection(
            "<surface>", "components", Invariant.CATALOG,
            f"components must be a list, got {type(components).__name__}")])

    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            rejections.append(Rejection(
                f"<index {index}>", "component", Invariant.CATALOG,
                f"component must be an object, got {type(comp).__name__}"))
            continue

        cid = comp.get("id", "<no id>")
        ctype = comp.get("type")

        # 1. Catalog invariant.
        if ctype not in COMPONENTS:
            rejections.append(
                Rejection(cid, "type", Invariant.CATALOG, f"unknown component type {ctype!r}")
            )
            continue

        spec = COMPONENTS[ctype]
        bad = False
        for field_name, value in comp.items():
            if field_name in ("id", "type", "children"):
                if field_name == "children":  # children are refs; validated by tree walk elsewhere
                    continue
                continue

            # 2. Data-not-code: the property must be one the schema declares.
            # An unknown property shaped like a DOM handler (onclick, onerror)
            # gets a specific message; both cases break data-not-code.
            if field_name not in spec.props:
                reason = (
                    "event-handler property is never allowed"
                    if _HANDLER.match(field_name)
                    else f"unknown property {field_name!r} on {ctype}"
                )
                rejections.append(Rejection(cid, field_name, Invariant.DATA_NOT_CODE, reason))
                bad = True
                break

            prop = spec.props[field_name]
            # Markup is checked on EVERY kind, not just text and binding. The
            # kind describes what the property means, not what a hostile agent
            # will put in it: `Slider.max = "<img src=x onerror=alert(1)>"` was
            # accepted, because `max` is a number prop and the check never ran.
            if _looks_like_markup(value):
                rejections.append(
                    Rejection(cid, field_name, Invariant.DATA_NOT_CODE, "value carries markup")
                )
                bad = True
                break
            # A structure where a scalar belongs. The markup check above is
            # isinstance(str)-guarded, so a dict walks past it untouched and
            # lands in the client as an object it was never told to expect.
            # `bindable` is the declared exception: props the client really does
            # resolve say so on the spec.
            if prop.kind == "text" and isinstance(value, (dict, list)):
                if not (prop.bindable and isinstance(value, dict) and set(value) == {"$bind"}):
                    rejections.append(Rejection(
                        cid, field_name, Invariant.DATA_NOT_CODE,
                        f"{prop.kind} property must be a scalar, got {type(value).__name__}"))
                    bad = True
                    break
            if _looks_like_js_url(value):
                rejections.append(
                    Rejection(cid, field_name, Invariant.DATA_NOT_CODE, "value is a script/data URL")
                )
                bad = True
                break
            # Exactly {"$bind": "<string>"} and nothing else. The old test was
            # `isinstance(dict) and "$bind" in value`, which accepted
            # {"$bind": 5} — and the pointer match on the next line then called
            # a regex against an int and raised TypeError, turning a hostile
            # surface into a 500. It also accepted {"$bind": "/ok", "onclick":
            # "..."}, carrying an extra key straight through the wall.
            if prop.kind == "binding" and not (
                    isinstance(value, dict) and set(value) == {"$bind"}
                    and isinstance(value["$bind"], str)):
                # A binding must be an explicit {"$bind": "/pointer"}. Inline
                # text where a binding belongs is how markup sneaks in.
                rejections.append(
                    Rejection(cid, field_name, Invariant.DATA_NOT_CODE, "binding must be {'$bind': '/pointer'}")
                )
                bad = True
                break
            if prop.kind == "binding" and not _POINTER.match(value["$bind"]):
                rejections.append(
                    Rejection(cid, field_name, Invariant.DATA_NOT_CODE, f"invalid JSON Pointer {value['$bind']!r}")
                )
                bad = True
                break
            if prop.kind == "enum" and value not in prop.values:
                rejections.append(
                    Rejection(cid, field_name, Invariant.DATA_NOT_CODE, f"{value!r} not in {prop.values}")
                )
                bad = True
                break

            # 3. Event invariant: an action references a registered name only.
            if prop.kind == "action":
                action_name = value.get("action") if isinstance(value, dict) else None
                if action_name not in REGISTERED_ACTIONS:
                    rejections.append(
                        Rejection(cid, field_name, Invariant.EVENT, f"unregistered action {action_name!r}")
                    )
                    bad = True
                    break

        if not bad:
            accepted.append(comp)

    return ValidationResult(accepted=accepted, rejections=rejections)
