"""Tests for zone coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.zone_coordinator import (
    ZoneConfig,
    ZoneCoordinator,
    ZoneCoordinatorRegistry,
    ZoneDemandSource,
    ZoneState,
    async_setup_zone_coordinators,
    get_zone_coordinator,
    get_zone_coordinator_registry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass_mock = MagicMock()
    hass_mock.data = {}
    hass_mock.async_create_task = MagicMock()
    return hass_mock


@pytest.fixture
def mock_adapter_registry():
    """Mock zone adapter registry."""
    registry = MagicMock()
    mock_adapter = MagicMock()
    mock_adapter.zone_id = "office"
    mock_adapter.is_available = True
    # Default position data that won't cause errors
    position_data = MagicMock()
    position_data.position = 50
    position_data.is_available = True
    mock_adapter.async_get_position = AsyncMock(return_value=position_data)
    mock_adapter.async_set_position = AsyncMock(return_value=True)
    registry.get_or_create_adapter = MagicMock(return_value=mock_adapter)
    return registry


@pytest.fixture
def mock_arbiter():
    """Mock fan speed arbiter."""
    arbiter = MagicMock()
    arbiter._set_demand_state = MagicMock()
    arbiter.clear_demand_state = MagicMock()
    arbiter.async_commit_state = AsyncMock(return_value=True)
    arbiter.get_active_demands = MagicMock(return_value=[])
    return arbiter


class TestZoneState:
    """Test ZoneState dataclass."""

    def test_zone_state_creation(self):
        """Test creating zone state."""
        from datetime import datetime

        state = ZoneState(
            zone_id="bathroom",
            fan_id="32:123456",
            position=50,
            is_available=True,
            is_controllable=True,
            demand_source=ZoneDemandSource.AUTO,
            demand_reason="Test",
            timestamp=datetime.now(),
        )

        assert state.zone_id == "bathroom"
        assert state.position == 50
        assert state.is_available is True


class TestZoneConfig:
    """Test ZoneConfig dataclass."""

    def test_default_config(self):
        """Test default zone configuration."""
        config = ZoneConfig(zone_id="office")

        assert config.zone_id == "office"
        assert config.priority == 50
        assert config.min_position_for_demand == 10

    def test_custom_config(self):
        """Test custom zone configuration."""
        config = ZoneConfig(
            zone_id="kitchen",
            priority=80,
            min_position_for_demand=20,
            demand_mapping={30: "fan_low", 60: "fan_medium"},
        )

        assert config.priority == 80
        assert config.min_position_for_demand == 20
        assert config.demand_mapping == {30: "fan_low", 60: "fan_medium"}


class TestZoneCoordinator:
    """Test ZoneCoordinator class."""

    def test_coordinator_initialization(self, hass, mock_adapter_registry):
        """Test coordinator initialization."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            assert coordinator.fan_id == "32:123456"
            assert coordinator.is_enabled is True

    def test_set_enabled(self, hass, mock_adapter_registry, mock_arbiter):
        """Test enabling/disabling coordinator."""
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_fan_speed_arbiter",
                return_value=mock_arbiter,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            # Disable
            coordinator.set_enabled(False)
            assert coordinator.is_enabled is False

            # Re-enable
            coordinator.set_enabled(True)
            assert coordinator.is_enabled is True

    def test_configure_zone(self, hass, mock_adapter_registry):
        """Test zone configuration."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            coordinator.configure_zone(
                zone_id="office",
                priority=70,
                min_position_for_demand=15,
            )

            config = coordinator.get_zone_config("office")
            assert config is not None
            assert config.priority == 70
            assert config.min_position_for_demand == 15

    def test_position_to_fan_speed_default_mapping(self, hass, mock_adapter_registry):
        """Test position to fan speed conversion with default mapping."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            assert coordinator._position_to_fan_speed(0) == "fan_auto"
            assert coordinator._position_to_fan_speed(15) == "fan_auto"
            assert coordinator._position_to_fan_speed(20) == "fan_low"
            assert coordinator._position_to_fan_speed(50) == "fan_medium"
            assert coordinator._position_to_fan_speed(80) == "fan_high"
            assert coordinator._position_to_fan_speed(100) == "fan_high"

    def test_position_to_fan_speed_custom_mapping(self, hass, mock_adapter_registry):
        """Test position to fan speed conversion with custom mapping."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            custom_mapping = {
                0: "off",
                25: "low",
                50: "medium",
                75: "high",
            }

            assert coordinator._position_to_fan_speed(10, custom_mapping) == "off"
            assert coordinator._position_to_fan_speed(30, custom_mapping) == "low"
            assert coordinator._position_to_fan_speed(60, custom_mapping) == "medium"
            assert coordinator._position_to_fan_speed(90, custom_mapping) == "high"

    @pytest.mark.asyncio
    async def test_async_update_zone_state(self, hass, mock_adapter_registry):
        """Test updating zone state from adapter."""
        mock_adapter = MagicMock()
        mock_adapter.zone_id = "bathroom"
        mock_adapter.is_available = True
        mock_position = MagicMock()
        mock_position.position = 75
        mock_position.is_available = True
        mock_adapter.async_get_position = AsyncMock(return_value=mock_position)

        mock_adapter_registry.get_or_create_adapter = MagicMock(
            return_value=mock_adapter
        )

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")
            coordinator.configure_zone("bathroom")

            state = await coordinator.async_update_zone_state("bathroom")

            assert state is not None
            assert state.zone_id == "bathroom"
            assert state.position == 75
            assert state.is_available is True

    @pytest.mark.asyncio
    async def test_async_update_zone_state_no_adapter(
        self, hass, mock_adapter_registry
    ):
        """Test updating zone state when no adapter available."""
        mock_adapter_registry.get_or_create_adapter = MagicMock(return_value=None)

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            state = await coordinator.async_update_zone_state("nonexistent")

            assert state is None

    @pytest.mark.asyncio
    async def test_async_evaluate_and_apply_disabled(self, hass, mock_adapter_registry):
        """Test evaluation when coordinator is disabled."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")
            coordinator.set_enabled(False)

            result = await coordinator.async_evaluate_and_apply()

            assert result is False

    @pytest.mark.asyncio
    async def test_async_evaluate_and_apply_no_adapters(
        self, hass, mock_adapter_registry
    ):
        """Test evaluation with no adapters."""
        mock_adapter_registry.get_all_adapters_for_fan = MagicMock(return_value=[])

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=mock_adapter_registry,
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            result = await coordinator.async_evaluate_and_apply()

            assert result is False

    @pytest.mark.asyncio
    async def test_async_evaluate_and_apply_below_threshold(
        self, hass, mock_adapter_registry, mock_arbiter
    ):
        """Test evaluation when zone position is below threshold."""
        mock_adapter = MagicMock()
        mock_adapter.zone_id = "office"
        mock_adapter.is_available = True
        mock_position = MagicMock()
        mock_position.position = 5  # Below default threshold of 10
        mock_position.is_available = True
        mock_adapter.async_get_position = AsyncMock(return_value=mock_position)

        mock_adapter_registry.get_all_adapters_for_fan = MagicMock(
            return_value=[mock_adapter]
        )
        mock_adapter_registry.get_or_create_adapter = MagicMock(
            return_value=mock_adapter
        )

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_fan_speed_arbiter",
                return_value=mock_arbiter,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")
            coordinator.configure_zone(
                "office", priority=50, min_position_for_demand=10
            )

            # Mock the _clear_zone_demand method to avoid async issues
            coordinator._clear_zone_demand = AsyncMock(return_value=False)

            result = await coordinator.async_evaluate_and_apply()

            # Should return False when position is below threshold
            # and no demand was applied
            assert result is False

    @pytest.mark.asyncio
    async def test_async_set_manual_zone_demand(
        self, hass, mock_adapter_registry, mock_arbiter
    ):
        """Test setting manual zone demand."""
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_fan_speed_arbiter",
                return_value=mock_arbiter,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")
            coordinator.configure_zone("office", priority=75)

            result = await coordinator.async_set_manual_zone_demand(
                zone_id="office",
                fan_speed="fan_high",
                reason="Manual test",
            )

            assert result is True
            mock_arbiter._set_demand_state.assert_called_once()
            mock_arbiter.async_commit_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_clear_manual_zone_demand(
        self, hass, mock_adapter_registry, mock_arbiter
    ):
        """Test clearing manual zone demand."""
        # Create a mock demand
        mock_demand = MagicMock()
        mock_demand.feature_id = "zones"
        mock_demand.source_id = "office"
        mock_arbiter.get_active_demands = MagicMock(return_value=[mock_demand])

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_fan_speed_arbiter",
                return_value=mock_arbiter,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")

            result = await coordinator.async_clear_manual_zone_demand("office")

            assert result is True
            mock_arbiter.clear_demand_state.assert_called_once()
            mock_arbiter.async_commit_state.assert_called_once()

    def test_get_diagnostics(self, hass, mock_adapter_registry, mock_arbiter):
        """Test getting coordinator diagnostics."""
        mock_arbiter.get_active_demands = MagicMock(return_value=[])

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_fan_speed_arbiter",
                return_value=mock_arbiter,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "32:123456")
            coordinator.configure_zone("office", priority=60)

            diag = coordinator.get_diagnostics()

            assert diag["fan_id"] == "32:123456"
            assert diag["enabled"] is True
            assert "office" in diag["configured_zones"]
            assert diag["configured_zones"]["office"]["priority"] == 60

    def test_zone_demand_source_enum(self):
        """Test ZoneDemandSource enum values."""
        assert ZoneDemandSource.AUTO.value == "auto"
        assert ZoneDemandSource.HUMIDITY.value == "humidity"
        assert ZoneDemandSource.CO2.value == "co2"
        assert ZoneDemandSource.MANUAL.value == "manual"
        assert ZoneDemandSource.SCHEDULE.value == "schedule"

    @pytest.mark.asyncio
    async def test_async_run_zone_actuation_cycle_with_demand(
        self, hass, mock_adapter_registry
    ):
        """Test actuation cycle drives to max when zone has demand."""
        from custom_components.ramses_extras.framework.helpers.zone_demand import (
            DemandSource,
        )

        mock_adapter = MagicMock()
        mock_adapter.zone_id = "office"
        mock_adapter.is_available = True
        mock_position = MagicMock()
        mock_position.position = 50
        mock_position.is_available = True
        mock_adapter.async_get_position = AsyncMock(return_value=mock_position)
        mock_adapter.async_set_position = AsyncMock(return_value=True)

        mock_adapter_registry.get_or_create_adapter = MagicMock(
            return_value=mock_adapter
        )

        mock_demand_registry = MagicMock()
        mock_demand_registry.has_demand = MagicMock(return_value=True)  # Has demand

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            coordinator.configure_zone(
                "office",
                min_position=0,
                max_position=100,
                is_controllable=True,
            )

            results = await coordinator.async_run_zone_actuation_cycle()

            assert "office" in results
            assert results["office"]["success"] is True
            assert results["office"]["target"] == 100
            mock_adapter.async_set_position.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_async_run_zone_actuation_cycle_no_demand(
        self, hass, mock_adapter_registry
    ):
        """Test actuation cycle commands zones without demand to min position."""
        mock_adapter = MagicMock()
        mock_adapter.zone_id = "office"
        mock_adapter.is_available = True
        position_data = MagicMock()
        position_data.position = 100
        position_data.is_available = True
        mock_adapter.async_get_position = AsyncMock(return_value=position_data)
        mock_adapter.async_set_position = AsyncMock(return_value=True)

        mock_adapter_registry.get_or_create_adapter = MagicMock(
            return_value=mock_adapter
        )

        mock_demand_registry = MagicMock()
        mock_demand_registry.has_demand = MagicMock(return_value=False)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            coordinator.configure_zone(
                "office",
                min_position=0,
                max_position=100,
                is_controllable=True,
            )

            results = await coordinator.async_run_zone_actuation_cycle()

            assert "office" in results
            assert results["office"]["success"] is True
            assert results["office"]["target"] == 0
            mock_adapter.async_set_position.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_async_run_zone_actuation_cycle_skips_when_close(
        self, hass, mock_adapter_registry
    ):
        """Test actuation skips when position difference is small."""
        mock_adapter = MagicMock()
        mock_adapter.zone_id = "office"
        mock_adapter.is_available = True
        position_data = MagicMock()
        position_data.position = 98  # Already very close to max (100)
        position_data.is_available = True
        mock_adapter.async_get_position = AsyncMock(return_value=position_data)
        mock_adapter.async_set_position = AsyncMock(return_value=True)

        mock_adapter_registry.get_or_create_adapter = MagicMock(
            return_value=mock_adapter
        )

        mock_demand_registry = MagicMock()
        mock_demand_registry.has_demand = MagicMock(return_value=True)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            coordinator.configure_zone(
                "office",
                min_position=0,
                max_position=100,
                is_controllable=True,
            )

            results = await coordinator.async_run_zone_actuation_cycle()

            # Zone should be in results but not moved (already close enough)
            assert "office" in results
            # Returns success, just no action
            assert results["office"]["success"] is True
            assert results["office"]["target"] == 100
            # Should NOT call set_position since already within 5% of target
            mock_adapter.async_set_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_run_zone_actuation_cycle_disabled(
        self, hass, mock_adapter_registry
    ):
        """Test actuation cycle returns empty when disabled."""
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            coordinator.set_enabled(False)

            results = await coordinator.async_run_zone_actuation_cycle()

            assert results == {}

    @pytest.mark.asyncio
    async def test_async_run_zone_actuation_cycle_not_controllable(
        self, hass, mock_adapter_registry
    ):
        """Test actuation skips non-controllable zones."""
        mock_adapter = MagicMock()
        mock_adapter.zone_id = "office"
        mock_adapter.is_available = True

        mock_adapter_registry.get_all_adapters_for_fan = MagicMock(
            return_value=[mock_adapter]
        )

        mock_demand_registry = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            coordinator.configure_zone(
                "office",
                min_position=0,
                max_position=100,
                is_controllable=False,  # Not controllable
            )

            results = await coordinator.async_run_zone_actuation_cycle()

            assert "office" not in results

    def test_has_zone_demand(self, hass, mock_adapter_registry):
        """Test has_zone_demand delegates to registry."""
        mock_demand_registry = MagicMock()
        mock_demand_registry.has_demand = MagicMock(return_value=True)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            result = coordinator.has_zone_demand("office")

            assert result is True
            mock_demand_registry.has_demand.assert_called_once_with(
                "18:000730", "office"
            )

    def test_get_zone_demand_breakdown(self, hass, mock_adapter_registry):
        """Test get_zone_demand_breakdown returns source mapping."""
        from custom_components.ramses_extras.framework.helpers.zone_demand import (
            DemandSource,
        )

        mock_demand_registry = MagicMock()
        mock_demand_registry.get_demand_breakdown = MagicMock(
            return_value={
                DemandSource.HUMIDITY: True,
                DemandSource.CO2: False,
            }
        )

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            breakdown = coordinator.get_zone_demand_breakdown("office")

            assert breakdown["HUMIDITY"] is True
            assert breakdown["CO2"] is False

    def test_configure_zone_actuator_params(self, hass, mock_adapter_registry):
        """Test configure_zone accepts actuator parameters."""
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")
            coordinator.configure_zone(
                "office",
                priority=60,
                min_position=10,
                max_position=90,
                is_controllable=True,
            )

            config = coordinator._zone_configs["office"]
            assert config.min_position == 10
            assert config.max_position == 90
            assert config.is_controllable is True

    @pytest.mark.asyncio
    async def test_set_max_open_zones(self, hass, mock_adapter_registry):
        """Test setting max_open_zones cap."""
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")

            # Default should be None (no limit)
            assert coordinator._max_open_zones is None

            # Set a limit
            coordinator.set_max_open_zones(2)
            assert coordinator._max_open_zones == 2

            # Clear the limit
            coordinator.set_max_open_zones(None)
            assert coordinator._max_open_zones is None

    @pytest.mark.asyncio
    async def test_priority_selection_with_max_open_zones(
        self, hass, mock_adapter_registry
    ):
        """Test Phase 5b: priority-based selection when max_open_zones is set."""
        # Create 3 zone adapters with different priorities
        mock_adapters = []
        for zone_id, priority in [
            ("zone_high", 200),
            ("zone_med", 100),
            ("zone_low", 50),
        ]:
            adapter = MagicMock()
            adapter.zone_id = zone_id
            adapter.is_available = True
            position_data = MagicMock()
            position_data.position = 0
            position_data.is_available = True
            adapter.async_get_position = AsyncMock(return_value=position_data)
            adapter.async_set_position = AsyncMock(return_value=True)
            mock_adapters.append(adapter)

        mock_adapter_registry.get_all_adapters_for_fan = MagicMock(
            return_value=mock_adapters
        )

        # All 3 zones have demand
        mock_demand_registry = MagicMock()
        mock_demand_registry.has_demand = MagicMock(return_value=True)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")

            # Configure zones with different priorities
            coordinator.configure_zone(
                "zone_high",
                min_position=0,
                max_position=100,
                is_controllable=True,
                actuation_priority=200,
            )
            coordinator.configure_zone(
                "zone_med",
                min_position=0,
                max_position=100,
                is_controllable=True,
                actuation_priority=100,
            )
            coordinator.configure_zone(
                "zone_low",
                min_position=0,
                max_position=100,
                is_controllable=True,
                actuation_priority=50,
            )

            # Set cap to 2 zones
            coordinator.set_max_open_zones(2)

            results = await coordinator.async_run_zone_actuation_cycle()

            # High and med priority zones should be selected for max
            assert results["zone_high"]["is_selected"] is True
            assert results["zone_high"]["target"] == 100
            assert results["zone_med"]["is_selected"] is True
            assert results["zone_med"]["target"] == 100

            # Low priority zone should NOT be selected, goes to min
            assert results["zone_low"]["is_selected"] is False
            assert results["zone_low"]["target"] == 0

    @pytest.mark.asyncio
    async def test_priority_selection_unlimited(self, hass, mock_adapter_registry):
        """Test all demanding zones go to max when no max_open_zones limit."""
        mock_adapters = []
        for zone_id in ["zone1", "zone2", "zone3"]:
            adapter = MagicMock()
            adapter.zone_id = zone_id
            adapter.is_available = True
            position_data = MagicMock()
            position_data.position = 0
            position_data.is_available = True
            adapter.async_get_position = AsyncMock(return_value=position_data)
            adapter.async_set_position = AsyncMock(return_value=True)
            mock_adapters.append(adapter)

        mock_adapter_registry.get_all_adapters_for_fan = MagicMock(
            return_value=mock_adapters
        )

        mock_demand_registry = MagicMock()
        mock_demand_registry.has_demand = MagicMock(return_value=True)

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
                return_value=mock_adapter_registry,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_demand_registry",
                return_value=mock_demand_registry,
            ),
        ):
            coordinator = ZoneCoordinator(hass, "18:000730")

            for zone_id in ["zone1", "zone2", "zone3"]:
                coordinator.configure_zone(
                    zone_id,
                    min_position=0,
                    max_position=100,
                    is_controllable=True,
                )

            # No limit set (default)
            assert coordinator._max_open_zones is None

            results = await coordinator.async_run_zone_actuation_cycle()

            # All zones should be selected for max
            for zone_id in ["zone1", "zone2", "zone3"]:
                assert results[zone_id]["is_selected"] is True
                assert results[zone_id]["target"] == 100


