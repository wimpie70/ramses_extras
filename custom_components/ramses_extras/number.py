import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
)
from .helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
    remove_orphaned_entities,
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
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    _LOGGER.info(f"Setting up number platform for {len(fans)} fans")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping number setup")
        return

    if not fans:
        _LOGGER.debug("No fans available for numbers")
        return

    numbers = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Create numbers based on enabled features and their requirements
    for fan_id in fans:
        device_type = "HvacVentilator"

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
                        RamsesNumberEntity(hass, fan_id, number_type, config)
                    )
                    _LOGGER.debug(f"Creating number: number.{fan_id}_{number_type}")

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities() -> None:
        try:
            # Get all possible number types for this device
            all_possible_numbers = []
            for _fan_id in fans:
                device_type = "HvacVentilator"
                if device_type in DEVICE_ENTITY_MAPPING:
                    entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
                    all_possible_numbers = entity_mapping.get("numbers", [])
                    break

            await remove_orphaned_entities(
                "number",
                hass,
                fans,
                calculate_required_entities("number", enabled_features, fans),
                all_possible_numbers,
            )
        except Exception as e:
            _LOGGER.warning(f"Error during number entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

    async_add_entities(numbers, True)


class RamsesNumberEntity(NumberEntity):
    """Number entity for Ramses device configuration values."""

    def __init__(
        self,
        hass: "HomeAssistant",
        fan_id: str,
        number_type: str,
        config: dict[str, Any],
    ):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._number_type = number_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({fan_id})"
        # Use format that matches card expectations: number.32_153289_rel_humid_min
        self._attr_unique_id = f"{fan_id.replace(':', '_')}_{number_type}"
        self._attr_icon = config["icon"]
        self._attr_entity_category = config["entity_category"]
        self._attr_native_unit_of_measurement = config.get("unit")
        self._attr_device_class = config.get("device_class")
        self._attr_native_min_value = config.get("min_value", 0)
        self._attr_native_max_value = config.get("max_value", 100)
        self._attr_native_step = config.get("step", 1)

        self._value = self._attr_native_min_value
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for number %s", signal, self.name)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self.name)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        _LOGGER.info(
            "Setting %s to %.1f for %s (LOGGING ONLY - not sent to device)",
            self._number_type,
            value,
            self.name,
        )

        # For threshold values, log what command would be sent
        if self._number_type in ["rel_humid_min", "rel_humid_max"]:
            device_id = self._fan_id.replace("_", ":")
            _LOGGER.info(
                "Would send 2411 parameter update: device_id=%s, param=%s, value=%.1f",
                device_id,
                self._number_type,
                value,
            )

        self._value = value
        self.async_write_ha_state()
