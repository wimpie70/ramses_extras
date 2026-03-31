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
    ws_get_fan_config_associations,
    ws_get_remote_bindings,
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
ws_get_fan_config_associations = ws_get_fan_config_associations.__wrapped__
ws_get_remote_bindings = ws_get_remote_bindings.__wrapped__


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
        1,
        {
            "enabled_features": {"humidity_control": True},
            "options": {},
        },
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
                options={
                    "enabled_features": {"default": True},
                    "ramses_debugger_default_poll_ms": 1234,
                },
            )
        }
    }

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1,
        {
            "enabled_features": {"default": True},
            "options": {"ramses_debugger_default_poll_ms": 1234},
        },
    )


async def test_ws_get_enabled_features_list_enabled(connection):
    hass = MagicMock()
    hass.data = {DOMAIN: {"enabled_features": ["default", "debug"]}}

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1,
        {
            "enabled_features": ["default", "debug"],
            "options": {},
        },
    )


async def test_ws_get_enabled_features_no_config_entry(connection):
    hass = MagicMock()
    hass.data = {DOMAIN: {}}

    msg = {"id": 1, "type": "ramses_extras/default/get_enabled_features"}
    await ws_get_enabled_features(hass, connection, msg)
    connection.send_result.assert_called_with(
        1,
        {
            "enabled_features": {},
            "options": {},
        },
    )


async def test_ws_get_cards_enabled(hass, connection):
    """Test ws_get_cards_enabled command."""
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}
    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_result.assert_called_once_with(
        1, {"cards_enabled": True, "_backend_version": "0.0.0"}
    )


async def test_ws_get_cards_enabled_error_path(connection):
    hass = MagicMock()
    hass.data = None  # triggers AttributeError in handler
    msg = {"id": 1, "type": "ramses_extras/default/get_cards_enabled"}

    await ws_get_cards_enabled(hass, connection, msg)
    connection.send_error.assert_called_with(1, "get_cards_enabled_failed", ANY)


async def test_ws_get_entity_mappings_missing_identifier(hass, connection):
    """Test ws_get_entity_mappings with missing feature identifier."""
    msg = {"id": 1, "type": "ramses_extras/get_entity_mappings"}
    await ws_get_entity_mappings(hass, connection, msg)
    connection.send_error.assert_called_with(
        1,
        "missing_feature_identifier",
        "Either feature_id or const_module must be provided",
    )


async def test_ws_get_entity_mappings_overlay_includes_area_sensors(hass, connection):
    """Test sensor_control overlay forwards area_sensors metadata."""
    hass.data[DOMAIN]["enabled_features"] = {"sensor_control": True}
    msg = {
        "id": 1,
        "type": "ramses_extras/get_entity_mappings",
        "feature_id": "default",
    }

    overlay_holder: dict[str, object] = {}

    class FakeCommand:
        def __init__(self, _hass, _feature_identifier, overlay_provider=None):
            overlay_holder["overlay_provider"] = overlay_provider

        async def execute(self, _connection, _msg):
            return None

    with (
        patch(
            "custom_components.ramses_extras.features.default.websocket_commands.GetEntityMappingsCommand",
            FakeCommand,
        ),
        patch(
            "custom_components.ramses_extras.features.sensor_control.resolver.SensorControlResolver"
        ) as mock_resolver_cls,
    ):
        mock_resolver = MagicMock()
        mock_resolver.resolve_entity_mappings = AsyncMock(
            return_value={
                "mappings": {"indoor_temperature": "sensor.room_temp"},
                "sources": {"indoor_temperature": {"kind": "external"}},
                "raw_internal": {"indoor_temperature": "sensor.internal_temp"},
                "abs_humidity_inputs": {"indoor_abs_humidity": {"temperature": {}}},
                "area_sensors": [
                    {
                        "source_id": "bathroom",
                        "label": "Bathroom",
                        "valid": True,
                    }
                ],
            }
        )
        mock_resolver_cls.return_value = mock_resolver

        await ws_get_entity_mappings(hass, connection, msg)

        overlay_provider = overlay_holder["overlay_provider"]
        assert callable(overlay_provider)
        overlay_result = await overlay_provider(
            "32:123456", {"indoor_temperature": "sensor.base_temp"}
        )

    assert overlay_result["mappings"]["indoor_temperature"] == "sensor.room_temp"
    assert overlay_result["area_sensors"][0]["source_id"] == "bathroom"
    assert overlay_result["sources"]["indoor_temperature"]["kind"] == "external"


