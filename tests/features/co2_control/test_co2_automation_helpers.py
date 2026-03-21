"""Additional tests for CO2 automation helper and setup paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Event, HomeAssistant

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.co2_control.automation import (
    CO2AutomationManager,
)


class _MockState:
    def __init__(self, value: str) -> None:
        self.state = value


@pytest.fixture
def manager() -> CO2AutomationManager:
    """CO2 automation manager with patched dependencies."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.data = {
        DOMAIN: {
            "enabled_features": {"co2_control": True, "sensor_control": True},
            "devices": [
                {"device_id": "32:123456", "type": "FAN"},
                {"device_id": "32_654321", "type": "FAN"},
                {"device_id": "32:123456 (FAN)", "type": "FAN"},
            ],
            "config_entry": MagicMock(
                data={"enabled_features": {"sensor_control": True}},
                options={"enabled_features": {"sensor_control": True}},
            ),
        }
    }

    config_entry = MagicMock()
    config_entry.options = {
        "enabled_features": {"co2_control": True, "sensor_control": True},
        "co2_control": {
            "automation_enabled": True,
            "32:123456": {"enabled": True},
            "32_654321": {"enabled": False},
        },
    }
    config_entry.data = {
        "enabled_features": {"co2_control": True, "sensor_control": True}
    }

    fan_speed_arbiter = MagicMock()
    fan_speed_arbiter.async_set_demand = AsyncMock(return_value=True)
    fan_speed_arbiter.async_clear_demand = AsyncMock(return_value=True)
    fan_speed_arbiter.get_device_debug_state = MagicMock(
        return_value={"resolved_command": "fan_auto"}
    )

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.automation.RamsesCommands"
        ),
        patch(
            "custom_components.ramses_extras.features.co2_control.automation.get_fan_speed_arbiter",
            return_value=fan_speed_arbiter,
        ),
    ):
        instance = CO2AutomationManager(hass, config_entry)

    instance.config.update_config({"automation_enabled": True})
    instance._automation_active = True
    return instance


def test_is_feature_enabled_fallbacks_and_error(manager: CO2AutomationManager) -> None:
    """Feature-enabled checks should respect hass data, entry fallback, and errors."""
    assert manager._is_feature_enabled() is True

    manager.hass.data[DOMAIN]["enabled_features"] = None
    assert manager._is_feature_enabled() is True

    manager.config_entry.options = MagicMock(side_effect=RuntimeError("boom"))
    assert manager._is_feature_enabled() is False


@pytest.mark.asyncio
async def test_start_returns_early_when_feature_disabled(
    manager: CO2AutomationManager,
) -> None:
    """Disabled feature state should skip CO2 automation startup work."""
    manager._is_feature_enabled = MagicMock(return_value=False)
    manager.config.async_load = AsyncMock()
    manager.async_setup = AsyncMock()

    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.ExtrasBaseAutomation.start",
        new=AsyncMock(),
    ) as base_start:
        await manager.start()

    manager.config.async_load.assert_not_awaited()
    manager.async_setup.assert_not_awaited()
    base_start.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_and_stop_manage_runtime_state(
    manager: CO2AutomationManager,
) -> None:
    """Start should register manager, stop should clean listeners and state."""
    manager.async_setup = AsyncMock(return_value=True)
    manager.config.async_load = AsyncMock()

    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.ExtrasBaseAutomation.start",
        new=AsyncMock(),
    ) as base_start:
        await manager.start()

    manager.async_setup.assert_awaited_once()
    manager.config.async_load.assert_awaited_once()
    base_start.assert_awaited_once()
    assert manager.hass.data[DOMAIN]["co2_automation"] is manager

    listener = MagicMock()
    manager._state_change_listeners = [listener]
    manager._source_listener_entities = {"32:123456": {"sensor.one"}}
    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.ExtrasBaseAutomation.stop",
        new=AsyncMock(),
    ) as base_stop:
        await manager.stop()

    listener.assert_called_once()
    base_stop.assert_awaited_once()
    assert manager._state_change_listeners == []
    assert manager._source_listener_entities == {}


def test_iter_candidate_ids_and_device_switch_logic(
    manager: CO2AutomationManager,
) -> None:
    """Candidate IDs and device automation enablement should use merged inputs."""
    manager._zone_managers = {"32:777777": MagicMock()}
    ids = manager._iter_candidate_device_ids()
    assert ids == ["32:123456", "32:123456 (FAN)", "32:777777", "32_654321"]

    assert manager._is_automation_enabled_for_device("32:123456") is True
    manager.config.update_config({"automation_enabled": False})
    manager.hass.states.get.side_effect = lambda entity_id: {
        "switch.co2_control_32_123456": _MockState("on"),
        "switch.co2_control_32_654321": _MockState("off"),
    }.get(entity_id)
    assert manager._is_automation_enabled_for_device("32:123456") is True
    assert manager._is_automation_enabled_for_device("32:654321") is False


