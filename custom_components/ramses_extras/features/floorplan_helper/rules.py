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
    DEVICE_VIEW_SERVICE,
    GENERATED_RULE_TAG,
    OPTION_CAPTION_FIELDS,
    OPTION_CAPTION_OVERRIDES,
    OPTION_DEVICE_VIEW_URL,
    OPTION_ELEMENT_BINDINGS,
    OPTION_EXTRA_RULES,
    ZONE_TOGGLE_SERVICE,
    is_generated_rule,
)
from .domains import caption_group_key, caption_suffix_for, get_domain
from .expressions import (
    CLASS_ROLES,
    element_caption_expr,
    element_class_expr,
    standalone_status_expr,
)
from .markers import (
    binding_maps,
    effective_zones,
    element_id_for_device,
    marker_meta_for_device,
)
from .zones import (
    model_entity_ids,
    resolve_bound,
    standalone_members,
    zone_tap_actions,
    zone_toggle_specs,
)

# Roles handled by the domain caption spec, not per-entity templates:
# the element has a single caption text, so every contributing entity
# re-emits the complete combined expression (see element_caption_expr)
# — individual text_set rules would clobber each other.
CAPTION_ROLES = ("temperature", "co2")

# Non-class rule templates emitted inside the managed block. Roles not
# listed here and not in CLASS_ROLES/CAPTION_ROLES get no rule.
ROLE_RULE_TEMPLATES: dict[str, list[dict[str, Any]]] = {}


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


def studio_tap_action(action: Any) -> dict[str, Any] | None:
    """Translate a studio marker action to an ha-floorplan action.

    Studio stores ``{kind, service, serviceData, navPath, url}`` —
    same mapping its own exporter uses. ``kind: none`` (or an
    incomplete action) returns ``None`` → inherit our defaults.
    """
    if not isinstance(action, dict):
        return None
    kind = action.get("kind")
    if kind == "more-info":
        return {"action": "more-info"}
    if kind == "toggle":
        return {"action": "toggle"}
    if kind == "navigate":
        path = action.get("navPath")
        return {"action": "navigate", "navigation_path": path} if path else None
    if kind == "url":
        url = action.get("url")
        return {"action": "url", "url_path": url} if url else None
    if kind == "call-service":
        service = action.get("service")
        if not service:
            return None
        data: Any = action.get("serviceData")
        if isinstance(data, str) and data.strip():
            try:
                data = yaml.safe_load(data)
            except yaml.YAMLError:
                data = None
        rule: dict[str, Any] = {"action": "call-service", "service": service}
        if isinstance(data, dict) and data:
            rule["service_data"] = data
        return rule
    return None


_ZONE_SHORTHAND_SERVICES = {ZONE_TOGGLE_SERVICE, "floorplan.class_toggle"}
_DEVICE_VIEW_SHORTHAND_SERVICES = {DEVICE_VIEW_SERVICE}


def _studio_shorthand(action: Any, services: set[str]) -> bool:
    """Studio ``call-service`` pointing at one of our bridge services
    is a seeded representation — regenerate the real action from
    current config so stale serviceData can't drift (zone members or
    the popup card may have changed since seeding)."""
    return (
        isinstance(action, dict)
        and action.get("kind") == "call-service"
        and action.get("service") in services
    )


def stale_managed_rule(rule: dict[str, Any], managed_entities: set[str]) -> bool:
    """Legacy generated rule replayed via stored extras.

    Pre-tagging exports wrote plain ``floorplan.*`` rules bound to
    model entities; on import they landed verbatim in ``extra_rules``
    and now shadow the fresh managed rules (e.g. an old
    ``${entity.state}`` text_set clobbering the combined caption).
    Anything tagged or flagged by ``is_generated_rule`` is already
    filtered; this catches the untagged remainder. A genuine user rule
    that pairs a ramses entity with a ``floorplan.*`` service is
    indistinguishable from our own output — and the managed block
    generates those anyway.
    """
    if is_generated_rule(rule) or not managed_entities:
        return False
    if rule.get("entity") not in managed_entities:
        return False
    svc = str((rule.get("state_action") or {}).get("service") or "")
    return svc.startswith("floorplan.")


