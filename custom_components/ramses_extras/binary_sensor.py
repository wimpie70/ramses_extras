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

from .const import (
    AVAILABLE_FEATURES,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    ENTITY_TYPE_CONFIGS,
)
from .framework.helpers.device.core import find_ramses_device, get_device_type
from .framework.helpers.entity.core import ExtrasBaseEntity
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
        if device_type not in DEVICE_ENTITY_MAPPING:
            _LOGGER.debug(f"Device type {device_type} not in entity mapping, skipping")
            continue

        # Create binary sensors for each required entity type
        for boolean_type in required_entities:
            if boolean_type in ENTITY_TYPE_CONFIGS.get("binary_sensor", {}):
                config = ENTITY_TYPE_CONFIGS["binary_sensor"][boolean_type]
                binary_sensors.append(
                    RamsesBinarySensor(hass, device_id, boolean_type, config)
                )
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

        # Set unique_id to prevent duplicate entities
        self._attr_unique_id = f"{boolean_type}_{device_id.replace(':', '_')}"

        self._is_on = False
        self._current_fan_speed = "auto"  # Track current fan speed
        self._unsub_state_change: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates and humidity entity changes."""
        # Call base class method first
        await super().async_added_to_hass()

        # For dehumidifying_active, start the hardcoded automation
        if self._boolean_type == "dehumidifying_active":
            _LOGGER.info(
                f"🔧 Starting humidity automation for binary sensor {self._attr_name} "
                f"(device: {self._device_id})"
            )
            # 🔧 START HUMIDITY AUTOMATION FOR THIS DEVICE
            automation_manager = await self._start_humidity_automation_for_device(self)

            # Store the automation manager for the switch to use
            if automation_manager:
                self.hass.data.setdefault(DOMAIN, {}).setdefault("automations", {})[
                    self._device_id
                ] = automation_manager
                # _LOGGER.info(
                #     f"✅ Stored automation for device {self._device_id} in "
                #     f"hass.data['{DOMAIN}']['automations']"
                # )
            else:
                _LOGGER.error(
                    f"❌ Failed to start automation for device {self._device_id}"
                )

            # Binary sensor is controlled directly by the automation

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

        # Binary sensor is controlled directly by the automation

    async def _start_humidity_automation_for_device(self, binary_sensor: Any) -> Any:
        """Start the hardcoded humidity automation for this specific device."""
        _LOGGER.info(
            f"🔧 Starting hardcoded humidity automation for device {self._device_id}"
        )

        try:
            from .features.humidity_control.automation import HumidityAutomationManager

            # Create automation manager for this device
            automation_manager = HumidityAutomationManager(
                self.hass, self.hass.data[DOMAIN]["config_entry"]
            )

            # Start the automation
            await automation_manager.start()

            # _LOGGER.info(
            #     f"✅ Hardcoded humidity automation started for "
            #     f"device {self._device_id}"
            # )

            return automation_manager

        except Exception as e:
            _LOGGER.error(
                f"❌ Failed to start humidity automation for device "
                f"{self._device_id}: {e}"
            )
            return None

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