@pytest.mark.asyncio
async def test_setup_zone_managers_and_source_listeners(
    manager: CO2AutomationManager,
) -> None:
    """Zone managers and source listeners should be created from config/context."""
    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.CO2ZoneManager"
    ) as zone_manager_cls:
        zone_manager = MagicMock()
        zone_manager_cls.return_value = zone_manager
        await manager._setup_zone_managers()

    assert "32:123456" in manager._zone_managers
    zone_manager_cls.assert_called_once_with(
        manager.hass,
        "32:123456",
        {"enabled": True},
    )

    manager._state_change_listeners = []
    manager._source_listener_entities = {}
    manager._handle_co2_sensor_change = AsyncMock()
    sensor_ctx = {
        "mappings": {"co2": "sensor.internal_co2"},
        "area_sensors": [
            {
                "area_co2_enabled": True,
                "co2_entity": "sensor.bath_co2",
                "co2_threshold_entity": "input_number.bath_threshold",
            },
            {"area_co2_enabled": False, "co2_entity": "sensor.ignored"},
        ],
    }
    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.async_track_state_change_event",
        return_value=MagicMock(),
    ) as track_listener:
        await manager._register_source_listeners("32:123456", sensor_ctx)
        await manager._register_source_listeners("32:123456", sensor_ctx)

    registered_entities = manager._source_listener_entities["32:123456"]
    assert registered_entities == {
        "sensor.internal_co2",
        "sensor.bath_co2",
        "input_number.bath_threshold",
    }
    track_listener.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_and_sensor_listener_edge_paths(
    manager: CO2AutomationManager,
) -> None:
    """Setup should cover disabled and active listener-registration branches."""
    manager._is_feature_enabled = MagicMock(return_value=False)
    assert await manager.async_setup() is False

    real_setup_sensor_listeners = CO2AutomationManager._setup_sensor_listeners.__get__(
        manager,
        CO2AutomationManager,
    )
    manager._is_feature_enabled = MagicMock(return_value=True)
    manager._setup_zone_managers = AsyncMock()
    manager._setup_sensor_listeners = AsyncMock()
    assert await manager.async_setup() is True
    manager._setup_zone_managers.assert_awaited_once()
    manager._setup_sensor_listeners.assert_awaited_once()
    manager._setup_sensor_listeners = real_setup_sensor_listeners

    zone_manager = MagicMock()
    zone_manager.zones = {
        "zone_1": MagicMock(sensor_entity="sensor.zone_one", zone_id="zone_1"),
        "zone_2": MagicMock(sensor_entity="", zone_id="zone_2"),
    }
    manager._zone_managers = {"32:123456": zone_manager}
    manager.hass.data[DOMAIN]["devices"] = [
        {"device_id": "32:123456", "type": "FAN"},
        {"device_id": "32:654321", "type": "FAN"},
        "32:777777",
        "",
    ]
    manager._setup_source_listeners_for_device = AsyncMock()
    manager._state_change_listeners = []
    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.async_track_state_change_event",
        return_value=MagicMock(),
    ) as track_listener:
        await manager._setup_sensor_listeners()

    track_listener.assert_called_once_with(
        manager.hass,
        ["sensor.zone_one"],
        manager._handle_co2_sensor_change,
    )
    manager._setup_source_listeners_for_device.assert_any_await("32:123456")
    manager._setup_source_listeners_for_device.assert_any_await("32:654321")
    manager._setup_source_listeners_for_device.assert_any_await("32:777777")


@pytest.mark.asyncio
async def test_homeassistant_started_skip_and_error_paths(
    manager: CO2AutomationManager,
) -> None:
    """Startup evaluation should skip when inactive and tolerate evaluation errors."""
    manager._automation_active = False
    manager._is_feature_enabled = MagicMock(return_value=True)
    manager._evaluate_co2_control = AsyncMock()

    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.ExtrasBaseAutomation._on_homeassistant_started",
        new=AsyncMock(),
    ):
        await manager._on_homeassistant_started(None)

    manager._evaluate_co2_control.assert_not_awaited()

    manager._automation_active = True
    manager._iter_candidate_device_ids = MagicMock(return_value=["32:123456"])
    manager._evaluate_co2_control = AsyncMock(side_effect=RuntimeError("boom"))

    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.ExtrasBaseAutomation._on_homeassistant_started",
        new=AsyncMock(),
    ):
        await manager._on_homeassistant_started(None)

    manager._evaluate_co2_control.assert_awaited_once_with("32:123456")


