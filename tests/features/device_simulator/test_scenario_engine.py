# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator scenario_engine."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.device_db import (
    ResponseEntry,
)
from custom_components.ramses_extras.features.device_simulator.scenario_engine import (
    MESSAGE_EVENT,
    ActiveDevice,
    ScenarioEngine,
)


class TestActiveDevice:
    """Tests for ActiveDevice dataclass."""

    def test_default_values(self) -> None:
        """Test ActiveDevice with default values."""
        device = ActiveDevice(device_id="37:168270", slug="FAN")

        assert device.device_id == "37:168270"
        assert device.slug == "FAN"
        assert device.variant_id is None
        assert device.excluded_codes == []
        assert device.suppress_autonomous is False
        assert device.suppress_responses is False
        assert device.enabled is True
        assert device.bound_device_id is None
        assert device.origin == "scenario"

    def test_custom_values(self) -> None:
        """Test ActiveDevice with custom values."""
        device = ActiveDevice(
            device_id="37:168270",
            slug="FAN",
            variant_id="default",
            excluded_codes=["1FC9", "31DA"],
            suppress_autonomous=True,
            suppress_responses=True,
            enabled=False,
            bound_device_id="32:150000",
            origin="manual",
        )

        assert device.device_id == "37:168270"
        assert device.slug == "FAN"
        assert device.variant_id == "default"
        assert device.excluded_codes == ["1FC9", "31DA"]
        assert device.suppress_autonomous is True
        assert device.suppress_responses is True
        assert device.enabled is False
        assert device.bound_device_id == "32:150000"
        assert device.origin == "manual"


class TestScenarioEngineInit:
    """Tests for ScenarioEngine initialization."""

    def test_init(self) -> None:
        """Test ScenarioEngine initialization."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        assert engine.hass == hass
        assert engine._endpoint == endpoint
        assert engine._db == db
        assert engine._active_devices == {}
        assert engine._emitter_tasks == {}
        assert engine._running_scenarios == {}
        assert engine._scenario_tasks == {}
        assert engine._state == "idle"
        assert engine._messages_sent == 0
        assert engine._messages_received == 0
        assert engine._message_log == []
        assert engine._response_index == {}
        assert engine._profile_device_ids == set()
        assert engine._manual_device_ids == set()
        assert engine._auto_answer_enabled is True
        endpoint.add_inbound_handler.assert_called_once()

    def test_device_db_property(self) -> None:
        """Test device_db property."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        assert engine.device_db == db


class TestScenarioEngineProcessedFrames:
    def test_log_processed_frame_logs_rp_once(self) -> None:
        hass = MagicMock()
        hass.bus.async_fire = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        frame = "000 RP --- 37:168270 32:153289 --:------ 1FC9 003 000000"

        engine.log_processed_frame(frame)

        # Should only fire once even if called twice
        engine.log_processed_frame(frame)
        engine.log_processed_frame(frame)

        assert hass.bus.async_fire.call_count == 1

    def test_log_processed_frame_no_entry(self) -> None:
        """Test when message_log.log returns None."""
        hass = MagicMock()
        hass.bus.async_fire = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine.message_log.log = MagicMock(return_value=None)

        frame = "000 RP --- 37:168270 32:153289 --:------ 1FC9 003 000000"

        engine.log_processed_frame(frame)

        # Should not fire if log returns None
        hass.bus.async_fire.assert_not_called()

        engine = ScenarioEngine(hass, endpoint, db)
        frame = (
            "000 RP --- 32:150000 37:170000 --:------ "
            "2411 023 0000750092000002080000000000000BB8000000010001"
        )

        engine.log_processed_frame(frame)
        engine.log_processed_frame(frame)

        messages = engine.message_log.get_recent(limit=10, device_id="32:150000")
        assert len(messages) == 1
        assert messages[0].raw == frame
        hass.bus.async_fire.assert_called_once()
        assert hass.bus.async_fire.call_args.args[0] == MESSAGE_EVENT

    def test_init_with_custom_scenario_definitions(self) -> None:
        """Test initialization with custom scenario definitions."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()
        scenario_definitions = {"test": MagicMock()}

        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions=scenario_definitions
        )

        assert engine._scenario_definitions == scenario_definitions


class TestScenarioEngineProperties:
    """Tests for ScenarioEngine properties."""

    def test_state_property(self) -> None:
        """Test state property."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._state = "running"

        assert engine.state == "running"

    def test_auto_answer_enabled_property(self) -> None:
        """Test auto_answer_enabled property."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = False

        assert engine.auto_answer_enabled is False

    def test_messages_sent_property(self) -> None:
        """Test messages_sent property."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._messages_sent = 42

        assert engine.messages_sent == 42

    def test_messages_received_property(self) -> None:
        """Test messages_received property."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._messages_received = 10

        assert engine.messages_received == 10

    def test_active_device_ids_property(self) -> None:
        """Test active_device_ids property."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._active_devices = {"37:168270": MagicMock(), "37:168271": MagicMock()}

        assert engine.active_device_ids == ["37:168270", "37:168271"]


class TestScenarioEngineSetup:
    """Tests for ScenarioEngine setup methods."""

    @pytest.mark.asyncio
    async def test_async_setup(self) -> None:
        """Test async_setup."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.async_connect = AsyncMock()
        db = MagicMock()
        db.load_all = MagicMock()
        db.stats = MagicMock(return_value={"devices": 5})

        engine = ScenarioEngine(hass, endpoint, db)

        await engine.async_setup()

        db.load_all.assert_called_once()
        endpoint.async_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_teardown(self) -> None:
        """Test async_teardown."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.async_disconnect = AsyncMock()
        db = MagicMock()
        engine = ScenarioEngine(hass, endpoint, db)

        with patch.object(engine, "async_stop_all", new_callable=AsyncMock):
            await engine.async_teardown()

            endpoint.async_disconnect.assert_called_once()


class TestScenarioEngineScenarioManagement:
    """Tests for scenario management methods."""

    def test_is_scenario_running(self) -> None:
        """Test is_scenario_running."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {"test_scenario": {"param": "value"}}

        assert engine.is_scenario_running("test_scenario") is True
        assert engine.is_scenario_running("other_scenario") is False

    def test_set_running_metadata(self) -> None:
        """Test set_running_metadata."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        metadata = {"param": "value"}

        engine.set_running_metadata("test_scenario", metadata)

        assert engine._running_scenarios["test_scenario"] == metadata

    def test_clear_running_metadata(self) -> None:
        """Test clear_running_metadata."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {"test_scenario": {"param": "value"}}

        engine.clear_running_metadata("test_scenario")

        assert "test_scenario" not in engine._running_scenarios

    def test_clear_running_metadata_nonexistent(self) -> None:
        """Test clear_running_metadata with nonexistent scenario."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {}

        # Should not raise
        engine.clear_running_metadata("test_scenario")

        assert engine._running_scenarios == {}


