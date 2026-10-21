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


class TestZoneVeto:
    """Test zone veto (inhibit) functionality."""

    def test_signal_creation(self):
        """Test creating a veto signal."""
        from custom_components.ramses_extras.framework.helpers.zone_demand import (
            ZoneVetoSignal,
        )

        signal = ZoneVetoSignal(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
            metadata={"input": "window_contact"},
        )

        assert signal.fan_id == "18:000730"
        assert signal.zone_id == "bedroom"
        assert signal.source == DemandSource.MANUAL
        assert signal.vetoed is True
        assert signal.metadata == {"input": "window_contact"}
        assert isinstance(signal.timestamp, datetime)

    def test_set_and_has_veto(self, registry):
        """Test setting and checking a veto."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        assert registry.has_veto("18:000730", "bedroom") is True

    def test_has_veto_no_sources(self, registry):
        """Test has_veto returns False when nothing registered."""
        assert registry.has_veto("18:000730", "bedroom") is False

    def test_veto_does_not_count_as_demand(self, registry):
        """A veto must not create demand."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        assert registry.has_veto("18:000730", "bedroom") is True
        assert registry.has_demand("18:000730", "bedroom") is False

    def test_demand_does_not_count_as_veto(self, registry):
        """A demand must not create a veto."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        assert registry.has_demand("18:000730", "bedroom") is True
        assert registry.has_veto("18:000730", "bedroom") is False

    def test_multiple_veto_sources(self, registry):
        """Veto persists until every vetoing source releases."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.SCHEDULE,
            vetoed=True,
        )

        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=False,
        )

        assert registry.has_veto("18:000730", "bedroom") is True  # SCHEDULE left

        breakdown = registry.get_veto_breakdown("18:000730", "bedroom")
        assert breakdown[DemandSource.MANUAL] is False
        assert breakdown[DemandSource.SCHEDULE] is True

    def test_clear_veto_specific_source(self, registry):
        """Test clearing a veto for one source."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.REM,
            vetoed=True,
        )

        registry.clear_veto("18:000730", "bedroom", DemandSource.MANUAL)

        assert registry.has_veto("18:000730", "bedroom") is True  # REM still vetoes
        sources = registry.get_veto_sources("18:000730", "bedroom")
        assert DemandSource.REM in sources
        assert DemandSource.MANUAL not in sources

    def test_clear_veto_all_sources(self, registry):
        """Test clearing all vetoes for a zone."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        registry.clear_veto("18:000730", "bedroom")

        assert registry.has_veto("18:000730", "bedroom") is False
        assert registry.get_veto_breakdown("18:000730", "bedroom") == {}

    def test_clear_veto_unknown_zone(self, registry):
        """Test clear_veto on an unknown zone is a no-op."""
        registry.clear_veto("18:000730", "unknown")

    def test_get_all_vetoes_for_fan(self, registry):
        """Test getting all vetoes for a FAN."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )
        registry.set_veto(
            fan_id="18:000731",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        vetoes = registry.get_all_vetoes_for_fan("18:000730")

        assert "bedroom" in vetoes
        assert vetoes["bedroom"][DemandSource.MANUAL] is True

    def test_clear_all_clears_vetoes(self, registry):
        """Test registry.clear() also clears vetoes."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        registry.clear()

        assert registry.has_veto("18:000730", "bedroom") is False

    def test_veto_in_diagnostics(self, registry):
        """Test vetoes appear in diagnostics."""
        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
            metadata={"input": "window_contact"},
        )

        diagnostics = registry.get_diagnostics()

        assert diagnostics["veto_count"] == 1
        veto_entry = diagnostics["vetoes"]["18:000730:bedroom"]["MANUAL"]
        assert veto_entry["vetoed"] is True
        assert veto_entry["metadata"] == {"input": "window_contact"}

    def test_set_veto_fires_event(self, hass, registry):
        """Test set_veto fires ramses_extras_zone_veto_changed."""
        fired = []
        hass.bus.fire = lambda event, data: fired.append((event, data))

        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        assert fired == [
            (
                "ramses_extras_zone_veto_changed",
                {
                    "fan_id": "18:000730",
                    "zone_id": "bedroom",
                    "source": "MANUAL",
                    "vetoed": True,
                },
            )
        ]

    def test_clear_veto_fires_event(self, hass, registry):
        """Test clear_veto fires a release event per source."""
        fired = []
        hass.bus.fire = lambda event, data: fired.append((event, data))

        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )
        fired.clear()

        registry.clear_veto("18:000730", "bedroom", DemandSource.MANUAL)

        assert fired == [
            (
                "ramses_extras_zone_veto_changed",
                {
                    "fan_id": "18:000730",
                    "zone_id": "bedroom",
                    "source": "MANUAL",
                    "vetoed": False,
                },
            )
        ]

    def test_set_veto_without_bus(self, registry):
        """Test set_veto when hass has no bus."""
        registry._hass.bus = None

        registry.set_veto(
            fan_id="18:000730",
            zone_id="bedroom",
            source=DemandSource.MANUAL,
            vetoed=True,
        )

        assert registry.has_veto("18:000730", "bedroom") is True


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

    def test_schedule_zone_actuation_empty_fan_id(self, registry):
        """Test _schedule_zone_actuation with empty fan_id."""
        # Should return early without error
        registry._schedule_zone_actuation("")

    def test_schedule_zone_actuation_no_hass_loop(self, registry):
        """Test _schedule_zone_actuation when hass has no loop."""
        registry._hass.loop = None

        # Should return early without error
        registry._schedule_zone_actuation("18:000730")

    def test_schedule_zone_actuation_missing_methods(self, registry):
        """Test _schedule_zone_actuation when hass methods are missing."""
        registry._hass.loop = MagicMock()
        registry._hass.loop.call_later = None  # Not callable

        # Should return early without error
        registry._schedule_zone_actuation("18:000730")

    def test_clear_demand_unknown_zone(self, registry):
        """Test clear_demand for unknown zone."""
        # Should return early without error
        registry.clear_demand("18:000730", "unknown")

    def test_clear_demand_specific_source_empty_dict(self, registry):
        """Test clear_demand for specific source when dict becomes empty."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        # Clear the only source - should delete the key
        registry.clear_demand("18:000730", "office", DemandSource.HUMIDITY)

        assert registry.has_demand("18:000730", "office") is False

    def test_get_demand_sources_unknown_zone(self, registry):
        """Test get_demand_sources for unknown zone."""
        sources = registry.get_demand_sources("18:000730", "unknown")
        assert sources == []

    def test_set_demand_with_metadata(self, registry):
        """Test set_demand with metadata."""
        metadata = {"threshold": 60, "current": 65}
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
            metadata=metadata,
        )

    def test_set_demand_without_bus(self, registry):
        """Test set_demand when hass has no bus."""
        registry._hass.bus = None

        # Should not raise
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        assert registry.has_demand("18:000730", "office") is True

    def test_clear_demand_without_bus(self, registry):
        """Test clear_demand when hass has no bus."""
        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )
        registry._hass.bus = None

        # Should not raise
        registry.clear_demand("18:000730", "office", DemandSource.HUMIDITY)

    def test_schedule_actuation_with_existing_handle(self, registry):
        """Test a pending handle absorbs the update instead of being reset.

        The actuation cycle evaluates the latest demand/veto state when it
        fires, so a scheduled call already covers newer signals — resetting
        the timer on every signal would starve actuation under a sustained
        signal stream (issue 292).
        """
        import asyncio

        # Mock the event loop
        loop = MagicMock()
        call_later = MagicMock()

        def _swallow_coro(coro, *args, **kwargs):
            coro.close()
            return MagicMock()

        async_create_task = MagicMock(side_effect=_swallow_coro)
        bus = MagicMock()
        fire_event = MagicMock()

        registry._hass.loop = loop
        loop.call_later = call_later
        registry._hass.async_create_task = async_create_task
        registry._hass.bus = bus
        bus.fire = fire_event

        # Set up existing handle
        existing_handle = MagicMock()
        registry._actuation_debounce_handles["18:000730"] = existing_handle

        registry.set_demand(
            fan_id="18:000730",
            zone_id="office",
            source=DemandSource.HUMIDITY,
            has_demand=True,
        )

        # The pending handle is kept (coalesced), not cancelled/re-armed,
        # and no second timer is scheduled
        existing_handle.cancel.assert_not_called()
        call_later.assert_not_called()
        assert registry._actuation_debounce_handles["18:000730"] is existing_handle