@pytest.mark.asyncio
async def test_setup_source_listeners_for_device_stores_context(
    manager: CO2AutomationManager,
) -> None:
    """Source-listener setup should cache the resolved sensor context."""
    sensor_ctx = {"mappings": {"co2": "sensor.internal_co2"}, "area_sensors": []}
    manager._get_sensor_control_context = AsyncMock(return_value=sensor_ctx)
    manager._register_source_listeners = AsyncMock()

    await manager._setup_source_listeners_for_device("32:123456")

    assert manager._latest_sensor_control_context["32:123456"] == sensor_ctx
    manager._register_source_listeners.assert_awaited_once_with("32:123456", sensor_ctx)


@pytest.mark.asyncio
async def test_handle_co2_sensor_change_routes_to_zone_or_sensor_context(
    manager: CO2AutomationManager,
) -> None:
    """Sensor changes should route through zones first, then sensor context."""
    zone_manager = MagicMock()
    zone_manager.zones = {
        "zone_1": MagicMock(sensor_entity="sensor.zone_co2", zone_id="zone_1")
    }
    zone_manager.update_from_state = AsyncMock()
    manager._zone_managers = {"32:123456": zone_manager}
    manager._latest_sensor_control_context = {
        "32:654321": {"mappings": {"co2": "sensor.internal_co2"}, "area_sensors": []}
    }
    manager._evaluate_co2_control = AsyncMock()

    zone_event = Event(
        "state_changed",
        {"entity_id": "sensor.zone_co2", "new_state": _MockState("1200")},
    )
    await manager._handle_co2_sensor_change(zone_event)
    zone_manager.update_from_state.assert_awaited_once()
    manager._evaluate_co2_control.assert_awaited_once_with("32:123456")

    manager._evaluate_co2_control.reset_mock()
    sensor_event = Event(
        "state_changed",
        {"entity_id": "sensor.internal_co2", "new_state": _MockState("900")},
    )
    await manager._handle_co2_sensor_change(sensor_event)
    manager._evaluate_co2_control.assert_awaited_once_with("32:654321")


@pytest.mark.asyncio
async def test_sensor_control_context_helpers(manager: CO2AutomationManager) -> None:
    """Sensor control helpers should handle fallback, selection, and disabled cases."""
    assert manager._entity_in_sensor_context(None, {"mappings": {}}) is False
    assert (
        manager._entity_in_sensor_context(
            "sensor.internal_co2",
            {
                "mappings": {"co2": "sensor.internal_co2"},
                "area_sensors": [],
            },
        )
        is True
    )
    assert (
        manager._entity_in_sensor_context(
            "sensor.bath_co2",
            {
                "mappings": {},
                "area_sensors": [
                    {"area_co2_enabled": True, "co2_entity": "sensor.bath_co2"}
                ],
            },
        )
        is True
    )

    sensor_control = manager._get_sensor_control_config("32_123456")
    assert isinstance(sensor_control, dict)
    assert manager._get_device_type_for_sensor_control("32:123456 (FAN)") == "FAN"

    manager.hass.data[DOMAIN]["config_entry"] = None
    assert manager._is_sensor_control_enabled() is False
    manager.hass.data[DOMAIN]["config_entry"] = MagicMock(
        data={"enabled_features": {"sensor_control": True}},
        options={"enabled_features": {"sensor_control": True}},
    )
    assert manager._is_sensor_control_enabled() is True

    manager._is_sensor_control_enabled = MagicMock(return_value=False)
    assert await manager._get_sensor_control_context("32:123456") is None

    manager._is_sensor_control_enabled = MagicMock(return_value=True)
    manager._get_device_type_for_sensor_control = MagicMock(return_value=None)
    assert await manager._get_sensor_control_context("32:123456") is None

    manager._get_device_type_for_sensor_control = MagicMock(return_value="FAN")
    with patch(
        "custom_components.ramses_extras.features.co2_control.automation.C02AutomationManager",
        create=True,
    ):
        with patch(
            "custom_components.ramses_extras.features.sensor_control.resolver.SensorControlResolver"
        ) as resolver_cls:
            resolver = MagicMock()
            resolver.resolve_entity_mappings = AsyncMock(
                return_value={
                    "mappings": {"co2": "sensor.internal_co2"},
                    "sources": {"co2": "internal"},
                    "raw_internal": {"co2": "sensor.internal_co2"},
                    "area_sensors": [],
                }
            )
            resolver_cls.return_value = resolver
            manager._get_raw_area_sensors_from_options = MagicMock(
                return_value=[{"co2_entity": "sensor.fallback"}]
            )
            context = await manager._get_sensor_control_context("32:123456")

    assert context is not None
    assert context["mappings"]["co2"] == "sensor.internal_co2"
    assert context["area_sensors"] == [{"co2_entity": "sensor.fallback"}]


