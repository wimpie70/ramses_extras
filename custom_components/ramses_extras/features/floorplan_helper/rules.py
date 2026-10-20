"""Floorplan rule assembly.

Builds the managed ``rules:`` list for the card yaml — per-entity
state/class rules, tap semantics, zone toggle + sync actions,
standalone zone-member rules, toolbar element rules — then appends
the user-authored extras. The small factories at the top
(``class_set_rule``…) are the reusable bits: new rule shapes should
be built from them, not hand-rolled dicts.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from .const import (
    GENERATED_RULE_TAG,
    OPTION_DEVICE_VIEW_URL,
    OPTION_DEVICE_ZONES,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    OPTION_TOOLBAR_ENABLED,
    TOOLBAR_ELEMENT_EDITOR,
    TOOLBAR_ELEMENT_EXPORT,
    TOOLBAR_ELEMENT_IMPORT,
    TOOLBAR_ELEMENT_PLANNER,
    TOOLBAR_ELEMENT_UPLOAD,
    is_generated_rule,
)
from .domains import get_domain
from .expressions import CLASS_ROLES, element_class_expr, standalone_status_expr
from .markers import (
    binding_maps,
    editor_url,
    element_id_for_device,
    planner_url,
)
from .zones import (
    resolve_bound,
    standalone_members,
    zone_clear_action,
    zone_tap_actions,
    zone_toggle_specs,
)

# Non-class rule templates emitted inside the managed block.
ROLE_RULE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "temperature": [
        {
            "state_action": {
                "service": "floorplan.text_set",
                "service_data": {"text": "${entity.state}"},
            }
        }
    ],
}


def class_set_rule(entity: str, element: str, class_expr: str) -> dict[str, Any]:
    """State rule writing the element's whole class attribute."""
    return {
        "entity": entity,
        "element": element,
        "state_action": {
            "service": "floorplan.class_set",
            "service_data": {"class": class_expr},
        },
    }


def text_set_rule(entity: str, element: str, template: str) -> dict[str, Any]:
    """State rule writing text into the element's ``.rx-state`` child."""
    return {
        "entity": entity,
        "element": element,
        "state_action": {
            "service": "floorplan.text_set",
            "service_data": {"text": template},
        },
    }


def fire_dom_event(**payload: Any) -> dict[str, Any]:
    """fire-dom-event action — picked up by the module-level listener."""
    return {"action": "fire-dom-event", **payload}


def link_action(target: str) -> dict[str, Any]:
    """Build a tap_action opening ``target``.

    Internal paths (leading ``/``) navigate inside HA; anything else is
    an external URL opened in a new tab.
    """
    if str(target).startswith("/"):
        return {"action": "navigate", "navigation_path": target}
    return {"action": "url", "url_path": target}


def parse_extra_rules(raw: Any) -> list[dict[str, Any]]:
    """Parse extra_rules entries (dicts or YAML blobs) into rule dicts.

    Generated rules (tagged, or matching the legacy generated
    signature) are dropped — re-importing a generated card yaml stays
    idempotent instead of accumulating stale copies.
    """
    rules: list[dict[str, Any]] = []
    for extra in raw or []:
        parsed: Any = None
        if isinstance(extra, dict):
            parsed = deepcopy(extra)
        elif isinstance(extra, str):
            try:
                parsed = yaml.safe_load(extra)
            except yaml.YAMLError:
                parsed = None
        if isinstance(parsed, dict) and not is_generated_rule(parsed):
            rules.append(parsed)
    return rules


def _device_view_actions(
    dev: dict[str, Any],
    primary: str,
    toggles: list[dict[str, Any]],
    options: dict[str, Any],
) -> list[dict[str, Any]]:
    """double_tap list: deterministic zone clear, then the device view.

    ha-floorplan waits ~250ms to tell a single click from a double
    click — a quick "second tap to deselect" is eaten as a double tap,
    so the clear fires first (all cards, including the origin) and the
    highlight can't get stuck.
    """
    view_url = options.get(OPTION_DEVICE_VIEW_URL) or ""
    view = (
        {"action": "navigate", "navigation_path": view_url}
        if view_url
        else fire_dom_event(
            # picked up by the ramses-floorplan-actions module (loaded
            # as a Lovelace resource → works on any view) to open the
            # device popup
            ramses_device_id=dev.get("device_id"),
            ramses_entity=primary,
            ramses_card=get_domain(dev).popup_card,
        )
    )
    return [zone_clear_action(toggles), view]


