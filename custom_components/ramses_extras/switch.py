import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

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
    """Set up the switch platform."""
    await _async_setup_switch_platform(hass, config_entry, async_add_entities)


async def _async_setup_switch_platform(
    hass: "HomeAssistant",
    config_entry: ConfigEntry | None,
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up the switch platform with entity creation."""
    _LOGGER.info("Setting up switch platform")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping switch setup")
        return

    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    if not devices:
        _LOGGER.warning("No devices available for switch")
        return

    # Get enabled features
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features for switch: {enabled_features}")

    # Calculate required entities for this platform
    required_entities = calculate_required_entities(
        "switch", enabled_features, devices, hass
    )

    if not required_entities:
        _LOGGER.info("No required switch entities, skipping setup")
        return

    _LOGGER.info(
        f"Platform switch setup completed with {len(required_entities)} "
        f"required entity types: {required_entities}"
    )

    # Create entities for each device
    switch_entities = []
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(
                f"Device {device_id} not found, skipping switch entity creation"
            )
            continue

        device_type = get_device_type(device)
        if device_type not in DEVICE_ENTITY_MAPPING:
            _LOGGER.debug(f"Device type {device_type} not in entity mapping, skipping")
            continue

        # Create switch entities for each required entity type
        for switch_type in required_entities:
            if switch_type in ENTITY_TYPE_CONFIGS.get("switch", {}):
                config = ENTITY_TYPE_CONFIGS["switch"][switch_type]
                switch_entities.append(
                    RamsesDehumidifySwitch(hass, device_id, switch_type, config)
                )
                _LOGGER.info(
                    f"Created switch entity: {switch_type} for device {device_id}"
                )

    if switch_entities:
        async_add_entities(switch_entities, True)
        _LOGGER.info(f"Added {len(switch_entities)} switch entities")
    else:
        _LOGGER.info("No switch entities to add")


class RamsesDehumidifySwitch(SwitchEntity, ExtrasBaseEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, switch_type, config)

        # Set switch-specific attributes
        self._switch_type = switch_type

        # Override unique_id for switch to match existing pattern
        self._attr_unique_id = f"dehumidify_{device_id.replace(':', '_')}"

        self._is_on = False

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        # Call base class method first
        await super().async_added_to_hass()
        _LOGGER.info("switch added to hass")

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if dehumidify is active."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate dehumidify mode."""
        _LOGGER.info("Activating dehumidify mode for %s", self._attr_name)
        self._is_on = True
        self.async_write_ha_state()

        # Use existing automation created by binary sensor
        automation = (
            self.hass.data.get("ramses_extras", {})
            .get("automations", {})
            .get(self._device_id)
        )
        if automation:
            # Update switch state for the existing automation
            automation.switch_state = True
            # Immediately evaluate current conditions since switch is now on
            await automation._evaluate_current_conditions()
        else:
            # Debug: log what's actually in the data
            ramses_data = self.hass.data.get("ramses_extras", {})
            automations_data = ramses_data.get("automations", {})
            _LOGGER.warning(
                f"No automation found for device {self._device_id}. "
                f"Available automations: {list(automations_data.keys())}. "
                f"Binary sensor should have created it."
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate dehumidify mode."""
        _LOGGER.info("Deactivating dehumidify mode for %s", self._attr_name)

        # Update automation state if exists
        automation = (
            self.hass.data.get("ramses_extras", {})
            .get("automations", {})
            .get(self._device_id)
        )
        if automation:
            # Update switch state for the existing automation
            automation.switch_state = False
            _LOGGER.info(f"Updated switch state in automation for {self._device_id}")

            # Reset fan to AUTO and turn off binary sensor
            await automation._reset_fan_to_auto(self._device_id.replace(":", "_"))
        else:
            _LOGGER.warning(
                f"No automation found for device {self._device_id} when turning off"
            )

        self._is_on = False
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "dehumidifying": self.is_on}
