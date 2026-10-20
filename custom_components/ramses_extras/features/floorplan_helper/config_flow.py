"""Floorplan Helper feature options flow.

Lets users edit the floorplan mapping inside ramses_extras: SVG mode,
custom SVG path, and icon overrides — then regenerate via
``ramses_extras.floorplan_export``.

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
    FLOORPLAN_ICONS,
    OPTION_CAPTION_OVERRIDES,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_EDITOR_URL,
    OPTION_ICON_OVERRIDES,
    OPTION_PLANNER_URL,
    OPTION_SVG_MODE,
    OPTION_TOOLBAR_ENABLED,
    SVG_MODE_CUSTOM,
    SVG_MODE_GENERATED,
)
from .mapping import get_floorplan_options, persist_floorplan_options

_LOGGER = logging.getLogger(__name__)

_VALID_ICON_KEYS = sorted(FLOORPLAN_ICONS)


def _parse_icon_overrides(text: str) -> dict[str, str]:
    """Parse ``KEY=icon`` lines into an overrides dict.

    Invalid lines are skipped; unknown icon keys are dropped.
    """
    overrides: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value in _VALID_ICON_KEYS:
            overrides[key] = value
    return overrides


def _format_icon_overrides(overrides: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(overrides.items()))


def _parse_caption_overrides(text: str) -> dict[str, list[str]]:
    """Parse ``KEY=entity[,entity|suffix]`` lines into an overrides dict.

    KEY is a ramses device id (``32:153289``), a device class (``FAN``,
    ``CO2``…), or a primary entity_id — same precedence as icon
    overrides. An empty entity list disables the caption for that key.
    """
    overrides: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            overrides[key] = [e.strip() for e in value.split(",") if e.strip()]
    return overrides


def _format_caption_overrides(overrides: dict[str, list[str]]) -> str:
    return "\n".join(f"{k}={','.join(v)}" for k, v in sorted(overrides.items()))


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
        section[OPTION_ICON_OVERRIDES] = _parse_icon_overrides(
            user_input.get("icon_overrides") or ""
        )
        section[OPTION_CAPTION_OVERRIDES] = _parse_caption_overrides(
            user_input.get("caption_overrides") or ""
        )
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

    overrides = options.get(OPTION_ICON_OVERRIDES, {})
    info_text = (
        "🗺️ **Floorplan Helper**\n\n"
        "Generates the ha-floorplan bundle (icons, CSS, rules YAML) from "
        "your RAMSES system. After changing settings, run the service "
        "`ramses_extras.floorplan_export` to regenerate.\n\n"
        f"- SVG mode: `{options.get(OPTION_SVG_MODE)}`\n"
        f"- Element bindings stored: "
        f"{len(options.get('element_bindings', {}))}\n"
        f"- Icon overrides: {len(overrides)}\n\n"
        "Icon overrides: one `TARGET=icon` per line, where TARGET is a "
        "device class (FAN, TRV, CTL, HGI, DHW...) or an entity_id. "
        f"Available icons: {', '.join(_VALID_ICON_KEYS)}\n\n"
        "Caption overrides: what a marker's state text shows — one "
        "`TARGET=entity_id[,entity_id|suffix]` per line, same TARGET "
        "rules (device id like `32:153289`, device class, or entity_id). "
        "Listed entity states join with ` / `, e.g. "
        "`32:153289=sensor.32_153289_indoor_temp|°,"
        "sensor.32_153289_outdoor_temp|°`. An empty value hides the "
        "caption.\n\n"
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
                "icon_overrides",
                default=_format_icon_overrides(overrides),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Optional(
                "caption_overrides",
                default=_format_caption_overrides(
                    options.get(OPTION_CAPTION_OVERRIDES, {})
                ),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
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
