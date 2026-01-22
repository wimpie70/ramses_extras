"""Tests for ramses_debugger websocket commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.ramses_debugger import websocket_commands

# Unwrap decorator for testing (same approach as other features)
ws_messages_get_messages = websocket_commands.ws_messages_get_messages.__wrapped__


@pytest.fixture
def hass() -> HomeAssistant:
    """Fixture for Home Assistant."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def conn() -> ActiveConnection:
    """Fixture for WebSocket connection."""
    conn = MagicMock(spec=ActiveConnection)
    conn.user = MagicMock()
    conn.context = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


class TestWsGetMessages:
    """Test ws_messages_get_messages websocket command."""

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
    )
    async def test_get_messages_success(self, mock_get_messages, hass, conn):
        """Test successful messages retrieval."""
        # Mock response
        mock_get_messages.return_value = [
            {
                "dtm": "2026-01-20T10:00:00.000000",
                "src": "32:153289",
                "dst": "37:169161",
                "verb": "RQ",
                "code": "31DA",
                "payload": "003 123",
                "packet": "RQ 32:153289 37:169161 --:------ 31DA 003 123",
                "source": "traffic_buffer",
                "raw_line": None,
                "parse_warnings": [],
            }
        ]

        # Call the handler
        await ws_messages_get_messages(
            hass,
            conn,
            {
                "id": "test-id",
                "type": "ramses_debugger/messages/get_messages",
                "sources": ["traffic_buffer"],
                "src": "32:153289",
                "limit": 100,
                "dedupe": True,
            },
        )

        # Verify the backend was called with correct parameters
        mock_get_messages.assert_called_once_with(
            hass,
            ["traffic_buffer"],
            src="32:153289",
            dst=None,
            verb=None,
            code=None,
            since=None,
            until=None,
            limit=100,
            dedupe=True,
        )

        # Verify response was sent
        conn.send_result.assert_called_once_with(
            "test-id", {"messages": mock_get_messages.return_value}
        )

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
    )
    async def test_get_messages_with_filters(self, mock_get_messages, hass, conn):
        """Test messages retrieval with all filters."""
        mock_get_messages.return_value = []

        await ws_messages_get_messages(
            hass,
            conn,
            {
                "id": "test-id",
                "type": "ramses_debugger/messages/get_messages",
                "sources": ["traffic_buffer", "packet_log"],
                "src": "32:153289",
                "dst": "37:169161",
                "verb": "RQ",
                "code": "31DA",
                "since": "2026-01-20T09:00:00",
                "until": "2026-01-20T11:00:00",
                "limit": 500,
                "dedupe": False,
            },
        )

        mock_get_messages.assert_called_once_with(
            hass,
            ["traffic_buffer", "packet_log"],
            src="32:153289",
            dst="37:169161",
            verb="RQ",
            code="31DA",
            since="2026-01-20T09:00:00",
            until="2026-01-20T11:00:00",
            limit=500,
            dedupe=False,
        )

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
    )
    async def test_get_messages_error_handling(self, mock_get_messages, hass, conn):
        """Test error handling in websocket handler."""
        # Mock an exception
        mock_get_messages.side_effect = Exception("Test error")

        await ws_messages_get_messages(
            hass,
            conn,
            {
                "id": "test-id",
                "type": "ramses_debugger/messages/get_messages",
                "sources": ["traffic_buffer"],
            },
        )

        # Verify error response was sent
        conn.send_error.assert_called_once_with("test-id", "error", "Test error")

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
    )
    async def test_get_messages_default_sources(self, mock_get_messages, hass, conn):
        """Test default sources when not specified."""
        mock_get_messages.return_value = []

        await ws_messages_get_messages(
            hass,
            conn,
            {
                "id": "test-id",
                "type": "ramses_debugger/messages/get_messages",
            },
        )

        # Should use default sources
        mock_get_messages.assert_called_once_with(
            hass,
            ["traffic_buffer", "packet_log", "ha_log"],
            src=None,
            dst=None,
            verb=None,
            code=None,
            since=None,
            until=None,
            limit=200,  # default in schema
            dedupe=True,
        )

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
    )
    async def test_get_messages_response_format(self, mock_get_messages, hass, conn):
        """Test response format matches expected structure."""
        mock_get_messages.return_value = [
            {
                "dtm": "2026-01-20T10:00:00.000000",
                "src": "32:153289",
                "dst": "37:169161",
                "verb": "RQ",
                "code": "31DA",
                "payload": "003 123",
                "packet": "RQ 32:153289 37:169161 --:------ 31DA 003 123",
                "source": "traffic_buffer",
                "raw_line": None,
                "parse_warnings": [],
            }
        ]

        await ws_messages_get_messages(
            hass,
            conn,
            {
                "id": "test-id",
                "type": "ramses_debugger/messages/get_messages",
                "sources": ["traffic_buffer"],
            },
        )

        conn.send_result.assert_called_once()
        result_payload = conn.send_result.call_args[0][1]
        assert "messages" in result_payload
        assert isinstance(result_payload["messages"], list)
        assert len(result_payload["messages"]) == 1

        msg = result_payload["messages"][0]
        required_fields = [
            "dtm",
            "src",
            "dst",
            "verb",
            "code",
            "payload",
            "packet",
            "source",
        ]
        for field in required_fields:
            assert field in msg

    @pytest.mark.asyncio
    @patch(
        "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
    )
    async def test_get_messages_decode_success(self, mock_get_messages, hass, conn):
        mock_get_messages.return_value = [
            {
                "dtm": "2026-01-20T10:00:00.000000",
                "src": "32:153289",
                "dst": "37:169161",
                "verb": "RQ",
                "code": "31DA",
                "payload": "003 123",
                "packet": "RQ 32:153289 37:169161 --:------ 31DA 003 123",
                "source": "traffic_buffer",
                "raw_line": None,
                "parse_warnings": [],
            }
        ]

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.messages_provider.decode_message_with_ramses_rf",
            return_value={"decoded": True},
        ):
            await ws_messages_get_messages(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_debugger/messages/get_messages",
                    "sources": ["traffic_buffer"],
                    "decode": True,
                },
            )

        conn.send_result.assert_called_once()
        result_payload = conn.send_result.call_args[0][1]
        assert result_payload["messages"][0]["decoded"] == {"decoded": True}
