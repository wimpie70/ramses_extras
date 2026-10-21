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
    DEFAULT_PLANNER_URL,
    FEATURE_ID,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_EDITOR_URL,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    SVG_MODE_CUSTOM,
    SVG_MODE_GENERATED,
)
from .mapping import get_floorplan_options, persist_floorplan_options

_LOGGER = logging.getLogger(__name__)


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
        section[OPTION_PLANNER_URL] = (
            user_input.get("planner_url") or DEFAULT_PLANNER_URL
        ).strip()
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
        "Tool URLs open from the in-SVG toolbar buttons. Point them at "
        "vendored copies or iframe panel paths (`/...` navigates inside "
        "HA instead of a new tab)."
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
            vol.Optional(
                "planner_url",
                default=options.get(OPTION_PLANNER_URL) or DEFAULT_PLANNER_URL,
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=False)),
        }
    )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )


__all__ = ["async_step_floorplan_helper_config"]
