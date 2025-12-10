"""Humidity Control Sensor Platform.

This module provides Home Assistant sensor platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSensorEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control sensor platform."""
    from custom_components.ramses_extras.framework.helpers import (
        platform,
    )

    await platform.PlatformSetup.async_create_and_add_platform_entities(
        platform="sensor",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs={},  # Not used for sensors
        entity_factory=create_humidity_sensor,
    )


async def create_humidity_sensor(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasSensorEntity]:
    """Create humidity sensor for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of sensor entities
    """
    # Import entity configurations from management layer
    from ..const import HUMIDITY_CONTROL_CONST
    from ..entities import HumidityEntities

    sensor: list[Any] = []

    # Note: Absolute humidity sensors are now created by the default feature
    # This function is kept for compatibility but no longer creates sensors
    _LOGGER.debug(
        f"Absolute humidity sensors for device {device_id} are now "
        f"created by default feature"
    )

    return sensor


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("sensor", "humidity_control", async_setup_entry)

__all__ = [
    "async_setup_entry",
    "create_humidity_sensor",
]