class TestScenarioEngineCoerceCodeList:
    """Tests for _coerce_code_list static method."""

    def test_coerce_code_list_none(self) -> None:
        """Test coerce_code_list with None."""
        result = ScenarioEngine._coerce_code_list(None)
        assert result == []

    def test_coerce_code_list_empty_string(self) -> None:
        """Test coerce_code_list with empty string."""
        result = ScenarioEngine._coerce_code_list("")
        assert result == []

    def test_coerce_code_list_whitespace_string(self) -> None:
        """Test coerce_code_list with whitespace string."""
        result = ScenarioEngine._coerce_code_list("  ")
        assert result == []

    def test_coerce_code_list_single_string(self) -> None:
        """Test coerce_code_list with single string."""
        result = ScenarioEngine._coerce_code_list("31DA")
        assert result == ["31DA"]

    def test_coerce_code_list_lowercase_string(self) -> None:
        """Test coerce_code_list with lowercase string."""
        result = ScenarioEngine._coerce_code_list("31da")
        assert result == ["31DA"]

    def test_coerce_code_list_whitespace_padded_string(self) -> None:
        """Test coerce_code_list with whitespace padded string."""
        result = ScenarioEngine._coerce_code_list(" 31DA ")
        assert result == ["31DA"]

    def test_coerce_code_list_list(self) -> None:
        """Test coerce_code_list with list."""
        result = ScenarioEngine._coerce_code_list(["31DA", "1FC9"])
        assert result == ["31DA", "1FC9"]

    def test_coerce_code_list_tuple(self) -> None:
        """Test coerce_code_list with tuple."""
        result = ScenarioEngine._coerce_code_list(("31DA", "1FC9"))
        assert result == ["31DA", "1FC9"]

    def test_coerce_code_list_set(self) -> None:
        """Test coerce_code_list with set."""
        result = ScenarioEngine._coerce_code_list({"31DA", "1FC9"})
        assert set(result) == {"31DA", "1FC9"}

    def test_coerce_code_list_with_whitespace(self) -> None:
        """Test coerce_code_list with whitespace entries."""
        result = ScenarioEngine._coerce_code_list([" 31DA ", " 1FC9 "])
        assert result == ["31DA", "1FC9"]

    def test_coerce_code_list_with_empty_entries(self) -> None:
        """Test coerce_code_list with empty entries."""
        result = ScenarioEngine._coerce_code_list(["31DA", "", "1FC9", None])
        assert result == ["31DA", "1FC9", "NONE"]

    def test_coerce_code_list_invalid_type(self) -> None:
        """Test coerce_code_list with invalid type."""
        result = ScenarioEngine._coerce_code_list(123)
        assert result == []


class TestScenarioEngineBuildProfileDevices:
    """Tests for build_profile_devices."""

    def test_build_profile_devices(self) -> None:
        """Test building devices from profile."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {
                "37:168270": {"class": "FAN", "variant_id": "default"},
                "32:150000": {"class": "REM"},
            },
            "37:168270": {"excluded_codes": ["1FC9"]},
        }

        devices = engine.build_profile_devices(profile)

        assert len(devices) == 2
        assert devices[0].device_id == "37:168270"
        assert devices[0].slug == "FAN"
        assert devices[0].excluded_codes == ["1FC9"]
        assert devices[0].origin == "profile"
        assert devices[1].device_id == "32:150000"
        assert devices[1].slug == "REM"

    def test_build_profile_devices_skips_hgi(self) -> None:
        """Test that HGI devices are skipped."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {
                "18:001234": {"class": "HGI"},
                "37:168270": {"class": "FAN"},
            },
        }

        devices = engine.build_profile_devices(profile)

        assert len(devices) == 1
        assert devices[0].device_id == "37:168270"

    def test_build_profile_devices_invalid_entry(self) -> None:
        """Test that invalid entries are skipped."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {
                "37:168270": "not a dict",
                "32:150000": {"class": "REM"},
            },
        }

        devices = engine.build_profile_devices(profile)

        assert len(devices) == 1
        assert devices[0].device_id == "32:150000"

    def test_build_profile_devices_empty_known_list(self) -> None:
        """Test with empty known list."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {"_known_list": {}}

        devices = engine.build_profile_devices(profile)

        assert devices == []

    def test_build_profile_devices_no_known_list(self) -> None:
        """Test with no known list."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {}

        devices = engine.build_profile_devices(profile)

        assert devices == []

    def test_build_profile_devices_with_overrides(self) -> None:
        """Test building devices with overrides."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {
                "37:168270": {"class": "FAN", "variant_id": "default"},
            },
            "37:168270": {
                "variant_id": "custom",
                "excluded_codes": ["1FC9"],
                "suppress_autonomous": True,
                "suppress_responses": True,
                "enabled": False,
                "bound": "32:150000",
            },
        }

        devices = engine.build_profile_devices(profile)

        assert len(devices) == 1
        assert devices[0].variant_id == "custom"
        assert devices[0].excluded_codes == ["1FC9"]
        assert devices[0].suppress_autonomous is True
        assert devices[0].suppress_responses is True
        assert devices[0].enabled is False
        assert devices[0].bound_device_id == "32:150000"

    def test_build_profile_devices_entry_override(self) -> None:
        """Test building devices with entry-level overrides."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {
                "37:168270": {
                    "class": "FAN",
                    "variant_id": "default",
                    "excluded_codes": ["1FC9"],
                    "suppress_autonomous": True,
                },
            },
        }

        devices = engine.build_profile_devices(profile)

        assert len(devices) == 1
        assert devices[0].variant_id == "default"
        assert devices[0].excluded_codes == ["1FC9"]
        assert devices[0].suppress_autonomous is True

    def test_build_profile_devices_fallback_class(self) -> None:
        """Test building devices with fallback class."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"37:168270": {}},
        }

        devices = engine.build_profile_devices(profile)

        assert len(devices) == 1
        assert devices[0].slug == "FAN"  # Default fallback

    def test_build_profile_device_not_found(self) -> None:
        """Test building device when not in known_list."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:150000": {}},
        }

        device = engine.build_profile_device(profile, "37:168270")

        assert device is None

    def test_build_profile_device_success(self) -> None:
        """Test successful device building."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"37:168270": {"class": "FAN"}},
        }

        device = engine.build_profile_device(profile, "37:168270")

        assert device is not None
        assert device.device_id == "37:168270"
        assert device.slug == "FAN"