async def test_ws_get_available_devices_empty_list(hass, connection):
    """Test ws_get_available_devices with empty devices list."""
    hass.data[DOMAIN]["devices"] = []
    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)
    connection.send_result.assert_called_once_with(1, {"devices": []})


async def test_ws_get_available_devices_with_slugs(hass, connection):
    """Test ws_get_available_devices extracts device slugs correctly."""
    mock_device = MagicMock()
    mock_device.id = "32:123456"
    mock_device.type = "FAN"
    hass.data[DOMAIN]["devices"] = [mock_device]
    msg = {"id": 1, "type": "ramses_extras/get_available_devices"}
    await ws_get_available_devices(hass, connection, msg)
    connection.send_result.assert_called_once()


async def test_ws_get_bound_rem(hass, connection):
    """Test ws_get_bound_rem returns both device and Extras bindings."""
    msg = {"id": 1, "type": "ramses_extras/get_bound_rem", "device_id": "32:123456"}

    with (
        patch(
            "custom_components.ramses_extras.features.default.websocket_commands.RamsesCommands"
        ) as mock_cls,
        patch(  # noqa: N806
            "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry"
        ) as mock_get_registry,
    ):
        mock_commands = MagicMock()
        mock_commands._get_bound_rem_device = AsyncMock(return_value="37:654321")
        mock_cls.return_value = mock_commands

        mock_registry = MagicMock()
        mock_registry.get_binding_for_fan.return_value = {
            "rem_id": "37:654321",
            "role": "primary",
            "enabled": True,
        }
        mock_registry.get_rem_id_for_fan.return_value = "37:654321"
        mock_get_registry.return_value = mock_registry

        await ws_get_bound_rem(hass, connection, msg)

        connection.send_result.assert_called_once_with(
            1,
            {
                "device_id": "32:123456",
                "bound_rem": "37:654321",
                "extras_binding": {
                    "rem_id": "37:654321",
                    "role": "primary",
                    "enabled": True,
                },
                "extras_rem_id": "37:654321",
                "source": "extras",
            },
        )


async def test_ws_get_2411_schema_with_states(hass, connection):
    """Test ws_get_2411_schema returns schema from existing states."""
    mock_state = MagicMock()
    mock_state.entity_id = "number.32_123456_param_01"
    mock_state.attributes = {
        "friendly_name": "Parameter 01",
        "min": 0,
        "max": 100,
        "step": 1,
        "unit_of_measurement": "%",
    }
    hass.states.async_all.return_value = [mock_state]
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}
    await ws_get_2411_schema(hass, connection, msg)
    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert "01" in schema
    assert schema["01"]["min_value"] == 0
    assert schema["01"]["max_value"] == 100


async def test_ws_get_2411_schema_multiple_params(hass, connection):
    """Test ws_get_2411_schema with multiple parameter entities."""
    states = []
    for i in range(3):
        mock_state = MagicMock()
        mock_state.entity_id = f"number.32_123456_param_0{i}"
        mock_state.attributes = {"friendly_name": f"Parameter 0{i}"}
        states.append(mock_state)
    hass.states.async_all.return_value = states
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}
    await ws_get_2411_schema(hass, connection, msg)
    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert len(schema) == 3


async def test_ws_get_2411_schema_fan_prefixed_params(hass, connection):
    """Test ws_get_2411_schema returns schema for fan-prefixed param entities."""
    mock_state = MagicMock()
    mock_state.entity_id = "number.fan_32_123456_param_75"
    mock_state.attributes = {
        "friendly_name": "Comfort temperature",
        "min": 5,
        "max": 35,
        "step": 0.5,
        "unit_of_measurement": "°C",
    }
    hass.states.async_all.return_value = [mock_state]
    msg = {"id": 1, "type": "ramses_extras/get_2411_schema", "device_id": "32:123456"}
    await ws_get_2411_schema(hass, connection, msg)
    connection.send_result.assert_called_once()
    schema = connection.send_result.call_args[0][1]
    assert "75" in schema
    assert schema["75"]["min_value"] == 5
    assert schema["75"]["max_value"] == 35


