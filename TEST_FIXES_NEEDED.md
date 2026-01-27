# Test Fixes Needed for Version Injection

## Summary

All WebSocket responses now include `_backend_version` field. Tests need to be updated to expect this field.

## Status

### ✅ Fixed

1. `tests/features/default/test_default_websocket_commands.py::test_ws_get_cards_enabled` - FIXED
2. `tests/features/ramses_debugger/test_ramses_debugger_log.py::test_ws_packet_log_list_files_not_configured` - FIXED
3. `tests/features/ramses_debugger/test_ramses_debugger_traffic.py::test_ws_get_stats_and_reset` - FIXED
4. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsGetMessages::test_get_messages_success` - FIXED
5. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsTrafficResetStats::test_traffic_reset_stats_success` - FIXED
6. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsTrafficSubscribeStats::test_traffic_subscribe_stats_success` - FIXED
7. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsPacketLogListFiles::test_packet_log_list_files_no_config` - FIXED
8. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsCacheGetStats::test_cache_get_stats_unavailable` - FIXED

### ❌ Still Need Fixing (9 tests)

1. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsTrafficGetStats::test_traffic_get_stats_log_sources` - Line 396
2. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsLogListFiles::test_log_list_files_success` - Line 503
3. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsPacketLogListFiles::test_packet_log_list_files_success` - Line 584
4. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsLogGetTail::test_log_get_tail_success` - Line 627
5. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsLogSearch::test_log_search_success` - Line 718
6. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsCacheGetStats::test_cache_get_stats_available` - Line 791
7. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsCacheClear::test_cache_clear_success` - Line 846
8. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsCacheClear::test_cache_clear_unavailable` - Line 866
9. `tests/features/ramses_debugger/test_websocket_commands.py::TestWsTrafficGetStats::test_traffic_get_stats_live` - Line 334 (changed to check \_backend_version presence)

## How to Fix

All remaining tests need their `conn.send_result.assert_called_once_with()` assertions updated to wrap the expected dict with `_with_version()`:

```python
# Before:
conn.send_result.assert_called_once_with("test-id", {"key": "value"})

# After:
conn.send_result.assert_called_once_with("test-id", _with_version({"key": "value"}))
```

The `_with_version()` helper function is already defined at the top of the test file:

```python
def _with_version(result: dict) -> dict:
    """Add _backend_version to expected result for test assertions."""
    return {**result, "_backend_version": "0.0.0"}
```

## Quick Fix Command

You can manually update the remaining assertions by finding each line number and wrapping the dict with `_with_version()`.
