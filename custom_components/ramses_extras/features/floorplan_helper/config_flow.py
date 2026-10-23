"""Floorplan Helper feature options flow.

One knob lives here: which plan editor owns the map (``editor`` —
``auto`` resolves to whichever installed editor already holds a plan).
Everything spatial or per-device — marker positions, icon/colours/
label/actions, zone membership, captions — belongs to the editor's
plan or the actions card's own YAML, which is the single source of
truth. Stored ``icon_overrides``/``caption_overrides``/
``marker_style_overrides``/``caption_fields`` options still apply as a
fallback for elements without a marker, and are migrated into the
project on the next export.

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
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import OPTION_EDITOR
from .editors import editor_keys
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
    if user_input is not None:
        options = get_floorplan_options(flow._config_entry)
        options[OPTION_EDITOR] = user_input.get(OPTION_EDITOR) or "auto"
        persist_floorplan_options(flow.hass, flow._config_entry, options)
        _LOGGER.info(
            "Floorplan Helper options saved (editor=%s)", options[OPTION_EDITOR]
        )
        return await flow.async_step_main_menu()

    current = get_floorplan_options(flow._config_entry).get(OPTION_EDITOR, "auto")
    info_text = (
        "🗺️ **Floorplan Helper**\n\n"
        "The editor's plan is the single source of truth — marker "
        "icon, colours, label, actions, zone membership and captions "
        "are edited there or per device in the actions card's "
        "⚙ Zones panel.\n\n"
        "Setup: put the **actions card** and a "
        "**ramses-editor-embed** card (editor: hfs) on one dashboard "
        "view, draw the map in the embedded editor, then **＋ Add "
        "devices** to seed the ramses and _extras markers. Drag them "
        "into rooms; **Sync areas → HA** links rooms to HA areas.\n\n"
        "Two ways to show the map: the editor's own "
        "**hfs-floorplan-card** (2D/2.5D/3D — our overlay adds icons, "
        "colours, captions, zone highlights and taps), or a generated "
        "**floorplan-card** (ha-floorplan) — edits autosave and "
        "matching cards regenerate automatically. **Export ⇒** / "
        "**⇒ Update cards** remain for a first card or after changing "
        "options outside the plan.\n\n"
        "For everything else, see the wiki on GitHub: "
        "https://github.com/wimpie70/ramses_extras/wiki"
    )

    schema = vol.Schema(
        {
            vol.Required(OPTION_EDITOR, default=current): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {
                            "value": "auto",
                            "label": "Auto — whichever installed editor holds the plan",
                        },
                        # NOTE: the tinkersoder "studio" adapter stays in the
                        # code as the reference implementation for future
                        # editors, but is hidden here — upstream development
                        # has stalled and ha-floorplan-studio covers it.
                        # Candidates for removal if upstream stays quiet.
                        # A yaml `editor: studio` still resolves for anyone
                        # with an existing studio plan.
                        {
                            "value": "hfs",
                            "label": "ha-floorplan-studio (integration)",
                        },
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
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
