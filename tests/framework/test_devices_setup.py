"""Tests for devices setup helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.setup import devices


@pytest.mark.asyncio
async def test_async_setup_platforms_skips_when_in_progress(hass) -> None:
    devices._setup_in_progress = True
    await devices.async_setup_platforms(hass)
    devices._setup_in_progress = False


@pytest.mark.asyncio
async def test_async_setup_platforms_uses_cached_devices(hass) -> None:
    hass.config.components.add("ramses_cc")
    hass.data.setdefault(DOMAIN, {})["devices"] = [MagicMock(id="01:123456")]
    hass.data[DOMAIN]["device_discovery_complete"] = True

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.discover_ramses_devices",
        side_effect=AssertionError("should not be called"),
    ):
        await devices.async_setup_platforms(hass)


@pytest.mark.asyncio
async def test_async_setup_platforms_retries_when_not_loaded(hass) -> None:
    hass.config.components.clear()

    scheduled: list[float] = []

    def fake_call_later(_hass, delay, callback):  # type: ignore[override]
        scheduled.append(delay)
        # avoid recursion: mark setup not in progress then invoke callback
        devices._setup_in_progress = False
        return callback(None)

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.async_call_later",
        side_effect=fake_call_later,
    ):
        await devices.async_setup_platforms(hass)

    assert scheduled and scheduled[0] == 60.0


@pytest.mark.asyncio
async def test_discover_ramses_devices_no_entries_fallback(hass) -> None:
    hass.config_entries.async_entries = MagicMock(return_value=[])

    with patch(
        "custom_components.ramses_extras.framework.setup.devices._discover_devices_from_entity_registry",
        new=AsyncMock(return_value=["dev_from_registry"]),
    ) as fallback:
        result = await devices.discover_ramses_devices(hass)

    fallback.assert_awaited_once()
    assert result == ["dev_from_registry"]


@pytest.mark.asyncio
async def test_discover_ramses_devices_error_fallback(hass) -> None:
    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = object()

    with patch(
        "custom_components.ramses_extras.framework.setup.devices._discover_devices_from_entity_registry",
        new=AsyncMock(return_value=["fallback"]),
    ) as fallback:
        with patch(
            "custom_components.ramses_extras.framework.setup.devices.getattr",
            side_effect=RuntimeError("err"),
        ):
            result = await devices.discover_ramses_devices(hass)

    fallback.assert_awaited_once()
    assert result == ["fallback"]
