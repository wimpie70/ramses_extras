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
from .framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)
from .framework.helpers.entity.core import EntityHelpers, ExtrasBaseEntity
from .framework.helpers.platform import (
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
    await _async_setup_number_platform(hass, config_entry, async_add_entities)


async def _async_setup_number_platform(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the number platform with entity creation."""
    _LOGGER.info("Setting up number platform")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping number setup")
        return

    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    if not devices:
        _LOGGER.warning("No devices available for number")
        return

    # Get enabled features
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features for number: {enabled_features}")

    # Calculate required entities for this platform
    required_entities = calculate_required_entities(
        "number", enabled_features, devices, hass
    )

    if not required_entities:
        _LOGGER.info("No required number entities, skipping setup")
        return

    _LOGGER.info(
        f"Platform number setup completed with {len(required_entities)} "
        f"required entity types: {required_entities}"
    )

    # Create entities for each device
    number_entities = []
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(
                f"Device {device_id} not found, skipping number entity creation"
            )
            continue

        device_type = get_device_type(device)
        if device_type not in DEVICE_ENTITY_MAPPING:
            _LOGGER.debug(f"Device type {device_type} not in entity mapping, skipping")
            continue

        # Create number entities for each required entity type
        for number_type in required_entities:
            if number_type in ENTITY_TYPE_CONFIGS.get("number", {}):
                config = ENTITY_TYPE_CONFIGS["number"][number_type]
                number_entities.append(
                    RamsesNumberEntity(hass, device_id, number_type, config)
                )
                _LOGGER.info(
                    f"Created number entity: {number_type} for device {device_id}"
                )

    if number_entities:
        async_add_entities(number_entities, True)
        _LOGGER.info(f"Added {len(number_entities)} number entities")
    else:
        _LOGGER.info("No number entities to add")


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

        # Set unique_id to prevent duplicate entities
        self._attr_unique_id = f"{number_type}_{device_id.replace(':', '_')}"

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
                        (self._config or {}).get("default_value", min_val),
                    )
                    self._value = (self._config or {}).get("default_value", min_val)
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "Failed to restore %s value from state '%s': %s, "
                    "using default %.1f",
                    self._number_type,
                    last_state.state,
                    e,
                    (self._config or {}).get(
                        "default_value", self._attr_native_min_value
                    ),
                )
                self._value = (self._config or {}).get(
                    "default_value", self._attr_native_min_value
                )
        else:
            # No previous state found, use default value
            self._value = (self._config or {}).get(
                "default_value", self._attr_native_min_value
            )
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
