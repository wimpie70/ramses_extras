"""Tests for default feature WebSocket commands."""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from homeassistant.components import websocket_api

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.default.websocket_commands import (
    ws_clear_zone_demand,
    ws_export_bindings,
    ws_export_zones,
    ws_get_2411_schema,
    ws_get_all_feature_entities,
    ws_get_available_devices,
    ws_get_binding_diagnostics,
    ws_get_binding_suggestions,
    ws_get_bound_rem,
    ws_get_cards_enabled,
    ws_get_enabled_features,
    ws_get_entity_mappings,
    ws_get_fan_config_associations,
    ws_get_remote_bindings,
    ws_get_zone_adapter_diagnostics,
    ws_get_zone_coordinator_state,
    ws_get_zone_position,
    ws_get_zones,
    ws_run_zone_actuation,
    ws_set_zone_demand,
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
ws_get_binding_diagnostics = ws_get_binding_diagnostics.__wrapped__
ws_export_bindings = ws_export_bindings.__wrapped__
ws_get_binding_suggestions = ws_get_binding_suggestions.__wrapped__
ws_get_zones = ws_get_zones.__wrapped__
ws_export_zones = ws_export_zones.__wrapped__
ws_get_zone_position = ws_get_zone_position.__wrapped__
ws_get_zone_adapter_diagnostics = ws_get_zone_adapter_diagnostics.__wrapped__
ws_get_zone_coordinator_state = ws_get_zone_coordinator_state.__wrapped__
ws_set_zone_demand = ws_set_zone_demand.__wrapped__
ws_run_zone_actuation = ws_run_zone_actuation.__wrapped__
ws_clear_zone_demand = ws_clear_zone_demand.__wrapped__


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
    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    result = call_args[0][1]
    assert result["cards_enabled"] is True
    assert "_backend_version" in result


async def test_ws_websocket_info(connection):
    """Test ws_websocket_info command."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    msg = {"id": 1, "type": "ramses_extras/default/websocket_info"}

    with (
        patch(
            "custom_components.ramses_extras.features.default.websocket_commands.extras_registry.get_all_websocket_commands"
        ) as mock_get_commands,
        patch(
            "custom_components.ramses_extras.features.default.websocket_commands.extras_registry.get_features_with_websocket_commands"
        ) as mock_get_features,
    ):
        mock_get_commands.return_value = {
            "default": {"test_command": "command"},
        }
        mock_get_features.return_value = ["default"]

        await ws_websocket_info(hass, connection, msg)

        # Verify send_result was called
        connection.send_result.assert_called_once()
        call_args = connection.send_result.call_args
        result = call_args[0][1]

        # Verify the result structure
        assert "commands" in result
        assert "domain" in result
        assert "total_commands" in result
        assert "features" in result
        assert result["domain"] == DOMAIN
        assert len(result["commands"]) == 1


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
    mock_device._SLUG = "FAN"
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


async def test_ws_get_binding_diagnostics_general(connection):
    """Test ws_get_binding_diagnostics returns general diagnostics."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_diagnostics.return_value = {"total_bindings": 5}
    mock_registry.detect_conflicts.return_value = []
    mock_registry.get_unmatched_traffic.return_value = [
        {"rem_id": "37:999999", "command": "fan_high"}
    ]

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/get_binding_diagnostics"}
        await ws_get_binding_diagnostics(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "diagnostics": {"total_bindings": 5},
            "conflicts": [],
            "unmatched_traffic": [{"rem_id": "37:999999", "command": "fan_high"}],
        },
    )


async def test_ws_get_binding_diagnostics_with_rem_id(connection):
    """Test ws_get_binding_diagnostics returns specific REM info."""
    hass = MagicMock()
    from datetime import datetime

    mock_registry = MagicMock()
    mock_registry.get_diagnostics.return_value = {"total_bindings": 5}
    mock_registry.detect_conflicts.return_value = []
    mock_registry.get_last_seen.return_value = datetime(2026, 1, 1, 12, 0, 0)
    mock_registry.find_fan_for_rem.return_value = "32:123456"

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_binding_diagnostics",
            "rem_id": "37:654321",
        }
        await ws_get_binding_diagnostics(hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["rem_id"] == "37:654321"
    assert result["last_seen"] == "2026-01-01T12:00:00"
    assert result["bound_fan"] == "32:123456"


async def test_ws_get_binding_diagnostics_error(connection):
    """Test ws_get_binding_diagnostics handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        side_effect=Exception("Diagnostics error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/get_binding_diagnostics"}
        await ws_get_binding_diagnostics(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "get_binding_diagnostics_failed", "Diagnostics error"
    )


async def test_ws_export_bindings(connection):
    """Test ws_export_bindings returns YAML export."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.export_bindings_yaml.return_value = (
        "remote_binding:\n  FANs:\n    ..."
    )
    mock_registry.detect_conflicts.return_value = []

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/export_bindings"}
        await ws_export_bindings(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "yaml": "remote_binding:\n  FANs:\n    ...",
            "conflicts": [],
        },
    )


