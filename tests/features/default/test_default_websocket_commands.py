"""Tests for default feature WebSocket commands."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from homeassistant.components import websocket_api

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.websocket_commands import (
    ws_get_2411_schema,
    ws_get_all_feature_entities,
    ws_get_available_devices,
    ws_get_bound_rem,
    ws_get_cards_enabled,
    ws_get_enabled_features,
    ws_get_entity_mappings,
    ws_websocket_info,
)

# Unwrap decorators for testing
ws_get_enabled_features = ws_get_enabled_features.__wrapped__
ws_get_cards_enabled = ws_get_cards_enabled.__wrapped__
ws_websocket_info = ws_websocket_info.__wrapped__
ws_get_entity_mappings = ws_get_entity_mappings.__wrapped__
ws_get_all_feature_entities = ws_get_all_feature_entities.__wrapped__
ws_get_available_devices = ws_get_available_devices.__wrapped__
ws_get_bound_rem = ws_get_bound_rem.__wrapped__
ws_get_2411_schema = ws_get_2411_schema.__wrapped__


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "enabled_features": {"humidity_control": True},
            "cards_enabled": True,
            "devices": [
                MagicMock(id="32:123456", type="FAN"),
                "37:654321",
            ],
        }
    }
    hass.states = MagicMock()
    hass.states.async_all.return_value = []
    return hass


@pytest.fixture
def connection():
    """Mock WebSocket connection."""
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


async def test_ws_get_enabled_features(hass, connection):
    """Test ws_get_enabled_features command."""
    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_once_with(
        1, {"enabled_features": {"humidity_control": True}}
    )

    # Test error path
    hass.data = None
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_error.assert_called()


async def test_ws_get_enabled_features_config_entry_fallback(connection):
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "config_entry": MagicMock(
                data={},
                options={"enabled_features": {"default": True}},
            )
        }
    }

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1, {"enabled_features": {"default": True}}
    )


async def test_ws_get_enabled_features_list_enabled(connection):
    hass = MagicMock()
    hass.data = {DOMAIN: {"enabled_features": ["default", "debug"]}}

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1, {"enabled_features": ["default", "debug"]}
    )


async def test_ws_get_enabled_features_no_config_entry(connection):
    hass = MagicMock()
    hass.data = {DOMAIN: {}}

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(1, {"enabled_features": {}})


async def test_ws_get_cards_enabled(hass, connection):
    """Test ws_get_cards_enabled command."""
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}
    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_result.assert_called_once_with(1, {"cards_enabled": True})


async def test_ws_get_cards_enabled_error_path(connection):
    hass = MagicMock()
    hass.data = None  # triggers AttributeError in handler
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}

    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_error.assert_called_with(1, "get_cards_enabled_failed", ANY)


async def test_ws_websocket_info(hass, connection):
    """Test ws_websocket_info command."""
    msg = {"id": 1, "type": "ramses_extras/websocket_info"}

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.extras_registry"
    ) as mock_registry:
        mock_registry.get_all_websocket_commands.return_value = {
            "default": {"test_cmd": "ramses_extras/test"}
        }
        mock_registry.get_features_with_websocket_commands.return_value = ["default"]

        await ws_websocket_info(hass, connection, msg)

        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert "commands" in result
        assert result["total_commands"] == 1
        assert result["features"] == ["default"]


async def test_ws_websocket_info_empty(hass, connection):
    msg = {"id": 1, "type": "ramses_extras/websocket_info"}

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.extras_registry"
    ) as mock_registry:
        mock_registry.get_all_websocket_commands.return_value = {}
        mock_registry.get_features_with_websocket_commands.return_value = []

        await ws_websocket_info(hass, connection, msg)

        connection.send_result.assert_called_once()
        result = connection.send_result.call_args[0][1]
        assert result["total_commands"] == 0
        assert result["features"] == []


async def test_ws_get_entity_mappings(hass, connection):
    """Test ws_get_entity_mappings command."""
    msg = {
        "id": 1,
        "type": "ramses_extras/get_entity_mappings",
        "feature_id": "humidity_control",
        "device_id": "32:123456",
    }

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.GetEntityMappingsCommand"
    ) as mock_cmd_class:
        mock_cmd = MagicMock()
        mock_cmd.execute = AsyncMock()
        mock_cmd_class.return_value = mock_cmd

        await ws_get_entity_mappings(hass, connection, msg)
        mock_cmd.execute.assert_called_once_with(connection, msg)

    # Error path - missing identifiers
    msg_error = {"id": 2, "type": "ramses_extras/get_entity_mappings"}
    await ws_get_entity_mappings(hass, connection, msg_error)
    connection.send_error.assert_called_with(2, "missing_feature_identifier", ANY)


async def test_ws_get_entity_mappings_error_path(hass, connection):
    """Test error handling when command execution fails."""
    msg = {
        "id": 1,
        "type": "ramses_extras/get_entity_mappings",
        "feature_id": "humidity_control",
    }

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.GetEntityMappingsCommand"
    ) as mock_cmd_class:
        mock_cmd = MagicMock()
        mock_cmd.execute = AsyncMock(side_effect=RuntimeError("boom"))
        mock_cmd_class.return_value = mock_cmd

        await ws_get_entity_mappings(hass, connection, msg)

        connection.send_error.assert_called_with(1, "get_entity_mappings_failed", ANY)


async def test_ws_get_all_feature_entities(hass, connection):
    """Test ws_get_all_feature_entities command."""
    msg = {
        "id": 1,
        "type": "ramses_extras/get_all_feature_entities",
        "feature_id": "humidity_control",
        "device_id": "32:123456",
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetAllFeatureEntitiesCommand"
    ) as mock_cmd_class:
        mock_cmd = MagicMock()
        mock_cmd.execute = AsyncMock()
        mock_cmd_class.return_value = mock_cmd

        await ws_get_all_feature_entities(hass, connection, msg)
        mock_cmd.execute.assert_called_once_with(connection, msg)


async def test_ws_get_all_feature_entities_error_path(hass, connection):
    msg = {
        "id": 1,
        "type": "ramses_extras/get_all_feature_entities",
        "feature_id": "humidity_control",
        "device_id": "32:123456",
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.websocket_base.GetAllFeatureEntitiesCommand"
    ) as mock_cmd_class:
        mock_cmd = MagicMock()
        mock_cmd.execute = AsyncMock(side_effect=RuntimeError("fail"))
        mock_cmd_class.return_value = mock_cmd

        await ws_get_all_feature_entities(hass, connection, msg)
        connection.send_error.assert_called_with(
            1, "get_all_feature_entities_failed", ANY
        )


async def test_ws_get_all_feature_entities_missing_identifier(hass, connection):
    """Error when neither feature_id nor const_module is provided."""
    msg_error = {"id": 2, "type": "ramses_extras/get_all_feature_entities"}

    await ws_get_all_feature_entities(hass, connection, msg_error)
    connection.send_error.assert_called_with(
        2,
        "missing_feature_identifier",
        "Either feature_id or const_module must be provided",
    )


async def test_ws_get_available_devices(hass, connection):
    """Test ws_get_available_devices command."""
    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)

    connection.send_result.assert_called_once()
    devices = connection.send_result.call_args[0][1]["devices"]
    assert len(devices) == 2
    assert devices[0]["device_id"] == "32:123456"
    assert devices[1]["device_id"] == "37:654321"


async def test_ws_get_available_devices_mixed_objects(hass, connection):
    class FakeDevice:
        def __init__(self) -> None:
            self.device_id = "01:AAAAAA"
            self.type = "TEMP"

    hass.data[DOMAIN]["devices"] = [
        FakeDevice(),
        MagicMock(id=None, __class__=MagicMock(__name__="Dummy")),
    ]

    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)

    connection.send_result.assert_called()
    devices = connection.send_result.call_args[0][1]["devices"]
    assert any(d.get("device_id") == "01:AAAAAA" for d in devices)


async def test_ws_get_available_devices_handles_non_list(hass, connection):
    """Gracefully handle devices stored as a non-list."""
    hass.data[DOMAIN]["devices"] = "not-a-list"

    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)

    connection.send_result.assert_called_once()
    devices = connection.send_result.call_args[0][1]["devices"]
    assert devices == []


async def test_ws_get_available_devices_slug_label(hass, connection):
    class FakeDevice:
        def __init__(self) -> None:
            self.id = "11:AAAAAA"
            self.type = "TEMP"

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.DeviceFilter._get_device_slugs",
        return_value=["temp", "temp", "sensor"],
    ):
        hass.data[DOMAIN]["devices"] = [FakeDevice()]

        msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
        await ws_get_available_devices(hass, connection, msg)

    devices = connection.send_result.call_args[0][1]["devices"]
    assert devices[0]["slug_label"] == "temp, sensor"


async def test_ws_get_available_devices_slugs_exception(hass, connection):
    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.DeviceFilter._get_device_slugs",
        side_effect=RuntimeError("boom"),
    ):
        msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
        await ws_get_available_devices(hass, connection, msg)

    connection.send_result.assert_called()
    devices = connection.send_result.call_args[0][1]["devices"]
    # Even if slug extraction fails, device entries should still exist
    assert len(devices) == 2


async def test_ws_get_bound_rem(hass, connection):
    """Test ws_get_bound_rem command."""
    msg = {"id": 1, "type": "ramses_extras/get_bound_rem", "device_id": "32:123456"}

    with patch(
        "custom_components.ramses_extras.features.default.websocket_commands.RamsesCommands"
    ) as mock_commands_class:
        mock_commands = MagicMock()
        mock_commands._get_bound_rem_device = AsyncMock(return_value="18:123456")
        mock_commands_class.return_value = mock_commands

        await ws_get_bound_rem(hass, connection, msg)
        connection.send_result.assert_called_once_with(
            1, {"device_id": "32:123456", "bound_rem": "18:123456"}
        )


async def test_ws_get_2411_schema(hass, connection):
    """Test ws_get_2411_schema command."""
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}

    mock_state = MagicMock()
    mock_state.entity_id = "number.32_123456_param_01"
    mock_state.attributes = {
        "friendly_name": "Test Param",
        "min": 0,
        "max": 100,
        "step": 1,
    }
    hass.states.async_all.return_value = [mock_state]

    await ws_get_2411_schema(hass, connection, msg)

    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert "01" in schema
    assert schema["01"]["name"] == "Test Param"


async def test_ws_get_2411_schema_empty(hass, connection):
    """Return empty schema when no matching states."""
    hass.states.async_all.return_value = []
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}

    await ws_get_2411_schema(hass, connection, msg)

    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert schema == {}


async def test_ws_get_2411_schema_missing_attrs(hass, connection):
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}

    mock_state = MagicMock()
    mock_state.entity_id = "number.32_123456_param_02"
    mock_state.attributes = {}
    hass.states.async_all.return_value = [mock_state]

    await ws_get_2411_schema(hass, connection, msg)

    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert "02" in schema
