"""Humidity Control Number Platform.

This module provides Home Assistant number platform integration
for humidity control feature.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasNumberEntity,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)

_LOGGER = logging.getLogger(__name__)


def is_supported_humidity_device(hass: object, device_id: str) -> bool:
    normalized_device_id = device_id.replace("_", ":")
    device = find_ramses_device(hass, normalized_device_id)
    return get_device_type(device) == "HvacVentilator"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up humidity control number platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    # Use the framework's device filtering helper
    filtered_devices = platform.PlatformSetup.get_filtered_devices_for_feature(
        hass, "humidity_control", config_entry
    )

    if not filtered_devices:
        _LOGGER.info("No enabled devices for humidity control number platform")
        return

    entities = []
    for device_id in filtered_devices:
        if not is_supported_humidity_device(hass, device_id):
            continue

        # Create humidity number entities for this device
        try:
            device_entities = await create_humidity_number(
                hass, device_id, config_entry
            )
            entities.extend(device_entities)
            _LOGGER.info(
                "Created %d humidity number entities for device %s",
                len(device_entities),
                device_id,
            )
        except Exception as e:
            _LOGGER.error(
                "Failed to create humidity number entities for device %s: %s",
                device_id,
                e,
            )

    _LOGGER.info("Total humidity number entities created: %d", len(entities))
    if entities:
        async_add_entities(entities, True)
        _LOGGER.info("Humidity number entities added to Home Assistant")


async def create_humidity_number(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[ExtrasNumberEntity]:
    """Create humidity control number for a device.

    :param hass: Home Assistant instance
    :param device_id: Device identifier
    :param config_entry: Configuration entry
    :return: List of number entities
    """
    # Import entity configurations from registry
    from ..const import HUMIDITY_NUMBER_CONFIGS

    number_list = []

    # Create configuration number entities
    for number_type, config in HUMIDITY_NUMBER_CONFIGS.items():
        if config.get("supported_device_types") and "HvacVentilator" in config.get(
            "supported_device_types", []
        ):
            number_entity = HumidityControlNumber(
                hass, device_id, number_type, config, config_entry
            )
            number_list.append(number_entity)

    return number_list


class HumidityControlNumber(ExtrasNumberEntity):
    """Number entity for humidity control feature.

    This class handles configuration parameters for humidity control,
    such as minimum/maximum humidity thresholds and offsets.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        number_type: str,
        config: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize humidity control number.

        :param hass: Home Assistant instance
        :param device_id: Device identifier
        :param number_type: Type of number entity
        :param config: Number configuration
        :param config_entry: Configuration entry for saving values
        """
        # Initialize base entity
        super().__init__(hass, device_id, number_type, config, config_entry)

        # Initialize value - load from config entry if available, else default
        self._native_value: float = self._load_value_from_config(
            config.get("default_value", 50.0)
        )

    def _load_value_from_config(self, default_value: float) -> float:
        """Load the number value from config entry.

        :param default_value: Default value if not found in config
        :return: The stored value or default
        """
        config_entry = self.config_entry
        if config_entry is None:
            return default_value

        latest = self.hass.config_entries.async_get_entry(config_entry.entry_id)
        if latest is not None:
            config_entry = latest

        device_key = str(self.device_id).replace(":", "_")
        legacy_store = config_entry.options.get("humidity_control", {})
        legacy_device_config = (
            legacy_store.get(device_key, {}) if isinstance(legacy_store, dict) else {}
        )

        canonical_store = config_entry.options.get("ramses_extras", {})
        canonical_features = (
            canonical_store.get("features", {})
            if isinstance(canonical_store, dict)
            else {}
        )
        canonical_humidity_control = (
            canonical_features.get("humidity_control", {})
            if isinstance(canonical_features, dict)
            else {}
        )
        canonical_device_config = (
            canonical_humidity_control.get(device_key, {})
            if isinstance(canonical_humidity_control, dict)
            else {}
        )

        stored_raw = None
        if isinstance(legacy_device_config, dict):
            stored_raw = legacy_device_config.get(self._entity_type)
        if stored_raw is None and isinstance(canonical_device_config, dict):
            stored_raw = canonical_device_config.get(self._entity_type)

        stored_value = float(stored_raw) if stored_raw is not None else default_value

        # Update legacy 66% max humidity to 60% for existing installations
        if (
            self._entity_type == "relative_humidity_maximum"
            and abs(stored_value - 66.0) < 0.1
        ):
            _LOGGER.info(
                "Updating legacy max humidity from 66%% to 60%% for device %s",
                self._device_id,
            )
            # The updated value will be saved when the user changes it
            return 60.0

        return stored_value

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.debug("Number %s added to hass", self._attr_name)

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        # Use base class method which calls _save_value_to_config
        await super().async_set_native_value(value)

    async def _save_value_to_config(self, value: float) -> None:
        """Save number value to config entry with humidity_control feature key."""
        config_entry = self.config_entry
        if config_entry is None:
            return

        latest = self.hass.config_entries.async_get_entry(config_entry.entry_id)
        if latest is not None:
            config_entry = latest

        device_key = str(self.device_id).replace(":", "_")
        options = dict(config_entry.options)

        legacy_store = options.get("humidity_control")
        legacy_store = legacy_store if isinstance(legacy_store, dict) else {}
        legacy_store = dict(legacy_store)
        legacy_device_config = legacy_store.get(device_key)
        legacy_device_config = (
            legacy_device_config if isinstance(legacy_device_config, dict) else {}
        )
        legacy_device_config = dict(legacy_device_config)
        legacy_device_config[self._entity_type] = value
        legacy_store[device_key] = legacy_device_config
        options["humidity_control"] = legacy_store

        root = options.get("ramses_extras")
        root = root if isinstance(root, dict) else {}
        root = dict(root)
        features = root.get("features")
        features = features if isinstance(features, dict) else {}
        features = dict(features)
        canonical_humidity_control = features.get("humidity_control")
        canonical_humidity_control = (
            canonical_humidity_control
            if isinstance(canonical_humidity_control, dict)
            else {}
        )
        canonical_humidity_control = dict(canonical_humidity_control)
        canonical_device_config = canonical_humidity_control.get(device_key)
        canonical_device_config = (
            canonical_device_config if isinstance(canonical_device_config, dict) else {}
        )
        canonical_device_config = dict(canonical_device_config)
        canonical_device_config[self._entity_type] = value
        canonical_humidity_control[device_key] = canonical_device_config
        features["humidity_control"] = canonical_humidity_control
        root["features"] = features
        options["ramses_extras"] = root

        self.hass.config_entries.async_update_entry(config_entry, options=options)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "number_type": self._entity_type,
            "min_value": self._attr_native_min_value,
            "max_value": self._attr_native_max_value,
            "step": self._attr_native_step,
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("number", "humidity_control", async_setup_entry)

__all__ = [
    "HumidityControlNumber",
    "async_setup_entry",
    "create_humidity_number",
]
