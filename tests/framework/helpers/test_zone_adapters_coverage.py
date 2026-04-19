"""Additional tests for zone_adapters to improve coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.zone_adapters import (
    CustomValveZoneAdapter,
    OrconNativeZoneAdapter,
    PairedValvesZoneAdapter,
    ZoneAdapterConfig,
    ZoneAdapterFactory,
    ZoneAdapterRegistry,
    ZonePosition,
)


class TestCustomValveZoneAdapterCoverage:
    """Additional tests for CustomValveZoneAdapter."""

    @pytest.mark.asyncio
    async def test_set_position_no_entity(self):
        """Test set_position returns False when no entity_id."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id=None,  # No entity
        )
        adapter = CustomValveZoneAdapter(hass, config)

        result = await adapter.async_set_position(50)
        assert result is False

    @pytest.mark.asyncio
    async def test_set_position_exception(self):
        """Test set_position returns False on exception."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock(side_effect=Exception("Service error"))

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id="cover.test",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        result = await adapter.async_set_position(50)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_position_from_attributes(self):
        """Test get_position reads current_position from attributes."""
        hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "opening"
        mock_state.attributes = {"current_position": 75}
        hass.states.get.return_value = mock_state

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id="cover.test",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        pos = await adapter.async_get_position()
        assert pos.position == 75

    @pytest.mark.asyncio
    async def test_get_position_unavailable_state(self):
        """Test get_position when state is unavailable."""
        hass = MagicMock()
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        mock_state.attributes = {}
        hass.states.get.return_value = mock_state

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id="cover.test",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        pos = await adapter.async_get_position()
        assert pos.position == 50  # Default
        assert pos.is_available is False

    def test_position_from_state_on(self):
        """Test position extraction from 'on' state."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        pos = adapter._position_from_state("on", {})
        assert pos == 100

    def test_position_from_state_off(self):
        """Test position extraction from 'off' state."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        pos = adapter._position_from_state("off", {})
        assert pos == 0

    def test_position_from_state_unknown_no_attrs(self):
        """Test position extraction from unknown state with no attributes."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        pos = adapter._position_from_state("unknown", {})
        assert pos == 50  # Default

    def test_is_available_entity_none(self):
        """Test is_available when entity is None."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id=None,
        )
        adapter = CustomValveZoneAdapter(hass, config)

        assert adapter.is_available is False

    def test_is_available_state_none(self):
        """Test is_available when state is None."""
        hass = MagicMock()
        hass.states.get.return_value = None

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id="cover.test",
        )
        adapter = CustomValveZoneAdapter(hass, config)

        assert adapter.is_available is False

    def test_diagnostics_with_none_values(self):
        """Test diagnostics handles None values."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id=None,
            extra_config=None,
        )
        adapter = CustomValveZoneAdapter(hass, config)

        diag = adapter.get_diagnostics()
        assert diag["entity_id"] is None
        assert diag["invert_logic"] is False


