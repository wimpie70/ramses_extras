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
from .helpers.device import find_ramses_device, get_device_type
from .helpers.entity import ExtrasBaseEntity
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
    """Set up the switch platform."""
    devices = hass.data.get(DOMAIN, {}).get("devices", [])
    _LOGGER.info(f"Setting up switch platform for {len(devices)} devices")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping switch setup")
        return

    if not devices:
        _LOGGER.debug("No devices available for switches")
        return

    switches = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Create switches based on enabled features and their requirements
    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(f"Device {device_id} not found, skipping switch creation")
            continue

        device_type = get_device_type(device)
        _LOGGER.debug(f"Creating switches for device {device_id} of type {device_type}")

        if device_type in DEVICE_ENTITY_MAPPING:
            entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

            # Get all possible switch types for this device
            all_possible_switches = entity_mapping.get("switches", [])

            # Check each possible switch type
            for switch_type in all_possible_switches:
                if switch_type not in ENTITY_TYPE_CONFIGS["switch"]:
                    continue

                # Check if this switch is needed by any enabled feature
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
                        # Check if this switch is required or optional for this feature
                        required_entities = feature_config.get("required_entities", {})
                        optional_entities = feature_config.get("optional_entities", {})

                        if isinstance(required_entities, dict):
                            required_switches = required_entities.get("switches", [])
                        else:
                            required_switches = []

                        if isinstance(optional_entities, dict):
                            optional_switches = optional_entities.get("switches", [])
                        else:
                            optional_switches = []

                        if (
                            isinstance(required_switches, list)
                            and switch_type in required_switches
                        ) or (
                            isinstance(optional_switches, list)
                            and switch_type in optional_switches
                        ):
                            is_needed = True
                            break

                if is_needed:
                    # Entity is needed - create it
                    config = ENTITY_TYPE_CONFIGS["switch"][switch_type]
                    switches.append(
                        RamsesDehumidifySwitch(hass, device_id, switch_type, config)
                    )
                    _LOGGER.debug(f"Creating switch: switch.{device_id}_{switch_type}")

    async_add_entities(switches, True)


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
