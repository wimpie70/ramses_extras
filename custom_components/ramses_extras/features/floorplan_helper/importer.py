"""Floorplan YAML importer — pure parsing for ``floorplan_import``.

Turns pasted floorplan YAML (floorplan-editor output, a full
``type: custom:floorplan-card`` config, a dashboard ``views:`` fragment,
or a bare rules list) into the stored mapping: rules carrying both an
element and an entity become ``element_bindings``; everything else is
kept verbatim in global ``extra_rules`` so it is re-emitted inside the
managed block on the next export.

Kept hass-free so it is unit-testable.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from typing import Any

import yaml

_MISSING = object()

# Keys that mark a dict as a floorplan rule (vs. a view/card container).
_RULE_KEYS = frozenset(
    {
        "entity",
        "entities",
        "element",
        "elements",
        "state_action",
        "tap_action",
        "hold_action",
        "double_tap_action",
        "hover_action",
        "long_press_action",
        "service",
        "services",
    }
)


def _looks_like_rules(items: list[Any]) -> bool:
    """True when ``items`` is a list of dicts with at least one rule key."""
    return all(isinstance(item, dict) for item in items) and any(
        _RULE_KEYS & item.keys() for item in items
    )


def _find_rules_list(node: Any, depth: int = 0) -> list[Any] | None:
    """Locate the floorplan rules list inside a parsed YAML structure.

    Checks the known shapes first (card config, dashboard views, bare
    list) and falls back to a bounded recursive search for a ``rules``
    key holding a list of rule dicts.
    """
    if depth > 6 or node is None:
        return None
    if isinstance(node, list):
        if node and _looks_like_rules(node):
            return node
        for item in node:
            found = _find_rules_list(item, depth + 1)
            if found is not None:
                return found
        return None
    if isinstance(node, dict):
        rules = node.get("rules", _MISSING)
        if isinstance(rules, list) and (not rules or _looks_like_rules(rules)):
            # An explicit empty `rules:` key is a valid (empty) import.
            return rules
        for key in ("config", "cards", "views"):
            child = node.get(key)
            if child is not None:
                found = _find_rules_list(child, depth + 1)
                if found is not None:
                    return found
    return None


def _as_list(value: Any) -> list[str]:
    """Normalise a scalar-or-list YAML value into a string list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def parse_floorplan_yaml(text: str) -> dict[str, Any]:
    """Parse pasted floorplan YAML into bindings + verbatim rules.

    :param text: YAML text — card config, dashboard view, or rules list
    :return: ``{bindings: {element_id: {"entity_id": ...}},
        extra_rules: [rule dicts], warnings: [str]}`` — on failure
        ``{"error": str}``.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        return {"error": f"Invalid YAML: {err}"}
    if data is None:
        return {"error": "Empty input"}

    rules = _find_rules_list(data)
    if rules is None:
        return {"error": "No rules list found in the pasted YAML"}

    bindings: dict[str, dict[str, Any]] = {}
    extra_rules: list[dict[str, Any]] = []
    warnings: list[str] = []

    for rule in rules:
        elements = _as_list(rule.get("element") or rule.get("elements"))
        entities = _as_list(rule.get("entity") or rule.get("entities"))
        if elements and entities:
            # Keep the authored rule verbatim AND record the binding so
            # generated rules target the same element on re-export.
            extra_rules.append(dict(rule))
            for element_id in elements:
                bindings.setdefault(element_id, {"entity_id": entities[0]})
            if len(entities) > 1:
                warnings.append(
                    f"{elements[0]}: rule binds {len(entities)} entities; "
                    f"stored binding uses {entities[0]}"
                )
        else:
            # Element-less rules (entity targets its own element) and
            # entity-less rules (pure actions) are kept verbatim.
            extra_rules.append(dict(rule))

    return {
        "bindings": bindings,
        "extra_rules": extra_rules,
        "warnings": warnings,
    }


__all__ = ["parse_floorplan_yaml"]