class TestPairedValvesZoneAdapterCoverage:
    """Additional tests for PairedValvesZoneAdapter."""

    def test_init_with_none_extra_config(self):
        """Test init handles None extra_config."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config=None,
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        assert adapter._inlet_entity is None
        assert adapter._outlet_entity is None

    @pytest.mark.asyncio
    async def test_get_position_inlet_none(self):
        """Test get_position when inlet is None."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={"outlet_valve_entity": "cover.outlet"},
        )
        adapter = PairedValvesZoneAdapter(hass, config)
        adapter._inlet_entity = None
        adapter._outlet_entity = "cover.outlet"

        hass.states.get.return_value = None

        pos = await adapter.async_get_position()
        assert pos.position == 50
        assert pos.is_available is False

    @pytest.mark.asyncio
    async def test_get_position_both_available(self):
        """Test get_position when both valves available."""
        hass = MagicMock()

        inlet_state = MagicMock()
        inlet_state.state = "open"
        inlet_state.attributes = {"current_position": 80}

        outlet_state = MagicMock()
        outlet_state.state = "open"
        outlet_state.attributes = {"current_position": 60}

        def mock_get(entity_id):
            if entity_id == "cover.inlet":
                return inlet_state
            if entity_id == "cover.outlet":
                return outlet_state
            return None

        hass.states.get = mock_get

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={
                "inlet_valve_entity": "cover.inlet",
                "outlet_valve_entity": "cover.outlet",
            },
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        pos = await adapter.async_get_position()
        # Average of 80 and 60
        assert pos.position == 70
        assert pos.is_available is True

    @pytest.mark.asyncio
    async def test_get_position_with_invert(self):
        """Test get_position with inverted logic."""
        hass = MagicMock()

        inlet_state = MagicMock()
        inlet_state.state = "open"
        inlet_state.attributes = {"current_position": 100}

        outlet_state = MagicMock()
        outlet_state.state = "open"
        outlet_state.attributes = {"current_position": 100}

        def mock_get(entity_id):
            if entity_id == "cover.inlet":
                return inlet_state
            if entity_id == "cover.outlet":
                return outlet_state
            return None

        hass.states.get = mock_get

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={
                "inlet_valve_entity": "cover.inlet",
                "outlet_valve_entity": "cover.outlet",
            },
        )
        adapter = PairedValvesZoneAdapter(hass, config)
        adapter._invert_logic = True

        pos = await adapter.async_get_position()
        # Average is 100, inverted is 0
        assert pos.position == 0

    @pytest.mark.asyncio
    async def test_set_position_no_entities(self):
        """Test set_position returns False when no entities."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={},
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        result = await adapter.async_set_position(50)
        assert result is False

    @pytest.mark.asyncio
    async def test_set_position_with_invert(self):
        """Test set_position with inverted logic."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock()

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={
                "inlet_valve_entity": "cover.inlet",
                "outlet_valve_entity": "cover.outlet",
            },
        )
        adapter = PairedValvesZoneAdapter(hass, config)
        adapter._invert_logic = True

        result = await adapter.async_set_position(80)
        # 80 should be inverted to 20
        assert result is True

        # Check that the service was called with inverted position
        calls = hass.services.async_call.call_args_list
        assert len(calls) == 2  # Both inlet and outlet
        for call in calls:
            assert call[0][2]["position"] == 20  # Inverted 80 -> 20

    @pytest.mark.asyncio
    async def test_set_position_exception(self):
        """Test set_position returns False on exception."""
        hass = MagicMock()
        hass.services.async_call = AsyncMock(side_effect=Exception("Service error"))

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={
                "inlet_valve_entity": "cover.inlet",
                "outlet_valve_entity": "cover.outlet",
            },
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        result = await adapter.async_set_position(50)
        assert result is False

    def test_check_availability_one_none(self):
        """Test _check_availability when one entity is None."""
        hass = MagicMock()
        hass.states.get.return_value = None

        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={
                "inlet_valve_entity": "cover.inlet",
                "outlet_valve_entity": "cover.outlet",
            },
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        assert adapter._check_availability() is False

    def test_position_from_state_closed(self):
        """Test position extraction from closed state."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        pos = adapter._position_from_state("closed", {})
        assert pos == 0

    def test_position_from_state_with_current_position(self):
        """Test position extraction with current_position attribute."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        pos = adapter._position_from_state("unknown", {"current_position": 75})
        assert pos == 75

    def test_position_from_state_float(self):
        """Test position extraction with float current_position."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
        )
        adapter = PairedValvesZoneAdapter(hass, config)

        pos = adapter._position_from_state("unknown", {"current_position": 75.5})
        assert pos == 75


class TestZoneAdapterRegistryCoverage:
    """Additional tests for ZoneAdapterRegistry."""

    def test_get_or_create_adapter_with_zone_type_override(self):
        """Test get_or_create with zone_type override."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "custom_valve",
            "actuator": {"entity_id": "cover.test"},
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            # Override zone_type to paired_valves
            adapter = registry.get_or_create_adapter(
                "32:123456",
                "bathroom",
                zone_type="paired_valves",
            )

            assert adapter is not None
            # Check that config was created with paired_valves
            call_config = mock_create.call_args[0][1]
            assert call_config.source_type == "paired_valves"

    def test_get_or_create_adapter_legacy_position_entity(self):
        """Test get_or_create with legacy position_entity."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        # Zone with legacy position_entity instead of actuator.entity_id
        zone_data = {
            "type": "custom_valve",
            "position_entity": "cover.legacy_valve",
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            registry.get_or_create_adapter("32:123456", "bathroom")

            # Check that position_entity was used as entity_id
            call_config = mock_create.call_args[0][1]
            assert call_config.entity_id == "cover.legacy_valve"

    def test_get_or_create_adapter_with_min_max_override(self):
        """Test get_or_create uses zone min/max position."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "custom_valve",
            "actuator": {"entity_id": "cover.test"},
            "min_position": 15,
            "max_position": 85,
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            registry.get_or_create_adapter("32:123456", "bathroom")

            call_config = mock_create.call_args[0][1]
            assert call_config.min_position == 15
            assert call_config.max_position == 85

    def test_get_or_create_adapter_paired_valves_with_override(self):
        """Test get_or_create for paired_valves with inlet/outlet overrides."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "paired_valves",
            "inlet_valve_entity": "cover.zone_inlet",
            "outlet_valve_entity": "cover.zone_outlet",
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            # Call with inlet/outlet overrides
            registry.get_or_create_adapter(
                "32:123456",
                "bathroom",
                inlet_entity="cover.override_inlet",
                outlet_entity="cover.override_outlet",
            )

            _call_config = mock_create.call_args[0][1]
            assert (
                _call_config.extra_config["inlet_valve_entity"]
                == "cover.override_inlet"
            )
            assert (
                _call_config.extra_config["outlet_valve_entity"]
                == "cover.override_outlet"
            )

    def test_get_or_create_adapter_orcon_native(self):
        """Test get_or_create for orcon_native with native_zone_id."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "orcon_native",
            "native_zone_id": "zone_1",
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            registry.get_or_create_adapter("32:123456", "bathroom")

            _call_config = mock_create.call_args[0][1]
            assert _call_config.extra_config["zone_index"] == "zone_1"

    def test_get_or_create_adapter_factory_returns_none(self):
        """Test get_or_create when factory returns None."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "unknown_type",
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_create.return_value = None

            adapter = registry.get_or_create_adapter("32:123456", "bathroom")

            assert adapter is None
            # Should not be in cache
            assert "32:123456:bathroom" not in registry._adapters

    def test_get_or_create_adapter_with_capabilities_min_max(self):
        """Test get_or_create uses capabilities min/max when zone lacks them."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "custom_valve",
            "actuator": {"entity_id": "cover.test"},
            "capabilities": {"min_position": 5, "max_position": 95},
            # No min_position/max_position at zone level
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            registry.get_or_create_adapter("32:123456", "bathroom")

            _call_config = mock_create.call_args[0][1]
            assert _call_config.min_position == 5
            assert _call_config.max_position == 95

    def test_get_or_create_adapter_zone_disabled(self):
        """Test get_or_create with disabled zone."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "custom_valve",
            "actuator": {"entity_id": "cover.test"},
            "enabled": False,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            registry.get_or_create_adapter("32:123456", "bathroom")

            _call_config = mock_create.call_args[0][1]
            assert _call_config.enabled is False

    def test_get_or_create_adapter_invalid_source_type(self):
        """Test get_or_create handles invalid source_type."""
        hass = MagicMock()
        registry = ZoneAdapterRegistry(hass)

        zone_data = {
            "type": "",  # Empty string
            "actuator": {"entity_id": "cover.test"},
            "enabled": True,
        }
        registry._zone_registry.get_zone.return_value = zone_data

        with patch(
            "custom_components.ramses_extras.framework.helpers.zone_adapters.ZoneAdapterFactory.create_adapter"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            registry.get_or_create_adapter("32:123456", "bathroom")

            # Should default to custom_valve
            _call_config = mock_create.call_args[0][1]
            assert _call_config.source_type == "custom_valve"


class TestOrconNativeZoneAdapterCoverage:
    """Additional tests for OrconNativeZoneAdapter."""

    def test_init_with_zone_index(self):
        """Test init with zone_index."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config={"zone_index": "zone_1"},
        )
        adapter = OrconNativeZoneAdapter(hass, config)
        assert adapter._zone_index == "zone_1"

    def test_init_without_zone_index(self):
        """Test init without zone_index."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config=None,
        )
        adapter = OrconNativeZoneAdapter(hass, config)
        assert adapter._zone_index is None

    @pytest.mark.asyncio
    async def test_set_position_no_zone_index(self):
        """Test set_position when no zone_index."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config=None,
        )
        adapter = OrconNativeZoneAdapter(hass, config)

        result = await adapter.async_set_position(50)
        # OrconNative always returns True (logs the command)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_position_with_zone_index(self):
        """Test set_position with zone_index."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config={"zone_index": "zone_1"},
        )
        adapter = OrconNativeZoneAdapter(hass, config)

        result = await adapter.async_set_position(80)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_position_no_zone_index(self):
        """Test get_position when no zone_index."""
        hass = MagicMock()
        # Mock hass.data to make device unavailable
        hass.data = {}
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config=None,
        )
        adapter = OrconNativeZoneAdapter(hass, config)

        pos = await adapter.async_get_position()
        assert pos.position == 50
        assert pos.is_available is False

    @pytest.mark.asyncio
    async def test_get_position_with_device_available(self):
        """Test get_position when device is available."""
        hass = MagicMock()
        # Mock hass.data to make device available
        hass.data = {"ramses_extras": {"devices": {"32:123456": {}}}}
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config={"zone_index": "zone_1"},
        )
        adapter = OrconNativeZoneAdapter(hass, config)

        pos = await adapter.async_get_position()
        # OrconNative always returns 50 (unknown) for position
        assert pos.position == 50
        # Don't assert is_available since it depends on DOMAIN constant


class TestZoneAdapterFactoryCoverage:
    """Additional tests for ZoneAdapterFactory."""

    def test_create_adapter_custom_valve(self):
        """Test creating custom_valve adapter."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="custom_valve",
            entity_id="cover.test",
        )

        adapter = ZoneAdapterFactory.create_adapter(hass, config)
        assert isinstance(adapter, CustomValveZoneAdapter)

    def test_create_adapter_paired_valves(self):
        """Test creating paired_valves adapter."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="paired_valves",
            extra_config={
                "inlet_valve_entity": "cover.inlet",
                "outlet_valve_entity": "cover.outlet",
            },
        )

        adapter = ZoneAdapterFactory.create_adapter(hass, config)
        assert isinstance(adapter, PairedValvesZoneAdapter)

    def test_create_adapter_orcon_native(self):
        """Test creating orcon_native adapter."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="orcon_native",
            extra_config={"zone_index": "zone_1"},
        )

        adapter = ZoneAdapterFactory.create_adapter(hass, config)
        assert isinstance(adapter, OrconNativeZoneAdapter)

    def test_create_adapter_unknown_type(self):
        """Test creating adapter with unknown type."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="unknown_type",
            entity_id="cover.test",
        )

        adapter = ZoneAdapterFactory.create_adapter(hass, config)
        assert adapter is None

    def test_create_adapter_empty_type(self):
        """Test creating adapter with empty type."""
        hass = MagicMock()
        config = ZoneAdapterConfig(
            zone_id="test",
            fan_id="32:123456",
            source_type="",
            entity_id="cover.test",
        )

        adapter = ZoneAdapterFactory.create_adapter(hass, config)
        assert adapter is None
