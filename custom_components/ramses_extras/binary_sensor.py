import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_state_change_event,
)

from .const import AVAILABLE_FEATURES, DOMAIN
from .framework.base_classes import ExtrasBaseEntity
from .framework.helpers.device.core import find_ramses_device, get_device_type
from .framework.helpers.entity.registry import entity_registry
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
    """Set up the binary sensor platform."""
    await _async_setup_binary_sensor_platform(hass, config_entry, async_add_entities)


async def _async_setup_binary_sensor_platform(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the binary sensor platform with entity creation."""
    _LOGGER.info("Setting up binary_sensor platform")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping binary_sensor setup")
        return

    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    if not devices:
        _LOGGER.warning("No devices available for binary_sensor")
        return

    # Get enabled features
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features for binary_sensor: {enabled_features}")

    # Calculate required entities for this platform
    required_entities = calculate_required_entities(
        "binary_sensor", enabled_features, devices, hass
    )

    if not required_entities:
        _LOGGER.info("No required binary_sensor entities, skipping setup")
        return

    _LOGGER.info(
        f"Platform binary_sensor setup completed with {len(required_entities)} "
        f"required entity types: {required_entities}"
    )

    # Get entity definitions from EntityRegistry
    all_device_mappings = entity_registry.get_all_device_mappings()
    all_boolean_configs = entity_registry.get_all_boolean_configs()

    # Create entities for each device
    binary_sensors = []
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(
                f"Device {device_id} not found, skipping binary_sensor creation"
            )
            continue

        device_type = get_device_type(device)
        if device_type not in all_device_mappings:
            _LOGGER.debug(f"Device type {device_type} not in entity mapping, skipping")
            continue

        # Create binary sensors for each required entity type
        for boolean_type in required_entities:
            if boolean_type in all_boolean_configs:
                config = all_boolean_configs[boolean_type]

                # Use feature-specific binary sensor for humidity control
                if boolean_type == "dehumidifying_active":
                    from .features.humidity_control.binary_sensor import (
                        create_humidity_control_binary_sensor,
                    )

                    binary_sensor = create_humidity_control_binary_sensor(
                        hass, device_id, boolean_type, config
                    )
                else:
                    # Use generic binary sensor for other types
                    binary_sensor = RamsesBinarySensor(
                        hass, device_id, boolean_type, config
                    )

                binary_sensors.append(binary_sensor)
                _LOGGER.info(
                    f"Created binary_sensor entity: {boolean_type} "
                    f"for device {device_id}"
                )

    if binary_sensors:
        async_add_entities(binary_sensors, True)
        _LOGGER.info(f"Added {len(binary_sensors)} binary_sensor entities")
    else:
        _LOGGER.info("No binary_sensor entities to add")


class RamsesBinarySensor(BinarySensorEntity, ExtrasBaseEntity):
    """Binary sensor for Ramses device states."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        boolean_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, boolean_type, config)

        # Set binary sensor-specific attributes
        self._boolean_type = boolean_type
        self._attr_device_class = config.get("device_class")

        # Convert device_id to underscore format for entity generation
        device_id_underscore = device_id.replace(":", "_")

        # Set unique_id to prevent duplicate entities
        self._attr_unique_id = f"{boolean_type}_{device_id_underscore}"

        # Set human-friendly name from template
        name_template = (
            config.get("name_template", "Dehumidifying Active {device_id}")
            or "Dehumidifying Active {device_id}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

        self._is_on = False
        self._current_fan_speed = "auto"  # Track current fan speed
        self._unsub_state_change: Callable[[], None] | None = None

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self._attr_name
            or f"Dehumidifying Active {self._device_id.replace(':', '_')}"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.debug("Binary sensor %s added to hass", self._attr_name)

        # Binary sensor is controlled by features - no platform-specific logic
        # Feature-specific integration is handled by the features themselves

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

        # Binary sensor is controlled directly by the automation

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor state is on."""
        # For dehumidifying_active: read-only, controlled by automation
        # Binary sensor is turned on/off by the automation, not calculated here
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the binary sensor - controlled by automation only."""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s turned ON by automation (is_on: %s)",
            self._attr_name,
            self._is_on,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the binary sensor - controlled by automation only."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.info(
            "Binary sensor %s turned OFF by automation (is_on: %s)",
            self._attr_name,
            self._is_on,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base_attrs = super().extra_state_attributes or {}
        return {
            **base_attrs,
            "boolean_type": self._boolean_type,
            "controlled_by": "automation",
        }
