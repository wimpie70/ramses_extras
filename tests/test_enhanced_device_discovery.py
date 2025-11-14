"""Test the enhanced device discovery architecture framework changes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import (
    DEVICE_TYPE_HANDLERS,
    EVENT_DEVICE_READY_FOR_ENTITIES,
    _extract_model_family,
    fire_device_ready_event,
    handle_hvac_ventilator,
    register_device_handler,
    safe_handle_device_discovery,
)


@pytest.fixture
def mock_device():
    """Create mock device for testing."""
    device = MagicMock()
    device.id = "test_device_123"
    device.model = "Orcon HRV400"
    device.__class__.__name__ = "HvacVentilator"
    device.capabilities = ["humidity_sensing", "dehumidification"]
    device.humidity_sensor = MagicMock()
    # Ensure _entity_metadata starts as a regular dict for the handler to work with
    device._entity_metadata = {}
    return device


@pytest.fixture
def mock_hass():
    """Create mock Home Assistant instance."""
    hass = MagicMock()
    hass.bus.async_fire = AsyncMock()
    return hass


class TestDeviceTypeHandlers:
    """Test device type handler registration and execution."""

    def test_handler_registration(self):
        """Test device handler registration."""
        # Count handlers before registration
        initial_count = len(DEVICE_TYPE_HANDLERS)

        @register_device_handler("TestDevice")
        async def test_handler(device, feature_name):
            return True

        # Verify handler was registered
        assert "TestDevice" in DEVICE_TYPE_HANDLERS
        assert DEVICE_TYPE_HANDLERS["TestDevice"] == test_handler
        assert len(DEVICE_TYPE_HANDLERS) == initial_count + 1

    def test_hvac_ventilator_handler_exists(self):
        """Test that HVAC Ventilator handler is registered."""
        assert "HvacVentilator" in DEVICE_TYPE_HANDLERS
        handler = DEVICE_TYPE_HANDLERS["HvacVentilator"]
        assert handler == handle_hvac_ventilator

    @pytest.mark.asyncio
    async def test_hvac_ventilator_handler_success(self, mock_device):
        """Test successful HVAC Ventilator handler execution."""
        handler = DEVICE_TYPE_HANDLERS["HvacVentilator"]
        result = await handler(mock_device, "humidity_control")

        assert result is True
        assert hasattr(mock_device, "_entity_metadata")

        # Verify metadata was set correctly
        metadata = mock_device._entity_metadata
        assert isinstance(metadata, dict)
        assert metadata["feature"] == "humidity_control"
        assert "humidity_sensing" in metadata["capabilities"]
        assert "dehumidification" in metadata["capabilities"]

    @pytest.mark.asyncio
    async def test_hvac_ventilator_handler_missing_capability(self, mock_device):
        """Test handler fails gracefully when capability is missing."""
        # Remove humidity sensor and capabilities to ensure failure
        mock_device.humidity_sensor = None
        if hasattr(mock_device, "capabilities"):
            delattr(mock_device, "capabilities")

        handler = DEVICE_TYPE_HANDLERS["HvacVentilator"]
        result = await handler(mock_device, "humidity_control")

        assert result is False

    @pytest.mark.asyncio
    async def test_hvac_ventilator_handler_missing_id(self, mock_device):
        """Test handler fails when device ID is missing."""
        del mock_device.id

        handler = DEVICE_TYPE_HANDLERS["HvacVentilator"]
        result = await handler(mock_device, "humidity_control")

        assert result is False


class TestSafeDeviceDiscovery:
    """Test the safe device discovery wrapper."""

    @pytest.mark.asyncio
    async def test_safe_discovery_success(self, mock_device, mock_hass):
        """Test successful device discovery with event firing."""
        result = await safe_handle_device_discovery(
            mock_device, "HvacVentilator", "humidity_control", mock_hass
        )

        assert result["success"] is True
        assert result["device"] == mock_device

        # Verify event was fired
        mock_hass.bus.async_fire.assert_called_once()
        call_args = mock_hass.bus.async_fire.call_args
        assert call_args[0][0] == EVENT_DEVICE_READY_FOR_ENTITIES

        event_data = call_args[0][1]
        assert event_data["device_id"] == "test_device_123"
        assert event_data["device_type"] == "HvacVentilator"
        assert event_data["handled_by"] == "humidity_control"
        assert len(event_data["entity_ids"]) > 0

    @pytest.mark.asyncio
    async def test_safe_discovery_unknown_device_type(self, mock_device, mock_hass):
        """Test handling of unknown device type."""
        result = await safe_handle_device_discovery(
            mock_device, "UnknownDeviceType", "humidity_control", mock_hass
        )

        assert result["success"] is False
        assert result["reason"] == "unknown_device_type"

    @pytest.mark.asyncio
    async def test_safe_discovery_handler_timeout(self, mock_device, mock_hass):
        """Test timeout handling in device discovery."""
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await safe_handle_device_discovery(
                mock_device, "HvacVentilator", "humidity_control", mock_hass
            )

            assert result["success"] is False
            assert result["reason"] == "handler_timeout"


class TestEventSystem:
    """Test event system functionality."""

    @pytest.mark.asyncio
    async def test_event_firing_structure(self, mock_device, mock_hass):
        """Test that events are fired with correct structure."""

        entity_ids = [
            f"sensor.humidity_{mock_device.id}",
            f"switch.dehumidify_{mock_device.id}",
        ]

        await fire_device_ready_event(
            mock_hass,
            mock_device.id,
            "HvacVentilator",
            mock_device,
            entity_ids,
            "humidity_control",
        )

        # Verify event was fired
        mock_hass.bus.async_fire.assert_called_once()
        event_type, event_data = mock_hass.bus.async_fire.call_args[0]

        assert event_type == EVENT_DEVICE_READY_FOR_ENTITIES
        assert event_data["device_id"] == mock_device.id
        assert event_data["device_type"] == "HvacVentilator"
        assert event_data["handled_by"] == "humidity_control"
        assert len(event_data["entity_ids"]) == 2
        assert "timestamp" in event_data
        assert event_data["device_object"] == mock_device


class TestModelFamilyExtraction:
    """Test model family extraction functionality."""

    def test_extract_orcon_family(self):
        """Test Orcon model family detection."""

        orcon_models = [
            "Orcon HRV400",
            "ORCON HRV300",
            "Soler & Palau Orcon 200",
            "orcon-vent-100",
        ]

        for model in orcon_models:
            family = _extract_model_family(model)
            assert family == "orcon"

    def test_extract_zehnder_family(self):
        """Test Zehnder model family detection."""

        zehnder_models = ["Zehnder ComfoAir Q350", "COMFOAIR Q450", "zehnder-vent-300"]

        for model in zehnder_models:
            family = _extract_model_family(model)
            assert family == "zehnder"

    def test_extract_generic_family(self):
        """Test generic model family detection."""

        generic_models = ["Generic Ventilator 100", "UNKNOWN BRAND DEVICE"]

        for model in generic_models:
            family = _extract_model_family(model)
            assert family in ["generic_ventilator", "unknown"]

    def test_extract_unknown_family(self):
        """Test unknown model handling."""

        assert _extract_model_family("") == "unknown"
        assert _extract_model_family(None) == "unknown"
        assert _extract_model_family("RandomDevice123") == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
