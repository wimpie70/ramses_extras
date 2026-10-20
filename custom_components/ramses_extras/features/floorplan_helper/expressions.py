"""``${…}`` expression builders for ha-floorplan rule actions.

Every ``floorplan.*_set`` ``service_data`` value here runs inside
ha-floorplan's sandboxed JS interpreter (sval, ES5-ish). The runtime
has a hard contract that is easy to break:

- The template is wrapped as ``return `…`;`` **only when the body
  contains no "return" substring** — a ``function``/``return`` inside
  a ``${}`` expression silently discards the result (we hit this: a
  spin IIFE evaluated to ``undefined`` and wiped the class attribute).
  Everything below must stay a pure expression — ternaries only.
- ``Array.prototype.includes`` is **not** available — use
  ``"…".indexOf(x) >= 0`` or pipe-delimited lookup strings.
- ``floorplan.class_set`` *replaces* the element's whole class
  attribute — a class rule must therefore re-emit the element's full
  class set (status + spin + preserved ``rx-zone-*``), or rules
  clobber each other.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from typing import Any

from .domains import get_domain

# Roles that produce a class rule on the element (non-class roles get
# their own templates in rules.py — e.g. temperature → text_set).
CLASS_ROLES = ("status", "heat_demand", "window_open", "fan_rate")


def _st(entity_id: str) -> str:
    """Sandbox-safe state accessor — ``states[...]`` not ``entity``, so
    expressions can be combined across rules."""
    return f'states["{entity_id}"]'


def role_class_expr(role: str | None, ents: list[str]) -> str | None:
    """JS expression yielding the class(es) for ``role`` entity(ies).

    Multiple entities of one role fold into a single OR-ed term, so
    the same class is never emitted twice.
    """
    sts = [_st(e) for e in ents]
    if not sts:
        return None
    if role == "status":
        cond = " || ".join(f'({s} && {s}.state === "on")' for s in sts)
        return f'(({cond}) ? "rx-online" : "rx-offline")'
    if role == "heat_demand":
        exprs = " || ".join(
            f'({s} && Number({s}.state) > 0 ? "rx-heat-demand" : "")' for s in sts
        )
        return f"({exprs})"
    if role == "window_open":
        exprs = " || ".join(
            f'({s} && {s}.state === "on" ? "rx-window-open" : "")' for s in sts
        )
        return f"({exprs})"
    if role == "fan_rate":
        # speed-proportional spin: numeric % state, else mode names;
        # entities OR-ed — first one carrying a value wins. Pure
        # ternary — see module docstring for the "return" constraint.
        def spin(st: str) -> str:
            num = f"parseFloat(String({st}.state).toLowerCase())"
            txt = f"String({st}.state).toLowerCase()"
            return (
                f'({st}?({num}>75?"rx-spin-fast"'
                f':{num}>40?"rx-spin"'
                f':{num}>0?"rx-spin-slow"'
                f':"|high|boost|".indexOf("|"+{txt}+ "|")>=0?"rx-spin-fast"'
                f':"|medium|normal|".indexOf("|"+{txt}+ "|")>=0?"rx-spin"'
                f':"|low|auto|away|".indexOf("|"+{txt}+ "|")>=0'
                '?"rx-spin-slow":""):"")'
            )

        return "(" + " || ".join(spin(s) for s in sts) + ")"
    return None


def _sorted_role_ents(by_role: dict[str, list[str]], role: str) -> list[str]:
    """fan_rate entities sorted: actual speed% first, then rate, mode."""
    ents = by_role.get(role) or []
    if role != "fan_rate":
        return ents
    return sorted(
        ents, key=lambda e: 0 if "fan_speed" in e else 1 if "fan_rate" in e else 2
    )


def element_class_expr(dev: dict[str, Any]) -> str | None:
    """Combined ``${}`` class expression for a device's element.

    Re-emits the element's complete class set (see module docstring);
    the trailing term preserves any toggled ``rx-zone-*`` classes so a
    status update can't drop a zone highlight.
    """
    domain = get_domain(dev)
    roles = domain.class_roles or CLASS_ROLES
    by_role: dict[str, list[str]] = {}
    for ent in dev.get("entities", []):
        role = ent.get("role") or ""
        eid = str(ent.get("entity_id") or "")
        if not eid or role not in roles:
            continue
        if role == "fan_rate" and not domain.can_spin:
            continue
        by_role.setdefault(role, []).append(eid)
    parts = [
        expr
        for role in roles
        if (expr := role_class_expr(role, _sorted_role_ents(by_role, role)))
    ]
    if not parts:
        return None
    parts.append(
        '((typeof element=="object"&&element&&element.getAttribute'
        '?(String(element.getAttribute("class")||"")'
        '.match(/rx-zone-\\S+/g)||[]):[]).join(" "))'
    )
    return "${" + ' + " " + '.join(parts) + "}"


def standalone_status_expr() -> str:
    """``${}`` expression colouring a standalone marker by availability."""
    return (
        '${(entity==null||entity.state==="unavailable"'
        '||entity.state==="unknown")'
        ' ? "rx-offline" : "rx-online"}'
    )


def element_caption_expr(
    pairs: list[tuple[str, str]],
) -> str | None:
    """``${}`` expression building the element's state caption.

    ``pairs`` are ``(entity_id, suffix)`` from
    ``DeviceDomain.caption_entities`` — each contributes
    ``state + suffix``, joined with `` / `` (e.g. a FAN's
    ``"12.9° / 9.1°"``, a CO2 sensor's ``"402 ppm"``). Reads
    ``states[...]`` so the same expression can be emitted on every
    contributing entity's rule — the element has one caption text,
    so per-entity rules must all write the complete value or they'd
    clobber each other (same lesson as ``class_set``).
    """
    terms = []
    for eid, suffix in pairs:
        s = _st(eid)
        terms.append(f'({s} ? String({s}.state) + "{suffix}" : "")')
    if not terms:
        return None
    return "${" + ' + " / " + '.join(terms) + "}"


__all__ = [
    "CLASS_ROLES",
    "element_caption_expr",
    "element_class_expr",
    "role_class_expr",
    "standalone_status_expr",
]
