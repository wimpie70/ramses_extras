# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for Device Simulator services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import ServiceCall

from custom_components.ramses_extras.features.device_simulator.const import (
    SCENARIO_DEVICE_PLAYBACK,
    SCENARIO_DEVICE_SUITE,
    SCENARIO_DISCOVERY_TEST,
    SCENARIO_FLOODING_TEST,
    SCENARIO_HVAC_DEVICE_LOSS,
    SCENARIO_MANUAL_DEVICE_INJECTION,
    SCENARIO_PROFILE_EMISSIONS,
    SCENARIO_TIMEOUT_TEST,
)
from custom_components.ramses_extras.features.device_simulator.services import (
    SCHEMA_ACTIVATE_DEVICE,
    SCHEMA_INJECT_MESSAGE,
    SCHEMA_RUN_SCENARIO,
    SCHEMA_SILENCE_DEVICE,
    SERVICE_ACTIVATE_DEVICE,
    SERVICE_INJECT_MESSAGE,
    SERVICE_RUN_CONVERSATION,
    SERVICE_RUN_SCENARIO,
    SERVICE_SILENCE_DEVICE,
    SERVICE_STOP_SCENARIO,
    async_setup_services,
)


class TestServiceSchemas:
    """Tests for service input validation schemas."""

    def test_schema_inject_message_valid(self) -> None:
        """Test valid inject message schema."""
        valid_data = {
            "source_id": "32:168270",
            "code": "31DA",
            "payload": "0021",
        }
        result = SCHEMA_INJECT_MESSAGE(valid_data)
        assert result["source_id"] == "32:168270"
        assert result["code"] == "31DA"
        assert result["payload"] == "0021"
        assert result["dst"] == "--:------"  # default
        assert result["verb"] == "I"  # default

    def test_schema_inject_message_with_optional(self) -> None:
        """Test inject message with optional fields."""
        valid_data = {
            "source_id": "32:168270",
            "code": "31DA",
            "payload": "0021",
            "dst": "37:126776",
            "verb": "RQ",
        }
        result = SCHEMA_INJECT_MESSAGE(valid_data)
        assert result["dst"] == "37:126776"
        assert result["verb"] == "RQ"

    def test_schema_inject_message_missing_required(self) -> None:
        """Test inject message with missing required fields."""
        invalid_data = {
            "source_id": "32:168270",
            # missing code and payload
        }
        with pytest.raises(vol.error.MultipleInvalid):
            SCHEMA_INJECT_MESSAGE(invalid_data)

    def test_schema_run_scenario_valid(self) -> None:
        """Test valid run scenario schema."""
        valid_data = {
            "scenario_type": SCENARIO_MANUAL_DEVICE_INJECTION,
        }
        result = SCHEMA_RUN_SCENARIO(valid_data)
        assert result["scenario_type"] == SCENARIO_MANUAL_DEVICE_INJECTION
        assert result["params"] == {}  # default

    def test_schema_run_scenario_with_params(self) -> None:
        """Test run scenario with custom params."""
        valid_data = {
            "scenario_type": SCENARIO_MANUAL_DEVICE_INJECTION,
            "params": {"device_id": "32:123456"},
        }
        result = SCHEMA_RUN_SCENARIO(valid_data)
        assert result["params"]["device_id"] == "32:123456"

    def test_schema_run_scenario_invalid_type(self) -> None:
        """Test run scenario with invalid scenario type."""
        invalid_data = {
            "scenario_type": "invalid_scenario",
        }
        with pytest.raises(vol.error.MultipleInvalid):
            SCHEMA_RUN_SCENARIO(invalid_data)

    def test_schema_activate_device_valid(self) -> None:
        """Test valid activate device schema."""
        valid_data = {
            "device_id": "32:168270",
            "slug": "FAN",
        }
        result = SCHEMA_ACTIVATE_DEVICE(valid_data)
        assert result["device_id"] == "32:168270"
        assert result["slug"] == "FAN"
        assert result.get("variant_id") is None  # optional, no default
        assert result["excluded_codes"] == []  # default
        assert result["suppress_autonomous"] is False  # default
        assert result["suppress_responses"] is False  # default
        assert result["enabled"] is True  # default

    def test_schema_activate_device_with_all_fields(self) -> None:
        """Test activate device with all optional fields."""
        valid_data = {
            "device_id": "32:168270",
            "slug": "FAN",
            "variant_id": "custom",
            "excluded_codes": ["1FC9", "31DA"],
            "suppress_autonomous": True,
            "suppress_responses": True,
            "enabled": False,
        }
        result = SCHEMA_ACTIVATE_DEVICE(valid_data)
        assert result["variant_id"] == "custom"
        assert result["excluded_codes"] == ["1FC9", "31DA"]
        assert result["suppress_autonomous"] is True
        assert result["suppress_responses"] is True
        assert result["enabled"] is False

    def test_schema_silence_device_valid(self) -> None:
        """Test valid silence device schema."""
        valid_data = {
            "device_id": "32:168270",
        }
        result = SCHEMA_SILENCE_DEVICE(valid_data)
        assert result["device_id"] == "32:168270"


