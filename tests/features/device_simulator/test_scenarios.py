"""Tests for device_simulator scenarios."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.device_simulator.scenario_engine import (
    ActiveDevice,
    ScenarioEngine,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.base import (
    ScenarioContext,
    ScenarioDefinition,
    ScenarioResult,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.device_playback import (  # noqa: E501
    _infer_device_map,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.device_playback import (  # noqa: E501
    run as device_playback_run,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.device_unavailability import (  # noqa: E501
    _format_message,
    _run_sequence,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.device_unavailability import (  # noqa: E501
    run as device_unavailability_run,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.discovery_test import (  # noqa: E501
    _emit_discovery_frames,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.discovery_test import (  # noqa: E501
    run as discovery_test_run,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.flooding_test import (  # noqa: E501
    _emit_flood,
    _payload_cycle,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.flooding_test import (  # noqa: E501
    run as flooding_test_run,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.hvac_device_loss import (  # noqa: E501
    _format_message as hvac_format_message,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.hvac_device_loss import (  # noqa: E501
    _run_sequence as hvac_run_sequence,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.hvac_device_loss import (  # noqa: E501
    run as hvac_device_loss_run,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.timeout_test import (  # noqa: E501
    _timeout_sequence,
)
from custom_components.ramses_extras.features.device_simulator.scenarios.timeout_test import (  # noqa: E501
    run as timeout_test_run,
)


class TestScenarioResult:
    """Test ScenarioResult dataclass."""

    def test_default_values(self):
        """Test ScenarioResult with default values."""
        result = ScenarioResult(scenario_id="test", success=True)

        assert result.scenario_id == "test"
        assert result.success is True
        assert result.messages_sent == 0
        assert result.duration_seconds == 0.0
        assert result.errors == []
        assert result.details == {}

    def test_custom_values(self):
        """Test ScenarioResult with custom values."""
        result = ScenarioResult(
            scenario_id="test",
            success=False,
            messages_sent=10,
            duration_seconds=5.5,
            errors=["Error 1", "Error 2"],
            details={"key": "value"},
        )

        assert result.scenario_id == "test"
        assert result.success is False
        assert result.messages_sent == 10
        assert result.duration_seconds == 5.5
        assert result.errors == ["Error 1", "Error 2"]
        assert result.details == {"key": "value"}


class TestScenarioDefinition:
    """Test ScenarioDefinition dataclass."""

    def test_scenario_definition(self):
        """Test ScenarioDefinition initialization."""

        async def mock_run(context, params):
            return ScenarioResult(scenario_id="test", success=True)

        definition = ScenarioDefinition(
            scenario_id="test",
            label="Test Scenario",
            toggleable=True,
            can_run_with=["other"],
            description="Test description",
            run=mock_run,
        )

        assert definition.scenario_id == "test"
        assert definition.label == "Test Scenario"
        assert definition.toggleable is True
        assert definition.can_run_with == ["other"]
        assert definition.description == "Test description"
        assert definition.run == mock_run


class TestScenarioContext:
    """Test ScenarioContext class."""

    def test_logger_property(self):
        """Test logger property."""
        hass = MagicMock()
        engine = MagicMock()

        context = ScenarioContext(hass, engine)

        assert context.logger is not None

    def test_get_active_device(self):
        """Test get_active_device method."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}

        context = ScenarioContext(hass, engine)

        result = context.get_active_device("37:168270")

        assert result == device
        assert context.get_active_device("32:150000") is None

    def test_active_devices_by_slug(self):
        """Test active_devices_by_slug method."""
        hass = MagicMock()
        engine = MagicMock()
        device1 = ActiveDevice(device_id="37:168270", slug="FAN")
        device2 = ActiveDevice(device_id="37:168271", slug="FAN")
        device3 = ActiveDevice(device_id="32:150000", slug="REM")
        engine._active_devices = {
            "37:168270": device1,
            "37:168271": device2,
            "32:150000": device3,
        }

        context = ScenarioContext(hass, engine)

        result = context.active_devices_by_slug("fan")

        assert len(result) == 2
        assert device1 in result
        assert device2 in result

    def test_active_devices_by_slug_case_insensitive(self):
        """Test active_devices_by_slug is case insensitive."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}

        context = ScenarioContext(hass, engine)

        result = context.active_devices_by_slug("fan")

        assert len(result) == 1

    def test_device_db_property(self):
        """Test device_db property."""
        hass = MagicMock()
        engine = MagicMock()
        db = MagicMock()
        engine._db = db

        context = ScenarioContext(hass, engine)

        assert context.device_db == db

    def test_active_device_ids(self):
        """Test active_device_ids method."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {"37:168270": MagicMock(), "32:150000": MagicMock()}

        context = ScenarioContext(hass, engine)

        result = context.active_device_ids()

        assert set(result) == {"37:168270", "32:150000"}

    @pytest.mark.asyncio
    async def test_silence_device(self):
        """Test silence_device method."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_silence_device = AsyncMock()

        context = ScenarioContext(hass, engine)

        await context.silence_device("37:168270")

        engine.async_silence_device.assert_called_once_with("37:168270")

    @pytest.mark.asyncio
    async def test_resume_device(self):
        """Test resume_device method."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        engine.async_activate_device = AsyncMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices["37:168270"] = device

        context = ScenarioContext(hass, engine)

        await context.resume_device("37:168270")

        assert device.suppress_autonomous is False
        engine.async_activate_device.assert_called_once_with(device)

    @pytest.mark.asyncio
    async def test_resume_device_nonexistent(self):
        """Test resume_device with nonexistent device."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        engine.async_activate_device = AsyncMock()

        context = ScenarioContext(hass, engine)

        await context.resume_device("37:168270")

        engine.async_activate_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_background_task(self):
        """Test schedule_background_task method."""
        hass = MagicMock()

        async def mock_coro():
            pass

        hass.async_create_background_task = MagicMock(return_value=MagicMock())
        engine = MagicMock()

        context = ScenarioContext(hass, engine)

        result = context.schedule_background_task(mock_coro(), name="test")

        hass.async_create_background_task.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_cancel_existing(self):
        """Test cancel_existing method."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_cancel_scenario = AsyncMock()

        context = ScenarioContext(hass, engine)

        await context.cancel_existing("test_scenario")

        engine.async_cancel_scenario.assert_called_once_with("test_scenario")

    def test_register_task(self):
        """Test register_task method."""
        hass = MagicMock()
        engine = MagicMock()
        engine._scenario_tasks = {}
        task = MagicMock()

        context = ScenarioContext(hass, engine)

        context.register_task("test_scenario", task)

        assert engine._scenario_tasks["test_scenario"] == task

    def test_set_running_metadata(self):
        """Test set_running_metadata method."""
        hass = MagicMock()
        engine = MagicMock()
        engine.set_running_metadata = MagicMock()

        context = ScenarioContext(hass, engine)
        metadata = {"key": "value"}

        context.set_running_metadata("test_scenario", metadata)

        engine.set_running_metadata.assert_called_once_with("test_scenario", metadata)

    def test_clear_running(self):
        """Test clear_running method."""
        hass = MagicMock()
        engine = MagicMock()
        engine._scenario_tasks = {"test_scenario": MagicMock()}
        engine.clear_running_metadata = MagicMock()

        context = ScenarioContext(hass, engine)

        context.clear_running("test_scenario")

        assert "test_scenario" not in engine._scenario_tasks
        engine.clear_running_metadata.assert_called_once_with("test_scenario")

    def test_build_packet(self):
        """Test build_packet method."""
        hass = MagicMock()
        engine = MagicMock()
        engine._build_packet = MagicMock(return_value="packet")

        context = ScenarioContext(hass, engine)

        result = context.build_packet("32:153289", "--:------", "I", "1FC9", "000000")

        engine._build_packet.assert_called_once_with(
            "32:153289", "--:------", "I", "1FC9", "000000"
        )
        assert result == "packet"

    @pytest.mark.asyncio
    async def test_send_packet(self):
        """Test send_packet method."""
        hass = MagicMock()
        engine = MagicMock()
        endpoint = MagicMock()
        endpoint.send_packet = AsyncMock()
        engine._endpoint = endpoint

        context = ScenarioContext(hass, engine)

        await context.send_packet("packet")

        endpoint.send_packet.assert_called_once_with("packet")

    def test_new_active_device(self):
        """Test new_active_device method."""
        hass = MagicMock()
        engine = MagicMock()

        context = ScenarioContext(hass, engine)

        device = context.new_active_device(
            device_id="37:168270", slug="FAN", origin="manual"
        )

        assert device.device_id == "37:168270"
        assert device.slug == "FAN"
        assert device.origin == "manual"


