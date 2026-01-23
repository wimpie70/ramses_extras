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


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_device_registry_none(hass, caplog) -> None:
    caplog.set_level("WARNING")

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.dr.async_get",
        return_value=None,
    ):
        await devices.cleanup_orphaned_devices(
            hass,
            MagicMock(),
            device_registry=None,
            entity_registry=MagicMock(),
        )

    assert any("Device registry unavailable" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_entity_registry_none(hass, caplog) -> None:
    caplog.set_level("WARNING")

    dummy_dr = MagicMock()

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.er.async_get",
        return_value=None,
    ):
        await devices.cleanup_orphaned_devices(
            hass,
            MagicMock(),
            device_registry=dummy_dr,
            entity_registry=None,
        )

    assert any("Entity registry unavailable" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_logs_orphan(hass, caplog) -> None:
    caplog.set_level("INFO")

    class DevEntry:
        def __init__(self, dev_id: str) -> None:
            self.identifiers = {(DOMAIN, dev_id)}
            self.id = dev_id

    device_registry = MagicMock()
    device_registry.devices = {"dev1": DevEntry("dev1")}

    entity_registry = MagicMock()
    entity_registry.entities = {}

    await devices.cleanup_orphaned_devices(
        hass,
        MagicMock(),
        device_registry=device_registry,
        entity_registry=entity_registry,
    )

    assert any("Removing 1 orphaned devices" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_discover_devices_from_entity_registry_error(hass, caplog) -> None:
    caplog.set_level("ERROR")

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.er.async_get",
        side_effect=RuntimeError("boom"),
    ):
        result = await devices._discover_devices_from_entity_registry(hass)

    assert result == []
    assert any(
        "Error discovering devices from entity registry" in msg
        for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_discover_devices_from_entity_registry_success(hass) -> None:
    entity = MagicMock()
    entity.domain = "sensor"
    entity.platform = "ramses_cc"
    entity.device_id = "dev1"

    registry = MagicMock()
    registry.entities = {"e1": entity}

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.er.async_get",
        return_value=registry,
    ):
        result = await devices._discover_devices_from_entity_registry(hass)

    assert result == ["dev1"]


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_no_registries(hass) -> None:
    """Test cleanup with no registries available."""
    # This should not raise, just log and return
    await devices.cleanup_orphaned_devices(hass, MagicMock())


@pytest.mark.asyncio
async def test_discover_ramses_devices_broker_dict(hass) -> None:
    class Broker:
        def __init__(self) -> None:
            self._devices = {"a": MagicMock(id="a")}

    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = Broker()

    result = await devices.discover_ramses_devices(hass)

    assert [getattr(d, "id", d) for d in result] == ["a"]


@pytest.mark.asyncio
async def test_discover_ramses_devices_broker_list(hass) -> None:
    class Broker:
        def __init__(self) -> None:
            self._devices = [MagicMock(id="b")]

    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = Broker()

    result = await devices.discover_ramses_devices(hass)

    assert [getattr(d, "id", d) for d in result] == ["b"]
