"""Dehumidify control services for Ramses Extras integration."""

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)


def register_dehumidify_services(hass: HomeAssistant) -> None:
    """Register dehumidify control services."""

    async def async_set_dehumidifying_active(call: ServiceCall) -> None:
        """Handle set_dehumidifying_active service call."""
        entity_id = call.data["entity_id"]
        active = call.data.get("active", True)

        # Find the binary sensor entity
        entity_registry = hass.helpers.entity_registry.async_get(hass)
        entity = entity_registry.async_get(entity_id)

        if not entity:
            _LOGGER.error(f"Entity {entity_id} not found")
            return

        # Call the appropriate method on the entity
        if active:
            await hass.services.async_call(
                "binary_sensor", "turn_on", {"entity_id": entity_id}, blocking=True
            )
        else:
            await hass.services.async_call(
                "binary_sensor", "turn_off", {"entity_id": entity_id}, blocking=True
            )

        _LOGGER.info(f"Set dehumidifying active for {entity_id} to {active}")

    # Register the service
    hass.services.async_register(
        "ramses_extras",
        "set_dehumidifying_active",
        async_set_dehumidifying_active,
        schema={
            "entity_id": str,
            "active": bool,
        },
    )

    _LOGGER.info("Registered set_dehumidifying_active service")
