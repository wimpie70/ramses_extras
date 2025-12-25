"""Tests for WebSocket command metadata handling in extras_registry."""

from custom_components.ramses_extras.extras_registry import RamsesEntityRegistry


def test_register_and_list_websocket_commands() -> None:
    registry = RamsesEntityRegistry()
    registry.clear()

    registry.register_websocket_commands(
        "hello_world",
        {
            "toggle_switch": "ramses_extras/hello_world/toggle_switch",
            "get_switch_state": "ramses_extras/hello_world/get_switch_state",
        },
    )
    registry.register_websocket_commands(
        "humidity_control",
        {"status": "ramses_extras/humidity_control/status"},
    )

    assert registry.get_websocket_commands_for_feature("hello_world") == {
        "toggle_switch": "ramses_extras/hello_world/toggle_switch",
        "get_switch_state": "ramses_extras/hello_world/get_switch_state",
    }
    assert registry.get_features_with_websocket_commands() == [
        "hello_world",
        "humidity_control",
    ]

    all_cmds = registry.get_all_websocket_commands()
    assert set(all_cmds) == {"hello_world", "humidity_control"}
    assert all_cmds["humidity_control"] == {
        "status": "ramses_extras/humidity_control/status"
    }


def test_websocket_registry_clear_resets_state() -> None:
    registry = RamsesEntityRegistry()
    registry.register_websocket_commands("foo", {"bar": "baz"})
    assert registry.get_features_with_websocket_commands() == ["foo"]

    registry.clear()

    assert registry.get_all_websocket_commands() == {}
    assert registry.get_features_with_websocket_commands() == []
