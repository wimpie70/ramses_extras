import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.ramses_extras.const import AVAILABLE_FEATURES, DOMAIN
from custom_components.ramses_extras.framework.base_classes import ExtrasBaseEntity
from custom_components.ramses_extras.framework.helpers.device.core import (
    find_ramses_device,
    get_device_type,
)
from custom_components.ramses_extras.framework.helpers.entity.registry import (
    entity_registry,
)
from custom_components.ramses_extras.framework.helpers.entity_core import EntityHelpers
from custom_components.ramses_extras.framework.helpers.platform import (
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

    # Debug: Check config entry data
    _LOGGER.info(
        f"Config entry data: {config_entry.data if config_entry else 'No config entry'}"
    )

    # Calculate required entities for this platform
    required_entities = calculate_required_entities(
        "switch", enabled_features, devices, hass
    )

    _LOGGER.info(f"Required switch entities: {required_entities}")

    if not required_entities:
        _LOGGER.info("No required switch entities, skipping setup")
        return

    _LOGGER.info(
        f"Platform switch setup completed with {len(required_entities)} "
        f"required entity types: {required_entities}"
    )

    # Get entity definitions from EntityRegistry
    all_device_mappings = entity_registry.get_all_device_mappings()
    all_switch_configs = entity_registry.get_all_switch_configs()

    # Create entities for each device
    switch_entities = []
    _LOGGER.info(f"Creating switch entities for {len(devices)} devices: {devices}")

    for device_id in devices:
        device = find_ramses_device(hass, device_id)
        if not device:
            _LOGGER.warning(
                f"Device {device_id} not found, skipping switch entity creation"
            )
            continue

        device_type = get_device_type(device)
        _LOGGER.info(f"Device {device_id} has type: {device_type}")
        _LOGGER.info(f"Available device mappings: {list(all_device_mappings.keys())}")

        if device_type not in all_device_mappings:
            _LOGGER.debug(f"Device type {device_type} not in entity mapping, skipping")
            continue

        # Log what entities this device should have
        entity_mapping = all_device_mappings[device_type]
        _LOGGER.info(f"Device {device_id} has mapping: {entity_mapping}")
        switch_entities_for_device = entity_mapping.get("switches", [])
        _LOGGER.info(
            f"Device {device_id} should have switches: {switch_entities_for_device}"
        )

        # Create switch entities for each required entity type
        for switch_type in required_entities:
            _LOGGER.info(f"Processing switch type: {switch_type}")
            _LOGGER.info(f"Available switch configs: {list(all_switch_configs.keys())}")
            if switch_type in all_switch_configs:
                config = all_switch_configs[switch_type]
                _LOGGER.info(
                    f"Creating switch entity: {switch_type} for device {device_id}"
                )
                _LOGGER.info(f"Switch config: {config}")
                switch_entity = RamsesDehumidifySwitch(
                    hass, device_id, switch_type, config
                )
                switch_entities.append(switch_entity)
                _LOGGER.info(
                    f"✅ Created switch entity: "
                    f"{switch_type} for device {device_id} - "
                    f"unique_id: {switch_entity._attr_unique_id}"
                )
            else:
                _LOGGER.warning(
                    f"❌ Switch type {switch_type} not found in ENTITY_TYPE_CONFIGS"
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

        # Convert device_id to underscore format for entity generation
        device_id_underscore = device_id.replace(":", "_")

        # Generate proper entity name using template system
        entity_name = EntityHelpers.generate_entity_name_from_template(
            "switch", switch_type, device_id_underscore
        )

        if entity_name:
            # Set entity name and unique_id using proper template
            name_template = (
                config.get("name_template", "Dehumidify {device_id}")
                or "Dehumidify {device_id}"
            )
            self._attr_name = name_template.format(device_id=device_id_underscore)
            self._attr_unique_id = entity_name.replace("switch.", "")
        else:
            # Fallback to hardcoded format (legacy)
            name_template = (
                config.get("name_template", "Dehumidify {device_id}")
                or "Dehumidify {device_id}"
            )
            self._attr_name = name_template.format(device_id=device_id_underscore)
            self._attr_unique_id = f"dehumidify_{device_id_underscore}"

        self._is_on = False

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._attr_name or "Dehumidify"

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
            # Get current entity states and evaluate humidity conditions
            device_id_underscore = self._device_id.replace(":", "_")
            try:
                entity_states = await automation._get_device_entity_states(
                    device_id_underscore
                )
                _LOGGER.info(f"Got entity states for evaluation: {entity_states}")

                # Call the method with proper parameters
                await automation._evaluate_humidity_conditions(
                    device_id=self._device_id,
                    indoor_abs=entity_states.get("indoor_abs", 0.0),
                    outdoor_abs=entity_states.get("outdoor_abs", 0.0),
                    min_humidity=entity_states.get("min_humidity", 40.0),
                    max_humidity=entity_states.get("max_humidity", 60.0),
                    offset=entity_states.get("offset", 0.0),
                )
            except Exception as e:
                _LOGGER.error(f"Failed to evaluate humidity conditions: {e}")
                # Fallback: just set the switch state but don't evaluate
                # pass
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

            # Just log the deactivation - avoid circular service calls
            _LOGGER.info(f"Dehumidification manually disabled for {self._device_id}")

            # In a full implementation, this would reset fan to auto
            # but we'll avoid the service call to prevent recursion
            pass  # noqa: PIE790
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
