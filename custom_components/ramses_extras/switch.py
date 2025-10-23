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
    """Set up the switch platform."""
    fans = hass.data.get(DOMAIN, {}).get("fans", [])
    _LOGGER.info(f"Setting up switch platform for {len(fans)} fans")

    if not config_entry:
        _LOGGER.warning("Config entry not available, skipping switch setup")
        return

    if not fans:
        _LOGGER.debug("No fans available for switches")
        return

    switches = []

    # Get enabled features from config entry
    enabled_features = get_enabled_features(hass, config_entry)
    _LOGGER.info(f"Enabled features: {enabled_features}")

    # Create switches based on enabled features and their requirements
    for fan_id in fans:
        device_type = "HvacVentilator"

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
                        RamsesDehumidifySwitch(hass, fan_id, switch_type, config)
                    )
                    _LOGGER.debug(f"Creating switch: switch.{fan_id}_{switch_type}")

    # Remove orphaned entities (defer to after entity creation)
    async def cleanup_orphaned_entities() -> None:
        try:
            # Get all possible switch types for this device
            all_possible_switches = []
            for _fan_id in fans:
                device_type = "HvacVentilator"
                if device_type in DEVICE_ENTITY_MAPPING:
                    entity_mapping = DEVICE_ENTITY_MAPPING[device_type]
                    all_possible_switches = entity_mapping.get("switches", [])
                    break

            await remove_orphaned_entities(
                "switch",
                hass,
                fans,
                calculate_required_entities("switch", enabled_features, fans),
                all_possible_switches,
            )
        except Exception as e:
            _LOGGER.warning(f"Error during switch entity cleanup: {e}")

    # Schedule cleanup after entity creation
    hass.async_create_task(cleanup_orphaned_entities())

    async_add_entities(switches, True)


class RamsesDehumidifySwitch(SwitchEntity):
    """Switch to toggle dehumidify mode."""

    def __init__(
        self,
        hass: "HomeAssistant",
        fan_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        self.hass = hass
        self._fan_id = fan_id  # Store device ID as string
        self._switch_type = switch_type
        self._config = config

        # Set attributes from configuration
        self._attr_name = f"{config['name_template']} ({fan_id})"
        # Use format that matches existing entities: switch.dehumidify_32_153289
        self._attr_unique_id = f"dehumidify_{fan_id.replace(':', '_')}"
        self._attr_icon = config["icon"]
        self._attr_entity_category = config["entity_category"]

        self._is_on = False
        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._fan_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for switch %s", signal, self.name)

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
        """Return true if dehumidify is active."""
        # For now, return stored state since we don't have access to device object
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate dehumidify mode."""
        _LOGGER.info("Activating dehumidify mode for %s", self.name)

        try:
            # Log what we would do instead of actually sending commands
            device_id = self._fan_id.replace("_", ":")

            # Get the bound REM device first (similar to card logic)
            try:
                # Try to get bound REM from climate entity attributes
                climate_entity = f"climate.{self._fan_id}_climate"
                climate_state = self.hass.states.get(climate_entity)

                if climate_state and climate_state.attributes.get("bound_rem"):
                    rem_id = climate_state.attributes["bound_rem"]
                    _LOGGER.info("Found bound REM: %s", rem_id)
                else:
                    # Fallback to device_id as from_id
                    rem_id = device_id
                    _LOGGER.info(
                        "No bound REM found, would use device_id: %s", device_id
                    )

                # Log what command would be sent (don't actually send it)
                _LOGGER.info(
                    "Would send dehumidify activation command: "
                    "device_id=%s, from_id=%s, verb=' I', code='22F1', payl='000807'",
                    device_id,
                    rem_id,
                )

                self._is_on = True
                _LOGGER.info(
                    "Successfully logged dehumidify activation (state updated locally)"
                )

            except Exception as e:
                _LOGGER.error("Error preparing dehumidify command: %s", e)
                # Still update state even if command preparation fails
                self._is_on = True

        except Exception as e:
            _LOGGER.error("Error activating dehumidify mode: %s", e)
            self._is_on = True  # Keep local state updated

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate dehumidify mode."""
        _LOGGER.info("Deactivating dehumidify mode for %s", self.name)

        try:
            # Log what we would do instead of actually sending commands
            device_id = self._fan_id.replace("_", ":")

            try:
                # Get the bound REM device first (similar to card logic)
                climate_entity = f"climate.{self._fan_id}_climate"
                climate_state = self.hass.states.get(climate_entity)

                if climate_state and climate_state.attributes.get("bound_rem"):
                    rem_id = climate_state.attributes["bound_rem"]
                    _LOGGER.info("Found bound REM: %s", rem_id)
                else:
                    # Fallback to device_id as from_id
                    rem_id = device_id
                    _LOGGER.info(
                        "No bound REM found, would use device_id: %s", device_id
                    )

                # Log what command would be sent (don't actually send it)
                _LOGGER.info(
                    "Would send dehumidify deactivation command: "
                    "device_id=%s, from_id=%s, verb=' I', code='22F1', payl='000507'",
                    device_id,
                    rem_id,
                )

                self._is_on = False
                _LOGGER.info(
                    "Successfully logged dehumidify deact (state updated locally)"
                )

            except Exception as e:
                _LOGGER.error("Error preparing dehumidify command: %s", e)
                # Still update state even if command preparation fails
                self._is_on = False

        except Exception as e:
            _LOGGER.error("Error deactivating dehumidify mode: %s", e)
            self._is_on = False  # Keep local state updated

        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"dehumidifying": self.is_on}