def parse_extra_rules(
    raw: Any, managed_entities: set[str] | None = None
) -> list[dict[str, Any]]:
    """Parse extra_rules entries (dicts or YAML blobs) into rule dicts.

    Generated rules (tagged, matching the legacy signature, or shaped
    like a stale managed rule on a model entity) are dropped —
    re-importing a generated card yaml stays idempotent instead of
    accumulating stale copies.
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
        if (
            isinstance(parsed, dict)
            and not is_generated_rule(parsed)
            and not stale_managed_rule(parsed, managed_entities or set())
        ):
            rules.append(parsed)
    return rules


def caption_override_for_device(
    dev: dict[str, Any], options: dict[str, Any]
) -> list[str] | None:
    """Stored ``caption_overrides`` entry for a device.

    Precedence: device id → device class → primary entity. Returns the
    raw ``"eid|suffix"`` item list, or None when no override applies.
    """
    overrides: dict[str, Any] = options.get(OPTION_CAPTION_OVERRIDES) or {}
    for key in (
        dev.get("device_id"),
        dev.get("device_class"),
        dev.get("primary_entity"),
    ):
        if key is not None and str(key) in overrides:
            raw = overrides[str(key)]
            return list(raw) if isinstance(raw, list) else [str(raw)]
    return None


def _parse_caption_items(raw: Any) -> list[tuple[str, str]]:
    """``"eid|suffix"`` items → ``(entity_id, suffix)`` pairs."""
    if isinstance(raw, str):
        raw = [raw]
    return [
        (eid.strip(), sfx.strip())
        for item in raw or []
        for eid, _, sfx in [str(item).partition("|")]
        if eid.strip()
    ]


def caption_pairs_for_device(
    dev: dict[str, Any],
    options: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Resolved ``(entity_id, suffix)`` caption pairs for a device.

    Precedence — the studio project wins over stored options:

    1. ``style.showState`` off → no caption (studio's per-marker toggle)
    2. ``marker.ramsesCaption`` — explicit ``eid|suffix`` items written
       by the actions card's caption editor
    3. ``marker.entities`` with more than one entity — entities the
       user attached to the marker in studio are what it shows
    4. ``caption_overrides`` option (device → class → primary entity)
    5. ``caption_fields`` option (stored per-class group selection —
       legacy; the UI moved to the actions card)
    6. the domain's ``caption_groups`` default
    """
    domain = get_domain(dev)
    if meta and meta.get("show_state") is False:
        # studio's "Show state" toggle persists with the project —
        # unticking it is the per-marker way to hide the caption
        return []
    raw = (meta or {}).get("ramses_caption")
    if raw is not None:
        return _parse_caption_items(raw)
    marker_ents = (meta or {}).get("entities") or []
    if len(marker_ents) > 1:
        return [(str(e), caption_suffix_for(str(e), domain)) for e in marker_ents]
    raw = caption_override_for_device(dev, options)
    if raw is not None:
        return _parse_caption_items(raw)
    # per-class stored selection — caption_fields maps device class →
    # group keys (first pattern); absent key = domain default,
    # empty list = no caption for the class
    selected = (options.get(OPTION_CAPTION_FIELDS) or {}).get(
        str(dev.get("device_class") or "")
    )
    if selected is not None:
        groups = tuple(
            g for g in domain.caption_groups if caption_group_key(g) in selected
        )
        return domain.caption_entities(dev.get("entities") or [], groups)
    return domain.caption_entities(dev.get("entities") or [])


def _device_view_actions(
    dev: dict[str, Any],
    primary: str,
    toggles: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any]:
    """double_tap action: open the device view via the service bridge.

    ``ramses_extras.floorplan_device_view`` fires an HA event — the
    module clears every zone highlight (covering the old deterministic
    zone_clear list, which a fast second tap needs since ha-floorplan
    waits ~250ms before deciding single-vs-double) and then opens the
    popup. A configured ``device_view_url`` still wins with a plain
    navigate action — both shapes are a single call, expressible in
    studio's marker actions.
    """
    view_url = options.get(OPTION_DEVICE_VIEW_URL) or ""
    if view_url:
        return {"action": "navigate", "navigation_path": view_url}
    return {
        "action": "call-service",
        "service": DEVICE_VIEW_SERVICE,
        "service_data": {
            "device_id": dev.get("device_id"),
            "entity": primary,
            "card": get_domain(dev).popup_card,
        },
    }


