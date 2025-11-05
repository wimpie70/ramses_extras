"""Dehumidify control services for Ramses Extras integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_set_dehumidifying_active(
    hass: HomeAssistant,
    entity_id: str,
    active: bool,
) -> None:
    """Set the state of a dehumidifying active binary sensor.

    Args:
        entity_id: The binary sensor entity ID
        active: Whether the dehumidifying should be active
    """
    _LOGGER.info(f"Setting dehumidifying active for {entity_id} to {active}")

    # Update the state directly (no entity validation needed)
    new_state = "on" if active else "off"
    hass.states.async_set(entity_id, new_state, {"source": "ramses_extras_service"})

    _LOGGER.info(
        f"Successfully set dehumidifying active for {entity_id} to {new_state}"
    )


def register_dehumidify_services(hass: HomeAssistant) -> None:
    """Register dehumidify control services."""

    # Register the set_dehumidifying_active service
    async def handle_set_dehumidifying_active(call: ServiceCall) -> None:
        """Handle set_dehumidifying_active service call."""
        entity_id = call.data["entity_id"]
        active = call.data["active"]

        await async_set_dehumidifying_active(
            hass,
            entity_id,
            active,
        )

    # Register the service
    hass.services.async_register(
        DOMAIN,
        "set_dehumidifying_active",
        handle_set_dehumidifying_active,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): str,
                vol.Required("active"): bool,
            }
        ),
    )

    _LOGGER.info("Registered set_dehumidifying_active service")
