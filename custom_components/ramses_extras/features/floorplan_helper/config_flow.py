"""Floorplan Helper feature options flow.

Lets users pick the floorplan SVG mode and toolbar tool URLs inside
ramses_extras — then regenerate via ``ramses_extras.floorplan_export``.

Per-marker settings (icon, colours, label, state text, tap/hold/double
actions, zone) are **not** configured here — they live on the marker in
the floorplan-studio project, which is the single source of truth.
Stored ``icon_overrides``/``caption_overrides``/``marker_style_overrides``
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
    FEATURE_ID,
    OPTION_CAPTION_FIELDS,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_EDITOR_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    SVG_MODE_CUSTOM,
    SVG_MODE_GENERATED,
)
from .domains import caption_group_key, caption_group_label, get_domain
from .mapping import get_floorplan_options, persist_floorplan_options

_LOGGER = logging.getLogger(__name__)

_CAPTION_FIELD_PREFIX = "caption_fields__"


def _caption_classes(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Device classes present in the model → their domain (ordered)."""
    classes: dict[str, Any] = {}
    for dev in devices or []:
        cls = str(dev.get("device_class") or "")
        if cls:
            classes.setdefault(cls, get_domain(cls))
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

    if user_input is not None:
        section = dict(options)
        section[OPTION_SVG_MODE] = user_input.get("svg_mode", SVG_MODE_GENERATED)
        section[OPTION_CUSTOM_SVG_PATH] = (
            user_input.get("custom_svg_path") or ""
        ).strip()
        section[OPTION_TOOLBAR_ENABLED] = bool(user_input.get("toolbar_enabled", True))
        section[OPTION_EDITOR_URL] = (
            user_input.get("editor_url") or DEFAULT_EDITOR_URL
        ).strip()
        fields = dict(options.get(OPTION_CAPTION_FIELDS) or {})
        for cls in classes:
            key = f"{_CAPTION_FIELD_PREFIX}{cls}"
            if key in user_input:
                fields[cls] = list(user_input.get(key) or [])
        section[OPTION_CAPTION_FIELDS] = fields
        persist_floorplan_options(flow.hass, config_entry, section)
        _LOGGER.info("Floorplan Helper options saved")
        return await flow.async_step_main_menu()

    info_text = (
        "🗺️ **Floorplan Helper**\n\n"
        "Generates the ha-floorplan bundle (icons, CSS, rules YAML) from "
        "your RAMSES system. After changing settings, run the service "
        "`ramses_extras.floorplan_export` to regenerate.\n\n"
        f"- SVG mode: `{options.get(OPTION_SVG_MODE)}`\n"
        f"- Element bindings stored: "
        f"{len(options.get('element_bindings', {}))}\n\n"
        "Per-marker settings (icon, colours, label, state text, "
        "tap/hold/double-tap actions, zone) are edited **in studio** on "
        "the marker itself — the project is the single source of truth. "
        "Our extras ride in the project too (`ramsesZone`, "
        "`ramsesCaption`, `style.glyph/ring/opacity`); any older "
        "stored overrides migrate into the project on the next export "
        "and stay as fallback only for elements without a marker.\n\n"
        "`editor_url` is the dashboard view holding the "
        "floorplan-studio card (default `/floorplan-studio`) — the "
        "in-SVG `⛓` toolbar button and the actions card's 'Open studio' "
        "navigate there. Point it at another view path or a vendored "
        "copy under `/local/...` if yours lives elsewhere.\n\n"
        "Below: per device *class*, pick which values the marker caption "
        "shows (untick all to hide it). Per-marker caption control stays "
        "in studio — `ramsesCaption` and the 'Show state' toggle win "
        "over this class default."
    )

    schema = vol.Schema(
        {
            vol.Required(
                "svg_mode",
                default=options.get(OPTION_SVG_MODE, SVG_MODE_GENERATED),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=SVG_MODE_GENERATED,
                            label="Generated elements SVG (default plan)",
                        ),
                        selector.SelectOptionDict(
                            value=SVG_MODE_CUSTOM,
                            label="Custom SVG (my own drawing)",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(
                "custom_svg_path",
                default=options.get(OPTION_CUSTOM_SVG_PATH, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(
                    multiline=False,
                )
            ),
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
    # shows under its marker. Options are the domain's caption groups;
    # the stored selection maps class → group keys ([] = no caption).
    stored_fields = options.get(OPTION_CAPTION_FIELDS) or {}
    for cls, domain in classes.items():
        if not domain.caption_groups:
            continue
        field = f"{_CAPTION_FIELD_PREFIX}{cls}"
        schema = schema.extend(
            {
                vol.Optional(
                    field,
                    default=stored_fields.get(
                        cls, [caption_group_key(g) for g in domain.caption_groups]
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=caption_group_key(g),
                                label=f"{cls}: {caption_group_label(g)}",
                            )
                            for g in domain.caption_groups
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