class TestServiceHandlers:
    """Tests for service handler functions (via service registration)."""

    @pytest.fixture
    async def setup_services(self):
        """Set up services and return mock hass with registered handlers."""
        hass = MagicMock()
        engine_mock = MagicMock()
        engine_mock.async_stop_manual_devices = AsyncMock()
        engine_mock.async_stop_profile_devices = AsyncMock()
        engine_mock.clear_running_metadata = MagicMock()
        engine_mock.is_manual_device = MagicMock(return_value=True)
        hass.data = {"ramses_extras": {"device_simulator_engine": engine_mock}}
        hass.services = MagicMock()
        hass.services.async_register = MagicMock()

        # Track registered handlers
        registered_handlers = {}

        def capture_register(domain, service, handler, schema=None):
            registered_handlers[service] = handler

        hass.services.async_register.side_effect = capture_register

        await async_setup_services(hass)

        return (
            hass,
            registered_handlers,
            hass.data["ramses_extras"]["device_simulator_engine"],
        )

    @pytest.mark.asyncio
    async def test_inject_message_service_success(self, setup_services) -> None:
        """Test successful inject message service call."""
        hass, handlers, engine = setup_services
        engine._endpoint.send_packet = AsyncMock()

        call = ServiceCall(
            hass,
            "device_simulator",
            SERVICE_INJECT_MESSAGE,
            {
                "source_id": "32:168270",
                "code": "31DA",
                "payload": "0021",
                "dst": "--:------",  # default
                "verb": "I",  # default
            },
        )

        handler = handlers.get(SERVICE_INJECT_MESSAGE)
        assert handler is not None

        result = await handler(call)

        assert result["success"] is True
        engine._endpoint.send_packet.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_message_service_no_engine(self, setup_services) -> None:
        """Test inject message when engine not available."""
        hass, handlers, engine = setup_services

        # Remove engine from hass data
        hass.data["ramses_extras"].pop("device_simulator_engine")

        call = ServiceCall(
            hass,
            "device_simulator",
            SERVICE_INJECT_MESSAGE,
            {
                "source_id": "32:168270",
                "code": "31DA",
                "payload": "0021",
                "dst": "--:------",
                "verb": "I",
            },
        )

        handler = handlers.get(SERVICE_INJECT_MESSAGE)
        assert handler is not None

        result = await handler(call)

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_activate_device_service_success(self, setup_services) -> None:
        """Test successful activate device service call."""
        hass, handlers, engine = setup_services
        engine.async_activate_device = AsyncMock()

        call = ServiceCall(
            hass,
            "device_simulator",
            SERVICE_ACTIVATE_DEVICE,
            {
                "device_id": "32:168270",
                "slug": "FAN",
                "variant_id": "default",
            },
        )

        handler = handlers.get(SERVICE_ACTIVATE_DEVICE)
        assert handler is not None

        result = await handler(call)

        assert result["success"] is True
        assert result["device_id"] == "32:168270"
        engine.async_activate_device.assert_called_once()

    @pytest.mark.asyncio
    async def test_silence_device_service_success(self, setup_services) -> None:
        """Test successful silence device service call."""
        hass, handlers, engine = setup_services
        engine.async_silence_device = AsyncMock()

        call = ServiceCall(
            hass,
            "device_simulator",
            SERVICE_SILENCE_DEVICE,
            {"device_id": "32:168270"},
        )

        handler = handlers.get(SERVICE_SILENCE_DEVICE)
        assert handler is not None

        result = await handler(call)

        assert result["success"] is True
        engine.async_silence_device.assert_called_once_with("32:168270")

    @pytest.mark.asyncio
    async def test_run_scenario_manual_injection(self, setup_services) -> None:
        """Test run manual device injection scenario service call."""
        hass, handlers, engine = setup_services
        engine.async_activate_device = AsyncMock()

        call = ServiceCall(
            hass,
            "device_simulator",
            SERVICE_RUN_SCENARIO,
            {
                "scenario_type": SCENARIO_MANUAL_DEVICE_INJECTION,
                "params": {"device_id": "32:123456"},
            },
        )

        handler = handlers.get(SERVICE_RUN_SCENARIO)
        assert handler is not None

        result = await handler(call)

        # Manual injection creates a device
        assert result["success"] is True
        assert "scenario_id" in result
        assert "device_id" in result

    @pytest.mark.asyncio
    async def test_stop_scenario_success(self, setup_services) -> None:
        """Test successful stop scenario service call."""
        hass, handlers, engine = setup_services
        engine.async_stop_manual_devices = AsyncMock()

        call = ServiceCall(
            hass,
            "device_simulator",
            SERVICE_STOP_SCENARIO,
            {"scenario_id": SCENARIO_MANUAL_DEVICE_INJECTION},
        )

        handler = handlers.get(SERVICE_STOP_SCENARIO)
        assert handler is not None

        result = await handler(call)

        assert result["success"] is True
        engine.async_stop_manual_devices.assert_awaited_once()


