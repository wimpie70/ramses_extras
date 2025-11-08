import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
)
from .helpers.device import (
    find_ramses_device,
    get_device_type,
)
from .helpers.entity import EntityHelpers, ExtrasBaseEntity
from .helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the number platform."""
    devices = hass.data.get(DOMAIN, {}).get("devices", [])
    _LOGGER.info(f"Setting up number platform for {len(devices)} devices")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping number setup")
        return

    if not devices:
        _LOGGER.debug("No devices available for numbers")
        return

    numbers = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Create numbers based on enabled features and their requirements
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(f"Device {device_id} not found, skipping number creation")
            continue

        device_type = get_device_type(device)
        _LOGGER.debug(f"Creating numbers for device {device_id} of type {device_type}")

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Get all possible number types for this device
            all_possible_numbers = entity_mapping.get("numbers", [])

            # Check each possible number type
            for number_type in all_possible_numbers:
                if number_type not in ENTITY_TYPE_CONFIGS["number"]:
                    continue

                # Check if this number is needed by any enabled feature
                is_needed = False
                for feature_key, is_enabled in enabled_features.items():
                    if not is_enabled or feature_key not in AVAILABLE_FEATURES:
                        continue

                    feature_config = AVAILABLE_FEATURES[feature_key]
                    supported_types = feature_config.get("supported_device_types", [])
                    if (
                        isinstance(supported_types, list)
                        and device_type in supported_types
                    ):
                        # Check if this number is required for this feature
                        required_entities = feature_config.get("required_entities", {})

                        if isinstance(required_entities, dict):
                            required_numbers = required_entities.get("numbers", [])
                        else:
                            required_numbers = []

                        if (
                            isinstance(required_numbers, list)
                            and number_type in required_numbers
                        ):
                            is_needed = True
                            break

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS["number"][number_type]
                    numbers.append(
                        RamsesNumberEntity(hass, device_id, number_type, config)
                    )
                    entity_id = EntityHelpers.generate_entity_name_from_template(
                        "number", number_type, device_id
                    )
                    _LOGGER.debug(f"Creating number: {entity_id}")

    async_add_entities(numbers, True)


class RamsesNumberEntity(NumberEntity, RestoreEntity, ExtrasBaseEntity):
    """Number entity for Ramses device configuration values."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        number_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, number_type, config)

        # Set number-specific attributes
        self._number_type = number_type
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_native_min_value = config.get("min_value", 0)
        self._attr_native_max_value = config.get("max_value", 100)
        self._attr_native_step = config.get("step", 1)

        # Use default value if specified, otherwise use min_value
        self._value = config.get("default_value", self._attr_native_min_value)

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()

        # Restore state for humidity control entities only
        await self._async_restore_state()

    async def _async_restore_state(self) -> None:
        """Restore state from previous session for humidity control entities."""
        # Only restore state for humidity control number entities
        if self._number_type not in ["rel_humid_min", "rel_humid_max"]:
            return

        _LOGGER.debug("Restoring state for %s", self.name)

        # Try to get previous state
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                # Convert the stored value back to float
                restored_value = float(last_state.state)
                # Validate the restored value is within allowed range
                min_val = self._attr_native_min_value
                max_val = self._attr_native_max_value

                if min_val <= restored_value <= max_val:
                    self._value = restored_value
                    _LOGGER.debug(
                        "Restored %s value: %.1f (valid range: %.1f-%.1f)",
                        self._number_type,
                        restored_value,
                        min_val,
                        max_val,
                    )
                else:
                    _LOGGER.warning(
                        "Restored %s value %.1f is outside valid range (%.1f-%.1f), "
                        "using default %.1f",
                        self._number_type,
                        restored_value,
                        min_val,
                        max_val,
                        self._config.get("default_value", min_val),
                    )
                    self._value = self._config.get("default_value", min_val)
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "Failed to restore %s value from state '%s': %s, "
                    "using default %.1f",
                    self._number_type,
                    last_state.state,
                    e,
                    self._config.get("default_value", self._attr_native_min_value),
                )
                self._value = self._config.get(
                    "default_value", self._attr_native_min_value
                )
        else:
            # No previous state found, use default value
            self._value = self._config.get("default_value", self._attr_native_min_value)
            _LOGGER.debug(
                "No previous state found for %s, using default value: %.1f",
                self._number_type,
                self._value,
            )

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self.name)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return float(self._value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        _LOGGER.debug(
            "Updated %s to %.1f for %s (configuration value)",
            self._number_type,
            value,
            self.name,
        )

        self._value = value
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "number_type": self._number_type}
