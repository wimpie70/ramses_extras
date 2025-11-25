"""Humidity Control Services.

This module provides services specific to humidity control functionality,
including dehumidification control and humidity threshold management.
"""

import logging
from typing import Any

from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

_LOGGER = logging.getLogger(__name__)


class HumidityServices:
    """Provides humidity control services.

    This class encapsulates all service operations specific to humidity control,
    providing a clean interface for the automation and entities modules.
    """

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize humidity services.

        Args:
            hass: Home Assistant instance
            config_entry: Configuration entry
        """
        self.hass = hass
        self.config_entry = config_entry

        # Service registry
        self._services = {
            "async_activate_dehumidification": self.async_activate_dehumidification,
            "async_deactivate_dehumidification": self.async_deactivate_dehumidification,
            "async_set_fan_speed": self.async_set_fan_speed,
            "async_set_min_humidity": self.async_set_min_humidity,
            "async_set_max_humidity": self.async_set_max_humidity,
            "async_set_offset": self.async_set_offset,
            "async_get_status": self.async_get_status,
        }

        _LOGGER.info("HumidityControl services initialized")

    async def async_activate_dehumidification(self, device_id: str) -> bool:
        """Activate dehumidification for a device.

        Args:
            device_id: Device identifier

        Returns:
            True if successful
        """
        _LOGGER.info(f"Activating dehumidification for device {device_id}")

        try:
            # Find dehumidify switch entity
            dehumidify_entity = await self._find_dehumidify_entity(device_id)
            if not dehumidify_entity:
                _LOGGER.error(f"Dehumidify switch not found for device {device_id}")
                return False

            # Turn on the switch
            await self.hass.services.async_call(
                "switch", SERVICE_TURN_ON, {"entity_id": dehumidify_entity}
            )

            # Set fan speed to HIGH for dehumidification
            success = await self.async_set_fan_speed(device_id, "high")
            if not success:
                _LOGGER.warning(f"Failed to set fan speed for device {device_id}")

            _LOGGER.info(f"Dehumidification activated: {dehumidify_entity}")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to activate dehumidification: {e}")
            return False

    async def async_deactivate_dehumidification(self, device_id: str) -> bool:
        """Deactivate dehumidification for a device.

        Args:
            device_id: Device identifier

        Returns:
            True if successful
        """
        _LOGGER.info(f"Deactivating dehumidification for device {device_id}")

        try:
            # Find dehumidify switch entity
            dehumidify_entity = await self._find_dehumidify_entity(device_id)
            if not dehumidify_entity:
                _LOGGER.error(f"Dehumidify switch not found for device {device_id}")
                return False

            # Turn off the switch
            await self.hass.services.async_call(
                "switch", SERVICE_TURN_OFF, {"entity_id": dehumidify_entity}
            )

            # Reset fan speed to AUTO/normal
            success = await self.async_set_fan_speed(device_id, "auto")
            if not success:
                _LOGGER.warning(f"Failed to set fan auto speed for device {device_id}")

            _LOGGER.info(f"Dehumidification deactivated: {dehumidify_entity}")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to deactivate dehumidification: {e}")
            return False

    async def async_set_fan_speed(self, device_id: str, speed: str) -> bool:
        """Set fan speed without changing switch state.

        Args:
            device_id: Device identifier
            speed: Fan speed ("low", "high", "auto", etc.)

        Returns:
            True if successful
        """
        _LOGGER.info(f"Setting fan speed to {speed} for device {device_id}")

        try:
            # Just set fan speed, don't touch the switch
            fan_entity = await self._find_fan_entity(device_id)
            if fan_entity:
                # Set fan to specified speed
                await self.hass.services.async_call(
                    "fan", "turn_on", {"entity_id": fan_entity, "speed": speed}
                )
                _LOGGER.info(f"Fan speed set to {speed.upper()}: {fan_entity}")
            else:
                _LOGGER.debug(
                    f"Fan entity not found for device {device_id}, "
                    f"skipping speed setting"
                )

            return True

        except Exception as e:
            _LOGGER.error(f"Failed to set fan speed to {speed}: {e}")
            return False

    async def async_set_min_humidity(self, device_id: str, value: float) -> bool:
        """Set minimum humidity threshold.

        Args:
            device_id: Device identifier
            value: Minimum humidity value

        Returns:
            True if successful
        """
        _LOGGER.info(f"Setting min humidity for device {device_id}: {value}%")

        try:
            # Find minimum humidity number entity
            min_entity = await self._find_min_humidity_entity(device_id)
            if not min_entity:
                _LOGGER.error(f"Min humidity entity not found for device {device_id}")
                return False

            # Set the value
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": min_entity, "value": value}
            )

            _LOGGER.info(f"Min humidity set: {min_entity} = {value}%")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to set min humidity: {e}")
            return False

    async def async_set_max_humidity(self, device_id: str, value: float) -> bool:
        """Set maximum humidity threshold.

        Args:
            device_id: Device identifier
            value: Maximum humidity value

        Returns:
            True if successful
        """
        _LOGGER.info(f"Setting max humidity for device {device_id}: {value}%")

        try:
            # Find maximum humidity number entity
            max_entity = await self._find_max_humidity_entity(device_id)
            if not max_entity:
                _LOGGER.error(f"Max humidity entity not found for device {device_id}")
                return False

            # Set the value
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": max_entity, "value": value}
            )

            _LOGGER.info(f"Max humidity set: {max_entity} = {value}%")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to set max humidity: {e}")
            return False

    async def async_set_offset(self, device_id: str, value: float) -> bool:
        """Set humidity offset adjustment.

        Args:
            device_id: Device identifier
            value: Offset value

        Returns:
            True if successful
        """
        _LOGGER.info(f"Setting humidity offset for device {device_id}: {value}")

        try:
            # Find offset number entity
            offset_entity = await self._find_offset_entity(device_id)
            if not offset_entity:
                _LOGGER.error(f"Offset entity not found for device {device_id}")
                return False

            # Set the value
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": offset_entity, "value": value}
            )

            _LOGGER.info(f"Humidity offset set: {offset_entity} = {value}")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to set humidity offset: {e}")
            return False

    async def async_get_status(self, device_id: str) -> dict[str, Any]:
        """Get humidity control status for a device.

        Args:
            device_id: Device identifier

        Returns:
            Status dictionary
        """
        try:
            # Get all humidity-related entities
            indoor_abs = await self._get_entity_state(
                device_id, "indoor_absolute_humidity"
            )
            outdoor_abs = await self._get_entity_state(
                device_id, "outdoor_absolute_humidity"
            )
            min_humidity = await self._get_entity_state(
                device_id, "relative_humidity_minimum"
            )
            max_humidity = await self._get_entity_state(
                device_id, "relative_humidity_maximum"
            )
            offset = await self._get_entity_state(device_id, "absolute_humidity_offset")
            dehumidify_switch = await self._get_entity_state(device_id, "dehumidify")
            dehumidifying_active = await self._get_entity_state(
                device_id, "dehumidifying_active"
            )

            status = {
                "device_id": device_id,
                "entities": {
                    "indoor_absolute_humidity": indoor_abs,
                    "outdoor_absolute_humidity": outdoor_abs,
                    "relative_humidity_minimum": min_humidity,
                    "relative_humidity_maximum": max_humidity,
                    "absolute_humidity_offset": offset,
                    "dehumidify": dehumidify_switch,
                    "dehumidifying_active": dehumidifying_active,
                },
                "automation_state": "unknown",
                "last_update": None,
            }

            # Determine automation state
            if dehumidifying_active and dehumidifying_active.get("state") == "on":
                status["automation_state"] = "dehumidifying"
            elif dehumidify_switch and dehumidify_switch.get("state") == "on":
                status["automation_state"] = "manual"
            else:
                status["automation_state"] = "idle"

            return status

        except Exception as e:
            _LOGGER.error(f"Failed to get humidity status: {e}")
            return {"device_id": device_id, "error": str(e)}

    async def _find_dehumidify_entity(self, device_id: str) -> str | None:
        """Find dehumidify switch entity for a device.

        Args:
            device_id: Device identifier

        Returns:
            Entity ID or None if not found
        """
        device_id_underscore = device_id.replace(":", "_")
        # Use EntityHelpers for consistent entity name generation
        entity_pattern = EntityHelpers.generate_entity_name_from_template(
            "switch", "dehumidify_{device_id}", device_id=device_id_underscore
        )
        return await self._find_entity_by_pattern(entity_pattern)

    async def _find_min_humidity_entity(self, device_id: str) -> str | None:
        """Find minimum humidity number entity for a device.

        Args:
            device_id: Device identifier

        Returns:
            Entity ID or None if not found
        """
        device_id_underscore = device_id.replace(":", "_")
        # Use EntityHelpers for consistent entity name generation
        entity_pattern = EntityHelpers.generate_entity_name_from_template(
            "number",
            "relative_humidity_minimum_{device_id}",
            device_id=device_id_underscore,
        )
        return await self._find_entity_by_pattern(entity_pattern)

    async def _find_max_humidity_entity(self, device_id: str) -> str | None:
        """Find maximum humidity number entity for a device.

        Args:
            device_id: Device identifier

        Returns:
            Entity ID or None if not found
        """
        device_id_underscore = device_id.replace(":", "_")
        # Use EntityHelpers for consistent entity name generation
        entity_pattern = EntityHelpers.generate_entity_name_from_template(
            "number",
            "relative_humidity_maximum_{device_id}",
            device_id=device_id_underscore,
        )
        return await self._find_entity_by_pattern(entity_pattern)

    async def _find_fan_entity(self, device_id: str) -> str | None:
        """Find fan entity for a device.

        Args:
            device_id: Device identifier

        Returns:
            Entity ID or None if not found
        """
        device_id_underscore = device_id.replace(":", "_")
        # Common fan entity patterns for Ramses devices
        fan_patterns = [
            f"fan.ramses_fan_{device_id_underscore}",
            f"fan.ventilation_fan_{device_id_underscore}",
            "fan.32_153289",  # Direct device pattern
        ]

        for pattern in fan_patterns:
            entity_id = await self._find_entity_by_pattern(pattern)
            if entity_id:
                return entity_id

        return None

    async def _find_offset_entity(self, device_id: str) -> str | None:
        """Find humidity offset number entity for a device.

        Args:
            device_id: Device identifier

        Returns:
            Entity ID or None if not found
        """
        device_id_underscore = device_id.replace(":", "_")
        # Use EntityHelpers for consistent entity name generation
        entity_pattern = EntityHelpers.generate_entity_name_from_template(
            "number",
            "absolute_humidity_offset_{device_id}",
            device_id=device_id_underscore,
        )
        return await self._find_entity_by_pattern(entity_pattern)

    async def _find_entity_by_pattern(self, pattern: str) -> str | None:
        """Find entity by pattern.

        Args:
            pattern: Entity pattern to search for

        Returns:
            Entity ID or None if not found
        """
        # Get all states and find matching entity
        states = self.hass.states.async_all()
        for state in states:
            if state.entity_id == pattern:
                return str(state.entity_id)  # Explicitly cast to str

        return None

    async def _get_entity_state(
        self, device_id: str, entity_type: str
    ) -> dict[str, Any] | None:
        """Get state for a specific entity type.

        Args:
            device_id: Device identifier
            entity_type: Type of entity

        Returns:
            State dictionary or None if not found
        """
        # Convert device_id to underscore format for entity lookup
        device_id_underscore = device_id.replace(":", "_")

        # Map entity types to entity patterns using EntityHelpers
        entity_patterns = {
            "indoor_absolute_humidity": (
                EntityHelpers.generate_entity_name_from_template(
                    "sensor",
                    "indoor_absolute_humidity_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
            "outdoor_absolute_humidity": (
                EntityHelpers.generate_entity_name_from_template(
                    "sensor",
                    "outdoor_absolute_humidity_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
            "relative_humidity_minimum": (
                EntityHelpers.generate_entity_name_from_template(
                    "number",
                    "relative_humidity_minimum_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
            "relative_humidity_maximum": (
                EntityHelpers.generate_entity_name_from_template(
                    "number",
                    "relative_humidity_maximum_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
            "absolute_humidity_offset": (
                EntityHelpers.generate_entity_name_from_template(
                    "number",
                    "absolute_humidity_offset_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
            "dehumidify": (
                EntityHelpers.generate_entity_name_from_template(
                    "switch",
                    "dehumidify_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
            "dehumidifying_active": (
                EntityHelpers.generate_entity_name_from_template(
                    "binary_sensor",
                    "dehumidifying_active_{device_id}",
                    device_id=device_id_underscore,
                )
            ),
        }

        pattern = entity_patterns.get(entity_type)
        if not pattern:
            return None

        state = self.hass.states.get(pattern)
        if state:
            return {
                "entity_id": state.entity_id,
                "state": state.state,
                "attributes": dict(state.attributes),
            }

        return None

    def get_service_descriptions(self) -> dict[str, str]:
        """Get descriptions of available services.

        Returns:
            Dictionary mapping service names to descriptions
        """
        return {
            "async_activate_dehumidification": "Activate dehumidification for a device",
            "async_deactivate_dehumidification": "Deactivate dehumidification "
            "for a device",
            "async_set_fan_speed": "Set fan speed without changing switch state",
            "async_set_min_humidity": "Set minimum humidity threshold value",
            "async_set_max_humidity": "Set maximum humidity threshold value",
            "async_set_offset": "Set humidity offset adjustment value",
            "async_get_status": "Get humidity control status",
        }

    def register_services(self) -> None:
        """Register humidity control services with Home Assistant.

        This method should be called during integration setup to register
        custom services that can be called by automations.
        """
        # Service registration would be done here
        # This is a placeholder for the service registration logic


# Service factory function
def create_humidity_services(
    hass: HomeAssistant, config_entry: Any
) -> HumidityServices:
    """Create humidity services instance.

    Args:
        hass: Home Assistant instance
        config_entry: Configuration entry

    Returns:
        HumidityServices instance
    """
    return HumidityServices(hass, config_entry)


__all__ = [
    "HumidityServices",
    "create_humidity_services",
]