async def test_ws_export_bindings_error(connection):
    """Test ws_export_bindings handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        side_effect=Exception("Export error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/export_bindings"}
        await ws_export_bindings(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "export_bindings_failed", "Export error"
    )


async def test_ws_get_binding_suggestions(connection):
    """Test ws_get_binding_suggestions returns suggestions."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_binding_suggestions.return_value = {
        "suggestions": [
            {"rem_id": "37:999999", "fan_id": "32:123456", "confidence": 0.9}
        ]
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/get_binding_suggestions"}
        await ws_get_binding_suggestions(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "suggestions": [
                {"rem_id": "37:999999", "fan_id": "32:123456", "confidence": 0.9}
            ]
        },
    )


async def test_ws_get_binding_suggestions_with_device_id(connection):
    """Test ws_get_binding_suggestions with device_id filter."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_binding_suggestions.return_value = {
        "suggestions": [{"rem_id": "37:999999", "fan_id": "32:123456"}]
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_binding_suggestions",
            "device_id": "32:123456",
        }
        await ws_get_binding_suggestions(hass, connection, msg)

    mock_registry.get_binding_suggestions.assert_called_once_with("32:123456")


async def test_ws_get_binding_suggestions_error(connection):
    """Test ws_get_binding_suggestions handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.remote_binding.get_remote_binding_registry",
        side_effect=Exception("Suggestions error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/get_binding_suggestions"}
        await ws_get_binding_suggestions(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "get_binding_suggestions_failed", "Suggestions error"
    )


async def test_ws_get_zones_all(connection):
    """Test ws_get_zones returns all zones."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.list_all_zones.return_value = {
        "32:123456": [{"zone_id": "bathroom"}, {"zone_id": "office"}]
    }

    with patch(
        "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/get_zones"}
        await ws_get_zones(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "zones_by_fan": {
                "32:123456": [{"zone_id": "bathroom"}, {"zone_id": "office"}]
            }
        },
    )


async def test_ws_get_zones_for_device(connection):
    """Test ws_get_zones returns zones for specific device."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_zones_for_fan.return_value = [
        {"zone_id": "bathroom", "type": "room"},
        {"zone_id": "office", "type": "room"},
    ]

    with patch(
        "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zones",
            "device_id": "32:123456",
        }
        await ws_get_zones(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "device_id": "32:123456",
            "zones": [
                {"zone_id": "bathroom", "type": "room"},
                {"zone_id": "office", "type": "room"},
            ],
        },
    )


async def test_ws_get_zones_error(connection):
    """Test ws_get_zones handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry",
        side_effect=Exception("Zones error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/get_zones"}
        await ws_get_zones(hass, connection, msg)

    connection.send_error.assert_called_once_with(1, "get_zones_failed", "Zones error")


async def test_ws_export_zones(connection):
    """Test ws_export_zones returns YAML export."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.export_zones_yaml.return_value = "zones:\n  FANs:\n    ..."

    with patch(
        "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/export_zones"}
        await ws_export_zones(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1, {"yaml": "zones:\n  FANs:\n    ..."}
    )


async def test_ws_export_zones_error(connection):
    """Test ws_export_zones handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry",
        side_effect=Exception("Export error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/export_zones"}
        await ws_export_zones(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "export_zones_failed", "Export error"
    )


async def test_ws_get_zone_position(connection):
    """Test ws_get_zone_position returns zone position."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_adapter = MagicMock()
    mock_adapter.is_available = True

    mock_position = MagicMock()
    mock_position.position = 50
    mock_position.target_position = 60
    mock_position.is_available = True
    mock_position.source = "adapter"

    mock_adapter.async_get_position = AsyncMock(return_value=mock_position)
    mock_registry.get_or_create_adapter.return_value = mock_adapter

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_position",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_position(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "position": 50,
            "target_position": 60,
            "is_available": True,
            "source": "adapter",
            "adapter_available": True,
        },
    )


async def test_ws_get_zone_position_no_adapter(connection):
    """Test ws_get_zone_position handles missing adapter."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_or_create_adapter.return_value = None

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_position",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_position(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "error": "Zone not found or no adapter available",
        },
    )


async def test_ws_get_zone_position_error(connection):
    """Test ws_get_zone_position handles errors."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_or_create_adapter.side_effect = Exception("Adapter error")

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_position",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_position(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "get_zone_position_failed", "Adapter error"
    )


