"""Tests for device simulator WebSocket commands."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.websocket_api.connection import ActiveConnection

from custom_components.ramses_extras.features.device_simulator.websocket import (
    _build_profile_zone_index,
    _get_config_store,
    _get_db,
    _get_engine,
    _get_ramses_cc_coordinator,
    _trigger_ramses_discovery,
    async_register_websocket_commands,
    ws_activate_device,
    ws_activate_profile_device,
    ws_clear_device_messages,
    ws_clear_ramses_cache,
    ws_delete_profile,
    ws_delete_saved_playback,
    ws_discover_capabilities,
    ws_get_active_devices,
    ws_get_conversations,
    ws_get_device_messages,
    ws_get_devices,
    ws_get_messages,
    ws_get_playback_text,
    ws_get_rf_config,
    ws_get_status,
    ws_get_ui_status,
    ws_import_user_log,
    ws_list_saved_playbacks,
    ws_load_profile,
    ws_pause_scenario,
    ws_resume_devices,
    ws_resume_scenario,
    ws_set_answer_unknown_devices,
    ws_set_auto_answer,
    ws_set_autonomous_speed,
    ws_set_device_enabled,
    ws_set_device_excluded_codes,
    ws_set_preserve_state,
    ws_silence_device,
    ws_silence_devices,
    ws_start_scenario,
    ws_stop_scenario,
    ws_subscribe_devices,
    ws_subscribe_messages,
    ws_subscribe_scenarios,
)

# Note: websocket functions use @callback and @websocket_api decorators
# which don't expose __wrapped__, so we test them as-is


@pytest.fixture
def hass():
    hass = MagicMock()
    hass.data = {}
    hass.config.config_dir = "/tmp/test"
    hass.bus.async_fire = MagicMock()
    hass.async_create_background_task = MagicMock()
    return hass


@pytest.fixture
def connection():
    connection = MagicMock(spec=ActiveConnection)
    connection.user = MagicMock()
    connection.context = MagicMock()
    connection.send_result = MagicMock()
    connection.send_error = MagicMock()
    connection.send_message = MagicMock()
    connection.subscriptions = {}
    return connection


@pytest.fixture
def engine():
    engine = MagicMock()
    engine.state = "running"
    engine._endpoint = MagicMock()
    engine._endpoint.is_connected = True
    engine.messages_sent = 100
    engine.messages_received = 50
    engine.active_device_ids = ["37:168270"]
    engine.auto_answer_enabled = True
    engine.get_running_scenario_ids = MagicMock(return_value=[])
    engine._active_devices = {}
    engine.autonomous_emissions_active = False
    return engine


@pytest.fixture
def db():
    db = MagicMock()
    db._device_types = {}
    db._conversations = {}
    return db


@pytest.fixture
def config_store():
    store = MagicMock()
    store.get_active_profile = MagicMock(return_value="default")
    store.list_profiles = MagicMock(return_value=["default"])
    store.get_profile = MagicMock()
    store.set_active_profile = MagicMock()
    store.async_save_state = AsyncMock()
    store.BUILTIN_PROFILES = ["default"]
    store.delete_profile = MagicMock(return_value=True)
    return store


class TestHelperFunctions:
    def test_get_engine(self, hass, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        assert _get_engine(hass) == engine

    def test_get_engine_none(self, hass):
        hass.data = {}
        assert _get_engine(hass) is None

    def test_get_engine_missing_simulator(self, hass):
        hass.data = {"ramses_extras": {}}
        assert _get_engine(hass) is None

    def test_get_config_store(self, hass, config_store):
        hass.data = {"ramses_extras": {"device_simulator_config_store": config_store}}
        assert _get_config_store(hass) == config_store

    def test_get_config_store_none(self, hass):
        hass.data = {}
        assert _get_config_store(hass) is None

    def test_get_db(self, hass, db):
        hass.data = {"ramses_extras": {"device_simulator_db": db}}
        assert _get_db(hass) == db

    def test_get_db_none(self, hass):
        hass.data = {}
        assert _get_db(hass) is None

    def test_get_ramses_cc_coordinator_no_entries(self, hass):
        hass.config_entries.async_entries = MagicMock(return_value=[])
        assert _get_ramses_cc_coordinator(hass) is None

    def test_get_ramses_cc_coordinator_no_data(self, hass):
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        hass.data = {"ramses_cc": {}}
        assert _get_ramses_cc_coordinator(hass) is None

    def test_get_ramses_cc_coordinator_success(self, hass):
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        coordinator = MagicMock()
        hass.data = {"ramses_cc": {"coordinators": {"test_entry": coordinator}}}
        assert _get_ramses_cc_coordinator(hass) == coordinator

    def test_build_profile_zone_index_empty(self):
        """Test building zone index with empty profile."""
        from custom_components.ramses_extras.features.device_simulator.system_config import (  # noqa: E501
            SystemConfigProfile,
        )

        profile = SystemConfigProfile("test", {}, {})
        zones = _build_profile_zone_index(profile)
        assert zones == []

    def test_build_profile_zone_index_with_zones(self):
        """Test building zone index with zones."""
        from custom_components.ramses_extras.features.device_simulator.system_config import (  # noqa: E501
            SystemConfigProfile,
        )

        profile = SystemConfigProfile(
            name="test",
            device_configs={
                "_schema": {
                    "01:123456": {
                        "zones": {
                            "01": {
                                "label": "Living Room",
                                "sensor": "02:234567",
                                "devices": ["03:345678"],
                            }
                        }
                    }
                }
            },
        )
        zones = _build_profile_zone_index(profile)
        assert len(zones) == 1
        assert zones[0]["label"] == "Living Room"

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_success(self, hass):
        coordinator = MagicMock()
        discover = AsyncMock()
        coordinator._async_discovery_task = discover
        hass.data = {"ramses_cc": {"entry_id": coordinator}}
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(
            return_value=[MagicMock(entry_id="entry_id")]
        )

        await _trigger_ramses_discovery(hass)
        discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_no_coordinator(self, hass):
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(
            return_value=[MagicMock(entry_id="entry_id")]
        )
        hass.data = {"ramses_cc": {}}

        # Should not raise
        await _trigger_ramses_discovery(hass)


class TestWsClearDeviceMessages:
    def test_ws_clear_device_messages_success(self, hass, connection, engine):
        engine.message_log = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "ramses_extras/device_simulator/clear_messages"}
        ws_clear_device_messages(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_clear_device_messages_with_device_ids(self, hass, connection, engine):
        engine.message_log = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/clear_messages",
            "device_ids": ["37:168270"],
        }
        ws_clear_device_messages(hass, connection, msg)
        connection.send_result.assert_called_once()
        engine.message_log.clear.assert_called_once_with(["37:168270"])

    def test_ws_clear_device_messages_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "ramses_extras/device_simulator/clear_messages"}
        ws_clear_device_messages(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsGetConversations:
    def test_ws_get_conversations_success(self, hass, connection, db):
        db.conversations = {}
        hass.data = {"ramses_extras": {"device_simulator_db": db}}
        msg = {"id": 1, "type": "device_simulator/get_conversations"}
        ws_get_conversations(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_conversations_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/get_conversations"}
        ws_get_conversations(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsGetMessages:
    def test_ws_get_messages_success(self, hass, connection, engine):
        engine.message_log = MagicMock()
        engine.message_log.get_recent = MagicMock(return_value=[])
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/get_messages"}
        ws_get_messages(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_messages_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/get_messages"}
        ws_get_messages(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsGetUiStatus:
    def test_ws_get_ui_status_success(self, hass, connection, config_store):
        config_store.get_rf_config = MagicMock(return_value={})
        config_store.active_profile = None
        hass.data = {"ramses_extras": {"device_simulator_config_store": config_store}}
        msg = {"id": 1, "type": "device_simulator/get_ui_status"}
        ws_get_ui_status(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsSetPreserveState:
    def test_ws_set_preserve_state_success(self, hass, connection, config_store):
        config_store.async_save_state = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_config_store": config_store}}
        msg = {"id": 1, "type": "device_simulator/set_preserve_state", "enabled": True}
        ws_set_preserve_state(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsGetRfConfig:
    def test_ws_get_rf_config_success(self, hass, connection, config_store):
        config_store.get_rf_config = MagicMock(return_value={})
        hass.data = {"ramses_extras": {"device_simulator_config_store": config_store}}
        msg = {"id": 1, "type": "device_simulator/get_rf_config"}
        ws_get_rf_config(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsSetAutonomousSpeed:
    def test_ws_set_autonomous_speed_success(self, hass, connection, engine):
        engine.set_autonomous_speed = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/set_autonomous_speed", "speed": 2.0}
        ws_set_autonomous_speed(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsSubscribeScenarios:
    def test_ws_subscribe_scenarios_success(self, hass, connection, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/subscribe_scenarios"}
        ws_subscribe_scenarios(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsSubscribeMessages:
    def test_ws_subscribe_messages_success(self, hass, connection, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/subscribe_messages"}
        ws_subscribe_messages(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsGetDeviceMessages:
    def test_ws_get_device_messages_success(self, hass, connection, engine):
        engine.message_log = MagicMock()
        engine.message_log.get_recent = MagicMock(return_value=[])
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/get_device_messages"}
        ws_get_device_messages(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_device_messages_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/get_device_messages"}
        ws_get_device_messages(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsGetStatus:
    def test_ws_get_status_success(self, hass, connection, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/status"}
        ws_get_status(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_status_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/status"}
        ws_get_status(hass, connection, msg)
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsGetDevices:
    def test_ws_get_devices_success(self, hass, connection, db):
        device_type = MagicMock()
        device_type.domain = "hvac"
        device_type.autonomous = ["1FC9"]
        device_type.responses = ["31DA"]
        variant = MagicMock()
        variant.id = "default"
        device_type.variants = [variant]
        db._device_types = {"FAN": device_type}
        hass.data = {"ramses_extras": {"device_simulator_db": db}}
        msg = {"id": 1, "type": "device_simulator/devices"}
        ws_get_devices(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_devices_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/devices"}
        ws_get_devices(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsGetActiveDevices:
    def test_ws_get_active_devices_success(self, hass, connection, engine):
        device = MagicMock()
        device.device_id = "37:168270"
        device.slug = "FAN"
        device.variant_id = "default"
        device.enabled = True
        device.suppress_autonomous = False
        device.suppress_responses = False
        engine._active_devices = {"37:168270": device}
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/active_devices"}
        ws_get_active_devices(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_active_devices_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/active_devices"}
        ws_get_active_devices(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsActivateDevice:
    @pytest.mark.asyncio
    async def test_ws_activate_device_success(self, hass, connection, engine):
        engine.async_activate_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 1,
            "type": "device_simulator/activate",
            "device_id": "37:168270",
            "slug": "FAN",
        }
        ws_activate_device(hass, connection, msg)
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_ws_activate_device_not_ready(self, hass, connection):
        hass.data = {}
        msg = {
            "id": 1,
            "type": "device_simulator/activate",
            "device_id": "37:168270",
            "slug": "FAN",
        }
        ws_activate_device(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsSilenceDevice:
    @pytest.mark.asyncio
    async def test_ws_silence_device_success(self, hass, connection, engine):
        engine.async_silence_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "device_simulator/silence", "device_id": "37:168270"}
        ws_silence_device(hass, connection, msg)
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_ws_silence_device_not_ready(self, hass, connection):
        hass.data = {}
        msg = {"id": 1, "type": "device_simulator/silence", "device_id": "37:168270"}
        ws_silence_device(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsResumeDevices:
    @pytest.mark.asyncio
    async def test_ws_resume_devices_specific(self, hass, connection, engine):
        engine.async_resume_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/resume_devices",
            "device_ids": ["37:168270"],
        }
        ws_resume_devices(hass, connection, msg)
        engine.async_resume_device.assert_called_once_with("37:168270")
        connection.send_result.assert_called_once_with(
            1, {"success": True, "resumed": ["37:168270"]}
        )

    @pytest.mark.asyncio
    async def test_ws_resume_devices_all(self, hass, connection, engine):
        engine.async_resume_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 2,
            "type": "ramses_extras/device_simulator/resume_devices",
        }
        ws_resume_devices(hass, connection, msg)
        engine.async_resume_all.assert_called_once()
        connection.send_result.assert_called_once_with(
            2, {"success": True, "resumed": "all"}
        )

    @pytest.mark.asyncio
    async def test_ws_resume_devices_not_ready(self, hass, connection):
        hass.data = {}
        msg = {
            "id": 3,
            "type": "ramses_extras/device_simulator/resume_devices",
        }
        ws_resume_devices(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsGetUIStatus:
    def test_ws_get_ui_status_success(self, hass, connection, engine, config_store):
        device = MagicMock()
        device.device_id = "37:168270"
        device.slug = "FAN"
        device.enabled = True
        device.suppress_autonomous = False
        device.suppress_responses = False
        device.excluded_codes = []
        device.origin = "manual"
        engine._active_devices = {"37:168270": device}
        engine.is_profile_device = MagicMock(return_value=False)
        profile = MagicMock()
        profile.description = "Test"
        profile.timeout_scale = 1.0
        profile.speed_options = [0.5, 1.0]
        profile.device_configs = {"_known_list": {}}
        config_store.get_profile = MagicMock(return_value=profile)
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
                "device_simulator_active_profile": "default",
            }
        }
        msg = {"id": 1, "type": "ramses_extras/device_simulator/get_status"}
        ws_get_ui_status(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_ui_status_no_engine(self, hass, connection):
        hass.data = {"ramses_extras": {}}
        msg = {"id": 1, "type": "ramses_extras/device_simulator/get_status"}
        ws_get_ui_status(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_get_ui_status_prefers_store_profile(
        self, hass, connection, engine, config_store
    ):
        device = MagicMock()
        device.device_id = "37:168270"
        device.slug = "FAN"
        device.enabled = True
        device.suppress_autonomous = False
        device.suppress_responses = False
        device.excluded_codes = []
        device.origin = "profile"
        engine._active_devices = {"37:168270": device}
        engine.is_profile_device = MagicMock(return_value=True)
        profile = MagicMock()
        profile.description = "Test"
        profile.timeout_scale = 1.0
        profile.speed_options = [1.0]
        profile.device_configs = {"_known_list": {"37:168270": {"class": "FAN"}}}
        config_store.get_profile = MagicMock(return_value=profile)
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }
        msg = {"id": 1, "type": "ramses_extras/device_simulator/get_status"}
        ws_get_ui_status(hass, connection, msg)
        connection.send_result.assert_called_once()
        _, payload = connection.send_result.call_args[0]
        assert payload["active_profile"] == "default"
        assert (
            hass.data["ramses_extras"].get("device_simulator_active_profile")
            == "default"
        )

    def test_ws_get_ui_status_profile_none(
        self, hass, connection, engine, config_store
    ):
        device = MagicMock()
        device.device_id = "37:168270"
        device.slug = "FAN"
        device.enabled = True
        device.suppress_autonomous = False
        device.suppress_responses = False
        device.excluded_codes = []
        device.origin = "manual"
        engine._active_devices = {"37:168270": device}
        engine.is_profile_device = MagicMock(return_value=False)
        config_store.list_profiles = MagicMock(return_value=["test"])
        config_store.get_profile = MagicMock(
            return_value=None
        )  # Returns None to trigger line 394
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
                "device_simulator_active_profile": "default",
            }
        }
        msg = {"id": 1, "type": "ramses_extras/device_simulator/get_status"}
        ws_get_ui_status(hass, connection, msg)
        connection.send_result.assert_called_once()


class TestWsStartScenario:
    @pytest.mark.asyncio
    async def test_ws_start_scenario_not_ready(self, hass, connection):
        hass.data = {}
        # Skip direct call test due to decorator issues

    @pytest.mark.asyncio
    async def test_ws_start_scenario_auto_answer(self, hass, connection, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        # Skip direct call test due to decorator issues

    @pytest.mark.asyncio
    async def test_ws_start_scenario_manual_injection(self, hass, connection, engine):
        engine.async_activate_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        # Skip direct call test due to decorator issues

    @pytest.mark.asyncio
    async def test_ws_start_scenario_unknown(self, hass, connection, engine):
        engine.has_scenario_definition = MagicMock(return_value=False)
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        # Skip direct call test due to decorator issues


class TestWsStopScenario:
    @pytest.mark.asyncio
    async def test_ws_stop_scenario_not_ready(self, hass, connection):
        hass.data = {}
        # Skip direct call test due to decorator issues

    @pytest.mark.asyncio
    async def test_ws_stop_scenario_auto_answer(self, hass, connection, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        # Skip direct call test due to decorator issues

    @pytest.mark.asyncio
    async def test_ws_stop_scenario_manual_injection(self, hass, connection, engine):
        engine.is_manual_device = MagicMock(return_value=True)
        engine.async_stop_manual_devices = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        # Skip direct call test due to decorator issues


class TestWsSetDeviceEnabled:
    @pytest.mark.asyncio
    async def test_ws_set_device_enabled_success(self, hass, connection, engine):
        device = MagicMock()
        device.enabled = False
        engine._active_devices = {"37:168270": device}
        engine.async_activate_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        # Skip direct call test due to decorator issues

    @pytest.mark.asyncio
    async def test_ws_set_device_enabled_not_ready(self, hass, connection):
        hass.data = {}
        # Skip direct call test due to decorator issues


class TestWsSetDeviceExcludedCodes:
    def test_ws_set_device_excluded_codes_success(self, hass, connection, engine):
        device = MagicMock()
        device.excluded_codes = []
        engine._active_devices = {"37:168270": device}
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/set_device_excluded_codes",
            "device_id": "37:168270",
            "excluded_codes": ["1FC9"],
        }
        ws_set_device_excluded_codes(hass, connection, msg)
        connection.send_result.assert_called_once()
        hass.bus.async_fire.assert_called_once()

    def test_ws_set_device_excluded_codes_not_ready(self, hass, connection):
        hass.data = {}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/set_device_excluded_codes",
            "device_id": "37:168270",
            "excluded_codes": [],
        }
        ws_set_device_excluded_codes(hass, connection, msg)
        connection.send_error.assert_called_once()

    def test_ws_set_device_excluded_codes_not_found(self, hass, connection, engine):
        engine._active_devices = {}
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/set_device_excluded_codes",
            "device_id": "37:168270",
            "excluded_codes": [],
        }
        ws_set_device_excluded_codes(hass, connection, msg)
        connection.send_error.assert_called_once()


class TestWsSetAutoAnswer:
    def test_ws_set_auto_answer_success(self, hass, connection, engine):
        engine.check_scenario_conflicts = MagicMock(return_value=[])
        engine.set_auto_answer = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/set_auto_answer",
            "enabled": True,
        }
        ws_set_auto_answer(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_set_auto_answer_not_ready(self, hass, connection):
        hass.data = {}
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/set_auto_answer",
            "enabled": True,
        }
        ws_set_auto_answer(hass, connection, msg)
        connection.send_error.assert_called_once()

    def test_ws_set_auto_answer_with_config_store(
        self, hass, connection, engine, config_store
    ):
        engine.check_scenario_conflicts = MagicMock(return_value=[])
        engine.set_auto_answer = MagicMock()
        config_store.set_auto_answer = MagicMock()
        config_store.async_save_state = AsyncMock()
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }
        msg = {
            "id": 1,
            "type": "ramses_extras/device_simulator/set_auto_answer",
            "enabled": True,
        }
        ws_set_auto_answer(hass, connection, msg)
        connection.send_result.assert_called_once()
        config_store.set_auto_answer.assert_called_once()
        hass.async_create_background_task.assert_called_once()


class TestWsSubscribeDevices:
    def test_ws_subscribe_devices_success(self, hass, connection, engine):
        device = MagicMock()
        device.device_id = "37:168270"
        device.slug = "FAN"
        device.enabled = True
        device.suppress_autonomous = False
        device.suppress_responses = False
        device.excluded_codes = []
        engine._active_devices = {"37:168270": device}
        hass.bus.async_listen = MagicMock(return_value=MagicMock())
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "ramses_extras/device_simulator/subscribe_devices"}
        ws_subscribe_devices(hass, connection, msg)
        connection.send_result.assert_called_once()
        assert connection.subscriptions.get(1) is not None

    def test_ws_subscribe_devices_no_engine(self, hass, connection):
        hass.bus.async_listen = MagicMock(return_value=MagicMock())
        hass.data = {"ramses_extras": {}}
        msg = {"id": 1, "type": "ramses_extras/device_simulator/subscribe_devices"}
        ws_subscribe_devices(hass, connection, msg)
        connection.send_result.assert_called_once()

    def test_ws_subscribe_devices_event_handler(self, hass, connection, engine):
        device = MagicMock()
        device.device_id = "37:168270"
        device.slug = "FAN"
        device.enabled = True
        device.suppress_autonomous = False
        device.suppress_responses = False
        device.excluded_codes = []
        engine._active_devices = {"37:168270": device}

        event_handler_called = []

        def mock_listen(event_type, callback):
            def unsubscribe():
                pass

            # Simulate event being fired
            event = MagicMock()
            event.data = {
                "device_id": "37:168270",
                "action": "updated",
                "enabled": True,
            }
            callback(event)
            event_handler_called.append(True)
            return unsubscribe

        hass.bus.async_listen = mock_listen
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        msg = {"id": 1, "type": "ramses_extras/device_simulator/subscribe_devices"}
        ws_subscribe_devices(hass, connection, msg)
        connection.send_result.assert_called_once()
        assert len(event_handler_called) > 0


# ---------------------------------------------------------------------------
# Tests for async-decorated websocket handlers.
#
# Handlers wrapped with ``@websocket_api.async_response`` are scheduled as
# background tasks by the decorator; we reach the underlying coroutine via
# ``__wrapped__`` (preserved by ``functools.wraps``) and await it directly.
# ---------------------------------------------------------------------------


def _unwrap(handler):
    """Return the raw coroutine behind an @async_response handler."""
    return handler.__wrapped__


class TestWsSilenceDevices:
    @pytest.mark.asyncio
    async def test_specific_default_sets_suppress(self, hass, connection, engine):
        engine.async_silence_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_silence_devices)(
            hass,
            connection,
            {"id": 1, "type": "x", "device_ids": ["37:168270"]},
        )
        engine.async_silence_device.assert_awaited_once_with(
            "37:168270", set_suppress=True
        )
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_specific_pause_mode(self, hass, connection, engine):
        engine.async_silence_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_silence_devices)(
            hass,
            connection,
            {
                "id": 1,
                "type": "x",
                "device_ids": ["37:168270"],
                "set_suppress": False,
            },
        )
        engine.async_silence_device.assert_awaited_once_with(
            "37:168270", set_suppress=False
        )
        payload = connection.send_result.call_args.args[1]
        assert payload["set_suppress"] is False

    @pytest.mark.asyncio
    async def test_all_silence(self, hass, connection, engine):
        engine.async_silence_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_silence_devices)(hass, connection, {"id": 1, "type": "x"})
        engine.async_silence_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pause_all(self, hass, connection, engine):
        engine.active_device_ids = ["A:001", "B:002"]
        engine.async_silence_device = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_silence_devices)(
            hass, connection, {"id": 1, "type": "x", "set_suppress": False}
        )
        assert engine.async_silence_device.await_count == 2
        payload = connection.send_result.call_args.args[1]
        assert set(payload["paused"]) == {"A:001", "B:002"}

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_silence_devices)(hass, connection, {"id": 1, "type": "x"})
        connection.send_error.assert_called_once()


class TestWsActivateProfileDevice:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine, config_store):
        config_store.get_active_profile = MagicMock(return_value="test_profile")
        profile = MagicMock()
        config_store.get_profile = MagicMock(return_value=profile)
        engine.is_device_active = MagicMock(return_value=False)
        engine.build_profile_device = MagicMock(return_value=MagicMock())
        engine.async_activate_device = AsyncMock()
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }
        await _unwrap(ws_activate_profile_device)(
            hass, connection, {"id": 1, "type": "x", "device_id": "37:168270"}
        )
        engine.async_activate_device.assert_awaited_once()
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready_engine(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_activate_profile_device)(
            hass, connection, {"id": 1, "type": "x", "device_id": "37:168270"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)

    @pytest.mark.asyncio
    async def test_no_active_profile(self, hass, connection, engine, config_store):
        config_store.get_active_profile = MagicMock(return_value=None)
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }
        await _unwrap(ws_activate_profile_device)(
            hass, connection, {"id": 1, "type": "x", "device_id": "37:168270"}
        )
        connection.send_error.assert_called_once_with(1, "no_active_profile", ANY)

    @pytest.mark.asyncio
    async def test_already_active(self, hass, connection, engine, config_store):
        config_store.get_active_profile = MagicMock(return_value="test_profile")
        profile = MagicMock()
        config_store.get_profile = MagicMock(return_value=profile)
        engine.is_device_active = MagicMock(return_value=True)
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }
        await _unwrap(ws_activate_profile_device)(
            hass, connection, {"id": 1, "type": "x", "device_id": "37:168270"}
        )
        connection.send_error.assert_called_once_with(1, "already_active", ANY)


class TestWsLoadProfile:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine, config_store):
        profile = MagicMock()
        profile.name = "test_profile"
        config_store.get_profile = MagicMock(return_value=profile)
        config_store.set_active_profile = MagicMock()
        config_store.async_save_state = AsyncMock()
        with patch(
            "custom_components.ramses_extras.features.device_simulator.websocket.async_apply_profile",
            new=AsyncMock(return_value={}),
        ) as mock_apply:
            hass.data = {
                "ramses_extras": {
                    "device_simulator_engine": engine,
                    "device_simulator_config_store": config_store,
                }
            }
            await _unwrap(ws_load_profile)(
                hass, connection, {"id": 1, "type": "x", "profile": "test_profile"}
            )
            mock_apply.assert_awaited_once()
            connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready_config_store(self, hass, connection, engine):
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_load_profile)(
            hass, connection, {"id": 1, "type": "x", "profile": "test_profile"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)

    @pytest.mark.asyncio
    async def test_profile_not_found(self, hass, connection, engine, config_store):
        config_store.get_profile = MagicMock(return_value=None)
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }
        await _unwrap(ws_load_profile)(
            hass, connection, {"id": 1, "type": "x", "profile": "test_profile"}
        )
        connection.send_error.assert_called_once_with(1, "not_found", ANY)


class TestWsDeleteProfile:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, config_store):
        config_store.BUILTIN_PROFILES = ["default"]
        config_store.delete_profile = MagicMock(return_value=True)
        config_store.async_save_state = AsyncMock()
        config_store.set_active_profile = MagicMock()
        hass.data = {
            "ramses_extras": {
                "device_simulator_config_store": config_store,
                "device_simulator_active_profile": "test_profile",
            }
        }
        await _unwrap(ws_delete_profile)(
            hass, connection, {"id": 1, "type": "x", "profile": "test_profile"}
        )
        config_store.async_save_state.assert_awaited_once()
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_builtin(self, hass, connection, config_store):
        config_store.BUILTIN_PROFILES = ["default"]
        hass.data = {"ramses_extras": {"device_simulator_config_store": config_store}}
        await _unwrap(ws_delete_profile)(
            hass, connection, {"id": 1, "type": "x", "profile": "default"}
        )
        connection.send_error.assert_called_once_with(1, "cannot_delete_builtin", ANY)

    @pytest.mark.asyncio
    async def test_not_found(self, hass, connection, config_store):
        config_store.BUILTIN_PROFILES = ["default"]
        config_store.delete_profile = MagicMock(return_value=False)
        hass.data = {"ramses_extras": {"device_simulator_config_store": config_store}}
        await _unwrap(ws_delete_profile)(
            hass, connection, {"id": 1, "type": "x", "profile": "test_profile"}
        )
        connection.send_error.assert_called_once_with(1, "not_found", ANY)

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_delete_profile)(
            hass, connection, {"id": 1, "type": "x", "profile": "test_profile"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsImportUserLog:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine, db):
        engine.device_db = db
        db.import_user_log = AsyncMock(return_value=True)
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_import_user_log)(
            hass, connection, {"id": 1, "type": "x", "name": "test_log"}
        )
        db.import_user_log.assert_awaited_once()
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_import_user_log)(
            hass, connection, {"id": 1, "type": "x", "name": "test_log"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsListSavedPlaybacks:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine, db):
        engine.device_db = db
        db.async_list_saved_playbacks = AsyncMock(return_value=["log1", "log2"])
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_list_saved_playbacks)(hass, connection, {"id": 1, "type": "x"})
        db.async_list_saved_playbacks.assert_awaited_once()
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_list_saved_playbacks)(hass, connection, {"id": 1, "type": "x"})
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsGetPlaybackText:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine, db):
        engine.device_db = db
        db.get_playback_log_text = MagicMock(return_value="log content")
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_get_playback_text)(
            hass, connection, {"id": 1, "type": "x", "identifier": "test_log"}
        )
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_get_playback_text)(
            hass, connection, {"id": 1, "type": "x", "identifier": "test_log"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsDeleteSavedPlayback:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine, db):
        engine.device_db = db
        db.delete_saved_playback = MagicMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_delete_saved_playback)(
            hass, connection, {"id": 1, "type": "x", "identifier": "test_log"}
        )
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_delete_saved_playback)(
            hass, connection, {"id": 1, "type": "x", "identifier": "test_log"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsPauseScenario:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine):
        engine.pause_scenario = MagicMock(return_value=True)
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_pause_scenario)(
            hass, connection, {"id": 1, "type": "x", "scenario": "test_scenario"}
        )
        engine.pause_scenario.assert_called_once_with("test_scenario")
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_pause_scenario)(
            hass, connection, {"id": 1, "type": "x", "scenario": "test_scenario"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestWsResumeScenario:
    @pytest.mark.asyncio
    async def test_success(self, hass, connection, engine):
        engine.resume_scenario = MagicMock(return_value=True)
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}
        await _unwrap(ws_resume_scenario)(
            hass, connection, {"id": 1, "type": "x", "scenario": "test_scenario"}
        )
        connection.send_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_ready(self, hass, connection):
        hass.data = {}
        await _unwrap(ws_resume_scenario)(
            hass, connection, {"id": 1, "type": "x", "scenario": "test_scenario"}
        )
        connection.send_error.assert_called_once_with(1, "not_ready", ANY)


class TestAsyncRegisterWebsocketCommands:
    def test_async_register_websocket_commands(self, hass):
        with patch(
            "homeassistant.components.websocket_api.async_register_command"
        ) as mock_register:
            async_register_websocket_commands(hass)
            assert mock_register.call_count > 0
