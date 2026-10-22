"""Floorplan Helper feature options flow.

Only feature-wide knobs live here (exported toolbar, studio URL,
per-class caption selection). Everything spatial — drawing SVG paths,
marker positions, per-marker icon/colours/label/actions/zone — belongs
to the floorplan-studio project or the actions card's own YAML
(``floors:``), which is the single source of truth. Stored
``icon_overrides``/``caption_overrides``/``marker_style_overrides``
options still apply as a fallback for elements without a marker, and
are migrated into the project on the next export.

Follows the feature config flow contract: exposes
``async_step_floorplan_helper_config(flow, user_input)`` which the main
options flow delegates to once ``_selected_feature`` is set.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from .const import (
    DEFAULT_EDITOR_URL,
    OPTION_CAPTION_FIELDS,
    OPTION_EDITOR_URL,
    OPTION_TOOLBAR_ENABLED,
)
from .domains import caption_group_key, caption_group_label, get_domain
from .mapping import get_floorplan_options, persist_floorplan_options

_LOGGER = logging.getLogger(__name__)

_CAPTION_FIELD_PREFIX = "caption_fields__"


def _caption_classes(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Device classes in the model → ``(domain, entities)``.

    ``entities`` pools every entity dict across that class's devices —
    the caption multi-select only offers groups matching a real
    entity, so a remote without a CO2 sensor is never offered
    ``co2_level ppm``.
    """
    classes: dict[str, Any] = {}
    for dev in devices or []:
        cls = str(dev.get("device_class") or "")
        if not cls:
            continue
        domain, entities = classes.setdefault(cls, (get_domain(cls), []))
        entities.extend(dev.get("entities") or [])
    return classes


async def async_step_floorplan_helper_config(
    flow: Any, user_input: dict[str, Any] | None = None
) -> Any:
    """Floorplan Helper configuration step.

    :param flow: The main options-flow handler instance
    :param user_input: Submitted form data (or None on first display)
    :return: ConfigFlowResult
    """
    config_entry = flow._config_entry  # noqa: SLF001
    options = get_floorplan_options(config_entry)

    classes: dict[str, Any] = {}
    try:
        from .topology import build_floorplan_model

        model = await build_floorplan_model(flow.hass)
        classes = _caption_classes(model.get("devices") or [])
    except Exception as err:  # pragma: no cover - model needs registries
        _LOGGER.debug("Caption fields skipped — topology unavailable: %s", err)

    # Per class, only the caption groups that match a real entity on
    # one of its devices — ``(group, example_entity_id)`` pairs for the
    # option labels.
    class_groups: dict[str, list[tuple[Any, str]]] = {}
    for cls, (domain, entities) in classes.items():
        groups = [
            (g, domain.caption_entities(entities, (g,))[0][0])
            for g in domain.caption_groups
            if domain.caption_entities(entities, (g,))
        ]
        if groups:
            class_groups[cls] = groups

    if user_input is not None:
        section = dict(options)
        section[OPTION_TOOLBAR_ENABLED] = bool(user_input.get("toolbar_enabled", True))
        section[OPTION_EDITOR_URL] = (
            user_input.get("editor_url") or DEFAULT_EDITOR_URL
        ).strip()
        fields = dict(options.get(OPTION_CAPTION_FIELDS) or {})
        for cls in class_groups:
            key = f"{_CAPTION_FIELD_PREFIX}{cls}"
            if key in user_input:
                fields[cls] = list(user_input.get(key) or [])
        section[OPTION_CAPTION_FIELDS] = fields
        persist_floorplan_options(flow.hass, config_entry, section)
        _LOGGER.info("Floorplan Helper options saved")
        return await flow.async_step_main_menu()

    info_text = (
        "🗺️ **Floorplan Helper**\n\n"
        "Compiles the floorplan-studio project into the floorplan card "
        "bundle (merged SVG, CSS, rules YAML). The project is the "
        "single source of truth — marker icon, colours, label, actions "
        "and zone are edited on the marker in studio.\n\n"
        "Place a `ramses-floorplan-actions` card next to the studio "
        "card on the same dashboard view — its buttons drive the "
        "workflow (store, seed, export, update cards) and its "
        "`floors:` config names the drawing SVG per floor, so "
        "different maps can live on different views.\n\n"
        "Below: which values each device class's marker caption shows "
        "(untick all to hide it) — only groups matching a real entity "
        "are listed. Per-marker control stays in studio "
        "(`ramsesCaption`)."
    )

    schema = vol.Schema(
        {
            vol.Optional(
                "toolbar_enabled",
                default=options.get(OPTION_TOOLBAR_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Optional(
                "editor_url",
                default=options.get(OPTION_EDITOR_URL) or DEFAULT_EDITOR_URL,
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=False)),
        }
    )

    # Per-device-class caption selection — which entity values a class
    # shows under its marker. Options are the domain's caption groups
    # filtered to entities that actually exist on that class; the
    # stored selection maps class → group keys ([] = no caption).
    stored_fields = options.get(OPTION_CAPTION_FIELDS) or {}
    for cls, groups in class_groups.items():
        avail_keys = [caption_group_key(g) for g, _eid in groups]
        schema = schema.extend(
            {
                vol.Optional(
                    f"{_CAPTION_FIELD_PREFIX}{cls}",
                    default=[
                        k for k in stored_fields.get(cls, avail_keys) if k in avail_keys
                    ],
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=caption_group_key(g),
                                label=f"{cls}: {caption_group_label(g)} — {eid}",
                            )
                            for g, eid in groups
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )


__all__ = ["async_step_floorplan_helper_config"]
