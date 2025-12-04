"""Config flow helpers for the default feature.

This module is intentionally small and feature-centric so it can serve as
an example for other features that want to own their config flow logic
while still integrating with the central options flow.

To add a feature-specific config step for another feature (for example
``hello_world_card``), use this file as a template and:

1. Add or update the feature entry in :mod:`const.AVAILABLE_FEATURES`:
   - Set ``feature_module`` to ``"features.<feature_id>"``.
   - Set ``has_device_config`` to ``True`` so it appears as a dynamic
     item in the main options menu.
   - Configure ``allowed_device_slugs`` to control which devices are
     selectable (for example ``["FAN"]``, ``["REM"]`` or ``["*"]``).
2. In :mod:`config_flow`, add an entrypoint method
   ``async_step_feature_<feature_id>`` that imports the feature's
   :mod:`config_flow` module and delegates to a helper similar to
   :func:`async_step_default_config` in this file.
3. Add translations for the menu item and step:
   - Root file ``translations/en.json``:
     add ``"feature_<feature_id>": "Feature:"`` under
     ``options.step.main_menu.menu_options`` (and equivalents in
     other languages).
   - Feature file
     ``features/<feature_id>/translations/en.json``:
     add a ``config.step.feature_<feature_id>`` block with
     ``title``/``description`` for the feature-specific texts.
4. Ensure the feature is enabled (via ``default_enabled`` or the
   "Enable/Disable Features" options step) so that it actually shows up
   in the main menu.

This keeps the Home Assistant flow wiring centralized while allowing
each feature to own its configuration logic and translations.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

from ...const import AVAILABLE_FEATURES


async def async_step_default_config(
    flow: Any, user_input: dict[str, Any] | None
) -> Any:
    """Handle configuration for the default feature.

    This function is called from the central options flow entrypoint
    (async_step_feature_default) and uses the central flow instance
    to access helpers and show the form.
    """

    feature_id = "default"
    feature_config = AVAILABLE_FEATURES.get(feature_id, {})

    # Get devices for this feature using the central helpers
    devices = flow._get_all_devices()  # noqa: SLF001
    helper = flow._get_config_flow_helper()  # noqa: SLF001
    filtered_devices = helper.get_devices_for_feature_selection(feature_config, devices)

    # Get current enabled devices for this feature
    current_enabled = helper.get_enabled_devices_for_feature(feature_id)

    if user_input is not None:
        # User submitted the form - process the device selections
        selected_device_ids = user_input.get("enabled_devices", [])

        # Store the new device configuration for this feature
        helper.set_enabled_devices_for_feature(feature_id, selected_device_ids)

        # Return to main menu after saving
        return flow.async_step_main_menu()

    # Build device options (value = device_id, label = human readable name)
    device_options = [
        selector.SelectOptionDict(
            value=device_id,
            label=flow._get_device_label(device),  # noqa: SLF001
        )
        for device in filtered_devices
        if (device_id := flow._extract_device_id(device))  # noqa: SLF001
    ]

    # Create schema for device selection
    # Use LIST mode so the UI renders as a list of checkboxes instead of
    # a dropdown with multi-select chips.
    schema = vol.Schema(
        {
            vol.Required(
                "enabled_devices", default=current_enabled
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=device_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
    )

    feature_name = feature_config.get("name", feature_id)
    info_text = f"🎛️ **{feature_name} Configuration**\n\n"
    info_text += f"Select devices to enable {feature_name} for:\n"

    # Reuse the generic "feature_config" step translations from the
    # root translations file; the detailed text comes from info_text.
    return flow.async_show_form(
        step_id="feature_config",
        data_schema=schema,
        description_placeholders={"info": info_text},
    )
