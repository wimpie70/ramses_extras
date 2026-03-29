"""Zone demand registry - tracks which zones have active demand from various sources.

This module provides a centralized way for features (humidity_control, co2_control,
etc.) to signal that a zone requires ventilation, and for the zone coordinator
to consume those signals and drive actuators.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class DemandSource(Enum):
    """Source of zone demand."""

    HUMIDITY = auto()
    CO2 = auto()
    MANUAL = auto()
    SCHEDULE = auto()
    OTHER = auto()


@dataclass
class ZoneDemandSignal:
    """A demand signal for a specific zone.

    Attributes:
        fan_id: FAN device ID
        zone_id: Zone identifier
        source: What feature/source generated this demand
        has_demand: True if zone requires ventilation
        timestamp: When the signal was generated
        metadata: Optional additional context
    """

    fan_id: str
    zone_id: str
    source: DemandSource
    has_demand: bool
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class ZoneDemandRegistry:
    """Registry for tracking zone demand signals from various sources.

    This allows features like humidity_control and co2_control to publish
    demand signals without knowing about zone actuation details.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the demand registry."""
        self._hass = hass
        # { (fan_id, zone_id): { source: ZoneDemandSignal } }
        self._demands: dict[tuple[str, str], dict[DemandSource, ZoneDemandSignal]] = {}

    def set_demand(
        self,
        fan_id: str,
        zone_id: str,
        source: DemandSource,
        has_demand: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set demand state for a zone from a specific source.

        Args:
            fan_id: FAN device ID
            zone_id: Zone identifier
            source: Source of the demand signal
            has_demand: True if this source demands ventilation
            metadata: Optional context (thresholds, values, etc.)
        """
        key = (fan_id, zone_id)
        if key not in self._demands:
            self._demands[key] = {}

        self._demands[key][source] = ZoneDemandSignal(
            fan_id=fan_id,
            zone_id=zone_id,
            source=source,
            has_demand=has_demand,
            metadata=metadata or {},
        )

        _LOGGER.debug(
            "Zone demand set: %s:%s source=%s has_demand=%s",
            fan_id,
            zone_id,
            source.name,
            has_demand,
        )

    def clear_demand(
        self,
        fan_id: str,
        zone_id: str,
        source: DemandSource | None = None,
    ) -> None:
        """Clear demand for a zone.

        Args:
            fan_id: FAN device ID
            zone_id: Zone identifier
            source: Specific source to clear, or None for all sources
        """
        key = (fan_id, zone_id)
        if key not in self._demands:
            return

        if source is None:
            del self._demands[key]
        elif source in self._demands[key]:
            del self._demands[key][source]
            if not self._demands[key]:
                del self._demands[key]

    def has_demand(self, fan_id: str, zone_id: str) -> bool:
        """Check if a zone has any active demand.

        Returns True if ANY source reports has_demand=True.
        """
        key = (fan_id, zone_id)
        if key not in self._demands:
            return False

        return any(signal.has_demand for signal in self._demands[key].values())

    def get_demand_breakdown(
        self,
        fan_id: str,
        zone_id: str,
    ) -> dict[DemandSource, bool]:
        """Get demand breakdown by source for a zone.

        Returns dict mapping each source to its demand state.
        """
        key = (fan_id, zone_id)
        if key not in self._demands:
            return {}

        return {
            source: signal.has_demand for source, signal in self._demands[key].items()
        }

    def get_all_demands_for_fan(
        self, fan_id: str
    ) -> dict[str, dict[DemandSource, bool]]:
        """Get all zone demands for a FAN.

        Returns: { zone_id: { source: has_demand } }
        """
        result: dict[str, dict[DemandSource, bool]] = {}
        for (fan, zone), sources in self._demands.items():
            if fan == fan_id:
                result[zone] = {
                    source: signal.has_demand for source, signal in sources.items()
                }
        return result

    def get_demand_sources(
        self,
        fan_id: str,
        zone_id: str,
    ) -> list[DemandSource]:
        """Get list of sources currently demanding for a zone."""
        key = (fan_id, zone_id)
        if key not in self._demands:
            return []

        return [
            source for source, signal in self._demands[key].items() if signal.has_demand
        ]

    def clear(self) -> None:
        """Clear all demand signals."""
        self._demands.clear()

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information."""
        return {
            "zone_count": len(self._demands),
            "demands": {
                f"{fan_id}:{zone_id}": {
                    source.name: {
                        "has_demand": signal.has_demand,
                        "timestamp": signal.timestamp.isoformat(),
                        "metadata": signal.metadata,
                    }
                    for source, signal in sources.items()
                }
                for (fan_id, zone_id), sources in self._demands.items()
            },
        }


def get_zone_demand_registry(hass: HomeAssistant) -> ZoneDemandRegistry:
    """Get or create the zone demand registry.

    Args:
        hass: Home Assistant instance

    Returns:
        ZoneDemandRegistry instance
    """
    from ...const import DOMAIN

    domain_data = hass.data.setdefault(DOMAIN, {})

    if "zone_demand_registry" not in domain_data:
        domain_data["zone_demand_registry"] = ZoneDemandRegistry(hass)
        _LOGGER.debug("Created zone demand registry")

    return domain_data["zone_demand_registry"]  # type: ignore[no-any-return]


__all__ = [
    "DemandSource",
    "ZoneDemandSignal",
    "ZoneDemandRegistry",
    "get_zone_demand_registry",
]
