"""Entity Factory for Hello World Card - creates entities for selected devices only."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .platforms.binary_sensor import create_hello_world_binary_sensor
from .platforms.switch import create_hello_world_switch

_LOGGER = logging.getLogger(__name__)


async def create_hello_world_entities_for_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    feature_id: str,
    device_id: str,
) -> list[Entity]:
    """Create hello world card entities for a specific device.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry
        feature_id: Feature identifier (should be "hello_world_card")
        device_id: Device ID to create entities for

    Returns:
        List of created entities
    """
    _LOGGER.info(f"🔧 Creating Hello World Card entities for device: {device_id}")

    created_entities = []

    try:
        # Create switch entity
        hello_switches = await create_hello_world_switch(hass, device_id, config_entry)
        if hello_switches:
            created_entities.extend(hello_switches)
            _LOGGER.debug(f"✅ Created hello world switch for {device_id}")

        # Create binary sensor entity
        hello_binary_sensors = await create_hello_world_binary_sensor(
            hass, device_id, config_entry
        )
        if hello_binary_sensors:
            created_entities.extend(hello_binary_sensors)
            _LOGGER.debug(f"✅ Created hello world binary sensor for {device_id}")

        _LOGGER.info(
            f"✅ Created {len(created_entities)} Hello World Card entities for "
            f"{device_id}"
        )
        return created_entities

    except Exception as e:
        _LOGGER.error(
            f"❌ Failed to create Hello World Card entities for {device_id}: {e}"
        )
        # Clean up any partially created entities
        for entity in created_entities:
            try:
                await entity.async_remove()
            except Exception:
                pass
        return []


async def hello_world_card_creation_callback(
    feature_id: str, device_id: str, created_entities: list[Entity]
) -> None:
    """Callback after Hello World Card entities are created.

    Args:
        feature_id: Feature identifier
        device_id: Device ID
        created_entities: List of created entities
    """
    _LOGGER.info(
        f"🎯 Hello World Card entities created for {device_id}: "
        f"{len(created_entities)} entities"
    )

    # Hello World Card is a template feature, so we can add additional
    # initialization logic here if needed


__all__ = [
    "create_hello_world_entities_for_device",
    "hello_world_card_creation_callback",
]