def test_get_status_includes_fan_arbiter(manager: CO2AutomationManager) -> None:
    """Status should include fan arbiter debug information."""
    status = manager.get_status()
    assert "fan_arbiter" in status
    assert status["fan_arbiter"]["32:123456"]["resolved_command"] == "fan_auto"


@pytest.mark.asyncio
async def test_evaluate_co2_control_activates_with_zone_manager(
    manager: CO2AutomationManager,
) -> None:
    """Active zone triggers should activate CO2 control and adjust fan speed."""
    zone_manager = MagicMock()
    zone_manager.check_zone_triggers = AsyncMock(return_value=["zone_1"])
    manager._zone_managers = {"32:123456": zone_manager}
    manager._get_sensor_control_context = AsyncMock(return_value={"area_sensors": []})
    manager._register_source_listeners = AsyncMock()
    manager._evaluate_trigger_sources = MagicMock(return_value=[])
    manager._update_automation_status = AsyncMock()
    manager._notify_priority_takeover = AsyncMock()
    manager._adjust_fan_speed = AsyncMock()
    manager._co2_active = False

    await manager._evaluate_co2_control("32:123456 (FAN)")

    assert manager._co2_active is True
    manager._notify_priority_takeover.assert_awaited_once()
    manager._adjust_fan_speed.assert_awaited_once_with("32:123456", zone_manager)
    manager._update_automation_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_co2_control_deactivates_and_returns_idle(
    manager: CO2AutomationManager,
) -> None:
    """Transition from active to inactive should release priority and return idle."""
    manager._zone_managers = {}
    manager._get_sensor_control_context = AsyncMock(return_value={"area_sensors": []})
    manager._register_source_listeners = AsyncMock()
    manager._evaluate_trigger_sources = MagicMock(return_value=[])
    manager._update_automation_status = AsyncMock()
    manager._notify_priority_release = AsyncMock()
    manager._return_to_idle = AsyncMock()
    manager._co2_active = True
    manager._is_automation_enabled_for_device = MagicMock(return_value=True)

    await manager._evaluate_co2_control("32:123456")

    assert manager._co2_active is False
    manager._notify_priority_release.assert_awaited_once()
    manager._return_to_idle.assert_awaited_once_with("32:123456")


@pytest.mark.asyncio
async def test_evaluate_co2_control_uses_trigger_fallback_when_no_zone_manager(
    manager: CO2AutomationManager,
) -> None:
    """Triggered sources without a zone manager should use the fallback boost path."""
    manager._zone_managers = {}
    manager._get_sensor_control_context = AsyncMock(return_value={"area_sensors": []})
    manager._register_source_listeners = AsyncMock()
    manager._evaluate_trigger_sources = MagicMock(
        return_value=[{"source_id": "internal_co2"}]
    )
    manager._update_automation_status = AsyncMock()
    manager._notify_priority_takeover = AsyncMock()
    manager._boost_from_triggers = AsyncMock()
    manager._co2_active = False

    await manager._evaluate_co2_control("32:123456")

    manager._boost_from_triggers.assert_awaited_once_with("32:123456")


@pytest.mark.asyncio
async def test_boost_return_idle_priority_and_unload_helpers(
    manager: CO2AutomationManager,
) -> None:
    """Boost, idle, priority notifications, and unload should update runtime state."""
    manager.fan_speed_arbiter.async_set_demand = AsyncMock(return_value=True)
    await manager._boost_from_triggers("32:123456")
    assert manager._last_fan_speed == 3

    manager.fan_speed_arbiter.async_set_demand.reset_mock()
    await manager._boost_from_triggers("32:123456")
    manager.fan_speed_arbiter.async_set_demand.assert_not_awaited()

    manager.fan_speed_arbiter.async_clear_demand = AsyncMock(return_value=True)
    manager._last_fan_speed = 5
    await manager._return_to_idle("32:123456")
    assert manager._last_fan_speed == 1

    humidity_manager = MagicMock()
    humidity_manager.pause_for_co2 = AsyncMock()
    humidity_manager.resume_from_co2 = AsyncMock()
    manager.humidity_manager = humidity_manager
    await manager._notify_priority_takeover()
    await manager._notify_priority_release()
    humidity_manager.pause_for_co2.assert_awaited_once()
    humidity_manager.resume_from_co2.assert_awaited_once()

    listener = MagicMock()
    manager._state_change_listeners = [listener]
    manager._source_listener_entities = {"32:123456": {"sensor.one"}}
    assert await manager.async_unload() is True
    listener.assert_called_once()
    assert manager._source_listener_entities == {}
