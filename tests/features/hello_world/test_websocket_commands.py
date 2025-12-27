"""Unit tests for Hello World websocket commands."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.features.hello_world.websocket_commands import (
    ws_toggle_switch,
)

# Get the original function without decorators
ws_toggle_switch = ws_toggle_switch.__wrapped__


class _FakeConnection:
    def __init__(self) -> None:
        self.errors: list[tuple[int, str, str]] = []
        self.results: list[tuple[int, dict[str, Any]]] = []

    def send_error(self, msg_id: int, code: str, message: str) -> None:
        self.errors.append((msg_id, code, message))

    def send_result(self, msg_id: int, payload: dict[str, Any]) -> None:
        self.results.append((msg_id, payload))


@pytest.mark.asyncio
async def test_ws_toggle_switch_sends_error_when_entity_missing(hass) -> None:
    """Entity lookup failure should return entity_not_found."""
    conn = _FakeConnection()

    msg = {
        "id": 1,
        "type": "ramses_extras/hello_world/toggle_switch",
        "device_id": "18:149488",
        "state": True,
    }

    # Create mock states and services
    mock_states = MagicMock()
    mock_states.get.return_value = None

    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(return_value=None)

    # Replace hass.states and hass.services temporarily
    original_states = hass.states
    original_services = hass.services
    hass.states = mock_states
    hass.services = mock_services

    try:
        await ws_toggle_switch(hass, conn, msg)
    finally:
        hass.states = original_states
        hass.services = original_services

    assert conn.errors == [
        (
            1,
            "entity_not_found",
            "Switch entity switch.hello_world_switch_18_149488 not found",
        )
    ]
    assert not conn.results


@pytest.mark.asyncio
async def test_ws_toggle_switch_calls_service_when_entity_exists(hass) -> None:
    """Existing entity should trigger HA switch service and send success."""
    conn = _FakeConnection()

    msg = {
        "id": 2,
        "type": "ramses_extras/hello_world/toggle_switch",
        "device_id": "18:149488",
        "state": False,
    }

    # Create mock states and services
    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.state = "on"  # Set a non-unavailable state
    mock_states.get.return_value = mock_entity

    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(return_value=None)

    # Mock entity registry
    mock_ent_reg = MagicMock()
    mock_registry_entry = MagicMock()
    mock_ent_reg.async_get.return_value = mock_registry_entry

    # Replace hass.states and hass.services temporarily
    original_states = hass.states
    original_services = hass.services
    hass.states = mock_states
    hass.services = mock_services

    try:
        with patch(
            "homeassistant.helpers.entity_registry.async_get", return_value=mock_ent_reg
        ):
            await ws_toggle_switch(hass, conn, msg)
            mock_services.async_call.assert_awaited_once_with(
                "switch",
                "turn_off",
                {"entity_id": "switch.hello_world_switch_18_149488"},
            )
    finally:
        hass.states = original_states
        hass.services = original_services

    assert conn.results and conn.results[0][0] == 2
    result_payload = conn.results[0][1]
    assert result_payload["success"] is True
    assert result_payload["entity_id"] == "switch.hello_world_switch_18_149488"
    assert result_payload["state"] is False
    assert not conn.errors