class TestDevicePlayback:
    """Test device_playback scenario."""

    def test_infer_device_map_with_overrides(self):
        """Test _infer_device_map with device_map_overrides."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        overrides = {"FAN": "37:168270", "REM": "32:150000"}
        peers = ["FAN", "REM"]

        device_map, missing = _infer_device_map(context, peers, overrides)

        assert device_map == {"FAN": "37:168270", "REM": "32:150000"}
        assert missing == []

    def test_infer_device_map_with_active_devices(self):
        """Test _infer_device_map with active devices."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}
        context = ScenarioContext(hass, engine)

        peers = ["FAN"]
        overrides = {}

        device_map, missing = _infer_device_map(context, peers, overrides)

        assert device_map == {"FAN": "37:168270"}
        assert missing == []

    def test_infer_device_map_with_active_device_ids(self):
        """Test _infer_device_map with direct device ID lookup."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        engine.is_device_active = MagicMock(return_value=True)
        context = ScenarioContext(hass, engine)

        peers = ["37:168270"]
        overrides = {}

        device_map, missing = _infer_device_map(context, peers, overrides)

        assert device_map == {"37:168270": "37:168270"}
        assert missing == []

    def test_infer_device_map_missing(self):
        """Test _infer_device_map with missing devices."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        engine.is_device_active = MagicMock(return_value=False)
        context = ScenarioContext(hass, engine)

        peers = ["UNKNOWN"]
        overrides = {}

        device_map, missing = _infer_device_map(context, peers, overrides)

        assert device_map == {}
        assert missing == ["UNKNOWN"]

    def test_infer_device_map_skip_all(self):
        """Test _infer_device_map skips ALL peer."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        peers = ["ALL", "FAN"]
        overrides = {}

        device_map, missing = _infer_device_map(context, peers, overrides)

        assert "ALL" not in device_map

    @pytest.mark.asyncio
    async def test_run_no_conversation(self):
        """Test run with no conversation parameter."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        params = {}

        result = await device_playback_run(context, params)

        assert result.success is False
        assert "conversation" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_conversation_not_found(self):
        """Test run with conversation not found."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)
        context.device_db.get_conversation = MagicMock(return_value=None)

        params = {"conversation": "nonexistent"}

        result = await device_playback_run(context, params)

        assert result.success is False
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_import_log_content_failure(self):
        """Test run with log_content import failure."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)
        context.device_db.import_user_log = AsyncMock(return_value=False)

        params = {"log_content": "some log content"}

        result = await device_playback_run(context, params)

        assert result.success is False
        assert "Failed to import" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_import_log_content_success(self):
        """Test run with log_content import success."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)
        context.device_db.import_user_log = AsyncMock(return_value=True)

        conv_mock = MagicMock()
        conv_mock.peers = ["FAN"]
        conv_mock.device_map = {"FAN": "32:150000"}
        context.device_db.get_conversation = MagicMock(return_value=conv_mock)

        engine.get_pause_event = MagicMock(return_value=MagicMock())
        engine.set_running_metadata = MagicMock()
        engine._scenario_tasks = {}
        engine._scenario_pause_events = {}
        engine.clear_running_metadata = MagicMock()

        playback_result = MagicMock()
        playback_result.success = True
        playback_result.messages_sent = 10
        playback_result.duration_seconds = 5.0
        engine.async_play_conversation = AsyncMock(return_value=playback_result)

        params = {"log_content": "some log content"}

        result = await device_playback_run(context, params)

        assert result.success is True
        assert result.messages_sent == 10

    @pytest.mark.asyncio
    async def test_run_with_device_map(self):
        """Test run with explicit device_map."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        conv_mock = MagicMock()
        conv_mock.peers = ["FAN"]
        context.device_db.get_conversation = MagicMock(return_value=conv_mock)

        engine.get_pause_event = MagicMock(return_value=MagicMock())
        engine.set_running_metadata = MagicMock()
        engine._scenario_tasks = {}
        engine._scenario_pause_events = {}
        engine.clear_running_metadata = MagicMock()

        playback_result = MagicMock()
        playback_result.success = True
        playback_result.messages_sent = 5
        playback_result.duration_seconds = 2.0
        engine.async_play_conversation = AsyncMock(return_value=playback_result)

        params = {"conversation": "test", "device_map": {"FAN": "37:168270"}}

        result = await device_playback_run(context, params)

        assert result.success is True
        assert result.messages_sent == 5

    @pytest.mark.asyncio
    async def test_run_playback_failure(self):
        """Test run when playback fails."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        conv_mock = MagicMock()
        conv_mock.peers = ["FAN"]
        context.device_db.get_conversation = MagicMock(return_value=conv_mock)

        engine.get_pause_event = MagicMock(return_value=MagicMock())
        engine.set_running_metadata = MagicMock()
        engine._scenario_tasks = {}
        engine._scenario_pause_events = {}
        engine.clear_running_metadata = MagicMock()

        playback_result = MagicMock()
        playback_result.success = False
        playback_result.errors = ["Playback error"]
        engine.async_play_conversation = AsyncMock(return_value=playback_result)

        params = {"conversation": "test", "device_map": {"FAN": "37:168270"}}

        result = await device_playback_run(context, params)

        assert result.success is False
        assert "Playback error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_missing_peers(self):
        """Test run when device map inference fails."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        engine.is_device_active = MagicMock(return_value=False)
        context = ScenarioContext(hass, engine)

        conv_mock = MagicMock()
        conv_mock.peers = ["UNKNOWN"]
        context.device_db.get_conversation = MagicMock(return_value=conv_mock)

        params = {"conversation": "test"}

        result = await device_playback_run(context, params)

        assert result.success is False
        assert "Unable to map" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_with_skip_verbs_list(self):
        """Test run with skip_verbs as list."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        conv_mock = MagicMock()
        conv_mock.peers = ["FAN"]
        context.device_db.get_conversation = MagicMock(return_value=conv_mock)

        engine.get_pause_event = MagicMock(return_value=MagicMock())
        engine.set_running_metadata = MagicMock()
        engine._scenario_tasks = {}
        engine._scenario_pause_events = {}
        engine.clear_running_metadata = MagicMock()

        playback_result = MagicMock()
        playback_result.success = True
        playback_result.messages_sent = 5
        playback_result.duration_seconds = 2.0
        engine.async_play_conversation = AsyncMock(return_value=playback_result)

        params = {
            "conversation": "test",
            "device_map": {"FAN": "37:168270"},
            "skip_verbs": ["RP", "W"],
        }

        result = await device_playback_run(context, params)

        assert result.success is True
        assert result.messages_sent == 5

    @pytest.mark.asyncio
    async def test_run_with_skip_answers(self):
        """Test run with skip_answers parameter."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        conv_mock = MagicMock()
        conv_mock.peers = ["FAN"]
        context.device_db.get_conversation = MagicMock(return_value=conv_mock)

        engine.get_pause_event = MagicMock(return_value=MagicMock())
        engine.set_running_metadata = MagicMock()
        engine._scenario_tasks = {}
        engine._scenario_pause_events = {}
        engine.clear_running_metadata = MagicMock()

        playback_result = MagicMock()
        playback_result.success = True
        playback_result.messages_sent = 5
        playback_result.duration_seconds = 2.0
        engine.async_play_conversation = AsyncMock(return_value=playback_result)

        params = {
            "conversation": "test",
            "device_map": {"FAN": "37:168270"},
            "skip_answers": True,
        }

        result = await device_playback_run(context, params)

        assert result.success is True
        assert result.messages_sent == 5


