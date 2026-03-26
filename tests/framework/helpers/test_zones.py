"""Tests for zone registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.zones import (
    VALID_ZONE_SOURCES,
    ZONE_SOURCE_CUSTOM_VALVE,
    ZONE_SOURCE_ORCON_NATIVE,
    ZONE_SOURCE_SHELLY_2PM_GEN3,
    ZoneRegistry,
    async_setup_zones,
    get_zone_registry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass_mock = MagicMock()
    hass_mock.data = {}
    return hass_mock


@pytest.fixture
def registry(hass):
    """Create a ZoneRegistry with mocked dependencies."""
    return ZoneRegistry(hass)


class TestZoneRegistryInitialization:
    """Test ZoneRegistry initialization and setup."""

    def test_registry_initialization(self, hass):
        """Test ZoneRegistry initializes correctly."""
        registry = ZoneRegistry(hass)

        assert registry._hass == hass
        assert registry._cache == {}

    def test_get_zone_registry_creates_instance(self, hass):
        """Test get_zone_registry creates new instance."""
        registry = get_zone_registry(hass)

        assert isinstance(registry, ZoneRegistry)
        assert "zone_registry" in hass.data["ramses_extras"]

    def test_get_zone_registry_returns_existing(self, hass):
        """Test get_zone_registry returns cached instance."""
        registry1 = get_zone_registry(hass)
        registry2 = get_zone_registry(hass)

        assert registry1 is registry2

    def test_async_setup_zones(self, hass):
        """Test async_setup_zones initializes registry."""
        hass.data["ramses_extras"] = {}

        async_setup_zones(hass)

        assert "zone_registry" in hass.data["ramses_extras"]


class TestZoneSourceTypes:
    """Test zone source type constants."""

    def test_valid_zone_sources(self):
        """Test valid zone source types are defined."""
        assert ZONE_SOURCE_ORCON_NATIVE in VALID_ZONE_SOURCES
        assert ZONE_SOURCE_CUSTOM_VALVE in VALID_ZONE_SOURCES
        assert ZONE_SOURCE_SHELLY_2PM_GEN3 in VALID_ZONE_SOURCES

    def test_valid_zone_sources_count(self):
        """Test correct number of valid zone sources."""
        assert len(VALID_ZONE_SOURCES) == 3


class TestGetZonesForFan:
    """Test get_zones_for_fan method."""

    def test_get_zones_for_fan_no_manager(self, registry, hass):
        """Test get_zones_for_fan returns empty when no config manager."""
        hass.data["ramses_extras"] = {}

        result = registry.get_zones_for_fan("32:123456")

        assert result == []

    def test_get_zones_for_fan_empty(self, registry, hass):
        """Test get_zones_for_fan returns empty when no zones."""
        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = []
            mock_get_manager.return_value = mock_manager

            result = registry.get_zones_for_fan("32:123456")

            assert result == []

    def test_get_zones_for_fan_with_zones(self, registry, hass):
        """Test get_zones_for_fan returns zones."""
        zones = [
            {"zone_id": "bathroom", "label": "Bathroom", "source_type": "orcon_native"},
            {"zone_id": "office", "label": "Office", "source_type": "custom_valve"},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.get_zones_for_fan("32:123456")

            assert len(result) == 2
            assert result[0]["zone_id"] == "bathroom"
            assert result[1]["zone_id"] == "office"

    def test_get_zones_caching(self, registry, hass):
        """Test get_zones_for_fan caches results."""
        zones = [{"zone_id": "test", "label": "Test Zone"}]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            # First call should cache
            result1 = registry.get_zones_for_fan("32:123456")
            # Change the mock return value
            mock_manager.get_fan_zones.return_value = []
            # Second call should use cached value
            result2 = registry.get_zones_for_fan("32:123456")

            assert result1 == result2
            assert len(result2) == 1


class TestGetZone:
    """Test get_zone method."""

    def test_get_zone_found(self, registry, hass):
        """Test get_zone returns zone when found."""
        zones = [
            {"zone_id": "bathroom", "label": "Bathroom"},
            {"zone_id": "office", "label": "Office"},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.get_zone("32:123456", "office")

            assert result is not None
            assert result["zone_id"] == "office"
            assert result["label"] == "Office"

    def test_get_zone_not_found(self, registry, hass):
        """Test get_zone returns None when not found."""
        zones = [{"zone_id": "bathroom", "label": "Bathroom"}]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.get_zone("32:123456", "office")

            assert result is None


class TestListAllZones:
    """Test list_all_zones method."""

    def test_list_all_zones_empty(self, registry, hass):
        """Test list_all_zones returns empty when no config manager."""
        hass.data["ramses_extras"] = {}

        result = registry.list_all_zones()

        assert result == {}

    def test_list_all_zones(self, registry, hass):
        """Test list_all_zones returns all zones grouped by FAN."""
        with (
            patch.object(registry, "_get_config_manager") as mock_get_manager,
            patch(
                "custom_components.ramses_extras.framework.helpers.config.model.get_fan_ids"
            ) as mock_fan_ids,
        ):
            mock_manager = MagicMock()
            mock_manager._config = {"features": {"zones": {"FANs": {}}}}
            # Mock get_fan_zones to return different zones per FAN
            mock_manager.get_fan_zones.side_effect = lambda fan_id: {
                "32:111111": [{"zone_id": "bathroom", "label": "Bathroom"}],
                "32:222222": [{"zone_id": "office", "label": "Office"}],
            }.get(fan_id, [])
            mock_get_manager.return_value = mock_manager
            mock_fan_ids.return_value = ["32:111111", "32:222222"]

            result = registry.list_all_zones()

            assert "32:111111" in result
            assert "32:222222" in result


class TestFindAreasForZone:
    """Test find_areas_for_zone method."""

    def test_find_areas_for_zone(self, registry, hass):
        """Test find_areas_for_zone returns areas from zone config."""
        zones = [
            {"zone_id": "bathroom", "label": "Bathroom", "areas": ["area1", "area2"]},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.find_areas_for_zone("32:123456", "bathroom")

            assert result == ["area1", "area2"]

    def test_find_areas_for_zone_no_areas(self, registry, hass):
        """Test find_areas_for_zone returns empty when no areas defined."""
        zones = [{"zone_id": "bathroom", "label": "Bathroom"}]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.find_areas_for_zone("32:123456", "bathroom")

            assert result == []


class TestFindEntitiesForZone:
    """Test find_entities_for_zone method."""

    def test_find_entities_for_zone_with_sensors(self, registry, hass):
        """Test find_entities_for_zone returns sensor entities."""
        zones = [
            {
                "zone_id": "bathroom",
                "label": "Bathroom",
                "sensors": {
                    "humidity_entity": "sensor.bathroom_humidity",
                    "temperature_entity": "sensor.bathroom_temp",
                    "co2_entity": "sensor.bathroom_co2",
                },
            },
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.find_entities_for_zone("32:123456", "bathroom")

            assert result["humidity"] == "sensor.bathroom_humidity"
            assert result["temperature"] == "sensor.bathroom_temp"
            assert result["co2"] == "sensor.bathroom_co2"

    def test_find_entities_for_zone_with_actuator(self, registry, hass):
        """Test find_entities_for_zone returns actuator entity."""
        zones = [
            {
                "zone_id": "office",
                "label": "Office",
                "actuator": {"entity_id": "cover.office_valve"},
            },
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.find_entities_for_zone("32:123456", "office")

            assert result["actuator"] == "cover.office_valve"


class TestGetControllableZones:
    """Test get_controllable_zones method."""

    def test_get_controllable_zones(self, registry, hass):
        """Test get_controllable_zones returns only controllable zones."""
        zones = [
            {
                "zone_id": "bathroom",
                "label": "Bathroom",
                "capabilities": {"controllable": True},
            },
            {
                "zone_id": "office",
                "label": "Office",
                "capabilities": {"controllable": False},
            },
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_zones.return_value = zones
            mock_get_manager.return_value = mock_manager

            result = registry.get_controllable_zones("32:123456")

            assert len(result) == 1
            assert result[0]["zone_id"] == "bathroom"


class TestExportZonesYaml:
    """Test export_zones_yaml method."""

    def test_export_zones_yaml(self, registry, hass):
        """Test export_zones_yaml returns valid structure."""
        with patch.object(registry, "list_all_zones") as mock_list:
            mock_list.return_value = {
                "32:123456": [
                    {
                        "zone_id": "bathroom",
                        "label": "Bathroom",
                        "source_type": "orcon_native",
                        "enabled": True,
                    }
                ],
            }

            yaml_str = registry.export_zones_yaml()

            assert "features" in yaml_str
            assert "zones" in yaml_str
            assert "32:123456" in yaml_str
            assert "bathroom" in yaml_str


class TestInvalidateCache:
    """Test invalidate_cache method."""

    def test_invalidate_cache(self, registry, hass):
        """Test invalidate_cache clears the cache."""
        # Pre-populate cache
        registry._cache["32:123456"] = [{"zone_id": "test"}]

        registry.invalidate_cache()

        assert registry._cache == {}
