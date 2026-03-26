"""Zone actuator adapters for controllable zones.

This module provides adapter classes for different zone actuator types,
following the normalized zone contract defined in the zones feature section.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ...const import DOMAIN
from .zones import ZoneRegistry, get_zone_registry

if TYPE_CHECKING:
    from datetime import datetime

_LOGGER = logging.getLogger(__name__)


@dataclass
class ZonePosition:
    """Represents a zone valve position with metadata."""

    position: int  # 0-100 percent
    target_position: int | None = None
    is_available: bool = True
    last_updated: datetime | None = None
    source: str = "unknown"


@dataclass
class ZoneAdapterConfig:
    """Configuration for a zone adapter."""

    zone_id: str
    fan_id: str
    source_type: str
    entity_id: str | None = None
    min_position: int = 0
    max_position: int = 100
    enabled: bool = True
    extra_config: dict[str, Any] | None = None


class ZoneAdapterBase(ABC):
    """Abstract base class for zone actuators.

    All zone adapters must implement this interface to provide
    normalized position control and availability reporting.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: ZoneAdapterConfig,
    ) -> None:
        """Initialize the zone adapter.

        Args:
            hass: Home Assistant instance
            config: Adapter configuration
        """
        self._hass = hass
        self._config = config
        self._last_position: ZonePosition | None = None
        self._last_command_time: datetime | None = None

    @property
    def zone_id(self) -> str:
        """Return the zone identifier."""
        return self._config.zone_id

    @property
    def fan_id(self) -> str:
        """Return the parent FAN device identifier."""
        return self._config.fan_id

    @property
    def is_available(self) -> bool:
        """Return True if the actuator is available for control."""
        if not self._config.enabled:
            return False
        return self._check_availability()

    @property
    def min_position(self) -> int:
        """Return the minimum allowed position (safety limit)."""
        return max(0, self._config.min_position)

    @property
    def max_position(self) -> int:
        """Return the maximum allowed position (safety limit)."""
        return min(100, self._config.max_position)

    def clamp_position(self, position: int) -> int:
        """Clamp position to safety limits.

        Args:
            position: Desired position (0-100)

        Returns:
            Position clamped to min/max safety limits
        """
        return max(self.min_position, min(self.max_position, position))

    @abstractmethod
    async def async_get_position(self) -> ZonePosition:
        """Get current zone position.

        Returns:
            ZonePosition with current state
        """

    @abstractmethod
    async def async_set_position(self, position: int) -> bool:
        """Set zone position.

        Args:
            position: Target position (0-100), will be clamped to safety limits

        Returns:
            True if command was sent successfully
        """

    @abstractmethod
    def _check_availability(self) -> bool:
        """Check if the actuator hardware is available.

        Returns:
            True if available for control
        """

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information for this adapter.

        Returns:
            Dictionary with adapter state
        """
        return {
            "zone_id": self.zone_id,
            "fan_id": self.fan_id,
            "source_type": self._config.source_type,
            "entity_id": self._config.entity_id,
            "min_position": self.min_position,
            "max_position": self.max_position,
            "enabled": self._config.enabled,
            "available": self.is_available,
            "last_position": (
                {
                    "position": self._last_position.position,
                    "target_position": self._last_position.target_position,
                    "is_available": self._last_position.is_available,
                    "source": self._last_position.source,
                }
                if self._last_position
                else None
            ),
        }


class OrconNativeZoneAdapter(ZoneAdapterBase):
    """Adapter for ORCON-native zone control.

    Uses the FAN's native zone protocol when available.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: ZoneAdapterConfig,
    ) -> None:
        """Initialize ORCON-native adapter."""
        super().__init__(hass, config)
        self._zone_index: int | None = (
            config.extra_config.get("zone_index") if config.extra_config else None
        )

    def _check_availability(self) -> bool:
        """Check if ORCON-native control is available."""
        # Check if the parent FAN device is available via ramses_cc
        domain_data = self._hass.data.get(DOMAIN, {})
        devices = domain_data.get("devices", {})
        fan_device = devices.get(self.fan_id) or devices.get(
            self.fan_id.replace(":", "_")
        )
        return fan_device is not None

    async def async_get_position(self) -> ZonePosition:
        """Get current zone position from ORCON protocol."""
        from datetime import datetime

        # This would query the FAN device for zone state
        # For now, return unknown position
        position = ZonePosition(
            position=50,  # Unknown - middle position
            is_available=self.is_available,
            last_updated=datetime.now(),
            source="orcon_native",
        )
        self._last_position = position
        return position

    async def async_set_position(self, position: int) -> bool:
        """Set zone position via ORCON protocol."""
        from datetime import datetime

        clamped = self.clamp_position(position)

        # This would send command to FAN device
        _LOGGER.debug(
            "ORCON zone %s (index %s) set to %d%% (clamped from %d%%)",
            self.zone_id,
            self._zone_index,
            clamped,
            position,
        )

        self._last_command_time = datetime.now()
        return True

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information including zone index."""
        diag = super().get_diagnostics()
        diag["zone_index"] = self._zone_index
        return diag


class CustomValveZoneAdapter(ZoneAdapterBase):
    """Adapter for generic custom valve control.

    Controls any HA cover entity as a zone valve.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: ZoneAdapterConfig,
    ) -> None:
        """Initialize custom valve adapter."""
        super().__init__(hass, config)
        self._invert_logic: bool = (
            config.extra_config.get("invert_logic", False)
            if config.extra_config
            else False
        )

    def _check_availability(self) -> bool:
        """Check if the valve entity is available."""
        if not self._config.entity_id:
            return False

        entity = self._hass.states.get(self._config.entity_id)
        if entity is None:
            return False

        # Check if entity is available
        return entity.state not in ("unavailable", "unknown", "none")

    def _position_from_state(self, state: str, attributes: dict[str, Any]) -> int:
        """Extract position from entity state.

        Args:
            state: Entity state string
            attributes: Entity attributes

        Returns:
            Position as percentage (0-100)
        """
        # Try current_position attribute first (standard for covers)
        if "current_position" in attributes:
            pos = attributes["current_position"]
            if isinstance(pos, (int, float)):
                return int(pos)

        # Map state to position
        state_lower = state.lower()
        if state_lower in ("open", "on"):
            return 100
        if state_lower in ("closed", "off"):
            return 0

        # Default to unknown (middle)
        return 50

    async def async_get_position(self) -> ZonePosition:
        """Get current valve position from entity state."""
        from datetime import datetime

        entity = (
            self._hass.states.get(self._config.entity_id)
            if self._config.entity_id
            else None
        )

        if entity is None:
            position = ZonePosition(
                position=50,
                is_available=False,
                last_updated=datetime.now(),
                source="custom_valve",
            )
        else:
            pos_value = self._position_from_state(entity.state, entity.attributes)

            # Invert if configured
            if self._invert_logic:
                pos_value = 100 - pos_value

            position = ZonePosition(
                position=pos_value,
                is_available=self.is_available,
                last_updated=datetime.now(),
                source="custom_valve",
            )

        self._last_position = position
        return position

    async def async_set_position(self, position: int) -> bool:
        """Set valve position via HA service call."""
        from datetime import datetime

        if not self._config.entity_id:
            return False

        clamped = self.clamp_position(position)

        # Invert if configured
        if self._invert_logic:
            clamped = 100 - clamped

        # Use cover.set_cover_position service
        try:
            await self._hass.services.async_call(
                "cover",
                "set_cover_position",
                {"entity_id": self._config.entity_id, "position": clamped},
                blocking=False,
            )

            self._last_command_time = datetime.now()
            _LOGGER.debug(
                "Custom valve %s set to %d%% (clamped from %d%%)",
                self._config.entity_id,
                clamped,
                position,
            )
            return True

        except Exception as err:
            _LOGGER.error(
                "Failed to set valve position for %s: %s", self._config.entity_id, err
            )
            return False

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information including inversion setting."""
        diag = super().get_diagnostics()
        diag["invert_logic"] = self._invert_logic
        return diag


class Shelly2PMGen3ZoneAdapter(CustomValveZoneAdapter):
    """Adapter for Shelly 2PM Gen3 valve control.

    Extends the custom valve adapter with Shelly-specific presets.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: ZoneAdapterConfig,
    ) -> None:
        """Initialize Shelly 2PM Gen3 adapter."""
        super().__init__(hass, config)
        self._channel: int | None = (
            config.extra_config.get("channel", 0) if config.extra_config else 0
        )
        # Shelly 2PM typically needs inverted logic (0% = open, 100% = closed)
        self._invert_logic = True

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information including channel."""
        diag = super().get_diagnostics()
        diag["channel"] = self._channel
        diag["device_type"] = "shelly_2pm_gen3"
        return diag


class ZoneAdapterFactory:
    """Factory for creating zone adapters based on source type."""

    _adapters: dict[str, type[ZoneAdapterBase]] = {
        "orcon_native": OrconNativeZoneAdapter,
        "custom_valve": CustomValveZoneAdapter,
        "shelly_2pm_gen3": Shelly2PMGen3ZoneAdapter,
    }

    @classmethod
    def create_adapter(
        cls,
        hass: HomeAssistant,
        config: ZoneAdapterConfig,
    ) -> ZoneAdapterBase | None:
        """Create a zone adapter for the given configuration.

        Args:
            hass: Home Assistant instance
            config: Adapter configuration

        Returns:
            ZoneAdapterBase instance or None if source type is unknown
        """
        adapter_class = cls._adapters.get(config.source_type)
        if adapter_class is None:
            _LOGGER.error("Unknown zone source type: %s", config.source_type)
            return None

        return adapter_class(hass, config)

    @classmethod
    def register_adapter(
        cls,
        source_type: str,
        adapter_class: type[ZoneAdapterBase],
    ) -> None:
        """Register a custom adapter class.

        Args:
            source_type: Source type identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[source_type] = adapter_class
        _LOGGER.debug("Registered zone adapter for source type: %s", source_type)


