# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Service definitions and handlers for Hello World Switch Card feature.

This module provides service definitions, handlers, and validation for the Hello World
feature, including toggle switch, get switch state, and bulk toggle services.

:platform: Home Assistant
:feature: Hello World Services
:components: Service Registration, Service Handlers, Validation
:service_types: Toggle Switch, Get State, Bulk Operations
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from custom_components.ramses_extras.const import DOMAIN as INTEGRATION_DOMAIN
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

from .const import HELLO_WORLD_BINARY_SENSOR_CONFIGS, HELLO_WORLD_SWITCH_CONFIGS

_LOGGER = logging.getLogger(__name__)


def _service_exists(hass: HomeAssistant, domain: str, service: str) -> bool:
    services = hass.services
    if hasattr(services, "async_service_exists"):
        return bool(services.async_service_exists(domain, service))
    return bool(services.has_service(domain, service))


# Service definitions
SERVICE_TOGGLE_SWITCH = "hello_world_toggle_switch"
SERVICE_GET_SWITCH_STATE = "hello_world_get_switch_state"
SERVICE_BULK_TOGGLE = "hello_world_bulk_toggle"

SERVICE_SCHEMA_TOGGLE_SWITCH = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("entity_id"): cv.string,
        vol.Required("state"): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)

SERVICE_SCHEMA_GET_SWITCH_STATE = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("entity_id"): cv.string,
    },
    extra=vol.PREVENT_EXTRA,
)

SERVICE_SCHEMA_BULK_TOGGLE = vol.Schema(
    {
        vol.Required("entity_ids"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("state"): cv.boolean,
    },
    extra=vol.PREVENT_EXTRA,
)


async def async_setup_services(
    hass: HomeAssistant, config_entry: Any | None = None
) -> None:
    """Set up Hello World services.

    This function registers all Hello World feature services with Home Assistant.
    It creates service handlers for toggle switch, get switch state, and bulk toggle
    operations.

    Services are only registered if they don't already exist to avoid conflicts.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry for the integration
    """
    _LOGGER.info("Setting up Hello World services")

    # Register toggle switch service
    if not _service_exists(hass, INTEGRATION_DOMAIN, SERVICE_TOGGLE_SWITCH):
        hass.services.async_register(
            INTEGRATION_DOMAIN,
            SERVICE_TOGGLE_SWITCH,
            partial(async_toggle_switch_service, hass),
            schema=SERVICE_SCHEMA_TOGGLE_SWITCH,
        )
        _LOGGER.info(
            "Registered service: %s.%s",
            INTEGRATION_DOMAIN,
            SERVICE_TOGGLE_SWITCH,
        )

    # Register get switch state service
    if not _service_exists(hass, INTEGRATION_DOMAIN, SERVICE_GET_SWITCH_STATE):
        hass.services.async_register(
            INTEGRATION_DOMAIN,
            SERVICE_GET_SWITCH_STATE,
            partial(async_get_switch_state_service, hass),
            schema=SERVICE_SCHEMA_GET_SWITCH_STATE,
        )
        _LOGGER.info(
            "Registered service: %s.%s",
            INTEGRATION_DOMAIN,
            SERVICE_GET_SWITCH_STATE,
        )

    # Register bulk toggle service
    if not _service_exists(hass, INTEGRATION_DOMAIN, SERVICE_BULK_TOGGLE):
        hass.services.async_register(
            INTEGRATION_DOMAIN,
            SERVICE_BULK_TOGGLE,
            partial(async_bulk_toggle_service, hass),
            schema=SERVICE_SCHEMA_BULK_TOGGLE,
        )
        _LOGGER.info(
            "Registered service: %s.%s",
            INTEGRATION_DOMAIN,
            SERVICE_BULK_TOGGLE,
        )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Hello World services."""
    _LOGGER.info("Unloading Hello World services")

    # Unregister services
    services_to_remove = [
        SERVICE_TOGGLE_SWITCH,
        SERVICE_GET_SWITCH_STATE,
        SERVICE_BULK_TOGGLE,
    ]

    for service_name in services_to_remove:
        if _service_exists(hass, INTEGRATION_DOMAIN, service_name):
            hass.services.async_remove(INTEGRATION_DOMAIN, service_name)
            _LOGGER.info(
                "Unregistered service: %s.%s",
                INTEGRATION_DOMAIN,
                service_name,
            )


async def async_toggle_switch_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle toggle switch service call."""
    device_id = call.data.get("device_id")
    state = call.data.get("state")
    entity_id = call.data.get("entity_id")

    _LOGGER.info(
        "Toggle switch service called - device_id: %s, entity_id: %s, state: %s",
        device_id,
        entity_id,
        state,
    )

    try:
        # If entity_id provided, extract device_id from it using EntityHelpers
        if entity_id and not device_id:
            parsed = EntityHelpers.parse_entity_id(entity_id)
            if parsed:
                device_id = parsed[2]  # device_id is the third element in the tuple

        if not device_id:
            _LOGGER.error("No device_id provided or found")
            return

        # Generate entity ID using the template from const
        switch_entity_id = EntityHelpers.generate_entity_name_from_template(
            "switch",
            HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]["entity_template"],
            device_id=device_id.replace(":", "_"),
        )

        # State must be explicitly provided to avoid synchronization issues
        if state is None:
            _LOGGER.error("State parameter is required for toggle_switch service")
            return

        # Toggle the switch entity
        if state:
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch_entity_id}
            )
        else:
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": switch_entity_id}
            )

        _LOGGER.info(
            "Switch %s set to %s via service",
            device_id,
            "ON" if state else "OFF",
        )

    except Exception as err:
        _LOGGER.error("Failed to toggle switch via service: %s", err)


