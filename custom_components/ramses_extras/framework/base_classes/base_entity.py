"""Base entity class for Ramses Extras framework.

This module provides the foundational base class that all Ramses Extras
entities inherit from. It provides common functionality that is shared
across all features.
"""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from ...const import DOMAIN
from ..helpers.entity.core import EntityHelpers

_LOGGER = logging.getLogger(__name__)


class ExtrasBaseEntity:
    """Base entity class for Ramses Extras entities.

    This base class provides common functionality that all Ramses Extras
    entities inherit, including device ID management, configuration handling,
    and common entity attributes.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        entity_type: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize base entity.

        Args:
            hass: Home Assistant instance
            device_id: Device identifier
            entity_type: Optional entity type (for compatibility with legacy platforms)
            config: Optional entity configuration (for compatibility
             with legacy platforms)
        """
        self.hass = hass
        self.device_id = device_id
        self._device_id = device_id  # Also set with underscore for compatibility
        self._entity_type = entity_type
        self._config = config or {}
        self._attr_name = ""
        self._attr_unique_id = ""

        device_id_str = self._get_device_id_str()
        device_type = None
        if hass is not None and device_id_str:
            try:
                from ..helpers.device.core import find_ramses_device, get_device_type

                device = find_ramses_device(hass, device_id_str)
                if device is not None:
                    device_type = get_device_type(device)
            except Exception:
                device_type = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id_str)},
            name=f"{device_type or 'Ramses'} {device_id_str}".strip(),
            manufacturer="RAMSES",
            model=device_type or "Device",
        )

    def _get_device_id_str(self) -> str:
        device_id = getattr(self, "device_id", None)
        if device_id is None:
            return ""
        if isinstance(device_id, str):
            return device_id

        value = getattr(device_id, "id", None)
        if value is not None:
            return str(value)

        value = getattr(device_id, "device_id", None)
        if value is not None:
            return str(value)

        value = getattr(device_id, "_id", None)
        if value is not None:
            return str(value)

        return str(device_id)

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        if self._attr_unique_id:
            return self._attr_unique_id

        entity_id = getattr(self, "entity_id", None)
        if isinstance(entity_id, str) and "." in entity_id:
            return entity_id.split(".", 1)[1]

        # Base entity instances are used in tests and as mixins. If we don't have an
        # explicit unique_id, an entity_id, or an entity type, return empty.
        # Real Home Assistant entities should set either `_attr_unique_id`,
        # `_entity_type`, or `entity_id`.
        if self._entity_type is None:
            return ""

        device_id = self._get_device_id_str().replace(":", "_")
        entity_type = self._entity_type or "entity"
        return f"{entity_type}_{device_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Attach entities to Ramses Extras devices."""
        return getattr(self, "_attr_device_info", None) or DeviceInfo(
            identifiers={(DOMAIN, self._get_device_id_str())}
        )


class RamsesSensorEntity(ExtrasBaseEntity, SensorEntity):
    """Base sensor entity for Ramses Extras features.

    This class provides the foundation for all Ramses Extras sensor entities,
    handling common sensor functionality and configuration.
    """

    def __init__(
        self,
        device_id: str,
        device_type: str,
        entity_name: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the sensor entity.

        Args:
            device_id: Device identifier (e.g., "32:153289")
            device_type: Device type (e.g., "HvacVentilator")
            entity_name: Entity name from config (e.g., "indoor_absolute_humidity")
            config: Entity configuration dictionary
        """
        # Initialize base entity
        super().__init__(None, device_id, "sensor", config)

        # Set entity attributes
        self._device_id = device_id
        self._device_type = device_type
        self._entity_name = entity_name
        self._config = config

        # Use automatic format detection from EntityHelpers
        try:
            self.entity_id = EntityHelpers.generate_entity_name_from_template(
                "sensor",
                entity_name + "_{device_id}",  # Use existing pattern from feature const
                device_id=device_id,
            )
            self._attr_unique_id = f"{device_id}_{entity_name}"
        except Exception as e:
            _LOGGER.warning(
                f"Entity name generation failed for {entity_name} device "
                f"{device_id}: {e}. "
                "This indicates a configuration issue that needs to be resolved."
            )

        # Set name from config template or use entity_name
        name_template = config.get("name_template", "")
        if name_template and "{device_id}" in name_template:
            self._attr_name = name_template.replace("{device_id}", device_id)
        else:
            self._attr_name = f"{entity_name.replace('_', ' ').title()} {device_id}"

        # Set other sensor attributes from config
        self._attr_entity_category = config.get("entity_category")
        if self._attr_entity_category == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        self._attr_unit_of_measurement = config.get("unit")
        self._attr_icon = config.get("icon")
        self._attr_device_class = config.get("device_class")

        # Initialize state
        self._attr_native_value: float | None = None

    @property
    def state(self) -> Any:
        """Return the state of the sensor."""
        return self._attr_native_value

    async def async_update(self) -> None:
        """Update the sensor state."""
        # This would be implemented by subclasses or through device polling
        # For now, set a placeholder value
        if self._attr_native_value is None:
            self._attr_native_value = 0.0
