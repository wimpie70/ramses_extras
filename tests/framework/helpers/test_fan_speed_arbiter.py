"""Tests for the shared fan speed arbiter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.fan_speed_arbiter import (
    FanSpeedArbiter,
    get_fan_speed_arbiter,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    mock_hass = MagicMock()
    mock_hass.data = {}
    return mock_hass


@pytest.fixture
def arbiter(hass):
    """Arbiter instance with mocked command sender."""
    with patch(
        "custom_components.ramses_extras.framework.helpers.fan_speed_arbiter.RamsesCommands"
    ) as mock_commands_cls:
        mock_commands = MagicMock()
        mock_commands.send_command = AsyncMock(return_value=MagicMock(success=True))
        mock_commands_cls.return_value = mock_commands
        instance = FanSpeedArbiter(hass)
        instance.ramses_commands = mock_commands
        return instance


def test_get_fan_speed_arbiter_returns_singleton(hass):
    """The same arbiter instance should be reused per hass."""
    with patch(
        "custom_components.ramses_extras.framework.helpers.fan_speed_arbiter.RamsesCommands"
    ):
        first = get_fan_speed_arbiter(hass)
        second = get_fan_speed_arbiter(hass)

    assert first is second


@pytest.mark.asyncio
async def test_async_set_demand_applies_highest_speed(arbiter):
    """Higher demanded speed should win across active features."""
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="humidity_control",
        source_id="humidity_control",
        requested_speed="fan_low",
        priority=5,
    )
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_medium",
        priority=30,
    )

    resolved = arbiter.resolve("32_123456")

    assert resolved.command_name == "fan_medium"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.feature_id == "co2_control"


@pytest.mark.asyncio
async def test_async_clear_demand_preserves_other_feature_demand(arbiter):
    """Clearing one feature should keep the other feature's demand active."""
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="humidity_control",
        source_id="humidity_control",
        requested_speed="fan_low",
        priority=5,
    )
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_medium",
        priority=30,
    )

    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_clear_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
    )

    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32_123456", "fan_low"
    )


@pytest.mark.asyncio
async def test_async_clear_demand_without_remaining_demands_returns_to_auto(arbiter):
    """No remaining demand should resolve to auto mode."""
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_high",
        priority=30,
    )

    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_clear_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
    )

    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32_123456", "fan_auto"
    )


@pytest.mark.asyncio
async def test_async_apply_sends_same_command_multiple_times(arbiter):
    """Arbiter should send command every time, even if same as previous."""
    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_medium",
        priority=30,
    )
    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32_123456", "fan_medium"
    )

    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_medium",
        priority=30,
    )

    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32_123456", "fan_medium"
    )


@pytest.mark.parametrize(
    ("requested_speed", "expected"),
    [
        ("auto", "fan_auto"),
        ("fan_low", "fan_low"),
        ("medium", "fan_medium"),
        (" FAN_HIGH ", "fan_high"),
        (4, "fan_high"),
    ],
)
def test_normalize_speed_variants(requested_speed, expected):
    """Different speed inputs should normalize to registry command names."""
    assert FanSpeedArbiter.normalize_speed(requested_speed) == expected


@pytest.mark.asyncio
async def test_async_clear_feature_without_source_id_removes_all_feature_demands(
    arbiter,
):
    """Clearing a feature without a source should remove all of its demands."""
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="humidity_control",
        source_id="humidity_balance",
        requested_speed="fan_low",
        priority=5,
    )
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="humidity_control",
        source_id="humidity_spike",
        requested_speed="fan_high",
        priority=20,
    )

    success = await arbiter.async_clear_demand(
        "32_123456",
        feature_id="humidity_control",
    )

    assert success is True
    assert arbiter.get_active_demands("32_123456") == []


@pytest.mark.asyncio
async def test_async_apply_returns_false_when_command_send_fails(arbiter):
    """A failed final command send should return False.

    It should also avoid updating the last-applied command cache.
    """
    arbiter.ramses_commands.send_command = AsyncMock(
        return_value=MagicMock(success=False)
    )

    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_high",
        priority=30,
    )

    assert success is False


def test_normalize_speed_invalid_raises_value_error():
    """Unsupported speeds should raise a clear error."""
    with pytest.raises(ValueError, match="Unsupported fan speed"):
        FanSpeedArbiter.normalize_speed("turbo")


def test_speed_rank_and_debug_state(hass, arbiter):
    """Debug helpers should expose resolved and active demand information."""
    assert FanSpeedArbiter.speed_rank("missing") == -1

    arbiter._demands = {
        "32_123456": {
            ("co2_control", "co2_control"): MagicMock(
                feature_id="co2_control",
                source_id="co2_control",
                requested_speed="fan_medium",
                priority=30,
                reason="co2_trigger",
                metadata={"target_speed": 3},
            )
        }
    }

    debug_state = arbiter.get_debug_state()
    device_state = arbiter.get_device_debug_state("32_123456")

    assert device_state["resolved_command"] == "fan_medium"
    assert device_state["winning_demand"]["feature_id"] == "co2_control"
    assert len(debug_state["devices"]["32_123456"]["active_demands"]) == 1


def test_get_fan_speed_arbiter_uses_fallback_attribute_for_mock_hass():
    """Mock-style hass objects should still reuse the fallback arbiter instance."""
    mock_hass = MagicMock()
    mock_hass.data = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.fan_speed_arbiter.RamsesCommands"
    ):
        first = get_fan_speed_arbiter(mock_hass)
        second = get_fan_speed_arbiter(mock_hass)

    assert first is second