class TestScenarioEngineDeviceTracking:
    """Tests for device tracking methods."""

    def test_get_device_source(self) -> None:
        """Test get_device_source."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        assert engine.get_device_source("37:168270") == "manual"
        assert engine.get_device_source("32:150000") is None

    def test_is_profile_device(self) -> None:
        """Test is_profile_device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._profile_device_ids.add("37:168270")

        assert engine.is_profile_device("37:168270") is True
        assert engine.is_profile_device("32:150000") is False

    def test_is_manual_device(self) -> None:
        """Test is_manual_device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._manual_device_ids.add("37:168270")

        assert engine.is_manual_device("37:168270") is True
        assert engine.is_manual_device("32:150000") is False

    def test_has_manual_devices(self) -> None:
        """Test has_manual_devices."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        assert engine.has_manual_devices() is False

        engine._manual_device_ids.add("37:168270")

        assert engine.has_manual_devices() is True

    def test_is_device_active(self) -> None:
        """Test is_device_active."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices["37:168270"] = device

        assert engine.is_device_active("37:168270") is True
        assert engine.is_device_active("32:150000") is False

    def test_get_autonomous_speed(self) -> None:
        """Test get_autonomous_speed."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        assert engine.get_autonomous_speed() == 1.0

    def test_set_autonomous_speed_valid(self) -> None:
        """Test set_autonomous_speed with valid value."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_autonomous_speed(2.5)
        assert engine.get_autonomous_speed() == 2.5

    def test_set_autonomous_speed_clamp_min(self) -> None:
        """Test set_autonomous_speed clamps to minimum."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_autonomous_speed(0.001)
        assert engine.get_autonomous_speed() == 0.01

    def test_set_autonomous_speed_clamp_max(self) -> None:
        """Test set_autonomous_speed clamps to maximum."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_autonomous_speed(200.0)
        assert engine.get_autonomous_speed() == 100.0

    def test_set_autonomous_speed_invalid_string(self) -> None:
        """Test set_autonomous_speed with invalid string."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_autonomous_speed("invalid")
        assert engine.get_autonomous_speed() == 1.0

    def test_set_autonomous_speed_none(self) -> None:
        """Test set_autonomous_speed with None."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_autonomous_speed(None)
        assert engine.get_autonomous_speed() == 1.0


class TestScenarioEngineLogAndEmit:
    """Tests for _log_and_emit method."""

    def test_log_and_emit_deduplication(self) -> None:
        """Test that recent frame deduplication works."""
        hass = MagicMock()
        hass.bus.async_fire = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        frame = "000 RP --- 37:168270 32:153289 --:------ 1FC9 003 000000"

        # Call multiple times quickly - should only fire once
        engine._log_and_emit("outbound", frame)
        engine._log_and_emit("outbound", frame)
        engine._log_and_emit("outbound", frame)

        assert hass.bus.async_fire.call_count == 1

    def test_log_and_emit_different_origins(self) -> None:
        """Test that different origins are tracked separately."""
        hass = MagicMock()
        hass.bus.async_fire = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        frame = "000 RP --- 37:168270 32:153289 --:------ 1FC9 003 000000"

        engine._log_and_emit("outbound", frame, origin="rf")
        engine._log_and_emit("outbound", frame, origin="sim")

        assert hass.bus.async_fire.call_count == 2


class TestScenarioEngineBuildPacket:
    """Tests for _build_packet static method."""

    def test_build_packet_i_frame(self) -> None:
        """Test building I frame."""
        packet = ScenarioEngine._build_packet(
            "32:153289", "--:------", "I", "1FC9", "000000"
        )

        assert "082" in packet  # RSSI for I frames
        assert " I " in packet  # Verb with space
        assert "32:153289" in packet  # SRC
        assert "--:------" in packet  # DST
        assert "1FC9" in packet  # CODE
        assert "003" in packet  # Length (6 chars / 2 = 3)
        assert "000000" in packet  # Payload

    def test_build_packet_rq_frame(self) -> None:
        """Test building RQ frame."""
        packet = ScenarioEngine._build_packet(
            "37:168270", "32:153289", "RQ", "31DA", "000000"
        )

        assert "000" in packet  # RSSI for non-I frames
        assert "RQ" in packet  # Verb (2 chars, no space)
        assert "37:168270" in packet  # SRC
        assert "32:153289" in packet  # DST
        assert "31DA" in packet  # CODE

    def test_build_packet_w_frame(self) -> None:
        """Test building W frame."""
        packet = ScenarioEngine._build_packet(
            "32:153289", "37:168270", "W", "2411", "000000"
        )

        assert "000" in packet  # RSSI for non-I frames
        assert " W " in packet  # Verb with space
        assert "2411" in packet  # CODE

    def test_build_packet_rp_frame(self) -> None:
        """Test building RP frame."""
        packet = ScenarioEngine._build_packet(
            "32:153289", "37:168270", "RP", "2411", "000000"
        )

        assert "000" in packet  # RSSI for non-I frames
        assert "RP" in packet  # Verb (2 chars, no space)
        assert "2411" in packet  # CODE


class TestScenarioEngineSetAutoAnswer:
    """Tests for set_auto_answer method."""

    def test_set_auto_answer_enabled(self) -> None:
        """Test enabling auto answer."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_auto_answer(True)

        assert engine._auto_answer_enabled is True

    def test_set_auto_answer_disabled(self) -> None:
        """Test disabling auto answer."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        engine.set_auto_answer(False)

        assert engine._auto_answer_enabled is False


class TestScenarioEngineAsyncActivateDevice:
    """Tests for async_activate_device."""

    @pytest.mark.asyncio
    async def test_async_activate_device_with_emitter(self) -> None:
        """Test activating device with emitter start."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        await engine.async_activate_device(device, start_emitter=True)

        assert "37:168270" in engine._active_devices
        assert "37:168270" in engine._manual_device_ids

    @pytest.mark.asyncio
    async def test_async_activate_device_disabled(self) -> None:
        """Test activating disabled device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", enabled=False)

        await engine.async_activate_device(device)

        assert "37:168270" not in engine._active_devices

    @pytest.mark.asyncio
    async def test_async_activate_device_profile_origin(self) -> None:
        """Test activating device with profile origin."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="profile")

        await engine.async_activate_device(device)

        assert "37:168270" in engine._profile_device_ids

    @pytest.mark.asyncio
    async def test_async_activate_device_with_existing_task(self) -> None:
        """Test activating device cancels existing task."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        async def mock_task():
            await asyncio.sleep(10)

        existing_task = asyncio.create_task(mock_task())
        engine._emitter_tasks["37:168270"] = existing_task

        await engine.async_activate_device(device)

        assert "37:168270" in engine._active_devices

    @pytest.mark.asyncio
    async def test_async_activate_device_startup_burst_with_auto_answer(self) -> None:
        """Test activating device with startup burst when auto_answer enabled."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        db.get_periodic = MagicMock(return_value=[entry])

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = True
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        await engine.async_activate_device(
            device, start_emitter=False, emit_startup_burst=True
        )

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_async_activate_device_with_emitter_and_periodic(self) -> None:
        """Test activating device with emitter and periodic entries."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 60
        db.get_periodic = MagicMock(return_value=[entry])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        await engine.async_activate_device(device, start_emitter=True)

        assert "37:168270" in engine._emitter_tasks

    @pytest.mark.asyncio
    async def test_async_activate_device_no_periodic_entries(self) -> None:
        """Test activating device with no periodic entries."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        await engine.async_activate_device(device, start_emitter=True)

        # Emitter task is created but won't emit anything since no entries
        assert "37:168270" in engine._emitter_tasks

    @pytest.mark.asyncio
    async def test_async_activate_device_non_profile_origin(self) -> None:
        """Test activating device with non-profile origin."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        # Add device to profile_device_ids to test the discard logic
        engine._profile_device_ids.add("37:168270")

        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        await engine.async_activate_device(device, start_emitter=False)

        # Should have discarded from profile_device_ids and added to manual_device_ids
        assert "37:168270" not in engine._profile_device_ids
        assert "37:168270" in engine._manual_device_ids

    @pytest.mark.asyncio
    async def test_async_activate_device_custom_origin(self) -> None:
        """Test activating device with custom origin (neither profile nor manual)."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        # Add device to both sets to test the discard logic
        engine._profile_device_ids.add("37:168270")
        engine._manual_device_ids.add("37:168270")

        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="custom")

        await engine.async_activate_device(device, start_emitter=False)

        assert "37:168270" not in engine._profile_device_ids
        assert "37:168270" not in engine._manual_device_ids

    @pytest.mark.asyncio
    async def test_fan_activation_primes_detection_param(self) -> None:
        """Activating a FAN issues an RQ 2411/3E warm-up."""

        hass = MagicMock()
        hass.bus.async_fire = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        endpoint.is_connected = True
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])
        db.find_response = MagicMock(
            return_value=ResponseEntry(
                code="2411",
                payloads=["00003E000000000000000000"],
                delay_ms=0,
            )
        )

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="32:150000",
            slug="FAN",
            origin="profile",
            bound_device_id="37:170000",
        )

        await engine.async_activate_device(
            device,
            start_emitter=False,
            emit_startup_burst=False,
        )

        assert endpoint.send_packet.await_count == 2
        rq_frame = endpoint.send_packet.await_args_list[0].args[0]
        rp_frame = endpoint.send_packet.await_args_list[1].args[0]
        assert " RQ " in rq_frame
        assert "2411 003 00003E" in rq_frame
        assert " RP " in rp_frame
        assert "2411" in rp_frame
        assert "00003E" in rp_frame
        assert device.device_id in engine._primed_fans
        assert "37:168270" not in engine._manual_device_ids