class TestZoneCoordinatorRegistry:
    """Test ZoneCoordinatorRegistry class."""

    def test_registry_initialization(self, hass):
        """Test registry initialization."""
        registry = ZoneCoordinatorRegistry(hass)

        assert registry._hass == hass
        assert registry._coordinators == {}

    def test_get_or_create_coordinator(self, hass):
        """Test getting or creating coordinator."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)

            coordinator1 = registry.get_or_create_coordinator("32:123456")
            assert coordinator1.fan_id == "32:123456"

            # Second call should return same instance
            coordinator2 = registry.get_or_create_coordinator("32:123456")
            assert coordinator1 is coordinator2

    def test_get_coordinator(self, hass):
        """Test getting existing coordinator."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)
            registry._coordinators["32:123456"] = MagicMock()

            result = registry.get_coordinator("32:123456")
            assert result is not None

            # Nonexistent should return None
            assert registry.get_coordinator("99:999999") is None

    def test_get_coordinator_normalizes_id(self, hass):
        """Test that fan_id is normalized."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)

            # Create with underscore format
            coordinator = registry.get_or_create_coordinator("32_123456")
            assert coordinator.fan_id == "32:123456"

            # Should be found with colon format too
            result = registry.get_coordinator("32:123456")
            assert result is coordinator

    def test_remove_coordinator(self, hass):
        """Test removing coordinator."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)
            mock_coordinator = MagicMock()
            registry._coordinators["32:123456"] = mock_coordinator

            registry.remove_coordinator("32:123456")

            assert "32:123456" not in registry._coordinators
            mock_coordinator.set_enabled.assert_called_once_with(False)

    def test_get_all_coordinators(self, hass):
        """Test getting all coordinators."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)
            coordinator1 = registry.get_or_create_coordinator("32:123456")
            coordinator2 = registry.get_or_create_coordinator("32:999999")

            all_coordinators = registry.get_all_coordinators()

            assert len(all_coordinators) == 2
            assert coordinator1 in all_coordinators
            assert coordinator2 in all_coordinators

    def test_clear(self, hass):
        """Test clearing all coordinators."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)
            mock_coord1 = MagicMock()
            mock_coord2 = MagicMock()
            registry._coordinators["32:123456"] = mock_coord1
            registry._coordinators["32:999999"] = mock_coord2

            registry.clear()

            assert registry._coordinators == {}
            mock_coord1.set_enabled.assert_called_once_with(False)
            mock_coord2.set_enabled.assert_called_once_with(False)

    def test_get_diagnostics(self, hass):
        """Test getting registry diagnostics."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            registry = ZoneCoordinatorRegistry(hass)
            mock_coord = MagicMock()
            mock_coord.get_diagnostics.return_value = {"fan_id": "32:123456"}
            registry._coordinators["32:123456"] = mock_coord

            diag = registry.get_diagnostics()

            assert diag["coordinator_count"] == 1
            assert "32:123456" in diag["coordinators"]


class TestRegistryHelpers:
    """Test helper functions."""

    def test_get_zone_coordinator_registry_creates(self, hass):
        """Test get_zone_coordinator_registry creates new instance."""
        # Clear any existing global state
        import custom_components.ramses_extras.framework.helpers.zone_coordinator as zc_mod  # noqa: E501

        zc_mod._zone_coordinator_registry = None

        registry = get_zone_coordinator_registry(hass)

        assert isinstance(registry, ZoneCoordinatorRegistry)

    def test_get_zone_coordinator_registry_returns_existing(self, hass):
        """Test get_zone_coordinator_registry returns cached instance."""
        registry1 = get_zone_coordinator_registry(hass)
        registry2 = get_zone_coordinator_registry(hass)

        assert registry1 is registry2

    def test_get_zone_coordinator(self, hass):
        """Test get_zone_coordinator helper."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_adapter_registry",
            return_value=MagicMock(),
        ):
            coordinator = get_zone_coordinator(hass, "32:123456")

            assert isinstance(coordinator, ZoneCoordinator)
            assert coordinator.fan_id == "32:123456"

    def test_async_setup_zone_coordinators(self, hass):
        """Test async_setup_zone_coordinators initializes registry."""
        async_setup_zone_coordinators(hass)

        # Should create registry
        import custom_components.ramses_extras.framework.helpers.zone_coordinator as zc_mod  # noqa: E501

        assert zc_mod._zone_coordinator_registry is not None
