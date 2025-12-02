# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Service definitions and handlers for Hello World Switch Card feature."""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Service definitions
SERVICE_TOGGLE_SWITCH = "toggle_switch"
SERVICE_GET_SWITCH_STATE = "get_switch_state"
SERVICE_BULK_TOGGLE = "bulk_toggle"

SERVICE_SCHEMA_TOGGLE_SWITCH = {
    "device_id": "str",
    "state": "bool",
    "entity_id": "str",
}

SERVICE_SCHEMA_GET_SWITCH_STATE = {
    "device_id": "str",
    "entity_id": "str",
}

SERVICE_SCHEMA_BULK_TOGGLE = {
    "entity_ids": ["str"],
    "state": "bool",
}


async def async_setup_services(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Set up Hello World services."""
    _LOGGER.info("Setting up Hello World services")

    # Register toggle switch service
    if not hass.services.async_service_exists(DOMAIN, SERVICE_TOGGLE_SWITCH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TOGGLE_SWITCH,
            async_toggle_switch_service,
            schema=SERVICE_SCHEMA_TOGGLE_SWITCH,
        )
        _LOGGER.info(f"Registered service: {DOMAIN}.{SERVICE_TOGGLE_SWITCH}")

    # Register get switch state service
    if not hass.services.async_service_exists(DOMAIN, SERVICE_GET_SWITCH_STATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_SWITCH_STATE,
            async_get_switch_state_service,
            schema=SERVICE_SCHEMA_GET_SWITCH_STATE,
        )
        _LOGGER.info(f"Registered service: {DOMAIN}.{SERVICE_GET_SWITCH_STATE}")

    # Register bulk toggle service
    if not hass.services.async_service_exists(DOMAIN, SERVICE_BULK_TOGGLE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_BULK_TOGGLE,
            async_bulk_toggle_service,
            schema=SERVICE_SCHEMA_BULK_TOGGLE,
        )
        _LOGGER.info(f"Registered service: {DOMAIN}.{SERVICE_BULK_TOGGLE}")


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
        if hass.services.async_service_exists(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
            _LOGGER.info(f"Unregistered service: {DOMAIN}.{service_name}")


async def async_toggle_switch_service(hass: HomeAssistant, call: Any) -> None:
    """Handle toggle switch service call."""
    device_id = call.data.get("device_id")
    state = call.data.get("state")
    entity_id = call.data.get("entity_id")

    _LOGGER.info(
        f"Toggle switch service called - device_id: {device_id}, "
        f"entity_id: {entity_id}, state: {state}"
    )

    try:
        # Import entities manager here to avoid circular imports
        from .entities import HelloWorldEntities

        # Create entities manager instance
        entities_manager = HelloWorldEntities(hass, None)

        # If entity_id provided, extract device_id from it
        if entity_id and not device_id:
            # Parse entity_id to get device_id
            # Format: switch.hello_world_switch_device_id
            #  (colons replaced with underscores)
            if "hello_world_switch_" in entity_id:
                device_id = entity_id.replace("switch.hello_world_switch_", "").replace(
                    "_", ":"
                )

        if not device_id:
            _LOGGER.error("No device_id provided or found")
            return

        # If state not specified, toggle current state
        if state is None:
            current_state = entities_manager.get_entity_state(
                device_id, "switch", "hello_world_switch"
            )
            state = not current_state

        # Update entity state
        entities_manager.set_entity_state(
            device_id, "switch", "hello_world_switch", state
        )

        _LOGGER.info(
            f"Switch {device_id} set to {'ON' if state else 'OFF'} via service"
        )

        # Fire state change event for real-time updates
        hass.bus.async_fire(
            "hello_world_switch_state_changed",
            {
                "device_id": device_id,
                "state": state,
                "entity_id": f"switch.hello_world_switch_{device_id.replace(':', '_')}",
                "source": "service",
            },
        )

    except Exception as err:
        _LOGGER.error(f"Failed to toggle switch via service: {err}")


async def async_get_switch_state_service(hass: HomeAssistant, call: Any) -> None:
    """Handle get switch state service call."""
    device_id = call.data.get("device_id")
    entity_id = call.data.get("entity_id")

    _LOGGER.info(
        f"Get switch state service called - device_id: {device_id}, "
        f"entity_id: {entity_id}"
    )

    try:
        # Import entities manager here to avoid circular imports
        from .entities import HelloWorldEntities

        # Create entities manager instance
        entities_manager = HelloWorldEntities(hass, None)

        # If entity_id provided, extract device_id from it
        if entity_id and not device_id:
            if "hello_world_switch_" in entity_id:
                device_id = entity_id.replace("switch.hello_world_switch_", "").replace(
                    "_", ":"
                )

        if not device_id:
            _LOGGER.error("No device_id provided or found")
            return

        # Get current states
        switch_state = entities_manager.get_entity_state(
            device_id, "switch", "hello_world_switch"
        )
        binary_sensor_state = entities_manager.get_entity_state(
            device_id, "binary_sensor", "hello_world_status"
        )

        _LOGGER.info(
            f"Switch states for {device_id} - "
            f"switch: {switch_state}, binary_sensor: {binary_sensor_state}"
        )

    except Exception as err:
        _LOGGER.error(f"Failed to get switch state via service: {err}")


async def async_bulk_toggle_service(hass: HomeAssistant, call: Any) -> None:
    """Handle bulk toggle service call."""
    entity_ids = call.data.get("entity_ids", [])
    state = call.data.get("state")

    _LOGGER.info(
        f"Bulk toggle service called - entity_ids: {entity_ids}, state: {state}"
    )

    if not entity_ids:
        _LOGGER.warning("No entity_ids provided for bulk toggle")
        return

    try:
        # Import entities manager here to avoid circular imports
        from .entities import HelloWorldEntities

        # Create entities manager instance
        entities_manager = HelloWorldEntities(hass, None)

        # Process each entity_id
        success_count = 0
        error_count = 0

        for entity_id in entity_ids:
            try:
                # Extract device_id from entity_id
                if "hello_world_switch_" in entity_id:
                    device_id = entity_id.replace(
                        "switch.hello_world_switch_", ""
                    ).replace("_", ":")

                    # Update entity state
                    entities_manager.set_entity_state(
                        device_id, "switch", "hello_world_switch", state
                    )

                    # Fire state change event
                    hass.bus.async_fire(
                        "hello_world_switch_state_changed",
                        {
                            "device_id": device_id,
                            "state": state,
                            "entity_id": entity_id,
                            "source": "bulk_service",
                        },
                    )

                    success_count += 1
                    _LOGGER.debug(f"Successfully toggled {entity_id}")

                else:
                    _LOGGER.warning(f"Invalid entity_id format: {entity_id}")
                    error_count += 1

            except Exception as err:
                _LOGGER.error(f"Failed to toggle {entity_id}: {err}")
                error_count += 1

        _LOGGER.info(
            f"Bulk toggle completed - success: {success_count}, errors: {error_count}"
        )

    except Exception as err:
        _LOGGER.error(f"Failed to execute bulk toggle service: {err}")


def get_service_info() -> dict[str, dict]:
    """Get information about available services.

    Returns:
        Dictionary containing service information
    """
    return {
        SERVICE_TOGGLE_SWITCH: {
            "name": "Toggle Switch",
            "description": "Toggle a Hello World switch on or off",
            "domain": DOMAIN,
            "parameters": {
                "device_id": "Ramses RF device ID (e.g., '32:153289')",
                "state": "True for ON, False for OFF (optional, "
                "toggles if not provided)",
                "entity_id": "Switch entity ID (alternative to device_id)",
            },
        },
        SERVICE_GET_SWITCH_STATE: {
            "name": "Get Switch State",
            "description": "Get current state of a Hello World switch",
            "domain": DOMAIN,
            "parameters": {
                "device_id": "Ramses RF device ID (e.g., '32:153289')",
                "entity_id": "Switch entity ID (alternative to device_id)",
            },
        },
        SERVICE_BULK_TOGGLE: {
            "name": "Bulk Toggle",
            "description": "Toggle multiple Hello World switches simultaneously",
            "domain": DOMAIN,
            "parameters": {
                "entity_ids": "List of switch entity IDs to toggle",
                "state": "True for ON, False for OFF",
            },
        },
    }


def get_registered_services(hass: HomeAssistant) -> list[str]:
    """Get list of registered Hello World services.

    Args:
        hass: Home Assistant instance

    Returns:
        List of registered service names
    """
    services = []
    service_domains = hass.services.async_services()

    if DOMAIN in service_domains:
        services.extend(service_domains[DOMAIN].keys())

    return services


def validate_service_call(service_name: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Validate a service call before execution.

    Args:
        service_name: Name of the service being called
        data: Service call data

    Returns:
        Tuple of (is_valid, error_message)
    """
    if service_name == SERVICE_TOGGLE_SWITCH:
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