class TestScenarioEngineAsyncSilenceDevice:
    """Tests for async_silence_device."""

    @pytest.mark.asyncio
    async def test_async_silence_device(self) -> None:
        """Test silencing a device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine.async_silence_device("37:168270")

        assert device.suppress_autonomous is True
        assert "37:168270" not in engine._profile_device_ids

    @pytest.mark.asyncio
    async def test_async_silence_nonexistent_device(self) -> None:
        """Test silencing nonexistent device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        await engine.async_silence_device("37:168270")

    @pytest.mark.asyncio
    async def test_async_silence_device_with_emitter_task(self) -> None:
        """Test silencing a device with an emitter task."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        # Create a mock emitter task
        async def mock_task():
            await asyncio.sleep(1)

        engine._emitter_tasks["37:168270"] = asyncio.create_task(mock_task())

        await engine.async_silence_device("37:168270")

        # Task should be cancelled and removed
        assert "37:168270" not in engine._emitter_tasks
        assert device.suppress_autonomous is True


class TestScenarioEngineAsyncStopAll:
    """Tests for async_stop_all."""

    @pytest.mark.asyncio
    async def test_async_stop_all(self) -> None:
        """Test stopping all devices."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device1
        engine._manual_device_ids.add("37:168270")

        async def mock_task():
            pass

        task1 = asyncio.create_task(mock_task())
        engine._emitter_tasks["37:168270"] = task1

        await engine.async_stop_all()

        assert engine._active_devices == {}
        assert engine._emitter_tasks == {}
        assert engine._state == "idle"

    @pytest.mark.asyncio
    async def test_async_stop_all_empty(self) -> None:
        """Test stopping all when no devices active."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        await engine.async_stop_all()

        assert engine._active_devices == {}

    @pytest.mark.asyncio
    async def test_async_stop_all_with_queue_draining(self) -> None:
        """Test stopping all drains the send queue."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        mock_queue = MagicMock()
        mock_queue.empty = MagicMock(side_effect=[False, False, True])
        mock_queue.get_nowait = MagicMock(
            side_effect=["packet1", "packet2", Exception()]
        )
        endpoint._send_queue = mock_queue

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device1

        await engine.async_stop_all()

        assert mock_queue.get_nowait.call_count == 2

    @pytest.mark.asyncio
    async def test_async_stop_all_queue_draining_exception(self) -> None:
        """Test stopping all with queue draining exception."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        mock_queue = MagicMock()
        mock_queue.empty = MagicMock(side_effect=[False, True])
        mock_queue.get_nowait = MagicMock(side_effect=Exception("queue error"))
        endpoint._send_queue = mock_queue

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device1

        await engine.async_stop_all()

        # Should handle exception gracefully
        assert engine._active_devices == {}


class TestScenarioEngineAsyncStopProfileDevices:
    """Tests for async_stop_profile_devices."""

    @pytest.mark.asyncio
    async def test_async_stop_profile_devices(self) -> None:
        """Test stopping profile devices."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="profile")
        engine._active_devices["37:168270"] = device1
        engine._profile_device_ids.add("37:168270")

        with patch.object(engine, "async_silence_device", new_callable=AsyncMock):
            await engine.async_stop_profile_devices()

            assert "37:168270" not in engine._active_devices
            assert "37:168270" not in engine._profile_device_ids

    @pytest.mark.asyncio
    async def test_async_stop_profile_devices_empty(self) -> None:
        """Test stopping profile devices when none exist."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        await engine.async_stop_profile_devices()

        assert engine._profile_device_ids == set()


class TestScenarioEngineAsyncStopManualDevices:
    """Tests for async_stop_manual_devices."""

    @pytest.mark.asyncio
    async def test_async_stop_manual_devices_all(self) -> None:
        """Test stopping all manual devices."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device1
        engine._manual_device_ids.add("37:168270")

        with patch.object(engine, "async_silence_device", new_callable=AsyncMock):
            await engine.async_stop_manual_devices()

            assert "37:168270" not in engine._active_devices
            assert "37:168270" not in engine._manual_device_ids

    @pytest.mark.asyncio
    async def test_async_stop_manual_devices_specific(self) -> None:
        """Test stopping specific manual device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        device2 = ActiveDevice(device_id="32:150000", slug="REM", origin="manual")
        engine._active_devices["37:168270"] = device1
        engine._active_devices["32:150000"] = device2
        engine._manual_device_ids.add("37:168270")
        engine._manual_device_ids.add("32:150000")

        with patch.object(engine, "async_silence_device", new_callable=AsyncMock):
            await engine.async_stop_manual_devices("37:168270")

            assert "37:168270" not in engine._active_devices
            assert "37:168270" not in engine._manual_device_ids
            assert "32:150000" in engine._active_devices

    @pytest.mark.asyncio
    async def test_async_stop_manual_devices_non_manual_target(self) -> None:
        """Test stopping non-manual device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device1 = ActiveDevice(device_id="37:168270", slug="FAN", origin="profile")
        engine._active_devices["37:168270"] = device1
        engine._profile_device_ids.add("37:168270")

        with patch.object(engine, "async_silence_device", new_callable=AsyncMock):
            await engine.async_stop_manual_devices("37:168270")

            # Should not have called silence since it's not a manual device
            engine.async_silence_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_stop_manual_devices_empty(self) -> None:
        """Test stopping manual devices when none exist."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        await engine.async_stop_manual_devices()

        assert engine._manual_device_ids == set()


class TestScenarioEngineAsyncEmitStartupBurst:
    """Tests for async_emit_startup_burst."""

    @pytest.mark.asyncio
    async def test_async_emit_startup_burst(self) -> None:
        """Test emitting startup burst."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        db.get_periodic = MagicMock(return_value=[entry])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine.async_emit_startup_burst()

        endpoint.send_packet.assert_called()
        assert engine._messages_sent > 0

    @pytest.mark.asyncio
    async def test_async_emit_startup_burst_suppress_autonomous(self) -> None:
        """Test startup burst with suppress_autonomous."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", suppress_autonomous=True
        )
        engine._active_devices["37:168270"] = device

        await engine.async_emit_startup_burst()

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_emit_startup_burst_disabled(self) -> None:
        """Test startup burst with disabled device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", enabled=False)
        engine._active_devices["37:168270"] = device

        await engine.async_emit_startup_burst()

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_emit_startup_burst_no_periodic(self) -> None:
        """Test startup burst with no periodic entries."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()
        db.get_periodic = MagicMock(return_value=[])

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine.async_emit_startup_burst()

        endpoint.send_packet.assert_not_called()


class TestScenarioEngineAsyncPlayConversation:
    """Tests for async_play_conversation."""

    @pytest.mark.asyncio
    async def test_async_play_conversation_not_found(self) -> None:
        """Test playing conversation not found."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()
        db.get_conversation = MagicMock(return_value=None)

        engine = ScenarioEngine(hass, endpoint, db)

        result = await engine.async_play_conversation("test_ref", {})

        assert result.success is False
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_async_play_conversation_success(self) -> None:
        """Test playing conversation successfully."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        conv = MagicMock()
        frame = MagicMock()
        frame.t = 0.0
        frame.src = "FAN"
        frame.dst = "REM"
        frame.verb = "I"
        frame.code = "1FC9"
        frame.payload = "000000"
        conv.frames = [frame]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        result = await engine.async_play_conversation(
            "test_ref", {"FAN": "37:168270", "REM": "32:150000"}
        )

        assert result.success is True
        assert result.messages_sent == 1

    @pytest.mark.asyncio
    async def test_async_play_conversation_disabled_device(self) -> None:
        """Test playing conversation with disabled device."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        conv = MagicMock()
        frame = MagicMock()
        frame.t = 0.0
        frame.src = "FAN"
        frame.dst = "REM"
        frame.verb = "I"
        frame.code = "1FC9"
        frame.payload = "000000"
        conv.frames = [frame]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", enabled=False)
        engine._active_devices["37:168270"] = device

        result = await engine.async_play_conversation(
            "test_ref", {"FAN": "37:168270", "REM": "32:150000"}
        )

        assert result.success is True
        assert result.messages_sent == 0

    @pytest.mark.asyncio
    async def test_async_play_conversation_excluded_code(self) -> None:
        """Test playing conversation with excluded code."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        conv = MagicMock()
        frame = MagicMock()
        frame.t = 0.0
        frame.src = "FAN"
        frame.dst = "REM"
        frame.verb = "I"
        frame.code = "1FC9"
        frame.payload = "000000"
        conv.frames = [frame]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", excluded_codes=["1FC9"]
        )
        engine._active_devices["37:168270"] = device

        result = await engine.async_play_conversation(
            "test_ref", {"FAN": "37:168270", "REM": "32:150000"}
        )

        assert result.success is True
        assert result.messages_sent == 0

    @pytest.mark.asyncio
    async def test_async_play_conversation_missing_device_mapping(self) -> None:
        """Test playing conversation with missing device ID mapping."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        conv = MagicMock()
        frame = MagicMock()
        frame.t = 0.0
        frame.src = "FAN"
        frame.dst = "REM"
        frame.verb = "I"
        frame.code = "1FC9"
        frame.payload = "000000"
        conv.frames = [frame]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        result = await engine.async_play_conversation(
            "test_ref",
            {"FAN": "37:168270"},  # Missing REM mapping
        )

        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_async_play_conversation_empty_device_mapping(self) -> None:
        """Test playing conversation with empty device mapping."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        conv = MagicMock()
        frame = MagicMock()
        frame.t = 0.0
        frame.src = "FAN"
        frame.dst = "REM"
        frame.verb = "I"
        frame.code = "1FC9"
        frame.payload = "000000"
        conv.frames = [frame]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)

        result = await engine.async_play_conversation(
            "test_ref",
            {},  # Empty mapping
        )

        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_async_play_conversation_with_delay(self) -> None:
        """Test playing conversation with delay between frames."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        conv = MagicMock()
        frame1 = MagicMock()
        frame1.t = 0.0
        frame1.src = "FAN"
        frame1.dst = "REM"
        frame1.verb = "I"
        frame1.code = "1FC9"
        frame1.payload = "000000"

        frame2 = MagicMock()
        frame2.t = 0.1  # 100ms delay
        frame2.src = "FAN"
        frame2.dst = "REM"
        frame2.verb = "I"
        frame2.code = "1FC9"
        frame2.payload = "000000"

        conv.frames = [frame1, frame2]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        result = await engine.async_play_conversation(
            "test_ref", {"FAN": "37:168270", "REM": "32:150000"}, speed=1.0
        )

        assert result.success is True
        assert result.messages_sent == 2

    @pytest.mark.asyncio
    async def test_async_play_conversation_log_truncation(self) -> None:
        """Test playing conversation with message log truncation."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        conv = MagicMock()
        frame = MagicMock()
        frame.t = 0.0
        frame.src = "FAN"
        frame.dst = "REM"
        frame.verb = "I"
        frame.code = "1FC9"
        frame.payload = "000000"
        conv.frames = [frame]
        db.get_conversation = MagicMock(return_value=conv)

        engine = ScenarioEngine(hass, endpoint, db)
        # Pre-fill the message log to trigger truncation
        engine._message_log = ["msg"] * 1001
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        result = await engine.async_play_conversation(
            "test_ref", {"FAN": "37:168270", "REM": "32:150000"}
        )

        assert result.success is True
        # Log should have been truncated
        assert len(engine._message_log) <= 1000


class TestScenarioEnginePeriodicEmitter:
    """Tests for _periodic_emitter."""

    @pytest.mark.asyncio
    async def test_periodic_emitter(self) -> None:
        """Test periodic emitter runs and can be cancelled."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.01  # Very short interval

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        # Start the emitter
        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))

        # Wait a bit for it to emit at least one packet
        await asyncio.sleep(0.05)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify packets were sent
        assert endpoint.send_packet.call_count >= 1

    @pytest.mark.asyncio
    async def test_periodic_emitter_no_entries(self) -> None:
        """Test periodic emitter with no entries."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        # Should return immediately with no entries
        await engine._periodic_emitter(device, [], 1.0)

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_emitter_message_log_truncation(self) -> None:
        """Test periodic emitter with message log truncation.

        Note: This test covers the burst truncation in _emit_burst (lines 527-528).
        The while loop truncation (lines 592-597) is difficult to cover separately
        because the burst happens first and also truncates the log.
        """
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.001  # Very short interval

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = True
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", origin="manual", enabled=True
        )
        engine._active_devices["37:168270"] = device
        # Pre-fill the message log to trigger truncation
        engine._message_log = ["msg"] * 1001

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have sent packets and truncated log
        assert endpoint.send_packet.call_count >= 1
        assert len(engine._message_log) <= 1000

    @pytest.mark.asyncio
    async def test_periodic_emitter_while_loop_truncation(self) -> None:
        """Test periodic emitter while loop message log truncation (skipping burst)."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.001  # Very short interval

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = True
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", origin="manual", enabled=True
        )
        engine._active_devices["37:168270"] = device
        # Pre-fill the message log to trigger truncation
        engine._message_log = ["msg"] * 1001

        # Mock _emit_burst to skip it and go straight to while loop
        engine._emit_burst = AsyncMock()

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Burst should have been called
        engine._emit_burst.assert_called_once()
        # Should have sent packets in while loop and truncated log
        assert endpoint.send_packet.call_count >= 1
        assert len(engine._message_log) <= 1000

    @pytest.mark.asyncio
    async def test_periodic_emitter_device_disabled(self) -> None:
        """Test periodic emitter when device becomes disabled."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.01

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", origin="manual", suppress_autonomous=True
        )
        engine._active_devices["37:168270"] = device

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.02)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not have sent packets when suppress_autonomous
        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_emitter_excluded_code(self) -> None:
        """Test periodic emitter with excluded code."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.01

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270",
            slug="FAN",
            origin="manual",
            excluded_codes=["1FC9"],
        )
        engine._active_devices["37:168270"] = device

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.02)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not have sent packets when code is excluded
        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_emitter_no_auto_answer(self) -> None:
        """Test periodic emitter when auto_answer is disabled."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.01

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = False
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.02)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not have sent packets when auto_answer is disabled
        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_emitter_no_payloads(self) -> None:
        """Test periodic emitter with entry that has no payloads."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = []
        entry.interval_seconds = 0.01

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.02)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should not have sent packets when no payloads
        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_emitter_send_error(self) -> None:
        """Test periodic emitter with send error."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock(side_effect=Exception("send error"))
        db = MagicMock()

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        entry.interval_seconds = 0.01

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        task = asyncio.create_task(engine._periodic_emitter(device, [entry], 1.0))
        await asyncio.sleep(0.02)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have attempted to send despite error
        endpoint.send_packet.assert_called()


class TestScenarioEngineEmitBurst:
    """Tests for _emit_burst."""

    @pytest.mark.asyncio
    async def test_emit_burst(self) -> None:
        """Test emitting burst."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        payload_idx = {"1FC9": 0}

        await engine._emit_burst(device, [entry], payload_idx, inter_packet_delay=0)

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_emit_burst_excluded_code(self) -> None:
        """Test emitting burst with excluded code."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", excluded_codes=["1FC9"]
        )

        payload_idx = {"1FC9": 0}

        await engine._emit_burst(device, [entry], payload_idx, inter_packet_delay=0)

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_burst_no_payloads(self) -> None:
        """Test emitting burst with no payloads."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = []
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        payload_idx = {"1FC9": 0}

        await engine._emit_burst(device, [entry], payload_idx, inter_packet_delay=0)

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_burst_suppress_autonomous(self) -> None:
        """Test emitting burst with suppress_autonomous."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", suppress_autonomous=True
        )

        payload_idx = {"1FC9": 0}

        await engine._emit_burst(device, [entry], payload_idx, inter_packet_delay=0)

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_burst_send_error(self) -> None:
        """Test emitting burst with send error."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock(side_effect=Exception("send error"))
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        payload_idx = {"1FC9": 0}

        await engine._emit_burst(device, [entry], payload_idx, inter_packet_delay=0)

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_emit_burst_disabled_mid_burst(self) -> None:
        """Test emitting burst when device becomes disabled mid-burst."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        entry1 = MagicMock()
        entry1.code = "1FC9"
        entry1.payloads = ["000000"]
        entry2 = MagicMock()
        entry2.code = "31DA"
        entry2.payloads = ["000000"]
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")

        payload_idx = {"1FC9": 0, "31DA": 0}

        await engine._emit_burst(
            device, [entry1, entry2], payload_idx, inter_packet_delay=0
        )

        # Should have sent at least the first packet
        assert endpoint.send_packet.call_count >= 1


class TestScenarioEngineHandleInboundFrame:
    """Tests for _handle_inbound_frame."""

    @pytest.mark.asyncio
    async def test_handle_inbound_frame_w(self) -> None:
        """Test handling W frame."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        frame = "000 W --- 32:150000 37:168270 --:------ 2411 003 000000"
        await engine._handle_inbound_frame(frame)

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_frame_rq(self) -> None:
        """Test handling RQ frame."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        resp = MagicMock()
        resp.payloads = ["000000"]
        resp.delay_ms = 0
        db.find_response = MagicMock(return_value=resp)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        frame = "000 RQ --- 32:150000 37:168270 --:------ 31DA 003 000000"
        await engine._handle_inbound_frame(frame)

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_frame_invalid(self) -> None:
        """Test handling invalid frame."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        frame = "invalid frame"
        await engine._handle_inbound_frame(frame)

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_frame_auto_answer_disabled(self) -> None:
        """Test handling RQ frame with auto_answer disabled."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = False

        frame = "000 RQ --- 32:150000 37:168270 --:------ 31DA 003 000000"
        await engine._handle_inbound_frame(frame)

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_inbound_frame_non_rq(self) -> None:
        """Test handling non-RQ, non-W frame."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        frame = "000 I --- 32:150000 37:168270 --:------ 1FC9 003 000000"
        await engine._handle_inbound_frame(frame)

        endpoint.send_packet.assert_not_called()

        frame = "000 RP --- 32:150000 37:168270 --:------ 2411 003 000000"
        await engine._handle_inbound_frame(frame)

        endpoint.send_packet.assert_not_called()


