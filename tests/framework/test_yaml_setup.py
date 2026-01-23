"""Tests for YAML setup helper."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.setup import yaml as yaml_setup


@pytest.mark.asyncio
async def test_async_setup_yaml_config_no_domain(hass) -> None:
    """Return early when YAML config for our domain is absent."""

    config: dict[str, dict] = {}
    await yaml_setup.async_setup_yaml_config(hass, config)


@pytest.mark.asyncio
async def test_async_setup_yaml_config_creates_flow(hass) -> None:
    """Ensure YAML config triggers a config flow init."""

    flow_init = AsyncMock()
    hass.config_entries.flow.async_init = flow_init

    config = {DOMAIN: {"enabled_features": {"default": True}}}

    created_tasks: list[asyncio.Task] = []

    def _capture_task(coro):  # type: ignore[override]
        task = hass.loop.create_task(coro)
        created_tasks.append(task)
        return task

    hass.async_create_task = _capture_task  # type: ignore[assignment]

    await yaml_setup.async_setup_yaml_config(hass, config)

    # Ensure the created task completes so the flow init is awaited
    for task in created_tasks:
        await task

    flow_init.assert_awaited_once_with(
        DOMAIN,
        context={"source": "yaml"},
        data={"yaml": True, "enabled_features": {"default": True}},
    )


@pytest.mark.asyncio
async def test_async_setup_registers_startup_listener(hass) -> None:
    """Verify async_setup registers a startup listener and returns True."""

    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

    before = len(hass.bus._listeners.get(EVENT_HOMEASSISTANT_STARTED, []))

    result = await yaml_setup.async_setup(hass, {})

    after = len(hass.bus._listeners.get(EVENT_HOMEASSISTANT_STARTED, []))

    assert result is True
    assert after == before + 1


@pytest.mark.asyncio
async def test_handle_startup_event_invokes_yaml_setup(hass) -> None:
    """_handle_startup_event should delegate to async_setup_yaml_config."""

    mock_event = MagicMock()
    mock_config: dict[str, dict] = {}

    with patch.object(
        yaml_setup, "async_setup_yaml_config", new=AsyncMock()
    ) as setup_mock:
        await yaml_setup._handle_startup_event(mock_event, hass, mock_config)

    setup_mock.assert_awaited_once_with(hass, mock_config)


@pytest.mark.asyncio
async def test_async_setup_yaml_config_logs_exception(hass, caplog) -> None:
    """Errors while creating flow should be caught and logged."""

    caplog.set_level("ERROR")

    failing_flow = AsyncMock()
    hass.config_entries.flow.async_init = failing_flow

    def _raise_on_create_task(_: Any) -> None:  # type: ignore[override]
        raise RuntimeError("boom")

    hass.async_create_task = _raise_on_create_task  # type: ignore[assignment]

    config = {DOMAIN: {"enabled_features": {"default": True}}}

    await yaml_setup.async_setup_yaml_config(hass, config)

    assert any(
        "Failed to set up Ramses Extras from YAML" in msg
        for msg in caplog.text.splitlines()
    )
