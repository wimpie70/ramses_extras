"""Tests for setup.features helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.setup import features


@pytest.mark.asyncio
async def test_create_and_start_feature_instances_no_enabled_features(hass) -> None:
    """Cards latch should enable when nothing pending."""

    hass.data.setdefault(DOMAIN, {})

    with patch(
        "custom_components.ramses_extras.framework.setup.features.get_enabled_feature_names",
        return_value=[],
    ):
        await features.create_and_start_feature_instances(hass, MagicMock())

    assert hass.data[DOMAIN]["cards_enabled"] is True


@pytest.mark.asyncio
async def test_create_and_start_feature_instances_with_automation(hass) -> None:
    """Automation managers should be started and cards latch released on ready."""

    hass.data.setdefault(DOMAIN, {})

    automation_started = asyncio.Event()

    class DummyAutomation:
        def __init__(self) -> None:
            self._active = False

        def is_automation_active(self) -> bool:
            return self._active

        async def start(self) -> None:
            self._active = True
            automation_started.set()

    def create_feature(_hass, _entry):
        return {"automation": DummyAutomation()}

    module = SimpleNamespace(create_foo_feature=create_feature)

    with (
        patch(
            "custom_components.ramses_extras.framework.setup.features.get_enabled_feature_names",
            return_value=["foo"],
        ),
        patch("importlib.import_module", return_value=module),
    ):
        await features.create_and_start_feature_instances(hass, MagicMock())

    # fire feature_ready to release latch
    hass.bus.async_fire("ramses_extras_feature_ready", {"feature_id": "foo"})
    await asyncio.sleep(0)

    assert hass.data[DOMAIN]["cards_enabled"] is True
    await asyncio.wait_for(automation_started.wait(), timeout=1)


@pytest.mark.asyncio
async def test_create_and_start_feature_instances_skips_existing(hass) -> None:
    """Existing feature entries are not recreated."""

    hass.data.setdefault(DOMAIN, {})["features"] = {"foo": object()}

    with patch(
        "custom_components.ramses_extras.framework.setup.features.get_enabled_feature_names",
        return_value=["foo"],
    ) as get_names:
        await features.create_and_start_feature_instances(hass, MagicMock())

    get_names.assert_called_once()
    # cards_enabled should be set because no pending automations
    assert hass.data[DOMAIN]["cards_enabled"] is True


@pytest.mark.asyncio
async def test_import_feature_platform_modules_warns_on_unexpected_error(
    caplog,
) -> None:
    caplog.set_level("WARNING")

    with patch(
        "asyncio.to_thread",
        side_effect=ModuleNotFoundError(
            "custom_components.ramses_extras.features.foo.platforms.sensor"
        ),
    ):
        await features.import_feature_platform_modules(["foo"])

    assert any("Unexpected import error" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_import_feature_platform_modules_warns_on_generic_error(caplog) -> None:
    caplog.set_level("WARNING")

    with patch("asyncio.to_thread", side_effect=RuntimeError("boom")):
        await features.import_feature_platform_modules(["foo"])

    assert any(
        "Error importing platform module" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_setup_websocket_integration_logs_error(caplog) -> None:
    caplog.set_level("ERROR")

    with patch(
        "custom_components.ramses_extras.websocket_integration.async_setup_websocket_integration",
        new=AsyncMock(side_effect=RuntimeError("fail")),
    ):
        await features.setup_websocket_integration(MagicMock())

    assert any(
        "Error setting up WebSocket integration" in msg
        for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_setup_websocket_integration_warns_on_false(caplog) -> None:
    caplog.set_level("WARNING")

    with patch(
        "custom_components.ramses_extras.websocket_integration.async_setup_websocket_integration",
        new=AsyncMock(return_value=False),
    ):
        await features.setup_websocket_integration(MagicMock())

    assert any(
        "WebSocket integration setup failed" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_create_and_start_feature_instances_logs_warning_on_error(
    caplog, hass
) -> None:  # noqa: E501
    caplog.set_level("WARNING")

    hass.data.setdefault(DOMAIN, {})

    with (
        patch(
            "custom_components.ramses_extras.framework.setup.features.get_enabled_feature_names",
            return_value=["foo"],
        ),
        patch(
            "importlib.import_module",
            side_effect=RuntimeError("fail"),
        ),
    ):
        await features.create_and_start_feature_instances(hass, MagicMock())

    assert any(
        "Failed to create feature instance" in msg for msg in caplog.text.splitlines()
    )
