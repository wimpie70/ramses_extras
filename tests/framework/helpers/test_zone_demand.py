"""Tests for zone demand registry."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.zone_demand import (
    DemandSource,
    ZoneDemandRegistry,
    ZoneDemandSignal,
    get_zone_demand_registry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass_mock = MagicMock()
    hass_mock.data = {}
    return hass_mock


@pytest.fixture
def registry(hass):
    """Create a fresh ZoneDemandRegistry."""
    return ZoneDemandRegistry(hass)


class TestZoneDemandSignal:
    """Test ZoneDemandSignal dataclass."""

    def test_signal_creation(self):
        """Test creating a demand signal."""
        signal = ZoneDemandSignal(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
            metadata={"threshold": 60, "current": 65},
        )

        assert signal.fan_id == "18:000730"
        assert signal.zone_id == "office"
        assert signal.source == DemandSource.HUMIDITY
        assert signal.has_demand is True
        assert signal.metadata == {"threshold": 60, "current": 65}
        assert isinstance(signal.timestamp, datetime)


class TestZoneDemandRegistry:
    """Test ZoneDemandRegistry functionality."""

    def test_set_and_get_demand(self, registry):
        """Test setting and checking demand."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        assert registry.has_demand("18:000730", "office") is True

    def test_set_demand_false(self, registry):
        """Test setting demand to False."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=False,
        )

        assert registry.has_demand("18:000730", "office") is False

    def test_has_demand_no_sources(self, registry):
        """Test has_demand returns False when no sources registered."""
        assert registry.has_demand("18:000730", "office") is False

    def test_multiple_sources_any_true(self, registry):
        """Test has_demand returns True if ANY source has demand."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=False,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.CO2,
            has_demand=True,
        )

        assert registry.has_demand("18:000730", "office") is True

    def test_multiple_sources_all_false(self, registry):
        """Test has_demand returns False if all sources have no demand."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=False,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.CO2,
            has_demand=False,
        )

        assert registry.has_demand("18:000730", "office") is False

    def test_get_demand_breakdown(self, registry):
        """Test getting demand breakdown by source."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.CO2,
            has_demand=False,
        )

        breakdown = registry.get_demand_breakdown("18:000730", "office")

        assert breakdown[DemandSource.HUMIDITY] is True
        assert breakdown[DemandSource.CO2] is False

    def test_get_demand_breakdown_empty(self, registry):
        """Test getting demand breakdown for unknown zone."""
        breakdown = registry.get_demand_breakdown("18:000730", "unknown")

        assert breakdown == {}

    def test_get_all_demands_for_fan(self, registry):
        """Test getting all demands for a FAN."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="bathroom",
            source=DemandSource.CO2,
            has_demand=False,
        )
        # Different FAN
        registry.set_demand(
            fan_id="18:000731",
            zone_id="kitchen",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        demands = registry.get_all_demands_for_fan("18:000730")

        assert "office" in demands
        assert "bathroom" in demands
        assert "kitchen" not in demands  # Different FAN
        assert demands["office"][DemandSource.HUMIDITY] is True
        assert demands["bathroom"][DemandSource.CO2] is False

    def test_get_demand_sources(self, registry):
        """Test getting list of active demand sources."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.CO2,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.MANUAL,
            has_demand=False,
        )

        sources = registry.get_demand_sources("18:000730", "office")

        assert DemandSource.HUMIDITY in sources
        assert DemandSource.CO2 in sources
        assert DemandSource.MANUAL not in sources

    def test_clear_demand_specific_source(self, registry):
        """Test clearing demand for a specific source."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.CO2,
            has_demand=True,
        )

        registry.clear_demand("18:000730", "office", DemandSource.HUMIDITY)

        assert registry.has_demand("18:000730", "office") is True  # CO2 still active
        breakdown = registry.get_demand_breakdown("18:000730", "office")
        assert DemandSource.HUMIDITY not in breakdown

    def test_clear_demand_all_sources(self, registry):
        """Test clearing all demands for a zone."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.CO2,
            has_demand=True,
        )

        registry.clear_demand("18:000730", "office")

        assert registry.has_demand("18:000730", "office") is False

    def test_clear_all(self, registry):
        """Test clearing entire registry."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        registry.clear()

        assert registry.has_demand("18:000730", "office") is False

    def test_get_diagnostics(self, registry):
        """Test getting diagnostic information."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
            metadata={"threshold": 60},
        )

        diagnostics = registry.get_diagnostics()

        assert diagnostics["zone_count"] == 1
        assert "18:000730:office" in diagnostics["demands"]
        assert (
            diagnostics["demands"]["18:000730:office"]["HUMIDITY"]["has_demand"] is True
        )

    def test_different_zones_same_fan(self, registry):
        """Test that different zones for same FAN are tracked separately."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000730",
            zone_id="bathroom",
            source=DemandSource.HUMIDITY,
            has_demand=False,
        )

        assert registry.has_demand("18:000730", "office") is True
        assert registry.has_demand("18:000730", "bathroom") is False

    def test_same_zone_different_fans(self, registry):
        """Test that same zone ID on different FANs are tracked separately."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry.set_demand(
            fan_id="18:000731",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=False,
        )

        assert registry.has_demand("18:000730", "office") is True
        assert registry.has_demand("18:000731", "office") is False


class TestGetZoneDemandRegistry:
    """Test get_zone_demand_registry function."""

    def test_creates_registry_if_not_exists(self, hass):
        """Test that function creates registry if not exists."""
        from custom_components.ramses_extras.const import DOMAIN

        hass.data = {DOMAIN: {}}

        registry = get_zone_demand_registry(hass)

        assert isinstance(registry, ZoneDemandRegistry)
        assert "zone_demand_registry" in hass.data[DOMAIN]

    def test_returns_existing_registry(self, hass):
        """Test that function returns existing registry."""
        from custom_components.ramses_extras.const import DOMAIN

        existing_registry = ZoneDemandRegistry(hass)
        hass.data = {DOMAIN: {"zone_demand_registry": existing_registry}}

        registry = get_zone_demand_registry(hass)

        assert registry is existing_registry

    def test_creates_domain_data_if_needed(self, hass):
        """Test that function creates domain data dict if needed."""
        from custom_components.ramses_extras.const import DOMAIN

        hass.data = {}

        get_zone_demand_registry(hass)

        assert DOMAIN in hass.data
        assert "zone_demand_registry" in hass.data[DOMAIN]
