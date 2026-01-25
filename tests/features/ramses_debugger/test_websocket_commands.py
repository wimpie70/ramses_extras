"""Tests for ramses_debugger websocket commands."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.ramses_debugger import websocket_commands

# Unwrap decorator for testing (same approach as other features)
ws_messages_get_messages = websocket_commands.ws_messages_get_messages.__wrapped__
ws_traffic_get_stats = websocket_commands.ws_traffic_get_stats.__wrapped__
ws_traffic_reset_stats = websocket_commands.ws_traffic_reset_stats.__wrapped__
ws_traffic_subscribe_stats = websocket_commands.ws_traffic_subscribe_stats.__wrapped__
ws_log_list_files = websocket_commands.ws_log_list_files.__wrapped__
ws_packet_log_list_files = websocket_commands.ws_packet_log_list_files.__wrapped__
ws_packet_log_get_messages = websocket_commands.ws_packet_log_get_messages.__wrapped__
ws_log_get_tail = websocket_commands.ws_log_get_tail.__wrapped__
ws_log_search = websocket_commands.ws_log_search.__wrapped__
ws_cache_get_stats = websocket_commands.ws_cache_get_stats.__wrapped__
ws_cache_clear = websocket_commands.ws_cache_clear.__wrapped__


@pytest.fixture
def hass() -> HomeAssistant:
    """Fixture for Home Assistant."""
    mock_hass = MagicMock(spec=HomeAssistant)
    mock_hass.data = {}
    mock_hass.bus = MagicMock()
    mock_hass.bus.async_listen = MagicMock()
    mock_hass.async_add_executor_job = AsyncMock()
    return mock_hass


@pytest.fixture
def conn() -> ActiveConnection:
    """Fixture for WebSocket connection."""
    conn = MagicMock(spec=ActiveConnection)
    conn.user = MagicMock()
    conn.context = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    conn.send_message = MagicMock()
    conn.subscriptions = {}
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


class TestWsTrafficGetStats:
    """Test ws_traffic_get_stats websocket command."""

    @pytest.mark.asyncio
    async def test_traffic_get_stats_live_success(self, hass, conn):
        """Test successful live traffic stats retrieval."""
        # Mock traffic collector
        mock_collector = MagicMock()
        mock_collector.get_stats.return_value = {
            "total_count": 100,
            "flows": [{"src": "32:153289", "dst": "37:169161", "count_total": 50}],
        }

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_traffic_collector",
            return_value=mock_collector,
        ):
            await ws_traffic_get_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/traffic/get_stats",
                    "traffic_source": "live",
                    "device_id": "32:153289",
                    "limit": 100,
                },
            )

            mock_collector.get_stats.assert_called_once_with(
                device_id="32:153289",
                src=None,
                dst=None,
                code=None,
                verb=None,
                limit=100,
            )
            conn.send_result.assert_called_once_with(
                "test-id", mock_collector.get_stats.return_value
            )

    @pytest.mark.asyncio
    async def test_traffic_get_stats_no_collector(self, hass, conn):
        """Test traffic stats when collector is not available."""
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_traffic_collector",
            return_value=None,
        ):
            await ws_traffic_get_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/traffic/get_stats",
                },
            )

            conn.send_error.assert_called_once()
            error_args = conn.send_error.call_args[0]
            assert error_args[0] == "test-id"
            assert error_args[1] == "collector_not_ready"

    @pytest.mark.asyncio
    async def test_traffic_get_stats_log_sources(self, hass, conn):
        """Test traffic stats for log sources."""
        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_traffic_collector",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_messages_from_sources"
            ) as mock_get_messages,
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_log_path"
            ) as mock_get_log_path,
        ):
            mock_get_messages.return_value = [
                {
                    "src": "32:153289",
                    "dst": "37:169161",
                    "dtm": "2026-01-20T10:00:00",
                    "code": "31DA",
                    "verb": "RQ",
                }
            ]
            mock_get_log_path.return_value = "/config/home-assistant.log"

            await ws_traffic_get_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/traffic/get_stats",
                    "traffic_source": "ha_log",
                    "limit": 50,
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "started_at": "2026-01-20T10:00:00",
                    "total_count": 1,
                    "by_code": {"31DA": 1},
                    "by_verb": {"RQ": 1},
                    "flows": [
                        {
                            "src": "32:153289",
                            "dst": "37:169161",
                            "count_total": 1,
                            "last_seen": "2026-01-20T10:00:00",
                            "verbs": {"RQ": 1},
                            "codes": {"31DA": 1},
                        }
                    ],
                },
            )


class TestWsTrafficResetStats:
    """Test ws_traffic_reset_stats websocket command."""

    @pytest.mark.asyncio
    async def test_traffic_reset_stats_success(self, hass, conn):
        """Test successful traffic stats reset."""
        mock_collector = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_traffic_collector",
            return_value=mock_collector,
        ):
            await ws_traffic_reset_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/traffic/reset_stats",
                },
            )

            mock_collector.reset.assert_called_once()
            conn.send_result.assert_called_once_with("test-id", {"success": True})

    @pytest.mark.asyncio
    async def test_traffic_reset_stats_no_collector(self, hass, conn):
        """Test traffic reset when collector is not available."""
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_traffic_collector",
            return_value=None,
        ):
            await ws_traffic_reset_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/traffic/reset_stats",
                },
            )

            conn.send_error.assert_called_once()
            error_args = conn.send_error.call_args[0]
            assert error_args[0] == "test-id"
            assert error_args[1] == "collector_not_ready"


class TestWsLogListFiles:
    """Test ws_log_list_files websocket command."""

    @pytest.mark.asyncio
    async def test_log_list_files_success(self, hass, conn):
        """Test successful log file listing."""
        mock_files = [
            MagicMock(
                file_id="home-assistant.log",
                size=1024,
                modified_at="2026-01-20T10:00:00",
            ),
            MagicMock(
                file_id="home-assistant.log.1",
                size=2048,
                modified_at="2026-01-19T10:00:00",
            ),
        ]

        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_log_path",
                return_value="/config/logs",
            ),
            patch.object(
                hass, "async_add_executor_job", new_callable=AsyncMock
            ) as mock_executor,
        ):
            mock_executor.return_value = mock_files
            await ws_log_list_files(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/log/list_files",
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "base": "/config/logs",
                    "files": [
                        {
                            "file_id": "home-assistant.log",
                            "size": 1024,
                            "modified_at": "2026-01-20T10:00:00",
                        },
                        {
                            "file_id": "home-assistant.log.1",
                            "size": 2048,
                            "modified_at": "2026-01-19T10:00:00",
                        },
                    ],
                },
            )


class TestWsPacketLogListFiles:
    """Test ws_packet_log_list_files websocket command."""

    @pytest.mark.asyncio
    async def test_packet_log_list_files_success(self, hass, conn):
        """Test successful packet log file listing."""
        mock_files = [
            MagicMock(
                file_id="packet.log", size=512, modified_at="2026-01-20T10:00:00"
            ),
        ]

        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_packet_log_path",
                return_value="/config/packet_logs",
            ),
            patch.object(
                hass, "async_add_executor_job", new_callable=AsyncMock
            ) as mock_executor,
        ):
            mock_executor.return_value = mock_files
            await ws_packet_log_list_files(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/packet_log/list_files",
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "base": "/config/packet_logs",
                    "files": [
                        {
                            "file_id": "packet.log",
                            "size": 512,
                            "modified_at": "2026-01-20T10:00:00",
                        },
                    ],
                },
            )

    @pytest.mark.asyncio
    async def test_packet_log_list_files_no_config(self, hass, conn):
        """Test packet log listing when no path is configured."""
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_packet_log_path",
            return_value=None,
        ):
            await ws_packet_log_list_files(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/packet_log/list_files",
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id", {"base": None, "files": []}
            )


class TestWsLogGetTail:
    """Test ws_log_get_tail websocket command."""

    @pytest.mark.asyncio
    async def test_log_get_tail_success(self, hass, conn):
        """Test successful log tail retrieval."""
        hass.async_add_executor_job.reset_mock()
        hass.async_add_executor_job.side_effect = [
            Path("/config/logs/home-assistant.log"),
            "log content here\n",
        ]

        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_log_path",
                return_value="/config/logs",
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
                return_value=None,
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._file_state",
                return_value=None,
            ),
        ):
            await ws_log_get_tail(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/log/get_tail",
                    "file_id": "home-assistant.log",
                    "max_lines": 100,
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "file_id": "home-assistant.log",
                    "text": "log content here\n",
                },
            )

    @pytest.mark.asyncio
    async def test_log_get_tail_invalid_file_id(self, hass, conn):
        """Test log tail with invalid file ID."""
        await ws_log_get_tail(
            hass,
            conn,
            {
                "id": "test-id",
                "type": "ramses_extras/ramses_debugger/log/get_tail",
                "file_id": "",
            },
        )

        conn.send_error.assert_called_once_with(
            "test-id", "invalid_file_id", "Missing file_id"
        )

    @pytest.mark.asyncio
    async def test_log_get_tail_file_not_allowed(self, hass, conn):
        """Test log tail when file is not allowed."""
        hass.async_add_executor_job.reset_mock()
        hass.async_add_executor_job.side_effect = [None]
        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_log_path",
                return_value="/config/logs",
            ),
        ):
            await ws_log_get_tail(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/log/get_tail",
                    "file_id": "invalid.log",
                },
            )

            conn.send_error.assert_called_once_with(
                "test-id", "file_not_allowed", "Requested file_id is not available"
            )


class TestWsLogSearch:
    """Test ws_log_search websocket command."""

    @pytest.mark.asyncio
    async def test_log_search_success(self, hass, conn):
        """Test successful log search."""
        mock_result = {"matches": 5, "total_chars": 1000, "truncated": False}

        hass.async_add_executor_job.reset_mock()
        hass.async_add_executor_job.side_effect = [
            Path("/config/logs/home-assistant.log"),
            mock_result,
        ]

        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_log_path",
                return_value="/config/logs",
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
                return_value=None,
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._file_state",
                return_value=None,
            ),
        ):
            await ws_log_search(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/log/search",
                    "file_id": "home-assistant.log",
                    "query": "error",
                    "max_matches": 10,
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "file_id": "home-assistant.log",
                    "matches": 5,
                    "total_chars": 1000,
                    "truncated": False,
                },
            )

    @pytest.mark.asyncio
    async def test_log_search_invalid_query(self, hass, conn):
        """Test log search with invalid query."""
        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_log_path",
                return_value="/config/logs",
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.resolve_log_file_id",
                return_value=Path("/config/logs/home-assistant.log"),
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
                return_value=None,
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._file_state",
                return_value=None,
            ),
            patch.object(
                hass, "async_add_executor_job", new_callable=AsyncMock
            ) as mock_executor,
        ):
            mock_executor.side_effect = [Path("/config/logs/home-assistant.log")]
            await ws_log_search(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/log/search",
                    "file_id": "home-assistant.log",
                    "query": "",
                },
            )

            conn.send_error.assert_called_once_with(
                "test-id", "invalid_query", "Missing query"
            )


class TestWsCacheGetStats:
    """Test ws_cache_get_stats websocket command."""

    @pytest.mark.asyncio
    async def test_cache_get_stats_available(self, hass, conn):
        """Test cache stats when cache is available."""
        mock_cache = MagicMock()
        mock_cache.stats.return_value = {"entries": 10, "max_entries": 256}

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
            return_value=mock_cache,
        ):
            await ws_cache_get_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/cache/get_stats",
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "available": True,
                    "stats": {"entries": 10, "max_entries": 256},
                },
            )

    @pytest.mark.asyncio
    async def test_cache_get_stats_unavailable(self, hass, conn):
        """Test cache stats when cache is not available."""
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
            return_value=None,
        ):
            await ws_cache_get_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/cache/get_stats",
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id",
                {
                    "available": False,
                    "stats": None,
                },
            )


class TestWsCacheClear:
    """Test ws_cache_clear websocket command."""

    @pytest.mark.asyncio
    async def test_cache_clear_success(self, hass, conn):
        """Test successful cache clearing."""
        mock_cache = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
            return_value=mock_cache,
        ):
            await ws_cache_clear(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/cache/clear",
                },
            )

            mock_cache.clear.assert_called_once()
            conn.send_result.assert_called_once_with(
                "test-id", {"available": True, "cleared": True}
            )

    @pytest.mark.asyncio
    async def test_cache_clear_unavailable(self, hass, conn):
        """Test cache clearing when cache is not available."""
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
            return_value=None,
        ):
            await ws_cache_clear(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/cache/clear",
                },
            )

            conn.send_result.assert_called_once_with(
                "test-id", {"available": False, "cleared": False}
            )


class TestWsTrafficSubscribeStats:
    """Test ws_traffic_subscribe_stats websocket command."""

    @pytest.mark.asyncio
    async def test_traffic_subscribe_stats_success(self, hass, conn):
        """Test successful traffic stats subscription."""
        mock_collector = MagicMock()
        mock_unsub = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_traffic_collector",
                return_value=mock_collector,
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.websocket_api"
            ) as mock_ws_api,
        ):
            mock_ws_api.event_message.return_value = {"event": "stats"}
            hass.bus.async_listen.return_value = mock_unsub

            await ws_traffic_subscribe_stats(
                hass,
                conn,
                {
                    "id": "test-id",
                    "type": "ramses_extras/ramses_debugger/traffic/subscribe_stats",
                    "device_id": "32:153289",
                    "throttle_ms": 500,
                },
            )

            assert conn.subscriptions["test-id"] == mock_unsub
            conn.send_result.assert_called_once_with("test-id", {"success": True})


class TestWsPacketLogGetMessages:
    """Test ws_packet_log_get_messages websocket command."""

    @pytest.mark.asyncio
    async def test_packet_log_get_messages_success(self, hass, conn):
        """Test successful packet log message retrieval."""
        mock_messages = [
            SimpleNamespace(
                src="32:153289",
                dst="37:169161",
                verb="RQ",
                code="31DA",
                payload="003 010203",
                dtm="2026-01-20T10:00:00",
                packet="",
                source="packet_log",
                raw_line="",
                parse_warnings=[],
            )
        ]

        hass.async_add_executor_job.reset(mock=True)
        hass.async_add_executor_job.side_effect = [
            Path("/config/packet_logs/packet.log"),
        ]

        with (
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands.get_configured_packet_log_path",
                return_value="/config/packet_logs",
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._get_cache",
                return_value=None,
            ),
            patch(
                "custom_components.ramses_extras.features.ramses_debugger.websocket_commands._file_state",
                return_value=None,
            ),
        ):
            # Mock the PacketLogParser.get_messages call
            with patch(
                "custom_components.ramses_extras.features.ramses_debugger.messages_provider.PacketLogParser.get_messages",
                new_callable=AsyncMock,
            ) as mock_parser:
                mock_parser.return_value = mock_messages

                await ws_packet_log_get_messages(
                    hass,
                    conn,
                    {
                        "id": "test-id",
                        "type": "ramses_extras/ramses_debugger/packet_log/get_messages",
                        "file_id": "packet.log",
                        "limit": 100,
                        "decode": False,
                    },
                )

                conn.send_result.assert_called_once()
                result = conn.send_result.call_args[0][1]
                assert result["file_id"] == "packet.log"
                assert result["messages"] == [
                    {
                        "src": "32:153289",
                        "dst": "37:169161",
                        "verb": "RQ",
                        "code": "31DA",
                        "payload": "003 010203",
                        "dtm": "2026-01-20T10:00:00",
                        "packet": "",
                        "source": "packet_log",
                        "raw_line": "",
                        "parse_warnings": [],
                    }
                ]