class ZoneAdapterRegistry:
    """Registry for active zone adapters.

    Manages the lifecycle and access to zone adapters for all FANs.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the adapter registry."""
        self._hass = hass
        self._adapters: dict[str, ZoneAdapterBase] = {}
        self._zone_registry = get_zone_registry(hass)

    def get_or_create_adapter(
        self,
        fan_id: str,
        zone_id: str,
    ) -> ZoneAdapterBase | None:
        """Get or create an adapter for a zone.

        Args:
            fan_id: FAN device ID
            zone_id: Zone identifier

        Returns:
            ZoneAdapterBase instance or None
        """
        key = f"{fan_id}:{zone_id}"

        # Check if adapter already exists
        if key in self._adapters:
            return self._adapters[key]

        # Get zone config from registry
        zone = self._zone_registry.get_zone(fan_id, zone_id)
        if zone is None:
            return None

        # Build adapter config
        source_type = zone.get("source_type", "custom_valve")
        actuator = zone.get("actuator", {})
        capabilities = zone.get("capabilities", {})

        config = ZoneAdapterConfig(
            zone_id=zone_id,
            fan_id=fan_id,
            source_type=source_type,
            entity_id=actuator.get("entity_id"),
            min_position=capabilities.get("min_position", 0),
            max_position=capabilities.get("max_position", 100),
            enabled=zone.get("enabled", True),
            extra_config=zone.get("extra_config"),
        )

        # Create adapter
        adapter = ZoneAdapterFactory.create_adapter(self._hass, config)
        if adapter:
            self._adapters[key] = adapter

        return adapter

    def get_adapter(self, fan_id: str, zone_id: str) -> ZoneAdapterBase | None:
        """Get an existing adapter for a zone.

        Args:
            fan_id: FAN device ID
            zone_id: Zone identifier

        Returns:
            ZoneAdapterBase instance or None if not found
        """
        key = f"{fan_id}:{zone_id}"
        return self._adapters.get(key)

    def remove_adapter(self, fan_id: str, zone_id: str) -> None:
        """Remove an adapter from the registry.

        Args:
            fan_id: FAN device ID
            zone_id: Zone identifier
        """
        key = f"{fan_id}:{zone_id}"
        self._adapters.pop(key, None)

    def get_all_adapters_for_fan(self, fan_id: str) -> list[ZoneAdapterBase]:
        """Get all adapters for a FAN device.

        Args:
            fan_id: FAN device ID

        Returns:
            List of ZoneAdapterBase instances
        """
        prefix = f"{fan_id}:"
        return [
            adapter for key, adapter in self._adapters.items() if key.startswith(prefix)
        ]

    def clear(self) -> None:
        """Clear all adapters."""
        self._adapters.clear()

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information for all adapters."""
        return {
            "adapter_count": len(self._adapters),
            "adapters": {
                key: adapter.get_diagnostics()
                for key, adapter in self._adapters.items()
            },
        }


def get_zone_adapter_registry(hass: HomeAssistant) -> ZoneAdapterRegistry:
    """Get or create the zone adapter registry.

    Args:
        hass: Home Assistant instance

    Returns:
        ZoneAdapterRegistry instance
    """
    from ...const import DOMAIN

    domain_data = hass.data.setdefault(DOMAIN, {})

    if "zone_adapter_registry" not in domain_data:
        domain_data["zone_adapter_registry"] = ZoneAdapterRegistry(hass)
        _LOGGER.debug("Created zone adapter registry")

    return domain_data["zone_adapter_registry"]  # type: ignore[no-any-return]


def async_setup_zone_adapters(hass: HomeAssistant) -> None:
    """Set up zone adapter infrastructure.

    Args:
        hass: Home Assistant instance
    """
    get_zone_adapter_registry(hass)
    _LOGGER.info("Zone adapter registry initialized")


__all__ = [
    "ZoneAdapterBase",
    "OrconNativeZoneAdapter",
    "CustomValveZoneAdapter",
    "Shelly2PMGen3ZoneAdapter",
    "ZoneAdapterFactory",
    "ZoneAdapterRegistry",
    "ZoneAdapterConfig",
    "ZonePosition",
    "get_zone_adapter_registry",
    "async_setup_zone_adapters",
]
