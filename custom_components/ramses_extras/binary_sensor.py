import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change

from .const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
)
from .helpers.device import find_ramses_device, get_device_type
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
    """Set up the binary sensor platform."""
    devices = hass.data.get(DOMAIN, {}).get("devices", [])
    _LOGGER.info(f"Setting up binary_sensor platform for {len(devices)} devices")

    # Check if config entry is available (it might not be during initial load)
    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping binary_sensor setup")
        return

    if not devices:
        _LOGGER.debug("No devices available for binary sensors")
        return

    binary_sensors = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Create binary sensors based on enabled features and their requirements
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(
                f"Device {device_id} not found, skipping binary sensor creation"
            )
            continue

        device_type = get_device_type(device)
        _LOGGER.debug(
            f"Creating binary sensors for device {device_id} of type {device_type}"
        )

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Get all possible binary sensor types for this device
            all_possible_booleans = entity_mapping.get("binary_sensors", [])

            # Check each possible binary sensor type
            for boolean_type in all_possible_booleans:
                if boolean_type not in ENTITY_TYPE_CONFIGS["binary_sensor"]:
                    continue

                # Check if this binary sensor is needed by any enabled feature
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
                        # Check if this binary sensor is required for this feature
                        required_entities = feature_config.get("required_entities", {})

                        if isinstance(required_entities, dict):
                            required_booleans = required_entities.get(
                                "binary_sensors", []
                            )
                        else:
                            required_booleans = []

                        if (
                            isinstance(required_booleans, list)
                            and boolean_type in required_booleans
                        ):
                            is_needed = True
                            break

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS["binary_sensor"][boolean_type]
                    binary_sensors.append(
                        RamsesBinarySensor(hass, device_id, boolean_type, config)
                    )
                    _LOGGER.debug(f"Creating binary sensor: {device_id}_{boolean_type}")

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities() -> None:
        try:
            # Get all possible binary sensor types for all devices
            all_possible_booleans = set()
            for device_id in devices:
                device = find_ramses_device(hass, device_id)
                if device:
                    device_type = get_device_type(device)
                    if device_type in DEVICE_ENTITY_MAPPING:
                        entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
                        all_possible_booleans.update(
                            entity_mapping.get("binary_sensors", [])
                        )

            await remove_orphaned_entities(
                "binary_sensor",
                hass,
                devices,
                calculate_required_entities(
                    "binary_sensor", enabled_features, devices, hass
                ),
                list(all_possible_booleans),
            )
        except Exception as e:
            _LOGGER.warning(f"Error during binary_sensor entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

    async_add_entities(binary_sensors, True)


class RamsesBinarySensor(BinarySensorEntity):
    """Binary sensor for Ramses device states."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        boolean_type: str,
        config: dict[str, Any],
    ):
        self.hass = hass
        self._device_id = device_id  # Store device ID as string
        self._boolean_type = boolean_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({device_id})"
        self._attr_unique_id = f"{device_id.replace(':', '_')}_{boolean_type}"
        self._attr_icon = config["icon"]
        self._attr_entity_category = config["entity_category"]
        self._attr_device_class = config.get("device_class")

        self._is_on = False
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._device_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for binary sensor %s", signal, self.name)

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
    def is_on(self) -> bool:
        """Return true if the binary sensor state is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the binary sensor."""
        _LOGGER.info("Turning on binary sensor %s", self.name)
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the binary sensor."""
        _LOGGER.info("Turning off binary sensor %s", self.name)
        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"device_id": self._device_id, "boolean_type": self._boolean_type}
