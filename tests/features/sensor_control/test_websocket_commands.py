"""Tests for the sensor_control websocket command handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.sensor_control import (
    websocket_commands as websocket,
)

# Unwrap decorator to bypass websocket_api.async_response wrappers during tests
ws_get_sensor_control_device_config = (
    websocket.ws_get_sensor_control_device_config.__wrapped__
)


pytestmark = pytest.mark.asyncio


@pytest.fixture
def hass():
    """Return a minimal hass mock with domain storage."""
    hass = MagicMock()
    hass.data = {DOMAIN: {"devices": [], "config_entry": MagicMock(options={})}}
    return hass


@pytest.fixture
def connection():
    """Mock websocket connection."""
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


async def test_ws_get_sensor_control_device_config_missing_device_id(hass, connection):
    """The handler should error when device_id is missing."""
    await ws_get_sensor_control_device_config(hass, connection, {"id": 10})

    connection.send_error.assert_called_once_with(
        10, "missing_device_id", "device_id is required"
    )


async def test_ws_get_sensor_control_device_config_unknown_device_type(
    hass, connection
):
    """If no device_type can be resolved, an error should be returned."""
    msg = {"id": 20, "device_id": "32:123456"}

    await ws_get_sensor_control_device_config(hass, connection, msg)

    connection.send_error.assert_called_once()
    args = connection.send_error.call_args.args
    assert args[0] == 20
    assert args[1] == "unknown_device_type"
    assert "32:123456" in args[2]


async def test_ws_get_sensor_control_device_config_success(hass, connection):
    """Successful resolver call should emit send_result with payload."""

    class Device:
        id = "32:999999"
        type = "FAN"

    hass.data[DOMAIN]["devices"] = [Device()]

    msg = {"id": 30, "device_id": "32:999999"}

    with patch.object(
        websocket, "SensorControlResolver", autospec=True
    ) as mock_resolver_cls:
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve_entity_mappings = AsyncMock(
            return_value={"mappings": {"indoor_temperature": "sensor.temp"}}
        )

        await ws_get_sensor_control_device_config(hass, connection, msg)

        mock_resolver.resolve_entity_mappings.assert_awaited_once_with(
            "32:999999", "FAN"
        )

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert result["device_id"] == "32:999999"
    assert result["device_type"] == "FAN"
    assert result["success"] is True
    assert result["mappings"] == {"indoor_temperature": "sensor.temp"}


async def test_ws_get_sensor_control_device_config_resolver_failure(hass, connection):
    """Resolver exceptions should be reported via send_error."""

    class Device:
        id = "32:000001"
        type = "FAN"

    hass.data[DOMAIN]["devices"] = [Device()]
    msg = {"id": 40, "device_id": "32:000001"}

    with patch.object(
        websocket, "SensorControlResolver", autospec=True
    ) as mock_resolver_cls:
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve_entity_mappings.side_effect = RuntimeError("boom")

        await ws_get_sensor_control_device_config(hass, connection, msg)

    connection.send_error.assert_called_once()
    args = connection.send_error.call_args.args
    assert args[0] == 40
    assert args[1] == "get_device_config_failed"
    assert "boom" in args[2]


async def test_ws_get_sensor_control_device_config_dict_device(hass, connection):
    """Test with device as dict (covers lines 55-56)."""
    hass.data[DOMAIN]["devices"] = [{"device_id": "32:123456", "type": "FAN"}]
    msg = {"id": 50, "device_id": "32:123456"}

    with patch.object(
        websocket, "SensorControlResolver", autospec=True
    ) as mock_resolver_cls:
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve_entity_mappings = AsyncMock(
            return_value={"mappings": {"indoor_temperature": "sensor.temp"}}
        )

        await ws_get_sensor_control_device_config(hass, connection, msg)

    connection.send_result.assert_called_once()


async def test_ws_get_sensor_control_device_config_device_without_id(hass, connection):
    """Test with device that has no id attribute (covers line 63)."""

    class Device:
        type = "FAN"

    hass.data[DOMAIN]["devices"] = [Device()]
    msg = {"id": 60, "device_id": "32:999999"}

    with patch.object(
        websocket, "SensorControlResolver", autospec=True
    ) as mock_resolver_cls:
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve_entity_mappings = AsyncMock(return_value={"mappings": {}})

        await ws_get_sensor_control_device_config(hass, connection, msg)

    connection.send_error.assert_called_once()


ws_set_abs_temperature_kind = websocket.ws_set_abs_temperature_kind.__wrapped__


async def test_ws_set_abs_temperature_kind_missing_device_id(hass, connection):
    """The handler should error when device_id is missing."""
    await ws_set_abs_temperature_kind(
        hass,
        connection,
        {"id": 1, "kind": "internal_supply"},
    )
    connection.send_error.assert_called_once()
    args = connection.send_error.call_args[0]
    assert args[1] == "missing_device_id"


async def test_ws_set_abs_temperature_kind_writes_option(hass, connection):
    """The handler should persist the temperature kind under
    abs_humidity_inputs."""
    entry = hass.data[DOMAIN]["config_entry"]
    entry.options = {}

    await ws_set_abs_temperature_kind(
        hass,
        connection,
        {
            "id": 2,
            "device_id": "32:153289",
            "metric": "outdoor_abs_humidity",
            "kind": "internal_supply",
        },
    )

    connection.send_result.assert_called_once()
    result = connection.send_result.call_args[0][1]
    assert result["success"] is True
    assert result["kind"] == "internal_supply"

    hass.config_entries.async_update_entry.assert_called_once()
    options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    canonical = options["ramses_extras"]["features"]["sensor_control"]
    temp_cfg = canonical["devices"]["32:153289"]["abs_humidity_inputs"][
        "outdoor_abs_humidity"
    ]["temperature"]
    assert temp_cfg["kind"] == "internal_supply"
    # humidity input defaults to internal so the pair stays valid
    hum_cfg = canonical["devices"]["32:153289"]["abs_humidity_inputs"][
        "outdoor_abs_humidity"
    ]["humidity"]
    assert hum_cfg["kind"] == "internal"


async def test_ws_set_abs_temperature_kind_preserves_existing(hass, connection):
    """Existing humidity config and other devices must be preserved."""
    entry = hass.data[DOMAIN]["config_entry"]
    entry.options = {
        "ramses_extras": {
            "version": 1,
            "features": {
                "sensor_control": {
                    "devices": {
                        "32:153289": {
                            "abs_humidity_inputs": {
                                "outdoor_abs_humidity": {
                                    "temperature": {"kind": "internal"},
                                    "humidity": {
                                        "kind": "external",
                                        "entity": "sensor.x",
                                    },
                                }
                            }
                        },
                        "32:000000": {"abs_humidity_inputs": {}},
                    }
                }
            },
        }
    }

    await ws_set_abs_temperature_kind(
        hass,
        connection,
        {
            "id": 3,
            "device_id": "32_153289",
            "kind": "internal_supply",
        },
    )

    connection.send_result.assert_called_once()
    options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    cfg = options["ramses_extras"]["features"]["sensor_control"]["devices"]
    out = cfg["32:153289"]["abs_humidity_inputs"]["outdoor_abs_humidity"]
    assert out["temperature"]["kind"] == "internal_supply"
    assert out["humidity"] == {"kind": "external", "entity": "sensor.x"}
    assert "32:000000" in cfg