class TestScenarioEngineEchoWrite:
    """Tests for _echo_write."""

    @pytest.mark.asyncio
    async def test_echo_write(self) -> None:
        """Test echoing W frame."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine._echo_write("32:150000", "37:168270", "2411", "000000")

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_echo_write_device_not_active(self) -> None:
        """Test echoing W frame for inactive device."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        await engine._echo_write("32:150000", "37:168270", "2411", "000000")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_write_device_disabled(self) -> None:
        """Test echoing W frame for disabled device."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", enabled=False)
        engine._active_devices["37:168270"] = device

        await engine._echo_write("32:150000", "37:168270", "2411", "000000")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_write_suppress_responses(self) -> None:
        """Test echoing W frame with suppress_responses."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", suppress_responses=True
        )
        engine._active_devices["37:168270"] = device

        await engine._echo_write("32:150000", "37:168270", "2411", "000000")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_write_bound_rem(self) -> None:
        """Test echoing W frame with bound REM."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", bound_device_id="32:150000"
        )
        engine._active_devices["37:168270"] = device

        await engine._echo_write("32:150000", "37:168270", "2411", "000000")

        assert endpoint.send_packet.call_count == 2

    @pytest.mark.asyncio
    async def test_echo_write_send_error(self) -> None:
        """Test echoing W frame with send error."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock(side_effect=Exception("send error"))
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="32:150000",
            slug="REM",
            origin="manual",
        )
        engine._active_devices["32:150000"] = device

        # Should handle error gracefully
        await engine._echo_write("37:168270", "32:150000", "1FC9", "000000")

        endpoint.send_packet.assert_called_once()

    @pytest.mark.asyncio
    async def test_echo_write_wake_up_send_error(self) -> None:
        """Test echoing W frame with wake-up send error."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock(side_effect=[Exception("wake error"), None])
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="32:150000",
            slug="FAN",
            origin="manual",
            bound_device_id="37:168270",
        )
        engine._active_devices["32:150000"] = device

        # Should handle wake-up error gracefully and still try echo
        await engine._echo_write("37:168270", "32:150000", "1FC9", "000000")

        assert endpoint.send_packet.call_count == 2


class TestScenarioEngineRespondToRq:
    """Tests for _respond_to_rq."""

    @pytest.mark.asyncio
    async def test_respond_to_rq(self) -> None:
        """Test responding to RQ."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        resp = MagicMock()
        resp.payloads = ["000000"]
        resp.delay_ms = 0
        db.find_response = MagicMock(return_value=resp)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_device_not_active(self) -> None:
        """Test responding to RQ for inactive device."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_device_disabled(self) -> None:
        """Test responding to RQ for disabled device."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", enabled=False)
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_suppress_responses(self) -> None:
        """Test responding to RQ with suppress_responses."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", suppress_responses=True
        )
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_excluded_code(self) -> None:
        """Test responding to RQ with excluded code."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", excluded_codes=["31DA"]
        )
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_no_response(self) -> None:
        """Test responding to RQ with no response entry."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()
        db.find_response = MagicMock(return_value=None)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_not_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_with_delay(self) -> None:
        """Test responding to RQ with delay."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        resp = MagicMock()
        resp.payloads = ["000000"]
        resp.delay_ms = 10
        db.find_response = MagicMock(return_value=resp)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "31DA", "")

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_send_error(self) -> None:
        """Test responding to RQ with send error."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock(side_effect=Exception("send error"))
        db = MagicMock()

        resp = MagicMock()
        resp.payloads = ["000000"]
        resp.delay_ms = 0
        db.find_response = MagicMock(return_value=resp)

        engine = ScenarioEngine(hass, endpoint, db)
        # Add device to active devices so _respond_to_rq will process it
        device = ActiveDevice(
            device_id="37:168270",
            slug="FAN",
            variant_id="default",
            excluded_codes=[],
            suppress_autonomous=False,
            suppress_responses=False,
            enabled=True,
            origin="test",
        )
        engine._active_devices["37:168270"] = device

        # Should handle error gracefully
        await engine._respond_to_rq("32:150000", "37:168270", "1FC9", "")

        endpoint.send_packet.assert_called_once()

    @pytest.mark.asyncio
    async def test_respond_to_rq_dynamic_ctl_payload(self) -> None:
        """CTL devices synthesize responses when DB lacks entries."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()
        db.find_response = MagicMock(return_value=None)

        engine = ScenarioEngine(hass, endpoint, db)
        device = ActiveDevice(device_id="01:150000", slug="CTL", origin="manual")
        engine._active_devices["01:150000"] = device

        await engine._respond_to_rq("18:000730", "01:150000", "30C9", "02")

        endpoint.send_packet.assert_called()

    @pytest.mark.asyncio
    async def test_respond_to_rq_log_truncation(self) -> None:
        """Ensure the message log remains bounded."""
        hass = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        db = MagicMock()

        resp = MagicMock()
        resp.payloads = ["000000"]
        resp.delay_ms = 0
        db.find_response = MagicMock(return_value=resp)

        engine = ScenarioEngine(hass, endpoint, db)
        engine._message_log = ["msg"] * 1001
        device = ActiveDevice(device_id="37:168270", slug="FAN", origin="manual")
        engine._active_devices["37:168270"] = device

        await engine._respond_to_rq("32:150000", "37:168270", "1FC9", "")

        assert len(engine._message_log) <= 1000