async def async_get_switch_state_service(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Handle get switch state service call."""
    device_id = call.data.get("device_id")
    entity_id = call.data.get("entity_id")

    _LOGGER.info(
        "Get switch state service called - device_id: %s, entity_id: %s",
        device_id,
        entity_id,
    )

    try:
        # If entity_id provided, extract device_id from it using EntityHelpers
        if entity_id and not device_id:
            parsed = EntityHelpers.parse_entity_id(entity_id)
            if parsed:
                device_id = parsed[2]  # device_id is the third element in the tuple

        if not device_id:
            _LOGGER.error("No device_id provided or found")
            return

        # Generate entity IDs using the templates from const
        switch_entity_id = EntityHelpers.generate_entity_name_from_template(
            "switch",
            HELLO_WORLD_SWITCH_CONFIGS["hello_world_switch"]["entity_template"],
            device_id=device_id.replace(":", "_"),
        )
        binary_sensor_entity_id = EntityHelpers.generate_entity_name_from_template(
            "binary_sensor",
            HELLO_WORLD_BINARY_SENSOR_CONFIGS["hello_world_status"]["entity_template"],
            device_id=device_id.replace(":", "_"),
        )

        switch_state = hass.states.get(switch_entity_id)
        binary_sensor_state = hass.states.get(binary_sensor_entity_id)

        switch_is_on = switch_state.state == "on" if switch_state else False
        binary_sensor_is_on = (
            binary_sensor_state.state == "on" if binary_sensor_state else False
        )

        _LOGGER.info(
            "Switch states for %s - switch: %s, binary_sensor: %s",
            device_id,
            switch_is_on,
            binary_sensor_is_on,
        )

    except Exception as err:
        _LOGGER.error("Failed to get switch state via service: %s", err)


async def async_bulk_toggle_service(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle bulk toggle service call."""
    entity_ids = call.data.get("entity_ids", [])
    state = call.data.get("state")

    _LOGGER.info(
        "Bulk toggle service called - entity_ids: %s, state: %s",
        entity_ids,
        state,
    )

    if not entity_ids:
        _LOGGER.warning("No entity_ids provided for bulk toggle")
        return

    try:
        # Process each entity_id using framework's entity services
        success_count = 0
        error_count = 0

        for entity_id in entity_ids:
            try:
                # Validate entity_id format using EntityHelpers
                parsed = EntityHelpers.parse_entity_id(entity_id)
                if parsed and "hello_world_switch" in parsed[1]:
                    # Use Home Assistant's switch service directly
                    if state:
                        await hass.services.async_call(
                            "switch", "turn_on", {"entity_id": entity_id}
                        )
                    else:
                        await hass.services.async_call(
                            "switch", "turn_off", {"entity_id": entity_id}
                        )

                    success_count += 1
                    _LOGGER.debug("Successfully toggled %s", entity_id)

                else:
                    _LOGGER.warning("Invalid entity_id format: %s", entity_id)
                    error_count += 1

            except Exception as err:
                _LOGGER.error("Failed to toggle %s: %s", entity_id, err)
                error_count += 1

        _LOGGER.info(
            "Bulk toggle completed - success: %d, errors: %d",
            success_count,
            error_count,
        )

    except Exception as err:
        _LOGGER.error("Failed to execute bulk toggle service: %s", err)


def get_service_info() -> dict[str, dict]:
    """Get information about available services.

    :return: Dictionary containing service information
    """
    return {
        SERVICE_TOGGLE_SWITCH: {
            "name": "Toggle Switch",
            "description": "Toggle a Hello World switch on or off",
            "domain": INTEGRATION_DOMAIN,
            "parameters": {
                "device_id": "Ramses RF device ID (e.g., '32:153289')",
                "state": "True for ON, False for OFF (required)",
                "entity_id": "Switch entity ID (alternative to device_id)",
            },
        },
        SERVICE_GET_SWITCH_STATE: {
            "name": "Get Switch State",
            "description": "Get current state of a Hello World switch",
            "domain": INTEGRATION_DOMAIN,
            "parameters": {
                "device_id": "Ramses RF device ID (e.g., '32:153289')",
                "entity_id": "Switch entity ID (alternative to device_id)",
            },
        },
        SERVICE_BULK_TOGGLE: {
            "name": "Bulk Toggle",
            "description": "Toggle multiple Hello World switches simultaneously",
            "domain": INTEGRATION_DOMAIN,
            "parameters": {
                "entity_ids": "List of switch entity IDs to toggle",
                "state": "True for ON, False for OFF",
            },
        },
    }


def get_registered_services(hass: HomeAssistant) -> list[str]:
    """Get list of registered Hello World services.

    :param hass: Home Assistant instance
    :return: List of registered service names
    """
    services = []
    service_domains = hass.services.async_services()

    if INTEGRATION_DOMAIN in service_domains:
        services.extend(service_domains[INTEGRATION_DOMAIN].keys())

    return services


def validate_service_call(service_name: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Validate a service call before execution.

    :param service_name: Name of the service being called
    :param data: Service call data
    :return: Tuple of (is_valid, error_message)
    """
    if service_name == SERVICE_TOGGLE_SWITCH:
        # Check that state is provided (required to avoid sync issues)
        if "state" not in data:
            return False, "State parameter is required"

        # Check that either device_id or entity_id is provided
        if not data.get("device_id") and not data.get("entity_id"):
            return False, "Either device_id or entity_id must be provided"

        # Validate device_id format if provided
        device_id = data.get("device_id")
        if device_id and ":" not in device_id:
            return False, "Invalid device_id format (should contain ':')"

        return True, ""

    if service_name == SERVICE_GET_SWITCH_STATE:
        # Similar validation as toggle service
        if not data.get("device_id") and not data.get("entity_id"):
            return False, "Either device_id or entity_id must be provided"

        return True, ""

    if service_name == SERVICE_BULK_TOGGLE:
        # Check that entity_ids is provided and is a list
        entity_ids = data.get("entity_ids")
        if not entity_ids:
            return False, "entity_ids must be provided"

        if not isinstance(entity_ids, list):
            return False, "entity_ids must be a list"

        if not entity_ids:
            return False, "entity_ids cannot be empty"

        return True, ""

    return False, f"Unknown service: {service_name}"


__all__ = [
    "async_setup_services",
    "async_unload_services",
    "SERVICE_TOGGLE_SWITCH",
    "SERVICE_GET_SWITCH_STATE",
    "SERVICE_BULK_TOGGLE",
    "get_service_info",
    "get_registered_services",
    "validate_service_call",
]
