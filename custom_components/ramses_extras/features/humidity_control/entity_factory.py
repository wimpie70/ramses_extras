"""Entity Factory for Humidity Control - creates entities for selected devices only."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from .automation import HumidityAutomationManager
from .entities import HumidityEntities
from .platforms.binary_sensor import create_humidity_control_binary_sensor
from .platforms.number import create_humidity_number
from .platforms.sensor import create_humidity_sensor
from .platforms.switch import create_humidity_switch

_LOGGER = logging.getLogger(__name__)


async def create_humidity_entities_for_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    feature_id: str,
    device_id: str,
) -> list[Entity]:
    """Create humidity control entities for a specific device.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry
        feature_id: Feature identifier (should be "humidity_control")
        device_id: Device ID to create entities for

    Returns:
        List of created entities
    """
    _LOGGER.info(f"🔧 Creating humidity control entities for device: {device_id}")

    created_entities = []

    try:
        # Create switch entities
        dehumidify_entities = await create_humidity_switch(
            hass, device_id, config_entry
        )
        if dehumidify_entities:
            created_entities.extend(dehumidify_entities)
            _LOGGER.debug(f"✅ Created dehumidify switch for {device_id}")

        # Create number entities
        humidity_min_entities = await create_humidity_number(
            hass, device_id, config_entry
        )
        if humidity_min_entities:
            created_entities.extend(humidity_min_entities)
            _LOGGER.debug(f"✅ Created humidity minimum number for {device_id}")

        humidity_max_entities = await create_humidity_number(
            hass, device_id, config_entry
        )
        if humidity_max_entities:
            created_entities.extend(humidity_max_entities)
            _LOGGER.debug(f"✅ Created humidity maximum number for {device_id}")

        humidity_offset_entities = await create_humidity_number(
            hass, device_id, config_entry
        )
        if humidity_offset_entities:
            created_entities.extend(humidity_offset_entities)
            _LOGGER.debug(f"✅ Created humidity offset number for {device_id}")

        # Create binary sensor entities
        dehumidifying_active_entities = await create_humidity_control_binary_sensor(
            hass, device_id, config_entry
        )
        if dehumidifying_active_entities:
            created_entities.extend(dehumidifying_active_entities)
            _LOGGER.debug(
                f"✅ Created dehumidifying active binary sensor for {device_id}"
            )

        # Get the device object to apply brand-specific logic
        device_object = await _get_device_object(hass, device_id)
        if device_object:
            # Apply brand-specific entities
            brand_entities = await _create_brand_specific_entities(
                hass, device_object, device_id
            )
            created_entities.extend(brand_entities)

        _LOGGER.info(
            f"✅ Created {len(created_entities)} humidity entities for {device_id}"
        )
        return created_entities

    except Exception as e:
        _LOGGER.error(f"❌ Failed to create humidity entities for {device_id}: {e}")
        # Clean up any partially created entities
        for entity in created_entities:
            try:
                await entity.async_remove()
            except Exception:
                pass
        return []


async def _get_device_object(hass: HomeAssistant, device_id: str) -> Any:
    """Get device object from Ramses broker.

    Args:
        hass: Home Assistant instance
        device_id: Device ID to find

    Returns:
        Device object or None if not found
    """
    try:
        if "ramses_cc" in hass.data:
            broker = hass.data["ramses_cc"]["broker"]
            for device in broker.devices:
                if device.id == device_id:
                    return device
    except Exception as e:
        _LOGGER.debug(f"Could not retrieve device object for {device_id}: {e}")

    return None


async def _create_brand_specific_entities(
    hass: HomeAssistant, device: Any, device_id: str
) -> list[Entity]:
    """Create brand-specific humidity entities based on device model.

    Args:
        hass: Home Assistant instance
        device: Device object
        device_id: Device ID

    Returns:
        List of brand-specific entities
    """
    brand_entities = []
    model = getattr(device, "model", "").lower()

    try:
        # Check for Orcon devices
        if any(pattern in model for pattern in ["orcon", "soler & palau"]):
            brand_entities.extend(await _create_orcon_entities(hass, device_id))

        # Check for Zehnder devices
        elif any(pattern in model for pattern in ["zehnder", "comfoair"]):
            brand_entities.extend(await _create_zehnder_entities(hass, device_id))

    except Exception as e:
        _LOGGER.error(f"❌ Failed to create brand-specific entities: {e}")

    return brand_entities


async def _create_orcon_entities(hass: HomeAssistant, device_id: str) -> list[Entity]:
    """Create Orcon-specific humidity entities.

    Args:
        hass: Home Assistant instance
        device_id: Device ID

    Returns:
        List of Orcon-specific entities
    """
    entities = []

    # Orcon-specific entities
    try:
        # Filter usage sensor
        filter_sensors = await create_humidity_sensor(
            hass, device_id, config_entry=None
        )
        if filter_sensors:
            entities.extend(filter_sensors)

        # Operation hours sensor
        hours_sensors = await create_humidity_sensor(hass, device_id, config_entry=None)
        if hours_sensors:
            entities.extend(hours_sensors)

        _LOGGER.debug(f"✅ Created {len(entities)} Orcon-specific entities")

    except Exception as e:
        _LOGGER.error(f"❌ Failed to create Orcon entities: {e}")

    return entities


async def _create_zehnder_entities(hass: HomeAssistant, device_id: str) -> list[Entity]:
    """Create Zehnder-specific humidity entities.

    Args:
        hass: Home Assistant instance
        device_id: Device ID

    Returns:
        List of Zehnder-specific entities
    """
    entities = []

    # Zehnder-specific entities
    try:
        # Filter usage sensor
        filter_sensors = await create_humidity_sensor(
            hass, device_id, config_entry=None
        )
        if filter_sensors:
            entities.extend(filter_sensors)

        # Operating hours sensor
        hours_sensors = await create_humidity_sensor(hass, device_id, config_entry=None)
        if hours_sensors:
            entities.extend(hours_sensors)

        _LOGGER.debug(f"✅ Created {len(entities)} Zehnder-specific entities")

    except Exception as e:
        _LOGGER.error(f"❌ Failed to create Zehnder entities: {e}")

    return entities


async def humidity_control_creation_callback(
    feature_id: str, device_id: str, created_entities: list[Entity]
) -> None:
    """Callback after humidity control entities are created.

    Args:
        feature_id: Feature identifier
        device_id: Device ID
        created_entities: List of created entities
    """
    _LOGGER.info(
        f"🎯 Humidity control entities created for {device_id}: "
        f"{len(created_entities)} entities"
    )

    # Here we could add logic to start automation for this device
    # or update any feature-specific state


__all__ = [
    "create_humidity_entities_for_device",
    "humidity_control_creation_callback",
]
