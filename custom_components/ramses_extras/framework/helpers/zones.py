"""Zone registry for FAN zones.

This module provides runtime management of zones attached to FAN devices,
following the configuration strategy defined in the ZONES feature section.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import DOMAIN

if TYPE_CHECKING:
    from ...framework.helpers.config.core import ExtrasConfigManager

_LOGGER = logging.getLogger(__name__)

# Zone source types
ZONE_SOURCE_ORCON_NATIVE = "orcon_native"
ZONE_SOURCE_CUSTOM_VALVE = "custom_valve"
ZONE_SOURCE_SHELLY_2PM_GEN3 = "shelly_2pm_gen3"

VALID_ZONE_SOURCES = {
    ZONE_SOURCE_ORCON_NATIVE,
    ZONE_SOURCE_CUSTOM_VALVE,
    ZONE_SOURCE_SHELLY_2PM_GEN3,
}


class ZoneRegistry:
    """Runtime registry for FAN zones.

    This registry provides fast in-memory lookup of zones backed by
    the persisted zones feature configuration.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the zone registry.

        :param hass: Home Assistant instance
        """
        self._hass = hass
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def _get_config_entry(self) -> ConfigEntry | None:
        domain_data = self._hass.data.get(DOMAIN, {})
        config_entry = domain_data.get("config_entry")
        if isinstance(config_entry, ConfigEntry):
            return config_entry
        return None

    def _get_raw_config(self) -> dict[str, Any]:
        config_entry = self._get_config_entry()
        if config_entry is None:
            return {}

        raw_config: dict[str, Any] = {}
        if config_entry.data:
            raw_config.update(config_entry.data)
        if config_entry.options:
            raw_config.update(config_entry.options)
        return raw_config

    def _get_zones_section(self) -> dict[str, Any]:
        # Import here to avoid circular imports
        from ...framework.helpers.config.migration import get_migrated_feature_section

        return get_migrated_feature_section(self._get_raw_config(), "zones")

    def get_zones_for_fan(self, fan_id: str) -> list[dict[str, Any]]:
        """Get all zones for a FAN device.

        :param fan_id: FAN device ID (canonical or legacy format)
        :return: List of zone dicts
        """
        normalized_id = fan_id.replace("_", ":").strip()

        # Check cache first
        if normalized_id in self._cache:
            return self._cache[normalized_id]

        # Import here to avoid circular imports
        from ...framework.helpers.config.model import get_zones_for_fan

        section = self._get_zones_section()
        zones = get_zones_for_fan(section, normalized_id)
        self._cache[normalized_id] = zones
        return zones

    def get_zone(self, fan_id: str, zone_id: str) -> dict[str, Any] | None:
        """Get a specific zone by FAN and zone_id.

        :param fan_id: FAN device ID
        :param zone_id: Zone identifier
        :return: Zone dict or None if not found
        """
        zones = self.get_zones_for_fan(fan_id)
        for zone in zones:
            if zone.get("zone_id") == zone_id:
                return zone
        return None

    def list_all_zones(self) -> dict[str, list[dict[str, Any]]]:
        """List all zones grouped by FAN.

        :return: Dict mapping FAN device IDs to lists of zone dicts
        """
        # Import here to avoid circular imports
        from ...framework.helpers.config.model import get_fan_ids

        section = self._get_zones_section()
        fan_ids = get_fan_ids(section)

        result: dict[str, list[dict[str, Any]]] = {}
        for fan_id in fan_ids:
            zones = self.get_zones_for_fan(fan_id)
            if zones:
                result[fan_id] = zones

        return result

    def find_areas_for_zone(self, fan_id: str, zone_id: str) -> list[str]:
        """Find area-like sensor configurations linked to a zone.

        :param fan_id: FAN device ID
        :param zone_id: Zone identifier
        :return: List of area identifiers
        """
        zone = self.get_zone(fan_id, zone_id)
        if zone is None:
            return []

        # Return areas from zone config if present
        areas = zone.get("areas", [])
        if isinstance(areas, list):
            return areas
        return []

    def find_entities_for_zone(self, fan_id: str, zone_id: str) -> dict[str, str]:
        """Find HA entities linked to a zone.

        :param fan_id: FAN device ID
        :param zone_id: Zone identifier
        :return: Dict mapping entity types to entity IDs
        """
        zone = self.get_zone(fan_id, zone_id)
        if zone is None:
            return {}

        entities: dict[str, str] = {}
        sensors = zone.get("sensors", {})

        # Map sensor entities
        for key in ["humidity_entity", "temperature_entity", "co2_entity"]:
            value = sensors.get(key)
            if value:
                entities[key.replace("_entity", "")] = value

        # Map actuator entities
        actuator = zone.get("actuator", {})
        if actuator.get("entity_id"):
            entities["actuator"] = actuator["entity_id"]

        return entities

    def get_controllable_zones(self, fan_id: str) -> list[dict[str, Any]]:
        """Get zones that support actuation for a FAN.

        :param fan_id: FAN device ID
        :return: List of controllable zone dicts
        """
        zones = self.get_zones_for_fan(fan_id)
        return [
            z for z in zones if z.get("capabilities", {}).get("controllable", False)
        ]

    def export_zones_yaml(self) -> str:
        """Export all zones as strict YAML for support/debugging.

        :return: YAML string representing the zones feature section
        """
        import json

        all_zones = self.list_all_zones()

        # Build canonical feature section structure
        export_data: dict[str, Any] = {"features": {"zones": {"FANs": {}}}}
        fans_section = export_data["features"]["zones"]["FANs"]

        for fan_id, zones in sorted(all_zones.items()):
            fans_section[fan_id] = []
            for zone in zones:
                zone_entry: dict[str, Any] = {
                    "zone_id": zone.get("zone_id"),
                    "label": zone.get("label"),
                    "source_type": zone.get("source_type"),
                    "enabled": zone.get("enabled", True),
                }
                if "sensors" in zone:
                    zone_entry["sensors"] = zone["sensors"]
                if "actuator" in zone:
                    zone_entry["actuator"] = zone["actuator"]
                if "capabilities" in zone:
                    zone_entry["capabilities"] = zone["capabilities"]
                fans_section[fan_id].append(zone_entry)

        # Use JSON as a simple YAML-compatible serialization
        return json.dumps(export_data, indent=2, sort_keys=True)

    def invalidate_cache(self) -> None:
        """Clear the zone cache.

        Call this after config changes to ensure fresh lookups.
        """
        self._cache.clear()
        _LOGGER.debug("Zone cache invalidated")


def get_zone_registry(hass: HomeAssistant) -> ZoneRegistry:
    """Get or create the zone registry.

    :param hass: Home Assistant instance
    :return: ZoneRegistry instance
    """
    domain_data = hass.data.setdefault(DOMAIN, {})

    if "zone_registry" not in domain_data:
        domain_data["zone_registry"] = ZoneRegistry(hass)
        _LOGGER.debug("Created zone registry")

    return domain_data["zone_registry"]  # type: ignore[no-any-return]


def async_setup_zones(hass: HomeAssistant) -> None:
    """Set up zone infrastructure.

    :param hass: Home Assistant instance
    """
    get_zone_registry(hass)
    _LOGGER.info("Zone registry initialized")


__all__ = [
    "ZoneRegistry",
    "get_zone_registry",
    "async_setup_zones",
    "ZONE_SOURCE_ORCON_NATIVE",
    "ZONE_SOURCE_CUSTOM_VALVE",
    "ZONE_SOURCE_SHELLY_2PM_GEN3",
    "VALID_ZONE_SOURCES",
]
