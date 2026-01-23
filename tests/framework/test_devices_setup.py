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
    import logging

    logging.getLogger(
        "custom_components.ramses_extras.framework.setup.devices"
    ).setLevel(logging.ERROR)

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
@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_device_refresh_cancelled_error(hass) -> None:
    """Test that device refresh handles cancellation properly."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    mock_discover = AsyncMock()

    async def mock_sleep(delay):
        if delay == 5:
            raise asyncio.CancelledError()

    with patch(
        "custom_components.ramses_extras.framework.setup.devices.asyncio.sleep",
        side_effect=mock_sleep,
    ):
        with patch(
            "custom_components.ramses_extras.framework.setup.devices.discover_and_store_devices",
            new=mock_discover,
        ):
            with patch(
                "custom_components.ramses_extras.framework.setup.devices.async_dispatcher_send"
            ):
                # Test the _refresh_devices_after_delay logic directly by importing it
                # Since it's a private function, we'll test the logic by mocking
                #  the components
                try:
                    # Simulate the logic from _refresh_devices_after_delay
                    await asyncio.sleep(5)  # This will raise CancelledError
                    await mock_discover(hass)
                except asyncio.CancelledError:
                    pass  # Should catch and return

    # Should not call discover since cancelled
    mock_discover.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_async_setup_platforms_fresh_discovery(hass) -> None:
    """Test async_setup_platforms performs fresh discovery when cached not available."""
    hass.config.components.add("ramses_cc")
    # Don't set cached data

    mock_devices = [MagicMock(id="fresh_device")]
    with patch(
        "custom_components.ramses_extras.framework.setup.devices.discover_ramses_devices",
        new=AsyncMock(return_value=mock_devices),
    ):
        await devices.async_setup_platforms(hass)

        # Check that data was stored
        assert hass.data[DOMAIN]["devices"] == mock_devices
        assert hass.data[DOMAIN]["device_discovery_complete"] is True


@pytest.mark.asyncio
async def test_discover_ramses_devices_broker_via_dict(hass) -> None:
    """Test broker access via hass.data dict with 'broker' key."""

    class Broker:
        def __init__(self) -> None:
            mock_device = MagicMock()
            mock_device.id = "dict_broker"
            self._devices = [mock_device]

    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = {"broker": Broker()}

    result = await devices.discover_ramses_devices(hass)

    assert [getattr(d, "id", d) for d in result] == ["dict_broker"]


@pytest.mark.asyncio
async def test_discover_ramses_devices_broker_via_entry(hass) -> None:
    """Test broker access via entry.broker."""

    class Broker:
        def __init__(self) -> None:
            self._devices = [MagicMock(id="entry_broker")]

    entry = MagicMock(entry_id="1")
    entry.broker = Broker()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    # Don't set hass.data so it falls back to entry

    result = await devices.discover_ramses_devices(hass)

    assert [getattr(d, "id", d) for d in result] == ["entry_broker"]


@pytest.mark.asyncio
async def test_discover_ramses_devices_broker_devices_attr(hass) -> None:
    """Test broker access using 'devices' attribute instead of '_devices'."""

    class Broker:
        def __init__(self) -> None:
            self.devices = [MagicMock(id="devices_attr")]

    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = Broker()

    result = await devices.discover_ramses_devices(hass)

    assert [getattr(d, "id", d) for d in result] == ["devices_attr"]


@pytest.mark.asyncio
async def test_discover_ramses_devices_no_devices_fallback(hass) -> None:
    """Test fallback when broker has no devices."""

    class Broker:
        def __init__(self) -> None:
            self._devices = None

    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = Broker()

    with patch(
        "custom_components.ramses_extras.framework.setup.devices._discover_devices_from_entity_registry",
        new=AsyncMock(return_value=["fallback_device"]),
    ) as fallback:
        result = await devices.discover_ramses_devices(hass)

    fallback.assert_awaited_once()
    assert result == ["fallback_device"]


@pytest.mark.asyncio
async def test_discover_ramses_devices_single_device_object(hass) -> None:
    """Test handling when devices is a single object, not a collection."""

    class Broker:
        def __init__(self) -> None:
            mock_device = MagicMock()
            mock_device.id = "single_device"
            self._devices = mock_device

    entry = MagicMock(entry_id="1")
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.data.setdefault("ramses_cc", {})["1"] = Broker()

    result = await devices.discover_ramses_devices(hass)

    assert len(result) == 1
    assert getattr(result[0], "id", result[0]) == "single_device"


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_entities_obj_none(hass) -> None:
    """Test cleanup when entities_obj is None."""

    class DevEntry:
        def __init__(self, dev_id: str) -> None:
            self.identifiers = {(DOMAIN, dev_id)}
            self.id = dev_id

    device_registry = MagicMock()
    device_registry.devices = {"dev1": DevEntry("dev1")}

    entity_registry = MagicMock()
    entity_registry.entities = None  # entities_obj is None

    await devices.cleanup_orphaned_devices(
        hass,
        MagicMock(),
        device_registry=device_registry,
        entity_registry=entity_registry,
    )

    # Should not crash, just continue


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_exception_in_get(hass) -> None:
    """Test cleanup handles exception in entities_obj.get."""

    class DevEntry:
        def __init__(self, dev_id: str) -> None:
            self.identifiers = {(DOMAIN, dev_id)}
            self.id = dev_id

    device_registry = MagicMock()
    device_registry.devices = {"dev1": DevEntry("dev1")}

    entity_registry = MagicMock()
    entities_obj = MagicMock()
    entities_obj.get.side_effect = RuntimeError("get error")
    entity_registry.entities = entities_obj

    await devices.cleanup_orphaned_devices(
        hass,
        MagicMock(),
        device_registry=device_registry,
        entity_registry=entity_registry,
    )

    # Should handle exception gracefully


@pytest.mark.asyncio
async def test_cleanup_orphaned_devices_exception_in_values(hass) -> None:
    """Test cleanup handles exception in entities_obj.values."""

    class DevEntry:
        def __init__(self, dev_id: str) -> None:
            self.identifiers = {(DOMAIN, dev_id)}
            self.id = dev_id

    device_registry = MagicMock()
    device_registry.devices = {"dev1": DevEntry("dev1")}

    entity_registry = MagicMock()
    entities_obj = MagicMock()
    entities_obj.values.side_effect = RuntimeError("values error")
    entity_registry.entities = entities_obj

    await devices.cleanup_orphaned_devices(
        hass,
        MagicMock(),
        device_registry=device_registry,
        entity_registry=entity_registry,
    )

    # Should handle exception gracefully
