"""Tests for the shared fan speed arbiter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.fan_speed_arbiter import (
    FanSpeedArbiter,
    FanSpeedDemand,
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
        "32:123456", "fan_low"
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
        "32:123456", "fan_auto"
    )


@pytest.mark.asyncio
async def test_async_apply_deduplicates_same_command(arbiter):
    """Arbiter should skip sending the same command within the dedup window."""
    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_medium",
        priority=30,
    )
    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32:123456", "fan_medium"
    )

    # Same command again within dedup window — should be skipped
    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_medium",
        priority=30,
    )

    assert success is True
    arbiter.ramses_commands.send_command.assert_not_awaited()

    # Different command — should be sent
    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_high",
        priority=30,
    )

    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32:123456", "fan_high"
    )

    # Same command after dedup window expires — should be re-sent
    arbiter.ramses_commands.send_command.reset_mock()
    # Simulate window expiry by backdating the last-applied timestamp
    arbiter._last_applied["32:123456"] = ("fan_high", 0.0)
    success = await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_high",
        priority=30,
    )

    assert success is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32:123456", "fan_high"
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


@pytest.mark.asyncio
async def test_manual_override_wins_over_automation_demands(arbiter):
    """Manual override should take precedence over automation demands."""
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="co2_control",
        source_id="co2_control",
        requested_speed="fan_high",
        priority=30,
    )

    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_set_manual_override(
        "32_123456",
        source_id="default_service",
        requested_speed="fan_low",
    )

    assert success is True
    assert arbiter.is_manual_override_active("32_123456") is True
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32:123456", "fan_low"
    )

    resolved = arbiter.resolve("32_123456")
    assert resolved.command_name == "fan_low"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.feature_id == "manual_override"


@pytest.mark.asyncio
async def test_clear_manual_override_resumes_automation_demands(arbiter):
    """Clearing manual override should resume the best remaining automation demand."""
    await arbiter.async_set_demand(
        "32_123456",
        feature_id="humidity_control",
        source_id="humidity_control",
        requested_speed="fan_low",
        priority=5,
    )
    await arbiter.async_set_manual_override(
        "32_123456",
        source_id="default_service",
        requested_speed="fan_high",
    )

    arbiter.ramses_commands.send_command.reset_mock()
    success = await arbiter.async_clear_manual_override("32_123456")

    assert success is True
    assert arbiter.is_manual_override_active("32_123456") is False
    arbiter.ramses_commands.send_command.assert_awaited_once_with(
        "32:123456", "fan_low"
    )


def test_get_control_mode_tracks_manual_and_extras(arbiter):
    """Control mode should reflect manual override and active Extras demands."""
    assert arbiter.get_control_mode("32_123456") == "auto_by_extras"

    arbiter._demands = {
        "32:123456": {
            ("co2_control", "co2_control"): MagicMock(
                feature_id="co2_control",
                source_id="co2_control",
                requested_speed="fan_medium",
                priority=30,
                reason="co2_trigger",
                metadata={},
            )
        }
    }
    assert arbiter.get_control_mode("32_123456") == "auto_by_extras"

    arbiter._demands["32:123456"][("manual_override", "default_service")] = MagicMock(
        feature_id="manual_override",
        source_id="default_service",
        requested_speed="fan_low",
        priority=1000,
        reason="manual_override",
        metadata={"manual": True},
    )
    assert arbiter.get_control_mode("32_123456") == "manual_override"


def test_get_control_mode_reports_unit_auto_when_extras_disabled(arbiter):
    """Disabling extras control should report unit-native auto mode."""
    arbiter._demands = {
        "32:123456": {
            ("co2_control", "co2_control"): MagicMock(
                feature_id="co2_control",
                source_id="co2_control",
                requested_speed="fan_medium",
                priority=30,
                reason="co2_trigger",
                metadata={},
            )
        }
    }
    arbiter.set_extras_control_enabled("32_123456", False)

    assert arbiter.get_control_mode("32_123456") == "auto_by_fan"


def test_resolve_returns_fan_auto_when_extras_disabled(arbiter):
    """Active automation demands should be ignored while extras control is disabled."""
    arbiter._demands = {
        "32:123456": {
            ("co2_control", "co2_control"): MagicMock(
                feature_id="co2_control",
                source_id="co2_control",
                requested_speed="fan_medium",
                priority=30,
                reason="co2_trigger",
                metadata={},
            )
        }
    }
    arbiter.set_extras_control_enabled("32_123456", False)

    resolved = arbiter.resolve("32_123456")

    assert resolved.command_name == "fan_auto"
    assert resolved.winning_demand is None
    assert len(resolved.active_demands) == 1


def test_normalize_speed_invalid_raises_value_error():
    """Unsupported speeds should raise a clear error."""
    with pytest.raises(ValueError, match="Unsupported fan speed"):
        FanSpeedArbiter.normalize_speed("turbo")


def test_speed_rank_and_debug_state(hass, arbiter):
    """Debug helpers should expose resolved and active demand information."""
    assert FanSpeedArbiter.speed_rank("missing") == -1

    arbiter._demands = {
        "32:123456": {
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
    assert device_state["control_mode"] == "auto_by_extras"
    assert device_state["winning_demand"]["feature_id"] == "co2_control"
    assert len(debug_state["devices"]["32:123456"]["active_demands"]) == 1


def test_debug_state_reports_extras_auto_without_active_demands(arbiter):
    """Enabled extras control should still report Extras Auto without demands."""
    device_state = arbiter.get_device_debug_state("32_123456")

    assert device_state["control_mode"] == "auto_by_extras"
    assert device_state["resolved_command"] == "fan_auto"


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


def test_veto_overrides_higher_speed_demand(arbiter):
    """A veto demand should win over a higher-speed normal demand."""
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_low",
                priority=100,
                reason="humidity_veto",
                is_veto=True,
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")

    assert resolved.command_name == "fan_low"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.is_veto is True
    assert resolved.winning_demand.feature_id == "humidity_control"


def test_veto_with_lower_priority_still_wins(arbiter):
    """A veto with lower priority than another veto still wins on priority."""
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_low",
                priority=50,
                reason="humidity_veto",
                is_veto=True,
            ),
            ("co2_control", "co2_control"): FanSpeedDemand(
                feature_id="co2_control",
                source_id="co2_control",
                requested_speed="fan_low",
                priority=200,
                reason="co2_veto",
                is_veto=True,
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")

    # Higher-priority veto wins among vetoes
    assert resolved.command_name == "fan_low"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.is_veto is True
    assert resolved.winning_demand.feature_id == "co2_control"


def test_no_veto_uses_highest_speed(arbiter):
    """Without vetoes, the highest speed demand should still win."""
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_low",
                priority=5,
                reason="humidity_balance_idle",
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")

    assert resolved.command_name == "fan_high"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.feature_id == "temp_control"


def test_neutral_clears_demand_lets_others_win(arbiter):
    """When humidity clears its demand (neutral), temp_control should win."""
    # Only temp_control has a demand — humidity cleared its demand
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")

    assert resolved.command_name == "fan_high"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.feature_id == "temp_control"


# --- Integration-style tests: simulate full humidity + temp_control flow ---


def test_integration_humidity_veto_blocks_temp_cooling(arbiter):
    """Simulate: temp_control wants cooling (fan_high) but humidity vetoes.

    This is the scenario from the bug report: humidity says 'stop' because
    outside is wetter, but temp_control wants to cool.  The veto should win.
    """
    # temp_control sets a fan_high demand (cooling mode)
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            # humidity_control vetoes because outside is wetter
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_low",
                priority=100,
                reason="humidity_veto",
                is_veto=True,
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")

    # Veto wins — fan should be low, not high
    assert resolved.command_name == "fan_low"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.is_veto is True
    assert resolved.winning_demand.feature_id == "humidity_control"
    # Both demands are still active (veto doesn't remove temp_control's demand)
    assert len(resolved.active_demands) == 2


def test_integration_humidity_neutral_lets_temp_cool(arbiter):
    """Simulate: humidity is neutral (steps aside), temp_control cools.

    Humidity clears its demand.  Only temp_control has a demand.
    temp_control's fan_high should win.
    """
    # humidity_control cleared its demand (neutral) — only temp_control remains
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
        }
    }

    resolved = arbiter.resolve("32:123456")

    assert resolved.command_name == "fan_high"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.feature_id == "temp_control"
    assert not resolved.winning_demand.is_veto


def test_integration_humidity_demand_and_temp_cool_both_want_high(arbiter):
    """Simulate: both humidity and temp want ventilation — no conflict."""
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_high",
                priority=20,
                reason="humidity_dehumidify",
            ),
        }
    }

    resolved = arbiter.resolve("32:123456")

    # Both want fan_high — highest speed wins (tie broken by priority/timestamp)
    assert resolved.command_name == "fan_high"
    assert resolved.winning_demand is not None
    assert not resolved.winning_demand.is_veto


def test_integration_co2_veto_overrides_temp_and_humidity(arbiter):
    """Simulate: CO2 vetoes, temp and humidity both want ventilation."""
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_high",
                priority=20,
                reason="humidity_dehumidify",
            ),
            ("co2_control", "co2_control"): FanSpeedDemand(
                feature_id="co2_control",
                source_id="co2_control",
                requested_speed="fan_low",
                priority=200,
                reason="co2_veto",
                is_veto=True,
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")

    # CO2 veto wins
    assert resolved.command_name == "fan_low"
    assert resolved.winning_demand is not None
    assert resolved.winning_demand.is_veto is True
    assert resolved.winning_demand.feature_id == "co2_control"


def test_integration_humidity_veto_then_clear_lets_temp_resume(arbiter):
    """Simulate: humidity vetoes, then clears veto — temp_control resumes.

    This verifies that clearing the veto demand allows temp_control's
    demand to take effect again.
    """
    # Step 1: humidity veto blocks temp_control
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
            ("humidity_control", "humidity_control"): FanSpeedDemand(
                feature_id="humidity_control",
                source_id="humidity_control",
                requested_speed="fan_low",
                priority=100,
                reason="humidity_veto",
                is_veto=True,
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")
    assert resolved.command_name == "fan_low"

    # Step 2: humidity clears its veto (conditions changed — now neutral)
    arbiter._demands = {
        "32:123456": {
            ("temp_control", "temp_control"): FanSpeedDemand(
                feature_id="temp_control",
                source_id="temp_control",
                requested_speed="fan_high",
                priority=20,
                reason="temp_control_cooling",
            ),
        }
    }

    resolved = arbiter.resolve("32_123456")
    assert resolved.command_name == "fan_high"
    assert resolved.winning_demand.feature_id == "temp_control"
