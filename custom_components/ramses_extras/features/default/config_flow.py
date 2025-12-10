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

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector

# Import using the full path to match test mocking
from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
    SimpleEntityManager,
)

from ...const import AVAILABLE_FEATURES

_LOGGER = logging.getLogger(__name__)


async def _generate_entity_ids_for_combination(
    feature_id: str, device_id: str, hass: Any
) -> list[str]:
    """Generate entity IDs for a specific feature/device combination.

    Args:
        feature_id: Feature identifier
        device_id: Device identifier
        hass: Home Assistant instance

    Returns:
        List of entity IDs for this combination
    """
    entity_ids = []

    # Generate entity IDs based on feature configuration
    if feature_id == "default":
        # Default feature creates absolute humidity sensors for all devices
        entity_ids = [
            f"sensor.indoor_absolute_humidity_{device_id.replace(':', '_')}",
            f"sensor.outdoor_absolute_humidity_{device_id.replace(':', '_')}",
        ]
    else:
        # For other features, try to get entity configurations
        try:
            feature_module = (
                f"custom_components.ramses_extras.features.{feature_id}.const"
            )
            feature_const = __import__(feature_module, fromlist=[""])

            # Get required entities from feature configuration
            required_entities = getattr(
                feature_const, f"{feature_id.upper()}_CONST", {}
            ).get("required_entities", {})

            for entity_type, entity_names in required_entities.items():
                for entity_name in entity_names:
                    # Generate entity ID using standard pattern
                    entity_id = (
                        f"{entity_type}.{entity_name}_{device_id.replace(':', '_')}"
                    )
                    entity_ids.append(entity_id)

        except Exception as e:
            _LOGGER.debug(
                f"Could not get required entities for feature {feature_id}: {e}"
            )

    return entity_ids


async def async_step_default_config(
    flow: Any, user_input: dict[str, Any] | None
) -> Any:
    """Handle configuration for the default feature.

    This function is called from the central options flow entrypoint
    (generic_step_feature_config) and uses the central flow instance
    to access helpers and show the form.
    """

    feature_id = "default"
    feature_config = AVAILABLE_FEATURES.get(feature_id, {})

    # Get devices for this feature using the central helpers
    devices = flow._get_all_devices()  # noqa: SLF001
    helper = flow._get_config_flow_helper()  # noqa: SLF001

    _LOGGER.info(f"Using step config flow for {feature_id}")
    # CRITICAL FIX: Restore matrix state so we can see which devices
    #  are currently enabled
    matrix_state = flow._config_entry.data.get("device_feature_matrix", {})
    if matrix_state:
        helper.restore_matrix_state(matrix_state)
        _LOGGER.info(
            f"Restored matrix state in config flow with {len(matrix_state)} devices"
        )
    else:
        _LOGGER.info(
            "No matrix state found in config entry, starting with empty matrix"
        )
    _LOGGER.info(f"matrix state: {matrix_state}")
    # save the matrix state to be used for comparison. Essential !!!
    # use deepcopy, or helper.set_enabled_devices_for_feature will modify flow
    flow._old_matrix_state = deepcopy(matrix_state)

    filtered_devices = helper.get_devices_for_feature_selection(feature_config, devices)
    _LOGGER.debug(f"Filtered devices: {filtered_devices}")
    current_enabled = helper.get_enabled_devices_for_feature(feature_id)
    _LOGGER.debug(f"Current enabled devices: {current_enabled}")

    if user_input is not None:
        _LOGGER.debug("User submitted the form - process the device selections")
        # User submitted the form - process the device selections
        selected_device_ids = user_input.get("enabled_devices", [])

        # Store the new device configuration for this feature
        helper.set_enabled_devices_for_feature(feature_id, selected_device_ids)

        temp_matrix_state = helper.get_feature_device_matrix_state()
        if not temp_matrix_state:
            temp_matrix_state = {}

        # Store the matrix state from the config entry as the old state
        # flow._old_matrix_state = matrix_state  # This is the line we need to add
        flow._temp_matrix_state = temp_matrix_state
        flow._selected_feature = feature_id

        # Log the matrix state for debugging
        _LOGGER.debug(f"flow.temp matrix state: {flow._temp_matrix_state}")
        _LOGGER.debug(f"flow.old_matrix_state: {flow._old_matrix_state}")

        # # Calculate entity changes using SimpleEntityManager
        # entity_manager = SimpleEntityManager(flow.hass)

        # # Calculate entities to create/remove based on matrix state changes
        # old_matrix_state = flow._old_matrix_state
        # new_matrix_state = temp_matrix_state

        # (
        #     flow._matrix_entities_to_create,
        #     flow._matrix_entities_to_remove,
        # ) = await entity_manager.calculate_entity_changes(
        #     old_matrix_state, new_matrix_state
        # )

        _LOGGER.info(f"📝 Entities to create: {len(flow._matrix_entities_to_create)}")
        _LOGGER.info(f"🗑️ Entities to remove: {len(flow._matrix_entities_to_remove)}")

        # Route through the matrix-based confirm step so changes are summarized
        return await flow._show_matrix_based_confirmation()

    _LOGGER.debug("build device options, we get here when there is no user input")
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
