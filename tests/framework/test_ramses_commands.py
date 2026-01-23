"""Tests for ramses_commands helpers."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers import ramses_commands


@pytest.mark.asyncio
async def test_send_command_immediate_success() -> None:
    rc = MagicMock()
    rc._send_packet = AsyncMock(return_value=True)

    mgr = ramses_commands.DeviceCommandManager(rc)
    mgr._min_interval = 0

    result = await mgr.send_command_to_device("01:123456", {"code": "foo"})

    assert result.success is True
    stats = mgr.get_queue_statistics()["command_statistics"]
    assert stats["successful_commands"] == 1
    assert stats["failed_commands"] == 0
    assert stats["queued_commands"] == 0


@pytest.mark.asyncio
async def test_send_command_queue_and_process() -> None:
    rc = MagicMock()
    rc._send_packet = AsyncMock(return_value=True)

    mgr = ramses_commands.DeviceCommandManager(rc)
    mgr._last_command_time["01:123456"] = time.time()

    result = await mgr.send_command_to_device("01:123456", {"code": "bar"})
    assert result.queued is True

    # allow background processor to drain queue
    await asyncio.sleep(0.7)

    stats = mgr.get_queue_statistics()["command_statistics"]
    assert stats["queued_commands"] == 1
    assert stats["successful_commands"] == 1


@pytest.mark.asyncio
async def test_execute_command_failure_path() -> None:
    rc = MagicMock()
    rc._send_packet = AsyncMock(side_effect=RuntimeError("boom"))

    mgr = ramses_commands.DeviceCommandManager(rc)
    mgr._min_interval = 0

    result = await mgr.send_command_to_device("01:123456", {"code": "baz"})

    assert result.success is False
    assert "boom" in result.error_message
    stats = mgr.get_queue_statistics()["command_statistics"]
    assert stats["failed_commands"] == 1


@pytest.mark.asyncio
async def test_process_device_queue_timeout_cleans_up() -> None:
    rc = MagicMock()
    rc._send_packet = AsyncMock(return_value=True)

    mgr = ramses_commands.DeviceCommandManager(rc)

    # enqueue one item then let processor timeout with empty queue
    mgr._last_command_time["01:123456"] = time.time()
    await mgr.send_command_to_device("01:123456", {"code": "baz"})

    # wait for queue to drain and timeout exit
    await asyncio.sleep(1)

    assert "01:123456" not in mgr._processors
    assert "01:123456" not in mgr._queue_depths


@pytest.mark.asyncio
async def test_process_device_queue_logs_error() -> None:
    rc = MagicMock()
    rc._send_packet = AsyncMock(side_effect=RuntimeError("fail"))

    mgr = ramses_commands.DeviceCommandManager(rc)
    mgr._last_command_time["01:123456"] = time.time()

    await mgr.send_command_to_device("01:123456", {"code": "err"})

    # allow processor to run
    await asyncio.sleep(0.7)

    stats = mgr.get_queue_statistics()["command_statistics"]
    assert stats["failed_commands"] >= 1


@pytest.mark.asyncio
async def test_process_device_queue_warns_on_failed_result(caplog) -> None:
    rc = MagicMock()

    mgr = ramses_commands.DeviceCommandManager(rc)

    # Preload queue and processor
    mgr._queues["01:000001"] = asyncio.Queue()
    mgr._queue_depths["01:000001"] = 1
    await mgr._queues["01:000001"].put({"command_def": {}, "timeout": 1})

    async def fail_execute(device_id, command_def, timeout):  # type: ignore[override]
        return ramses_commands.CommandResult(success=False, error_message="bad")

    mgr._execute_command = fail_execute  # type: ignore[assignment]

    caplog.set_level("WARNING")

    await mgr._process_device_queue("01:000001")

    assert any("Queued command failed" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_execute_command_logs_error(caplog) -> None:
    rc = MagicMock()
    rc._send_packet = AsyncMock(side_effect=RuntimeError("boom"))

    mgr = ramses_commands.DeviceCommandManager(rc)
    mgr._min_interval = 0

    caplog.set_level("ERROR")

    await mgr.send_command_to_device("01:999999", {"code": "oops"})

    stats = mgr.get_queue_statistics()["command_statistics"]
    assert stats["failed_commands"] >= 1