async def test_ws_get_zone_adapter_diagnostics_global(connection):
    """Test ws_get_zone_adapter_diagnostics returns global diagnostics."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_diagnostics.return_value = {"total_adapters": 3}

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {"id": 1, "type": "ramses_extras/get_zone_adapter_diagnostics"}
        await ws_get_zone_adapter_diagnostics(hass, connection, msg)

    connection.send_result.assert_called_once_with(1, {"total_adapters": 3})


async def test_ws_get_zone_adapter_diagnostics_for_fan(connection):
    """Test ws_get_zone_adapter_diagnostics returns diagnostics for a FAN."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_adapter1 = MagicMock()
    mock_adapter1.get_diagnostics.return_value = {
        "zone_id": "bathroom",
        "available": True,
    }
    mock_adapter2 = MagicMock()
    mock_adapter2.get_diagnostics.return_value = {
        "zone_id": "office",
        "available": True,
    }
    mock_registry.get_all_adapters_for_fan.return_value = [mock_adapter1, mock_adapter2]

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_adapter_diagnostics",
            "fan_id": "32:123456",
        }
        await ws_get_zone_adapter_diagnostics(hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["fan_id"] == "32:123456"
    assert len(result["adapters"]) == 2


async def test_ws_get_zone_adapter_diagnostics_for_zone(connection):
    """Test ws_get_zone_adapter_diagnostics returns diagnostics for a specific zone."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_adapter = MagicMock()
    mock_adapter.get_diagnostics.return_value = {
        "zone_id": "bathroom",
        "available": True,
    }
    mock_registry.get_adapter.return_value = mock_adapter

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_adapter_diagnostics",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_adapter_diagnostics(hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["fan_id"] == "32:123456"
    assert result["zone_id"] == "bathroom"
    assert result["adapter"]["zone_id"] == "bathroom"


async def test_ws_get_zone_adapter_diagnostics_zone_not_found(connection):
    """Test ws_get_zone_adapter_diagnostics handles missing zone adapter."""
    hass = MagicMock()
    mock_registry = MagicMock()
    mock_registry.get_adapter.return_value = None

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        return_value=mock_registry,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_adapter_diagnostics",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_adapter_diagnostics(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "error": "Adapter not found",
        },
    )


async def test_ws_get_zone_adapter_diagnostics_error(connection):
    """Test ws_get_zone_adapter_diagnostics handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_adapters.get_zone_adapter_registry",
        side_effect=Exception("Diagnostics error"),
    ):
        msg = {"id": 1, "type": "ramses_extras/get_zone_adapter_diagnostics"}
        await ws_get_zone_adapter_diagnostics(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "get_zone_adapter_diagnostics_failed", "Diagnostics error"
    )


async def test_ws_get_zone_coordinator_state_full(connection):
    """Test ws_get_zone_coordinator_state returns full coordinator state."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.is_enabled = True

    from custom_components.ramses_extras.framework.helpers.zone_demand import (
        DemandSource,
    )

    mock_state1 = MagicMock()
    mock_state1.position = 50
    mock_state1.is_available = True
    mock_state1.demand_source = DemandSource.HUMIDITY
    mock_state1.demand_reason = "High humidity"

    mock_state2 = MagicMock()
    mock_state2.position = 30
    mock_state2.is_available = True
    mock_state2.demand_source = DemandSource.CO2
    mock_state2.demand_reason = "High CO2"

    mock_coordinator.get_zone_states.return_value = {
        "bathroom": mock_state1,
        "office": mock_state2,
    }
    mock_coordinator.get_diagnostics.return_value = {"total_zones": 2}

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_coordinator_state",
            "fan_id": "32:123456",
        }
        await ws_get_zone_coordinator_state(hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["fan_id"] == "32:123456"
    assert result["enabled"] is True
    assert len(result["states"]) == 2
    assert "diagnostics" in result


async def test_ws_get_zone_coordinator_state_single_zone(connection):
    """Test ws_get_zone_coordinator_state returns single zone state."""
    hass = MagicMock()
    mock_coordinator = MagicMock()

    from custom_components.ramses_extras.framework.helpers.zone_demand import (
        DemandSource,
    )

    mock_state = MagicMock()
    mock_state.position = 50
    mock_state.is_available = True
    mock_state.is_controllable = True
    mock_state.demand_source = DemandSource.HUMIDITY
    mock_state.demand_reason = "High humidity"

    mock_coordinator.get_zone_states.return_value = {"bathroom": mock_state}

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_coordinator_state",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_coordinator_state(hass, connection, msg)

    result = connection.send_result.call_args[0][1]
    assert result["fan_id"] == "32:123456"
    assert result["zone_id"] == "bathroom"
    assert result["state"]["position"] == 50
    assert result["state"]["available"] is True
    assert result["state"]["controllable"] is True


async def test_ws_get_zone_coordinator_state_zone_not_found(connection):
    """Test ws_get_zone_coordinator_state handles missing zone."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.get_zone_states.return_value = {}

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_coordinator_state",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_get_zone_coordinator_state(hass, connection, msg)

    connection.send_result.assert_called_once_with(
        1,
        {
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "error": "Zone state not found",
        },
    )