class TestServiceSetup:
    """Tests for service registration."""

    @pytest.mark.asyncio
    async def test_async_setup_services_registers_all(self) -> None:
        """Test that all services are registered."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.async_register = MagicMock()

        mock_engine = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": mock_engine}}

        await async_setup_services(hass)

        # Verify services were registered
        registered_calls = hass.services.async_register.call_args_list
        registered_services = [call[0][1] for call in registered_calls]

        expected_services = [
            SERVICE_INJECT_MESSAGE,
            SERVICE_RUN_SCENARIO,
            SERVICE_STOP_SCENARIO,
            SERVICE_ACTIVATE_DEVICE,
            SERVICE_SILENCE_DEVICE,
            SERVICE_RUN_CONVERSATION,
        ]

        for service in expected_services:
            assert service in registered_services

    @pytest.mark.asyncio
    async def test_service_schemas_applied(self) -> None:
        """Test that schemas are applied during registration."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.async_register = MagicMock()

        mock_engine = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": mock_engine}}

        await async_setup_services(hass)

        # Find inject_message registration
        inject_calls = [
            call
            for call in hass.services.async_register.call_args_list
            if call[0][1] == SERVICE_INJECT_MESSAGE
        ]
        assert len(inject_calls) == 1
        # Verify schema was passed
        assert "schema" in inject_calls[0][1]


class TestServiceConstants:
    """Tests for service constants."""

    def test_service_names(self) -> None:
        """Test that all service names are defined."""
        from custom_components.ramses_extras.features.device_simulator import services

        assert hasattr(services, "SERVICE_INJECT_MESSAGE")
        assert hasattr(services, "SERVICE_RUN_SCENARIO")
        assert hasattr(services, "SERVICE_STOP_SCENARIO")
        assert hasattr(services, "SERVICE_ACTIVATE_DEVICE")
        assert hasattr(services, "SERVICE_SILENCE_DEVICE")
        assert hasattr(services, "SERVICE_RUN_CONVERSATION")
        assert hasattr(services, "SERVICE_IMPORT_USER_CONFIG")

    def test_schema_constants(self) -> None:
        """Test that all schema constants are defined."""
        from custom_components.ramses_extras.features.device_simulator import services

        assert hasattr(services, "SCHEMA_INJECT_MESSAGE")
        assert hasattr(services, "SCHEMA_RUN_SCENARIO")
        assert hasattr(services, "SCHEMA_STOP_SCENARIO")
        assert hasattr(services, "SCHEMA_ACTIVATE_DEVICE")
        assert hasattr(services, "SCHEMA_SILENCE_DEVICE")


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_engine_success(self) -> None:
        """Test _get_engine when engine exists."""
        from custom_components.ramses_extras.features.device_simulator.services import (
            _get_engine,
        )

        hass = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": MagicMock()}}
        result = _get_engine(hass)
        assert result is not None

    def test_get_engine_not_found(self) -> None:
        """Test _get_engine when engine doesn't exist."""
        from custom_components.ramses_extras.features.device_simulator.services import (
            _get_engine,
        )

        hass = MagicMock()
        hass.data = {}
        result = _get_engine(hass)
        assert result is None

    def test_get_config_store_success(self) -> None:
        """Test _get_config_store when store exists."""
        from custom_components.ramses_extras.features.device_simulator.services import (
            _get_config_store,
        )

        hass = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_config_store": MagicMock()}}
        result = _get_config_store(hass)
        assert result is not None

    def test_get_config_store_not_found(self) -> None:
        """Test _get_config_store when store doesn't exist."""
        from custom_components.ramses_extras.features.device_simulator.services import (
            _get_config_store,
        )

        hass = MagicMock()
        hass.data = {}
        result = _get_config_store(hass)
        assert result is None


class TestUnloadServices:
    """Tests for service unloading."""

    @pytest.mark.asyncio
    async def test_async_unload_services(self) -> None:
        """Test that all services are removed."""
        from custom_components.ramses_extras.features.device_simulator.services import (
            SERVICE_ACTIVATE_DEVICE,
            SERVICE_IMPORT_USER_CONFIG,
            SERVICE_INJECT_MESSAGE,
            SERVICE_RUN_CONVERSATION,
            SERVICE_RUN_SCENARIO,
            SERVICE_SILENCE_DEVICE,
            SERVICE_STOP_SCENARIO,
            async_unload_services,
        )

        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.async_remove = MagicMock()

        await async_unload_services(hass)

        # Verify services were removed
        removed_calls = hass.services.async_remove.call_args_list
        removed_services = [call[0][1] for call in removed_calls]

        expected_services = [
            SERVICE_INJECT_MESSAGE,
            SERVICE_RUN_SCENARIO,
            SERVICE_STOP_SCENARIO,
            SERVICE_ACTIVATE_DEVICE,
            SERVICE_SILENCE_DEVICE,
            SERVICE_RUN_CONVERSATION,
            SERVICE_IMPORT_USER_CONFIG,
        ]

        for service in expected_services:
            assert service in removed_services
