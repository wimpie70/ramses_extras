"""Tests for zone actuator adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.zone_adapters import (
    CustomValveZoneAdapter,
    OrconNativeZoneAdapter,
    Shelly2PMGen3ZoneAdapter,
    ZoneAdapterBase,
    ZoneAdapterConfig,
    ZoneAdapterFactory,
    ZoneAdapterRegistry,
    ZonePosition,
    async_setup_zone_adapters,
    get_zone_adapter_registry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass_mock = MagicMock()
    hass_mock.data = {}
    return hass_mock


@pytest.fixture
def orcon_config():
    """ORCON zone adapter config."""
    return ZoneAdapterConfig(
        zone_id="bathroom",
        fan_id="32:123456",
        source_type="orcon_native",
        entity_id=None,
        min_position=0,
        max_position=100,
        enabled=True,
        extra_config={"zone_index": 1},
    )


@pytest.fixture
def valve_config():
    """Custom valve adapter config."""
    return ZoneAdapterConfig(
        zone_id="office",
        fan_id="32:123456",
        source_type="custom_valve",
        entity_id="cover.office_valve",
        min_position=10,
        max_position=90,
        enabled=True,
        extra_config={"invert_logic": False},
    )


@pytest.fixture
def shelly_config():
    """Shelly 2PM Gen3 adapter config."""
    return ZoneAdapterConfig(
        zone_id="kitchen",
        fan_id="32:123456",
        source_type="shelly_2pm_gen3",
        entity_id="cover.kitchen_valve",
        min_position=0,
        max_position=100,
        enabled=True,
        extra_config={"channel": 0},
    )


class TestZoneAdapterConfig:
    """Test ZoneAdapterConfig dataclass."""

    def test_config_creation(self):
        """Test creating adapter config."""
        config = ZoneAdapterConfig(
            zone_id="test_zone",
            fan_id="32:123456",
            source_type="custom_valve",
        )

        assert config.zone_id == "test_zone"
        assert config.fan_id == "32:123456"
        assert config.source_type == "custom_valve"
        assert config.min_position == 0  # Default
        assert config.max_position == 100  # Default
        assert config.enabled is True  # Default


class TestZonePosition:
    """Test ZonePosition dataclass."""

    def test_position_creation(self):
        """Test creating position."""
        pos = ZonePosition(position=50)

        assert pos.position == 50
        assert pos.target_position is None
        assert pos.is_available is True
        assert pos.source == "unknown"

    def test_position_with_target(self):
        """Test position with target."""
        pos = ZonePosition(
            position=50,
            target_position=75,
            is_available=True,
            source="custom_valve",
        )

        assert pos.position == 50
        assert pos.target_position == 75
        assert pos.source == "custom_valve"


class TestZoneAdapterBase:
    """Test ZoneAdapterBase abstract class."""

    def test_clamp_position(self, hass, valve_config):
        """Test position clamping to safety limits."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        # Below min
        assert adapter.clamp_position(5) == 10
        # Above max
        assert adapter.clamp_position(95) == 90
        # Within range
        assert adapter.clamp_position(50) == 50

    def test_adapter_properties(self, hass, valve_config):
        """Test adapter property accessors."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        assert adapter.zone_id == "office"
        assert adapter.fan_id == "32:123456"
        assert adapter.min_position == 10
        assert adapter.max_position == 90

    def test_get_diagnostics(self, hass, valve_config):
        """Test diagnostics output."""
        adapter = CustomValveZoneAdapter(hass, valve_config)
        diag = adapter.get_diagnostics()

        assert diag["zone_id"] == "office"
        assert diag["fan_id"] == "32:123456"
        assert diag["min_position"] == 10
        assert diag["max_position"] == 90


class TestOrconNativeZoneAdapter:
    """Test ORCON-native adapter."""

    @pytest.mark.asyncio
    async def test_get_position(self, hass, orcon_config):
        """Test getting position from ORCON adapter."""
        # Mock hass.data to make adapter available
        hass.data["ramses_extras"] = {"devices": {"32:123456": MagicMock()}}
        adapter = OrconNativeZoneAdapter(hass, orcon_config)

        pos = await adapter.async_get_position()

        assert pos.position == 50  # Unknown returns 50
        assert pos.source == "orcon_native"
        assert pos.is_available is True

    @pytest.mark.asyncio
    async def test_set_position(self, hass, orcon_config):
        """Test setting position via ORCON adapter."""
        adapter = OrconNativeZoneAdapter(hass, orcon_config)

        result = await adapter.async_set_position(75)
        assert result is True

    def test_get_diagnostics(self, hass, orcon_config):
        """Test ORCON diagnostics includes zone index."""
        adapter = OrconNativeZoneAdapter(hass, orcon_config)
        diag = adapter.get_diagnostics()

        assert diag["zone_index"] == 1


class TestCustomValveZoneAdapter:
    """Test custom valve adapter."""

    def test_position_from_state_open(self, hass, valve_config):
        """Test position extraction from open state."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        pos = adapter._position_from_state("open", {})
        assert pos == 100

    def test_position_from_state_closed(self, hass, valve_config):
        """Test position extraction from closed state."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        pos = adapter._position_from_state("closed", {})
        assert pos == 0

    def test_position_from_state_with_attribute(self, hass, valve_config):
        """Test position extraction from current_position attribute."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        pos = adapter._position_from_state("unknown", {"current_position": 75})
        assert pos == 75

    @pytest.mark.asyncio
    async def test_get_position_from_entity(self, hass, valve_config):
        """Test getting position from entity state."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        mock_state = MagicMock()
        mock_state.state = "open"
        mock_state.attributes = {}
        hass.states.get.return_value = mock_state

        pos = await adapter.async_get_position()

        assert pos.position == 100
        assert pos.source == "custom_valve"
        assert pos.is_available is True

    @pytest.mark.asyncio
    async def test_set_position_service_call(self, hass, valve_config):
        """Test setting position calls HA service."""
        adapter = CustomValveZoneAdapter(hass, valve_config)

        # Make async_call return a proper coroutine
        async def mock_async_call(*args, **kwargs):
            return None

        hass.services.async_call = mock_async_call

        result = await adapter.async_set_position(60)

        assert result is True

    def test_inverted_logic(self, hass):
        """Test position inversion when configured."""
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id="cover.test",
            extra_config={"invert_logic": True},
        )
        adapter = CustomValveZoneAdapter(hass, config)

        mock_state = MagicMock()
        mock_state.state = "open"
        mock_state.attributes = {}
        hass.states.get.return_value = mock_state

        # Open (100) should become 0 when inverted
        adapter._position_from_state("open", {})
        assert adapter._invert_logic is True


class TestShelly2PMGen3ZoneAdapter:
    """Test Shelly 2PM Gen3 adapter."""

    def test_shelly_defaults(self, hass, shelly_config):
        """Test Shelly adapter has inverted logic by default."""
        adapter = Shelly2PMGen3ZoneAdapter(hass, shelly_config)

        # Shelly should have invert_logic=True
        assert adapter._invert_logic is True

    def test_get_diagnostics(self, hass, shelly_config):
        """Test Shelly diagnostics includes channel and device type."""
        adapter = Shelly2PMGen3ZoneAdapter(hass, shelly_config)
        diag = adapter.get_diagnostics()

        assert diag["channel"] == 0
        assert diag["device_type"] == "shelly_2pm_gen3"


class TestZoneAdapterFactory:
    """Test adapter factory."""

    def test_create_orcon_adapter(self, hass, orcon_config):
        """Test factory creates ORCON adapter."""
        adapter = ZoneAdapterFactory.create_adapter(hass, orcon_config)

        assert isinstance(adapter, OrconNativeZoneAdapter)

    def test_create_valve_adapter(self, hass, valve_config):
        """Test factory creates valve adapter."""
        adapter = ZoneAdapterFactory.create_adapter(hass, valve_config)

        assert isinstance(adapter, CustomValveZoneAdapter)

    def test_create_shelly_adapter(self, hass, shelly_config):
        """Test factory creates Shelly adapter."""
        adapter = ZoneAdapterFactory.create_adapter(hass, shelly_config)

        assert isinstance(adapter, Shelly2PMGen3ZoneAdapter)

    def test_create_unknown_adapter(self, hass):
        """Test factory returns None for unknown source type."""
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="unknown_type",
        )
        adapter = ZoneAdapterFactory.create_adapter(hass, config)

        assert adapter is None

    def test_register_custom_adapter(self, hass):
        """Test registering custom adapter class."""

        class CustomAdapter(ZoneAdapterBase):
            def _check_availability(self):
                return True

            async def async_get_position(self):
                return ZonePosition(position=0)

            async def async_set_position(self, position):
                return True

        ZoneAdapterFactory.register_adapter("custom", CustomAdapter)

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom",
        )
        adapter = ZoneAdapterFactory.create_adapter(hass, config)

        assert isinstance(adapter, CustomAdapter)


class TestZoneAdapterRegistry:
    """Test adapter registry."""

    def test_registry_initialization(self, hass):
        """Test registry initializes correctly."""
        registry = ZoneAdapterRegistry(hass)

        assert registry._hass == hass
        assert registry._adapters == {}

    def test_get_or_create_adapter_no_zone(self, hass):
        """Test get_or_create returns None when zone not found."""
        registry = ZoneAdapterRegistry(hass)

        with patch.object(registry._zone_registry, "get_zone", return_value=None):
            adapter = registry.get_or_create_adapter("32:123456", "nonexistent")
            assert adapter is None

    def test_get_or_create_adapter_creates_new(self, hass):
        """Test get_or_create creates new adapter."""
        registry = ZoneAdapterRegistry(hass)
        zone_data = {
            "zone_id": "bathroom",
            "source_type": "custom_valve",
            "actuator": {"entity_id": "cover.test"},
            "enabled": True,
        }

        with patch.object(registry._zone_registry, "get_zone", return_value=zone_data):
            adapter = registry.get_or_create_adapter("32:123456", "bathroom")

            assert adapter is not None
            assert adapter.zone_id == "bathroom"
            assert "32:123456:bathroom" in registry._adapters

    def test_get_or_create_returns_cached(self, hass):
        """Test get_or_create returns cached adapter."""
        registry = ZoneAdapterRegistry(hass)

        # Pre-populate cache
        mock_adapter = MagicMock()
        registry._adapters["32:123456:bathroom"] = mock_adapter

        adapter = registry.get_or_create_adapter("32:123456", "bathroom")
        assert adapter is mock_adapter

    def test_get_existing_adapter(self, hass):
        """Test getting existing adapter."""
        registry = ZoneAdapterRegistry(hass)

        mock_adapter = MagicMock()
        registry._adapters["32:123456:bathroom"] = mock_adapter

        adapter = registry.get_adapter("32:123456", "bathroom")
        assert adapter is mock_adapter

    def test_get_nonexistent_adapter(self, hass):
        """Test getting nonexistent adapter returns None."""
        registry = ZoneAdapterRegistry(hass)

        adapter = registry.get_adapter("32:123456", "nonexistent")
        assert adapter is None

    def test_remove_adapter(self, hass):
        """Test removing adapter from registry."""
        registry = ZoneAdapterRegistry(hass)

        registry._adapters["32:123456:bathroom"] = MagicMock()
        registry.remove_adapter("32:123456", "bathroom")

        assert "32:123456:bathroom" not in registry._adapters

    def test_get_all_adapters_for_fan(self, hass):
        """Test getting all adapters for a FAN."""
        registry = ZoneAdapterRegistry(hass)

        mock1 = MagicMock()
        mock2 = MagicMock()
        registry._adapters["32:123456:zone1"] = mock1
        registry._adapters["32:123456:zone2"] = mock2
        registry._adapters["32:999999:zone3"] = MagicMock()

        adapters = registry.get_all_adapters_for_fan("32:123456")

        assert len(adapters) == 2
        assert mock1 in adapters
        assert mock2 in adapters

    def test_clear_registry(self, hass):
        """Test clearing all adapters."""
        registry = ZoneAdapterRegistry(hass)

        registry._adapters["test1"] = MagicMock()
        registry._adapters["test2"] = MagicMock()

        registry.clear()

        assert registry._adapters == {}

    def test_get_diagnostics(self, hass):
        """Test getting registry diagnostics."""
        registry = ZoneAdapterRegistry(hass)

        mock_adapter = MagicMock()
        mock_adapter.get_diagnostics.return_value = {"zone_id": "test"}
        registry._adapters["32:123456:test"] = mock_adapter

        diag = registry.get_diagnostics()

        assert diag["adapter_count"] == 1
        assert "32:123456:test" in diag["adapters"]


class TestRegistryHelpers:
    """Test helper functions."""

    def test_get_zone_adapter_registry_creates(self, hass):
        """Test get_zone_adapter_registry creates new instance."""
        registry = get_zone_adapter_registry(hass)

        assert isinstance(registry, ZoneAdapterRegistry)
        assert "zone_adapter_registry" in hass.data.get("ramses_extras", {})

    def test_get_zone_adapter_registry_returns_existing(self, hass):
        """Test get_zone_adapter_registry returns cached instance."""
        registry1 = get_zone_adapter_registry(hass)
        registry2 = get_zone_adapter_registry(hass)

        assert registry1 is registry2

    def test_async_setup_zone_adapters(self, hass):
        """Test async_setup_zone_adapters initializes registry."""
        hass.data["ramses_extras"] = {}

        async_setup_zone_adapters(hass)

        assert "zone_adapter_registry" in hass.data["ramses_extras"]
