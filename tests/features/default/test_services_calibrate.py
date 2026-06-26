"""Tests for _async_calibrate_all_valves service.

This service has asyncio.sleep(90) and asyncio.sleep(5) calls that would
make tests hang. We mock asyncio.sleep to make it instant.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.services import (
    SVC_CALIBRATE_ALL_VALVES,
    async_setup_services,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.bus.fire = MagicMock()
    hass.services = MagicMock()
    hass.data = {}
    hass.loop = MagicMock()
    hass.loop.call_later = MagicMock(return_value=MagicMock())
    hass.loop.call_soon_threadsafe = MagicMock()
    hass.states = MagicMock()
    return hass


def _get_service_func(hass, service_name):
    """Extract a registered service function by name."""
    for call in hass.services.async_register.call_args_list:
        if call.args[1] == service_name:
            return call.args[2]
    return None


@pytest.fixture
async def setup_hass(hass):
    """Set up services and return hass."""
    hass.services.has_service.return_value = False
    with patch(
        "custom_components.ramses_extras.features.default.services.RamsesCommands"
    ) as mock_cmds:
        mock_cmds.return_value._get_ramses_cc_coordinator = AsyncMock(return_value=None)
        await async_setup_services(hass)
    return hass


class TestCalibrateAllValves:
    """Tests for _async_calibrate_all_valves service."""

    @pytest.mark.asyncio
    async def test_calibrate_no_zones(self, setup_hass):
        """Test calibration with no zones."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {}
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            await func(call)

            # Should fire started event with 0 zones
            hass.bus.fire.assert_any_call(
                "ramses_extras_valve_calibration_started",
                {"fan_id": "32:123456", "zone_count": 0},
            )
            # Should fire completed event
            hass.bus.fire.assert_any_call(
                "ramses_extras_valve_calibration_completed",
                {"fan_id": "32:123456", "results": {}},
            )

    @pytest.mark.asyncio
    async def test_calibrate_uncontrollable_zone(self, setup_hass):
        """Test calibration with uncontrollable zone (skipped)."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}
            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = False
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            await func(call)

            # Should fire started event
            hass.bus.fire.assert_any_call(
                "ramses_extras_valve_calibration_started",
                {"fan_id": "32:123456", "zone_count": 1},
            )

    @pytest.mark.asyncio
    async def test_calibrate_with_controllable_zone_no_valves(self, setup_hass):
        """Test calibration with controllable zone but no valve entities."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = None
            mock_zone_config.outlet_valve_entity = None
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            await func(call)

            # Should fire completed event
            hass.bus.fire.assert_any_call(
                "ramses_extras_valve_calibration_completed",
                {"fan_id": "32:123456", "results": {}},
            )

    @pytest.mark.asyncio
    async def test_calibrate_with_valves_no_ip(self, setup_hass, caplog):
        """Test calibration with valve entities but no IP found."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        mock_state = MagicMock()
        mock_state.attributes = {}
        mock_state.state = "open"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("aiohttp.ClientSession"),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = "cover.outlet_01"
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            await func(call)

            # Should log IP not found warnings
            assert "Could not determine IP" in caplog.text

    @pytest.mark.asyncio
    async def test_calibrate_with_ip_from_attributes(self, setup_hass):
        """Test calibration gets IP from state attributes."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        mock_state = MagicMock()
        mock_state.attributes = {
            "ip_address": "192.168.1.100",
            "current_position": 50,
        }
        mock_state.state = "open"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("aiohttp.ClientTimeout"),
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = "cover.outlet_01"
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            # Mock aiohttp session
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_aiohttp.return_value = mock_session

            await func(call)

            # Should have called rest_command to calibrate
            hass.services.async_call.assert_any_call(
                "rest_command",
                "shelly_calibrate_cover_0",
                {"ip": "192.168.1.100"},
                blocking=False,
            )

    @pytest.mark.asyncio
    async def test_calibrate_restores_positions(self, setup_hass):
        """Test that calibration restores valve positions."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        # Mock state with position and IP
        mock_state = MagicMock()
        mock_state.attributes = {
            "ip_address": "192.168.1.100",
            "current_position": 75,
        }
        mock_state.state = "open"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("aiohttp.ClientTimeout"),
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = None
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            # Mock aiohttp
            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_aiohttp.return_value = mock_session

            await func(call)

            # Should have called set_cover_position to restore
            hass.services.async_call.assert_any_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inlet_01", "position": 75},
                blocking=True,
            )

    @pytest.mark.asyncio
    async def test_calibrate_restore_failure(self, setup_hass, caplog):
        """Test that restore failure is handled gracefully."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        mock_state = MagicMock()
        mock_state.attributes = {
            "ip_address": "192.168.1.100",
            "current_position": 50,
        }
        mock_state.state = "open"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("aiohttp.ClientTimeout"),
            patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_async_call,
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = None
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_aiohttp.return_value = mock_session

            # Make set_cover_position fail
            mock_async_call.side_effect = Exception("Service unavailable")

            await func(call)

            # Should log failure
            assert "Failed to restore" in caplog.text

    @pytest.mark.asyncio
    async def test_calibrate_position_attr_fallback(self, setup_hass):
        """Test that 'position' attribute is used as fallback."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        # State with 'position' but not 'current_position'
        mock_state = MagicMock()
        mock_state.attributes = {
            "ip_address": "192.168.1.100",
            "position": 60,
        }
        mock_state.state = "open"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("aiohttp.ClientTimeout"),
            patch.object(hass.services, "async_call", new_callable=AsyncMock),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = None
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            mock_session = MagicMock()
            mock_resp = MagicMock()
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_aiohttp.return_value = mock_session

            await func(call)

            # Should restore to position 60
            hass.services.async_call.assert_any_call(
                "cover",
                "set_cover_position",
                {"entity_id": "cover.inlet_01", "position": 60},
                blocking=True,
            )

    @pytest.mark.asyncio
    async def test_calibrate_shelly_offline(self, setup_hass, caplog):
        """Test calibration when Shelly device is offline."""
        hass = setup_hass
        func = _get_service_func(hass, SVC_CALIBRATE_ALL_VALVES)
        assert func is not None

        call = MagicMock()
        call.data = {"device_id": "32:123456"}

        mock_state = MagicMock()
        mock_state.attributes = {
            "ip_address": "192.168.1.100",
            "current_position": 50,
        }
        mock_state.state = "open"
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.features.default.services.get_zone_coordinator"
            ) as mock_get_coord,
            patch(
                "custom_components.ramses_extras.features.default.services.RamsesCommands"
            ) as mock_cmds_class,
            patch(
                "custom_components.ramses_extras.features.default.services.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("aiohttp.ClientSession") as mock_aiohttp,
            patch("aiohttp.ClientTimeout"),
        ):
            mock_coord = MagicMock()
            mock_coord._zone_configs = {"01": MagicMock()}

            mock_zone_config = MagicMock()
            mock_zone_config.is_controllable = True
            mock_zone_config.inlet_valve_entity = "cover.inlet_01"
            mock_zone_config.outlet_valve_entity = None
            mock_coord.get_zone_config.return_value = mock_zone_config
            mock_get_coord.return_value = mock_coord

            mock_commands = MagicMock()
            mock_commands.send_command = AsyncMock()
            mock_cmds_class.return_value = mock_commands

            # Mock aiohttp to raise (device offline)
            mock_session = MagicMock()
            mock_session.get = MagicMock(side_effect=Exception("Connection refused"))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_aiohttp.return_value = mock_session

            await func(call)

            # Should log device offline
            assert "offline" in caplog.text or "ip_not_found" in caplog.text
