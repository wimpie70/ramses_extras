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
    FEATURE_ID,
    FLOORPLAN_ICONS,
    OPTION_CUSTOM_SVG_PATH,
    OPTION_ICON_OVERRIDES,
    OPTION_SVG_MODE,
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
        f"Available icons: {', '.join(_VALID_ICON_KEYS)}"
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
        }
    )

    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )


__all__ = ["async_step_floorplan_helper_config"]