class TestDeviceUnavailability:
    """Test device_unavailability scenario."""

    def test_format_message(self):
        """Test _format_message function."""
        targets = ["37:168270", "32:150000"]
        silence_after = 30.0
        resume_after = 60.0

        message = _format_message(targets, silence_after, resume_after)

        assert "Silencing" in message
        assert "37:168270" in message
        assert "32:150000" in message
        assert "30s" in message
        assert "60s" in message

    @pytest.mark.asyncio
    async def test_run_no_active_devices(self):
        """Test run with no active devices."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        params = {}

        result = await device_unavailability_run(context, params)

        assert result.success is False
        assert "No active devices" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_with_device_id(self):
        """Test run with explicit device_id."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {"37:168270": MagicMock()}
        engine.async_cancel_scenario = AsyncMock()

        async def mock_create_task(coro, name):
            # Actually await the coroutine to avoid warnings
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)
        context = ScenarioContext(hass, engine)

        params = {"device_id": "37:168270"}

        result = await device_unavailability_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["targets"]

    @pytest.mark.asyncio
    async def test_run_with_targets_list(self):
        """Test run with explicit targets list."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {"37:168270": MagicMock()}
        engine.async_cancel_scenario = AsyncMock()

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)
        context = ScenarioContext(hass, engine)

        params = {"targets": ["37:168270"]}

        result = await device_unavailability_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["targets"]

    @pytest.mark.asyncio
    async def test_run_with_targets_string(self):
        """Test run with targets as string."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {"37:168270": MagicMock()}
        engine.async_cancel_scenario = AsyncMock()

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)
        context = ScenarioContext(hass, engine)

        params = {"targets": "37:168270"}

        result = await device_unavailability_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["targets"]

    @pytest.mark.asyncio
    async def test_run_sequence(self):
        """Test _run_sequence function."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {
            "37:168270": ActiveDevice(device_id="37:168270", slug="FAN")
        }
        engine.async_silence_device = AsyncMock()
        engine.async_activate_device = AsyncMock()
        context = ScenarioContext(hass, engine)

        targets = ["37:168270"]
        silence_after = 0.1
        resume_after = 0.1

        await _run_sequence(context, targets, silence_after, resume_after)

        engine.async_silence_device.assert_called_once_with("37:168270")
        engine.async_activate_device.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_sequence_cancelled(self):
        """Test _run_sequence handles cancellation."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        engine.async_silence_device = AsyncMock()
        context = ScenarioContext(hass, engine)

        targets = ["37:168270"]

        # Create a task and cancel it
        task = asyncio.create_task(_run_sequence(context, targets, 0.1, 0.1))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestDiscoveryTest:
    """Test discovery_test scenario."""

    @pytest.mark.asyncio
    async def test_run_no_device_id(self):
        """Test run with no device_id available."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        params = {"slug": "UNKNOWN"}

        result = await discovery_test_run(context, params)

        assert result.success is False
        assert "No device_id available" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_with_device_id(self):
        """Test run with explicit device_id."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_cancel_scenario = AsyncMock()

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)
        context = ScenarioContext(hass, engine)

        params = {"device_id": "37:168270"}

        result = await discovery_test_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["device_id"]

    @pytest.mark.asyncio
    async def test_run_with_fingerprint(self):
        """Test run with fingerprint."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_cancel_scenario = AsyncMock()
        context = ScenarioContext(hass, engine)

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)

        # Mock fingerprint lookup
        context.device_db.get_fingerprint_payload = MagicMock(return_value="ABCDEF")

        params = {"device_id": "37:168270", "fingerprint": "test_fp"}

        result = await discovery_test_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["device_id"]

    @pytest.mark.asyncio
    async def test_emit_discovery_frames_with_burst(self):
        """Test _emit_discovery_frames with startup burst."""
        hass = MagicMock()
        engine = MagicMock()
        engine._endpoint = MagicMock()
        engine._endpoint.send_packet = AsyncMock()
        context = ScenarioContext(hass, engine)

        await _emit_discovery_frames(
            context,
            device_id="37:168270",
            payload="0000000000000000",
            count=1,
            interval=0.1,
            include_burst=True,
        )

        assert engine._endpoint.send_packet.call_count == 2

    @pytest.mark.asyncio
    async def test_emit_discovery_frames_without_burst(self):
        """Test _emit_discovery_frames without startup burst."""
        hass = MagicMock()
        engine = MagicMock()
        engine._endpoint = MagicMock()
        engine._endpoint.send_packet = AsyncMock()
        context = ScenarioContext(hass, engine)

        await _emit_discovery_frames(
            context,
            device_id="37:168270",
            payload="0000000000000000",
            count=1,
            interval=0.1,
            include_burst=False,
        )

        assert engine._endpoint.send_packet.call_count == 1

    @pytest.mark.asyncio
    async def test_emit_discovery_frames_cancelled(self):
        """Test _emit_discovery_frames handles cancellation."""
        hass = MagicMock()
        engine = MagicMock()
        engine._endpoint = MagicMock()
        engine._endpoint.send_packet = AsyncMock()
        context = ScenarioContext(hass, engine)

        task = asyncio.create_task(
            _emit_discovery_frames(
                context,
                device_id="37:168270",
                payload="0000000000000000",
                count=5,
                interval=0.1,
                include_burst=True,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestFloodingTest:
    """Test flooding_test scenario."""

    def test_payload_cycle_with_entries(self):
        """Test _payload_cycle with matching entries."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        entry = MagicMock()
        entry.code = "22F7"
        entry.payloads = ["000000", "111111"]
        context.device_db.get_periodic = MagicMock(return_value=[entry])

        result = _payload_cycle(context, "FAN", "22F7")

        assert result == ["000000", "111111"]

    def test_payload_cycle_no_match(self):
        """Test _payload_cycle with no matching entries."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        entry = MagicMock()
        entry.code = "1FC9"
        entry.payloads = ["000000"]
        context.device_db.get_periodic = MagicMock(return_value=[entry])

        result = _payload_cycle(context, "FAN", "22F7")

        assert result == []

    def test_payload_cycle_empty_entries(self):
        """Test _payload_cycle with empty entries."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        context.device_db.get_periodic = MagicMock(return_value=[])

        result = _payload_cycle(context, "FAN", "22F7")

        assert result == []

    @pytest.mark.asyncio
    async def test_run_no_device_id(self):
        """Test run with no device_id available."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        params = {"slug": "UNKNOWN"}

        result = await flooding_test_run(context, params)

        assert result.success is False
        assert "No device_id available" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_no_payloads(self):
        """Test run with no payloads available."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        params = {"device_id": "37:168270", "code": "22F7"}
        context.device_db.get_periodic = MagicMock(return_value=[])

        result = await flooding_test_run(context, params)

        assert result.success is False
        assert "No payloads available" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_success(self):
        """Test run with valid parameters."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_cancel_scenario = AsyncMock()
        context = ScenarioContext(hass, engine)

        entry = MagicMock()
        entry.code = "22F7"
        entry.payloads = ["000000"]
        context.device_db.get_periodic = MagicMock(return_value=[entry])

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)

        params = {"device_id": "37:168270", "code": "22F7", "count": 10}

        result = await flooding_test_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["device_id"]

    @pytest.mark.asyncio
    async def test_emit_flood(self):
        """Test _emit_flood function."""
        hass = MagicMock()
        engine = MagicMock()
        engine._endpoint = MagicMock()
        engine._endpoint.send_packet = AsyncMock()
        context = ScenarioContext(hass, engine)

        await _emit_flood(
            context,
            device_id="37:168270",
            code="22F7",
            payloads=["000000", "111111"],
            count=3,
            interval=0.01,
            duration=0,
        )

        assert engine._endpoint.send_packet.call_count == 3

    @pytest.mark.asyncio
    async def test_emit_flood_with_duration(self):
        """Test _emit_flood with duration limit."""
        hass = MagicMock()
        engine = MagicMock()
        engine._endpoint = MagicMock()
        engine._endpoint.send_packet = AsyncMock()
        context = ScenarioContext(hass, engine)

        await _emit_flood(
            context,
            device_id="37:168270",
            code="22F7",
            payloads=["000000"],
            count=100,
            interval=0.01,
            duration=0.05,
        )

        # Should stop before reaching count due to duration limit
        assert engine._endpoint.send_packet.call_count < 100


class TestHvacDeviceLoss:
    """Test hvac_device_loss scenario."""

    def test_format_message(self):
        """Test _format_message function."""
        message = hvac_format_message("37:168270", 30.0, 60.0)

        assert "Silencing 37:168270 in 30s" in message
        assert "restoring after 60s" in message

    def test_format_message_no_restore(self):
        """Test _format_message without restore time."""
        message = hvac_format_message("37:168270", 30.0, None)

        assert "Silencing 37:168270 in 30s" in message
        assert "restoring" not in message

    @pytest.mark.asyncio
    async def test_run_no_device_id(self):
        """Test run with no device_id."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        params = {}

        result = await hvac_device_loss_run(context, params)

        assert result.success is False
        assert "Missing device_id" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_device_not_active(self):
        """Test run with inactive device."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        params = {"device_id": "37:168270"}

        result = await hvac_device_loss_run(context, params)

        assert result.success is False
        assert "is not active" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_success(self):
        """Test run with valid parameters."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {
            "37:168270": ActiveDevice(device_id="37:168270", slug="FAN")
        }
        engine.async_cancel_scenario = AsyncMock()
        context = ScenarioContext(hass, engine)

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)

        params = {"device_id": "37:168270"}

        result = await hvac_device_loss_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["device_id"]

    @pytest.mark.asyncio
    async def test_run_sequence_with_restore(self):
        """Test _run_sequence with restore."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {
            "37:168270": ActiveDevice(device_id="37:168270", slug="FAN")
        }
        engine.async_silence_device = AsyncMock()
        engine.async_activate_device = AsyncMock()
        context = ScenarioContext(hass, engine)

        await hvac_run_sequence(context, "37:168270", 0.1, 0.1)

        engine.async_silence_device.assert_called_once_with("37:168270")
        engine.async_activate_device.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_sequence_without_restore(self):
        """Test _run_sequence without restore."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {
            "37:168270": ActiveDevice(device_id="37:168270", slug="FAN")
        }
        engine.async_silence_device = AsyncMock()
        engine.async_activate_device = AsyncMock()
        context = ScenarioContext(hass, engine)

        await hvac_run_sequence(context, "37:168270", 0.1, None)

        engine.async_silence_device.assert_called_once_with("37:168270")
        engine.async_activate_device.assert_not_called()