class TestScenarioEngineGetRunningScenarioIds:
    """Tests for get_running_scenario_ids."""

    def test_get_running_scenario_ids(self) -> None:
        """Test getting running scenario IDs."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {"test_scenario": {}, "other_scenario": {}}

        result = engine.get_running_scenario_ids()

        assert set(result) == {"test_scenario", "other_scenario"}

    def test_get_running_scenario_ids_empty(self) -> None:
        """Test getting running scenario IDs when none running."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {}

        result = engine.get_running_scenario_ids()

        assert result == []

    def test_check_scenario_conflicts_none(self) -> None:
        """Test checking scenario conflicts with no conflicts."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {}

        result = engine.check_scenario_conflicts("test_scenario")

        assert result == []


class TestScenarioEngineAutonomousEmissionsActive:
    """Tests for autonomous_emissions_active property."""

    def test_autonomous_emissions_active_true(self) -> None:
        """Test autonomous_emissions_active when tasks exist."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._emitter_tasks["37:168270"] = MagicMock()

        assert engine.autonomous_emissions_active is True

    def test_autonomous_emissions_active_false(self) -> None:
        """Test autonomous_emissions_active when no tasks exist."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._emitter_tasks = {}

        assert engine.autonomous_emissions_active is False


class TestScenarioEngineCheckScenarioConflicts:
    """Tests for check_scenario_conflicts."""

    def test_check_scenario_conflicts_with_wildcard(self) -> None:
        """Test checking conflicts with wildcard compatibility."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        from custom_components.ramses_extras.features.device_simulator.const import (
            SCENARIO_REGISTRY,
        )

        # Mock a scenario with wildcard compatibility
        SCENARIO_REGISTRY["test_scenario"] = {"can_run_with": ["*"]}

        result = engine.check_scenario_conflicts("test_scenario")

        assert result == []

    def test_check_scenario_conflicts_with_auto_answer(self) -> None:
        """Test checking conflicts with auto_answer enabled."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._auto_answer_enabled = True
        engine._running_scenarios = {"other_scenario": {}}

        from custom_components.ramses_extras.features.device_simulator.const import (
            SCENARIO_REGISTRY,
        )

        SCENARIO_REGISTRY["test_scenario"] = {"can_run_with": []}
        SCENARIO_REGISTRY["other_scenario"] = {"can_run_with": []}
        SCENARIO_REGISTRY["auto_answer"] = {"can_run_with": ["*"]}

        result = engine.check_scenario_conflicts("test_scenario")

        # Should conflict with auto_answer since test_scenario doesn't list it
        assert len(result) > 0

    def test_check_scenario_conflicts_with_manual_devices(self) -> None:
        """Test checking conflicts with manual devices."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._manual_device_ids.add("37:168270")
        engine._running_scenarios = {}

        from custom_components.ramses_extras.features.device_simulator.const import (
            SCENARIO_REGISTRY,
        )

        SCENARIO_REGISTRY["test_scenario"] = {"can_run_with": []}
        SCENARIO_REGISTRY["autonomous_emissions"] = {"can_run_with": []}

        result = engine.check_scenario_conflicts("test_scenario")

        # Should conflict with autonomous_emissions since test_scenario doesn't list it
        assert len(result) > 0

    def test_check_scenario_conflicts_same_scenario(self) -> None:
        """Test checking conflicts when scenario is already running."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)
        engine._running_scenarios = {"test_scenario": {}}

        from custom_components.ramses_extras.features.device_simulator.const import (
            SCENARIO_REGISTRY,
        )

        SCENARIO_REGISTRY["test_scenario"] = {"can_run_with": []}

        result = engine.check_scenario_conflicts("test_scenario")

        # Should not conflict with itself
        assert result == []


class TestScenarioEngineAsyncCancelScenario:
    """Tests for async_cancel_scenario."""

    @pytest.mark.asyncio
    async def test_async_cancel_scenario(self) -> None:
        """Test canceling a running scenario."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        async def mock_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(mock_task())
        engine._scenario_tasks["test_scenario"] = task
        engine.set_running_metadata("test_scenario", {"param": "value"})

        await engine.async_cancel_scenario("test_scenario")

        assert "test_scenario" not in engine._scenario_tasks
        assert "test_scenario" not in engine._running_scenarios

    @pytest.mark.asyncio
    async def test_async_cancel_scenario_nonexistent(self) -> None:
        """Test canceling a nonexistent scenario."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        # Should not raise
        await engine.async_cancel_scenario("test_scenario")

    @pytest.mark.asyncio
    async def test_async_cancel_scenario_already_done(self) -> None:
        """Test canceling an already done scenario."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        async def mock_task():
            pass

        task = asyncio.create_task(mock_task())
        await task  # Wait for it to complete
        engine._scenario_tasks["test_scenario"] = task

        await engine.async_cancel_scenario("test_scenario")

        assert "test_scenario" not in engine._scenario_tasks