async def test_ws_get_zone_coordinator_state_error(connection):
    """Test ws_get_zone_coordinator_state handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        side_effect=Exception("Coordinator error"),
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/get_zone_coordinator_state",
            "fan_id": "32:123456",
        }
        await ws_get_zone_coordinator_state(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "get_zone_coordinator_state_failed", "Coordinator error"
    )


async def test_ws_set_zone_demand(connection):
    """Test ws_set_zone_demand sets manual zone demand."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.get_zone_states.return_value = {"bathroom": MagicMock()}
    mock_coordinator.async_set_manual_zone_demand = AsyncMock(return_value=True)

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/set_zone_demand",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "fan_speed": "fan_high",
        }
        await ws_set_zone_demand(hass, connection, msg)

    mock_coordinator.async_set_manual_zone_demand.assert_called_once_with(
        zone_id="bathroom",
        fan_speed="fan_high",
        reason="Manual WebSocket demand",
    )
    connection.send_result.assert_called_once_with(
        1,
        {
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "fan_speed": "fan_high",
            "applied": True,
        },
    )


async def test_ws_set_zone_demand_with_reason(connection):
    """Test ws_set_zone_demand with custom reason."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.get_zone_states.return_value = {"bathroom": MagicMock()}
    mock_coordinator.async_set_manual_zone_demand = AsyncMock(return_value=True)

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/set_zone_demand",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "fan_speed": "fan_high",
            "reason": "Test demand",
        }
        await ws_set_zone_demand(hass, connection, msg)

    mock_coordinator.async_set_manual_zone_demand.assert_called_once_with(
        zone_id="bathroom",
        fan_speed="fan_high",
        reason="Test demand",
    )


async def test_ws_set_zone_demand_configures_zone(connection):
    """Test ws_set_zone_demand configures zone if not in states."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.get_zone_states.return_value = {}
    mock_coordinator.async_set_manual_zone_demand = AsyncMock(return_value=True)

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/set_zone_demand",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "fan_speed": "fan_high",
        }
        await ws_set_zone_demand(hass, connection, msg)

    mock_coordinator.configure_zone.assert_called_once_with("bathroom")


async def test_ws_set_zone_demand_error(connection):
    """Test ws_set_zone_demand handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        side_effect=Exception("Set demand error"),
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/set_zone_demand",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "fan_speed": "fan_high",
        }
        await ws_set_zone_demand(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "set_zone_demand_failed", "Set demand error"
    )


async def test_ws_run_zone_actuation(connection):
    """Test ws_run_zone_actuation triggers actuation cycle."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.async_run_zone_actuation_cycle = AsyncMock(
        return_value={"bathroom": {"position": 50, "success": True}}
    )

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/run_zone_actuation",
            "fan_id": "32:123456",
        }
        await ws_run_zone_actuation(hass, connection, msg)

    mock_coordinator.async_run_zone_actuation_cycle.assert_awaited_once()
    result = connection.send_result.call_args[0][1]
    assert result["fan_id"] == "32:123456"
    assert result["results"] == {"bathroom": {"position": 50, "success": True}}
    assert "timestamp" in result


async def test_ws_run_zone_actuation_error(connection):
    """Test ws_run_zone_actuation handles errors."""
    hass = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        side_effect=Exception("Actuation error"),
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/run_zone_actuation",
            "fan_id": "32:123456",
        }
        await ws_run_zone_actuation(hass, connection, msg)

    connection.send_error.assert_called_once_with(
        1, "run_zone_actuation_failed", "Actuation error"
    )


async def test_ws_clear_zone_demand(connection):
    """Test ws_clear_zone_demand clears manual zone demand."""
    hass = MagicMock()
    mock_coordinator = MagicMock()
    mock_coordinator.async_clear_manual_zone_demand = AsyncMock(return_value=True)

    with patch(
        "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator",
        return_value=mock_coordinator,
    ):
        msg = {
            "id": 1,
            "type": "ramses_extras/clear_zone_demand",
            "fan_id": "32:123456",
            "zone_id": "bathroom",
        }
        await ws_clear_zone_demand(hass, connection, msg)

    mock_coordinator.async_clear_manual_zone_demand.assert_called_once_with("bathroom")
    connection.send_result.assert_called_once_with(
        1,
        {
            "fan_id": "32:123456",
            "zone_id": "bathroom",
            "cleared": True,
        },
    )