def _device_rules(
    model: dict[str, Any],
    dev: dict[str, Any],
    options: dict[str, Any],
    entity_binding_map: dict[str, dict[str, Any]],
    managed_entities: set[str],
    marker_meta: dict[str, dict[str, Any]] | None = None,
    zones: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(managed rules, binding-level extras)`` for one model device.

    Binding extras stay separate from the managed list — they are
    user-authored, so they get appended *after* the tagged block."""
    zones = zones if zones is not None else effective_zones(model, options, marker_meta)
    primary = dev.get("primary_entity")
    element_id = element_id_for_device(dev, options)
    combined_class = element_class_expr(dev)

    rules: list[dict[str, Any]] = []
    for ent in dev.get("entities", []):
        role = ent.get("role") or ""
        eid = ent["entity_id"]
        is_class_role = role in CLASS_ROLES
        templates = ROLE_RULE_TEMPLATES.get(role)
        if role in CAPTION_ROLES or (not is_class_role and not templates):
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

    # caption: one combined ${} emitted on every contributing entity's
    # rule — whichever state updates, the caption rewrites in full.
    meta = marker_meta_for_device(dev, marker_meta)
    caption_pairs = caption_pairs_for_device(dev, options, meta)
    caption_expr = element_caption_expr(caption_pairs)
    if caption_expr:
        for eid, _ in caption_pairs:
            rule = text_set_rule(eid, element_id, caption_expr)
            if eid == element_id:
                rule.pop("element")
            if eid != primary:
                rule["tap_action"] = {"action": "none"}
            rules.append(rule)

    if primary:
        # tap the marker → more-info on the device's own entity
        # (climate dialog for a FAN), not a secondary stat sensor;
        # zoned devices get tap = highlight served rooms instead,
        # keep the entity dialog on hold. Studio marker actions
        # override: a deliberate non-default gesture wins, while
        # "none"/more-info/our seeded class_toggle shorthand keep the
        # zone behaviour.
        tap_rule: dict[str, Any] = {"entity": primary}
        if primary != element_id:
            tap_rule["element"] = element_id
        # presence in device_zones is what makes a device a zone parent
        # — resolve_bound always folds the device into its own bound
        # set, so bound alone can't be the gate (every unzoned device
        # would emit a self-referencing class_toggle)
        zone = zones.get(str(dev.get("device_id") or ""))
        area_elements, bound = (
            ([], [])
            if zone is None
            else resolve_bound(
                model, dev, zone, lambda d: element_id_for_device(d, options)
            )
        )
        studio_actions = (meta or {}).get("actions") or {}
        tap_override = studio_tap_action(studio_actions.get("tap"))
        hold_override = studio_tap_action(studio_actions.get("hold"))
        double_override = studio_tap_action(studio_actions.get("double"))
        if area_elements or bound:
            toggles = zone_toggle_specs(str(dev.get("device_id")), area_elements, bound)
            if (
                tap_override is None
                or tap_override.get("action") == "more-info"
                or _studio_shorthand(
                    studio_actions.get("tap"), _ZONE_SHORTHAND_SERVICES
                )
            ):
                tap_rule["tap_action"] = zone_tap_actions(toggles)
            else:
                tap_rule["tap_action"] = tap_override
            tap_rule["hold_action"] = hold_override or {"action": "more-info"}
            if double_override and not _studio_shorthand(
                studio_actions.get("double"), _DEVICE_VIEW_SHORTHAND_SERVICES
            ):
                tap_rule["double_tap_action"] = double_override
            else:
                tap_rule["double_tap_action"] = _device_view_actions(
                    dev, str(primary), toggles, options
                )
        else:
            tap_rule["tap_action"] = tap_override or {"action": "more-info"}
            if hold_override:
                tap_rule["hold_action"] = hold_override
            if double_override:
                tap_rule["double_tap_action"] = double_override
        rules.append(tap_rule)

    binding = entity_binding_map.get(primary or "")
    extras = (
        parse_extra_rules(binding.get("extra_rules"), managed_entities)
        if isinstance(binding, dict)
        else []
    )
    return rules, extras


def build_rules(
    model: dict[str, Any],
    options: dict[str, Any],
    marker_meta: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the managed floorplan rules list.

    Element bindings may be keyed by the bound entity id or by a custom
    element id carrying ``entity_id`` — either way the device's rules
    target the bound element.

    :param marker_meta: entity_id → studio-marker map (the value map
        of ``studio_marker_positions``) — studio edits to actions /
        showState / label persist in the project and are honoured
        here; studio is the per-marker editor, tweaks only cover what
        it can't express.
    """
    zones = effective_zones(model, options, marker_meta)
    _, entity_binding_map = binding_maps(options)
    standalone = standalone_members(model, zones)
    # model entities + standalone members — anything the managed block
    # already owns; untagged floorplan.* rules on these in stored
    # extras are stale leftovers from pre-tagging exports
    managed = model_entity_ids(model) | set(standalone)
    rules: list[dict[str, Any]] = []
    extras: list[dict[str, Any]] = []
    for dev in model.get("devices", []):
        dev_rules, dev_extras = _device_rules(
            model, dev, options, entity_binding_map, managed, marker_meta, zones
        )
        rules.extend(dev_rules)
        extras.extend(dev_extras)

    # Standalone zone members (non-ramses entities like DIY valves or
    # zigbee sensors listed in a zone's devices) get a status class +
    # plain more-info on tap; their marker is rendered by
    # build_overlay_fragment.
    for ent in standalone:
        rule = class_set_rule(ent, ent, standalone_status_expr())
        rule.pop("element")  # element id == entity id
        meta = (marker_meta or {}).get(ent) or {}
        rule["tap_action"] = studio_tap_action(
            (meta.get("actions") or {}).get("tap")
        ) or {"action": "more-info"}
        rules.append(rule)

    # Tag generated rules so floorplan_import can tell them apart from
    # user-authored extras — importing a generated card yaml then stays
    # idempotent instead of accumulating stale copies in extra_rules.
    for rule in rules:
        rule[GENERATED_RULE_TAG] = True

    # User-authored extras appended last, untagged: binding-level ones
    # collected above, then the global extra_rules option.
    extras.extend(parse_extra_rules(options.get(OPTION_EXTRA_RULES), managed))
    return rules + extras


__all__ = [
    "ROLE_RULE_TEMPLATES",
    "stale_managed_rule",
    "build_rules",
    "caption_override_for_device",
    "caption_pairs_for_device",
    "class_set_rule",
    "fire_dom_event",
    "link_action",
    "parse_extra_rules",
    "studio_tap_action",
    "text_set_rule",
]
