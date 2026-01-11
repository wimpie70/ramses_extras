# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more debugrmation
#
"""Switch platform for Hello World Switch Card feature.

This module provides the switch platform implementation for the Hello World feature,
demonstrating basic switch entities that can be controlled and monitored.

:platform: Home Assistant
:feature: Hello World Switch Platform
:components: Switch Entity, State Management, Entity Coordination
:entity_type: Switch
:capabilities: ON/OFF Control, State Monitoring
"""

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.framework.base_classes.platform_entities import (
    ExtrasSwitchEntity,
)
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

# Import SimpleEntityManager and EntityHelpers from framework
from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
    SimpleEntityManager,
)

from ..const import HELLO_WORLD_SWITCH_CONFIGS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: "HomeAssistant",
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hello World switch platform."""
    from custom_components.ramses_extras.framework.helpers import platform

    hass.data.setdefault("ramses_extras", {})
    hass.data["ramses_extras"].setdefault(
        "hello_world_entities", SimpleEntityManager(hass)
    )

    await platform.PlatformSetup.async_create_and_add_platform_entities(
        platform="switch",
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        entity_configs=HELLO_WORLD_SWITCH_CONFIGS,
        entity_factory=create_hello_world_switch,
        feature_id="hello_world",
        store_entities_for_automation=True,
    )


async def create_hello_world_switch(
    hass: "HomeAssistant",
    device_id: str,
    entity_configs: dict[str, Any],
    config_entry: ConfigEntry | None = None,
) -> list[ExtrasSwitchEntity]:
    """Create Hello World switch for a device.

    Args:
        hass: Home Assistant instance
        device_id: Device identifier
        config_entry: Configuration entry

    Returns:
        List of switch entities
    """
    switch_list = []

    device_type: str | None = None
    try:
        devices = hass.data.get("ramses_extras", {}).get("devices", [])
        for device in devices:
            if isinstance(device, dict):
                raw_id = device.get("device_id")
                dev_type = device.get("type")
            else:
                raw_id = device
                dev_type = getattr(device, "type", None)

            if raw_id is None:
                continue
            raw_str = str(raw_id)
            if raw_str in {
                device_id,
                device_id.replace(":", "_"),
                device_id.replace("_", ":"),
            }:
                device_type = str(dev_type) if dev_type is not None else None
                break
    except Exception:
        device_type = None

    for switch_type, config in HELLO_WORLD_SWITCH_CONFIGS.items():
        if config.get("optional") is True:
            continue
        supported_types = config.get("device_types", [])
        if (
            supported_types
            and device_type is not None
            and device_type not in supported_types
        ):
            continue

        switch_entity = HelloWorldSwitch(hass, device_id, switch_type, config)
        switch_list.append(switch_entity)

    return switch_list


class HelloWorldSwitch(ExtrasSwitchEntity):
    """Hello World Switch entity for demonstration purposes.

    This switch entity demonstrates the basic functionality of the Ramses Extras
    framework. It provides a simple ON/OFF switch that can be controlled and
    monitored through Home Assistant.

    The switch integrates with the SimpleEntityManager for automatic state
    coordination, eliminating the need for manual entity synchronization.

    Attributes:
        _is_on (bool): Current state of the switch (True for ON, False for OFF).

    Inherits from:
        ExtrasSwitchEntity: Base class providing common switch functionality.
    """

    def __init__(
        self,
        hass: "HomeAssistant",
        device_id: str,
        switch_type: str,
        config: dict[str, Any],
    ):
        """Initialize Hello World switch entity."""
        super().__init__(hass, device_id, switch_type, config)

        # Initialize state - will be updated when entities manager becomes available
        self._is_on = False

    async def async_added_to_hass(self) -> None:
        """Initialize Hello World switch entity."""
        await super().async_added_to_hass()
        _LOGGER.debug("Hello World switch %s added to hass", self._attr_name)

        # Note: SimpleEntityManager handles state coordination automatically
        # No custom callback registration needed - framework handles coordination

    @property
    def is_on(self) -> bool:
        """Return true if Hello World switch is active.

        Returns the current state of the switch. The state is managed locally and
        automatically coordinated with other entities through the SimpleEntityManager.

        Returns:
            bool: True if the switch is ON, False if the switch is OFF.
        """
        # Use local state - SimpleEntityManager handles coordination automatically
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate Hello World switch."""
        _LOGGER.debug("Activating Hello World switch for %s", self._attr_name)

        # SimpleEntityManager handles coordination automatically
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate Hello World switch."""
        _LOGGER.debug("Deactivating Hello World switch for %s", self._attr_name)

        # SimpleEntityManager handles coordination automatically
        self._is_on = False
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        await super().async_will_remove_from_hass()

        # Note: SimpleEntityManager handles cleanup automatically
        # No custom cleanup needed - framework handles coordination

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        base_attrs = super().extra_state_attributes or {}

        device_id_underscore = self.device_id.replace(":", "_")
        return {
            **base_attrs,
            "hello_world_active": self.is_on,
            "demo_feature": True,
            "binary_sensor_entity": EntityHelpers.generate_entity_name_from_template(
                "binary_sensor",
                "hello_world_status_{device_id}",
                device_id=device_id_underscore,
            ),
        }


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("switch", "hello_world", async_setup_entry)

__all__ = [
    "HelloWorldSwitch",
    "async_setup_entry",
    "create_hello_world_switch",
]