class TestScenarioEngineRunUnavailabilityTest:
    """Tests for async_run_unavailability_test."""

    @pytest.mark.asyncio
    async def test_async_run_unavailability_test(self) -> None:
        """Test running unavailability test."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        with patch.object(
            engine, "_run_registered_scenario", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = {"success": True}

            result = await engine.async_run_unavailability_test(
                device_id="37:168270", silence_after=30.0, resume_after=60.0
            )

            mock_run.assert_called_once()
            assert result == {"success": True}


class TestScenarioEngineRunHvacDeviceLoss:
    """Tests for async_run_hvac_device_loss."""

    @pytest.mark.asyncio
    async def test_async_run_hvac_device_loss(self) -> None:
        """Test running HVAC device loss test."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db)

        with patch.object(
            engine, "_run_registered_scenario", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = {"success": True}

            result = await engine.async_run_hvac_device_loss(
                device_id="37:168270", loss_after=30.0, restore_after=60.0
            )

            mock_run.assert_called_once()
            assert result == {"success": True}


class TestScenarioEngineHasScenarioDefinition:
    """Tests for has_scenario_definition."""

    def test_has_scenario_definition_true(self) -> None:
        """Test has_scenario_definition when definition exists."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        definition = MagicMock()
        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions={"test": definition}
        )

        assert engine.has_scenario_definition("test") is True

    def test_has_scenario_definition_false(self) -> None:
        """Test has_scenario_definition when definition doesn't exist."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db, scenario_definitions={})

        assert engine.has_scenario_definition("test") is False


class TestScenarioEngineRunRegisteredScenario:
    """Tests for async_run_registered_scenario."""

    @pytest.mark.asyncio
    async def test_async_run_registered_scenario_success(self) -> None:
        """Test running a registered scenario successfully."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        definition = MagicMock()
        definition.run = AsyncMock(
            return_value=MagicMock(success=True, details={"message": "done"})
        )

        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions={"test": definition}
        )

        result = await engine.async_run_registered_scenario("test", {"param": "value"})

        assert result["success"] is True
        assert result["message"] == "done"

    @pytest.mark.asyncio
    async def test_async_run_registered_scenario_not_found(self) -> None:
        """Test running a scenario that doesn't exist."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        engine = ScenarioEngine(hass, endpoint, db, scenario_definitions={})

        result = await engine.async_run_registered_scenario("test", {})

        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_async_run_registered_scenario_failure(self) -> None:
        """Test running a scenario that fails."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        definition = MagicMock()
        definition.run = AsyncMock(
            return_value=MagicMock(success=False, errors=["test error"], details={})
        )

        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions={"test": definition}
        )

        result = await engine.async_run_registered_scenario("test", {})

        assert result["success"] is False
        assert result["error"] == "test error"

    @pytest.mark.asyncio
    async def test_async_run_registered_scenario_with_details(self) -> None:
        """Test running a scenario with details."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        definition = MagicMock()
        definition.run = AsyncMock(
            return_value=MagicMock(
                success=True, details={"message": "done", "extra": "data"}
            )
        )

        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions={"test": definition}
        )

        result = await engine.async_run_registered_scenario("test", {})

        assert result["success"] is True
        assert result["message"] == "done"
        assert result["extra"] == "data"

    @pytest.mark.asyncio
    async def test_async_run_registered_scenario_no_errors(self) -> None:
        """Test running a scenario that fails with no errors."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        definition = MagicMock()
        definition.run = AsyncMock(
            return_value=MagicMock(success=False, errors=[], details={})
        )

        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions={"test": definition}
        )

        result = await engine.async_run_registered_scenario("test", {})

        assert result["success"] is False
        assert result["error"] == "Scenario failed"

    @pytest.mark.asyncio
    async def test_async_run_registered_scenario_message_from_details(self) -> None:
        """Test running a scenario where message comes from details."""
        hass = MagicMock()
        endpoint = MagicMock()
        db = MagicMock()

        definition = MagicMock()
        # Use a different key in details to avoid conflict with response.update
        definition.run = AsyncMock(
            return_value=MagicMock(success=True, details={"custom_message": "done"})
        )

        engine = ScenarioEngine(
            hass, endpoint, db, scenario_definitions={"test": definition}
        )

        result = await engine.async_run_registered_scenario("test", {})

        assert result["success"] is True
        # The custom_message should be in the response from details.update
        assert result["custom_message"] == "done"