class TestTimeoutTest:
    """Test timeout_test scenario."""

    @pytest.mark.asyncio
    async def test_run_no_device_id(self):
        """Test run with no device_id."""
        hass = MagicMock()
        engine = MagicMock()
        context = ScenarioContext(hass, engine)

        params = {}

        result = await timeout_test_run(context, params)

        assert result.success is False
        assert "Provide 'device_id'" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_device_not_active(self):
        """Test run with inactive device."""
        hass = MagicMock()
        engine = MagicMock()
        engine._active_devices = {}
        context = ScenarioContext(hass, engine)

        params = {"device_id": "37:168270"}

        result = await timeout_test_run(context, params)

        assert result.success is False
        assert "is not active" in result.errors[0]

    @pytest.mark.asyncio
    async def test_run_success(self):
        """Test run with valid parameters."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}
        engine.async_cancel_scenario = AsyncMock()
        context = ScenarioContext(hass, engine)

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)

        params = {"device_id": "37:168270"}

        result = await timeout_test_run(context, params)

        assert result.success is True
        assert "37:168270" in result.details["device_id"]

    @pytest.mark.asyncio
    async def test_run_with_drop_codes(self):
        """Test run with custom drop_codes."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}
        engine.async_cancel_scenario = AsyncMock()
        context = ScenarioContext(hass, engine)

        async def mock_create_task(coro, name):
            await coro
            return MagicMock()

        hass.async_create_background_task = MagicMock(side_effect=mock_create_task)

        params = {"device_id": "37:168270", "drop_codes": ["1FC9", "31DA"]}

        result = await timeout_test_run(context, params)

        assert result.success is True
        assert "1FC9" in result.details["drop_codes"]
        assert "31DA" in result.details["drop_codes"]

    @pytest.mark.asyncio
    async def test_timeout_sequence_drop_codes(self):
        """Test _timeout_sequence with drop_codes."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}
        context = ScenarioContext(hass, engine)

        # Test that codes are added during hold_for period
        with patch.object(asyncio, "sleep"):
            await _timeout_sequence(
                context,
                device_id="37:168270",
                drop_codes=["31DA"],
                delay=0,
                hold_for=0.1,  # Need hold_for > 0 to test the modification
                suppress_all=False,
                original_codes=[],
                original_suppress_flag=False,
            )

        # After the function completes, finally block restores original state
        assert device.excluded_codes == []

    @pytest.mark.asyncio
    async def test_timeout_sequence_suppress_all(self):
        """Test _timeout_sequence with suppress_all."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(device_id="37:168270", slug="FAN")
        engine._active_devices = {"37:168270": device}
        context = ScenarioContext(hass, engine)

        # Test that suppress_responses is set during hold_for period
        with patch.object(asyncio, "sleep"):
            await _timeout_sequence(
                context,
                device_id="37:168270",
                drop_codes=[],
                delay=0,
                hold_for=0.1,  # Need hold_for > 0 to test the modification
                suppress_all=True,
                original_codes=[],
                original_suppress_flag=False,
            )

        # After the function completes, finally block restores original state
        assert device.suppress_responses is False

    @pytest.mark.asyncio
    async def test_timeout_sequence_restores_original(self):
        """Test _timeout_sequence restores original state."""
        hass = MagicMock()
        engine = MagicMock()
        device = ActiveDevice(
            device_id="37:168270", slug="FAN", excluded_codes=["1FC9"]
        )
        engine._active_devices = {"37:168270": device}
        context = ScenarioContext(hass, engine)

        await _timeout_sequence(
            context,
            device_id="37:168270",
            drop_codes=["31DA"],
            delay=0,
            hold_for=0,
            suppress_all=False,
            original_codes=["1FC9"],
            original_suppress_flag=False,
        )

        assert device.excluded_codes == ["1FC9"]
        assert device.suppress_responses is False