def _device_rules(
    model: dict[str, Any],
    dev: dict[str, Any],
    options: dict[str, Any],
    entity_binding_map: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(managed rules, binding-level extras)`` for one model device.

    Binding extras stay separate from the managed list — they are
    user-authored, so they get appended *after* the tagged block."""
    zones = options.get(OPTION_DEVICE_ZONES) or {}
    primary = dev.get("primary_entity")
    element_id = element_id_for_device(dev, options)
    combined_class = element_class_expr(dev)

    rules: list[dict[str, Any]] = []
    for ent in dev.get("entities", []):
        role = ent.get("role") or ""
        eid = ent["entity_id"]
        is_class_role = role in CLASS_ROLES
        templates = ROLE_RULE_TEMPLATES.get(role)
        if not is_class_role and not templates:
            continue
        rule: dict[str, Any] = {"entity": eid}
        if eid != element_id:
            rule["element"] = element_id
        if is_class_role:
            rule["state_action"] = {
                "service": "floorplan.class_set",
                "service_data": {"class": combined_class},
            }
        elif templates:
            rule.update(deepcopy(templates[0]))
        if eid != primary:
            # every rule bound to the element fires its tap_action;
            # suppress it here so the primary-entity rule below is
            # the one more-info opens ("none" is a no-op action)
            rule["tap_action"] = {"action": "none"}
        rules.append(rule)

    if primary:
        # tap the marker → more-info on the device's own entity
        # (climate dialog for a FAN), not a secondary stat sensor;
        # zoned devices get tap = highlight served rooms instead,
        # keep the entity dialog on hold
        tap_rule: dict[str, Any] = {"entity": primary}
        if primary != element_id:
            tap_rule["element"] = element_id
        zone = zones.get(dev.get("device_id")) or {}
        area_elements, bound = resolve_bound(
            model, dev, zone, lambda d: element_id_for_device(d, options)
        )
        if area_elements or bound:
            toggles = zone_toggle_specs(str(dev.get("device_id")), area_elements, bound)
            tap_rule["tap_action"] = zone_tap_actions(toggles)
            tap_rule["hold_action"] = {"action": "more-info"}
            tap_rule["double_tap_action"] = _device_view_actions(
                dev, str(primary), toggles, options
            )
        else:
            tap_rule["tap_action"] = {"action": "more-info"}
        rules.append(tap_rule)

    binding = entity_binding_map.get(primary or "")
    extras = (
        parse_extra_rules(binding.get("extra_rules"))
        if isinstance(binding, dict)
        else []
    )
    return rules, extras


def _toolbar_rules(options: dict[str, Any]) -> list[dict[str, Any]]:
    """Rules for the in-SVG toolbar glyphs (see ``build_toolbar_svg``).

    Emitted inside the managed block so bindings stay managed; harmless
    for SVGs that don't contain the toolbar elements.
    """
    if not options.get(OPTION_TOOLBAR_ENABLED, True):
        return []
    rules: list[dict[str, Any]] = [
        # export/import/upload need service data or a response — they go
        # through ll-custom so the module-level listener can show real
        # dialogs (file picker, results, copy buttons) instead of just
        # dumping the user on the developer-tools page
        {
            "element": TOOLBAR_ELEMENT_EXPORT,
            "tap_action": fire_dom_event(ramses_fp_action="export"),
        },
        {
            "element": TOOLBAR_ELEMENT_IMPORT,
            "tap_action": fire_dom_event(ramses_fp_action="import"),
        },
        {
            "element": TOOLBAR_ELEMENT_UPLOAD,
            "tap_action": fire_dom_event(ramses_fp_action="upload"),
        },
        {
            "element": TOOLBAR_ELEMENT_EDITOR,
            "tap_action": link_action(editor_url(options)),
        },
    ]
    if planner_url(options) != editor_url(options):
        rules.append(
            {
                "element": TOOLBAR_ELEMENT_PLANNER,
                "tap_action": link_action(planner_url(options)),
            }
        )
    return rules


def build_rules(model: dict[str, Any], options: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the managed floorplan rules list.

    Element bindings may be keyed by the bound entity id or by a custom
    element id carrying ``entity_id`` — either way the device's rules
    target the bound element.
    """
    zones = options.get(OPTION_DEVICE_ZONES) or {}
    _, entity_binding_map = binding_maps(options)
    rules: list[dict[str, Any]] = []
    extras: list[dict[str, Any]] = []
    for dev in model.get("devices", []):
        dev_rules, dev_extras = _device_rules(model, dev, options, entity_binding_map)
        rules.extend(dev_rules)
        extras.extend(dev_extras)

    # Standalone zone members (non-ramses entities like DIY valves or
    # zigbee sensors listed in a zone's devices) get a status class +
    # plain more-info on tap; their marker is rendered by
    # build_overlay_fragment.
    for ent in standalone_members(model, zones):
        rule = class_set_rule(ent, ent, standalone_status_expr())
        rule.pop("element")  # element id == entity id
        rule["tap_action"] = {"action": "more-info"}
        rules.append(rule)

    rules.extend(_toolbar_rules(options))
    # Tag generated rules so floorplan_import can tell them apart from
    # user-authored extras — importing a generated card yaml then stays
    # idempotent instead of accumulating stale copies in extra_rules.
    for rule in rules:
        rule[GENERATED_RULE_TAG] = True

    # User-authored extras appended last, untagged: binding-level ones
    # collected above, then the global extra_rules option.
    extras.extend(parse_extra_rules(options.get(OPTION_EXTRA_RULES)))
    return rules + extras


__all__ = [
    "ROLE_RULE_TEMPLATES",
    "build_rules",
    "class_set_rule",
    "fire_dom_event",
    "link_action",
    "parse_extra_rules",
    "text_set_rule",
]