async def test_ws_get_fan_config_associations_no_config_entry(connection):
    """Test ws_get_fan_config_associations returns empty when no config entry."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}  # No config_entry

    msg = {
        "id": 1,
        "type": "ramses_extras/get_fan_config_associations",
        "device_id": "32:123456",
    }
    await ws_get_fan_config_associations(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "device_id": "32:123456",
            "zones": [],
            "zone_ids": [],
            "remote_bindings": [],
            "remote_binding_ids": [],
            "source": "config",
        },
    )


async def test_ws_get_fan_config_associations_with_config(connection):
    """Test ws_get_fan_config_associations returns zones and REMs from config."""
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "config_entry": MagicMock(
                data={
                    "ramses_extras": {
                        "schema_version": 1,
                        "features": {
                            "zones": {
                                "FANs": {
                                    "32:123456": [
                                        {
                                            "zone_id": "bathroom",
                                            "actuator": {"min_position": 15},
                                        },
                                        {"zone_id": "office"},
                                    ]
                                }
                            },
                            "remote_binding": {
                                "FANs": {
                                    "32:123456": {
                                        "REMs": [
                                            {
                                                "rem_id": "37_654321",
                                                "role": "primary",
                                            },
                                        ]
                                    }
                                }
                            },
                        },
                    }
                },
                options={},
            )
        }
    }

    msg = {
        "id": 1,
        "type": "ramses_extras/get_fan_config_associations",
        "device_id": "32:123456",
    }
    await ws_get_fan_config_associations(hass, connection, msg)

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]

    assert result["device_id"] == "32:123456"
    assert result["zone_ids"] == ["bathroom", "office"]
    assert len(result["zones"]) == 2
    assert result["zones"][0]["zone_id"] == "bathroom"
    assert result["remote_binding_ids"] == ["37:654321"]
    assert len(result["remote_bindings"]) == 1
    assert result["remote_bindings"][0]["rem_id"] == "37:654321"
    assert result["source"] == "config"


async def test_ws_get_fan_config_associations_legacy_remote_id(connection):
    """Test ws_get_fan_config_associations normalizes legacy remote_id values."""
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "config_entry": MagicMock(
                data={
                    "ramses_extras": {
                        "schema_version": 1,
                        "features": {
                            "remote_binding": {
                                "FANs": {
                                    "32:123456": {
                                        "REMs": [
                                            {
                                                "remote_id": "37_654321",
                                                "role": "primary",
                                            },
                                        ]
                                    }
                                }
                            },
                        },
                    }
                },
                options={},
            )
        }
    }

    msg = {
        "id": 1,
        "type": "ramses_extras/get_fan_config_associations",
        "device_id": "32:123456",
    }
    await ws_get_fan_config_associations(hass, connection, msg)

    result = connection.send_result.call_args[0][1]

    # Legacy remote_id should be normalized to rem_id
    assert result["remote_binding_ids"] == ["37:654321"]
    assert result["remote_bindings"][0]["rem_id"] == "37:654321"
    assert "remote_id" not in result["remote_bindings"][0]


async def test_ws_get_remote_bindings_all(connection):
    """Test ws_get_remote_bindings returns all bindings."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.list_bindings.return_value = {
        "32:123456": [{"rem_id": "37:654321", "role": "primary"}],
        "32:789012": [{"rem_id": "37:987654", "role": "primary"}],
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/get_remote_bindings"}
        await ws_get_remote_bindings(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "bindings": {
                "32:123456": [{"rem_id": "37:654321", "role": "primary"}],
                "32:789012": [{"rem_id": "37:987654", "role": "primary"}],
            },
            "count": 2,
        },
    )


async def test_ws_get_remote_bindings_for_device(connection):
    """Test ws_get_remote_bindings returns binding for specific device."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_binding_for_fan.return_value = {
        "rem_id": "37:654321",
        "role": "primary",
        "enabled": True,
    }
    mock_registry.get_rem_id_for_fan.return_value = "37:654321"

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_remote_bindings",
            "device_id": "32:123456",
        }
        await ws_get_remote_bindings(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "device_id": "32:123456",
            "binding": {
                "rem_id": "37:654321",
                "role": "primary",
                "enabled": True,
            },
            "rem_id": "37:654321",
        },
    )


async def test_ws_get_remote_bindings_error(connection):
    """Test ws_get_remote_bindings handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        side_effect=Exception("Registry error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/get_remote_bindings"}
        await ws_get_remote_bindings(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "get_remote_bindings_failed", "Registry error"
    )
