from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.feature_utils import get_enabled_feature_names
from custom_components.ramses_extras.services_integration import (
    _import_services_module,
    async_register_feature_services,
    async_unload_feature_services,
)


def _make_hass(*, enabled_features=None, config_entry=None):
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    if enabled_features is not None:
        hass.data[DOMAIN]["enabled_features"] = enabled_features
    if config_entry is not None:
        hass.data[DOMAIN]["config_entry"] = config_entry
    return hass


def test_get_enabled_feature_names_from_dict_and_adds_default():
    hass = _make_hass(enabled_features={"hello_world": True, "humidity_control": False})
    enabled = get_enabled_feature_names(hass)
    assert "hello_world" in enabled
    assert "humidity_control" not in enabled
    assert "default" in enabled


def test_get_enabled_feature_names_from_list_and_adds_default():
    hass = _make_hass(enabled_features=["hello_world"])
    enabled = get_enabled_feature_names(hass)
    assert enabled.count("default") == 1
    assert "hello_world" in enabled


def test_get_enabled_feature_names_falls_back_to_config_entry_options():
    config_entry = MagicMock()
    config_entry.data = {}
    config_entry.options = {"enabled_features": {"hello_world": True}}
    hass = _make_hass(config_entry=config_entry)

    enabled = get_enabled_feature_names(hass)
    assert "hello_world" in enabled
    assert "default" in enabled


def test_get_enabled_feature_names_unknown_shape_returns_default_only():
    hass = _make_hass(enabled_features="invalid")
    enabled = get_enabled_feature_names(hass)
    assert enabled == ["default"]


def test_import_services_module_builds_expected_module_path():
    with patch(
        "custom_components.ramses_extras.services_integration.importlib.import_module"
    ) as mock_import:
        expected = "custom_components.ramses_extras.features.hello_world.services"
        mock_import.return_value = SimpleNamespace()

        result = _import_services_module("hello_world")

        assert result is mock_import.return_value
        mock_import.assert_called_once_with(expected)


@pytest.mark.asyncio
async def test_register_feature_services_skips_missing_services_module():
    hass = _make_hass(enabled_features=["default", "no_services"])

    async def fake_to_thread(fn, feature_name):
        if feature_name == "no_services":
            raise ImportError("No module named 'services'")
        return SimpleNamespace(async_setup_services=AsyncMock())

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_register_feature_services_warns_on_import_error_other_than_services():
    hass = _make_hass(enabled_features=["default", "bad_feature"])

    async def fake_to_thread(fn, feature_name):
        if feature_name == "bad_feature":
            raise ImportError("No module named 'boom'")
        return SimpleNamespace(async_setup_services=AsyncMock())

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_register_feature_services_calls_setup_with_one_param():
    hass = _make_hass(enabled_features=["default"])

    async def setup(hass_param):
        assert hass_param is hass

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_setup_services=setup)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_register_feature_services_calls_setup_with_two_params():
    config_entry = MagicMock()
    hass = _make_hass(enabled_features=["default"], config_entry=config_entry)

    async def setup(hass_param, config_entry_param):
        assert hass_param is hass
        assert config_entry_param is config_entry

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_setup_services=setup)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_register_feature_services_ignores_incompatible_signature():
    hass = _make_hass(enabled_features=["default"])

    async def setup(a, b, c):  # noqa: ANN001
        raise AssertionError("Should not be called")

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_setup_services=setup)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_register_feature_services_catches_setup_exception():
    hass = _make_hass(enabled_features=["default"])

    async def setup(hass_param):
        raise RuntimeError("boom")

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_setup_services=setup)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_register_feature_services_skips_module_without_setup():
    hass = _make_hass(enabled_features=["default"])

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace()

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_register_feature_services(hass)


@pytest.mark.asyncio
async def test_unload_feature_services_calls_unload_with_one_param():
    hass = _make_hass(enabled_features=["default"])

    called = {"ok": False}

    async def unload(hass_param):
        assert hass_param is hass
        called["ok"] = True

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_unload_services=unload)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_unload_feature_services(hass)


@pytest.mark.asyncio
async def test_unload_feature_services_skips_missing_services_module():
    hass = _make_hass(enabled_features=["default", "no_services"])

    called = {"ok": False}

    async def unload(hass_param):
        assert hass_param is hass
        called["ok"] = True

    async def fake_to_thread(fn, feature_name):
        if feature_name == "no_services":
            raise ImportError("No module named 'services'")
        return SimpleNamespace(async_unload_services=unload)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_unload_feature_services(hass)

    assert called["ok"] is True


@pytest.mark.asyncio
async def test_unload_feature_services_calls_unload_with_two_params():
    config_entry = MagicMock()
    hass = _make_hass(enabled_features=["default"], config_entry=config_entry)

    called = {"ok": False}

    async def unload(hass_param, config_entry_param):
        assert hass_param is hass
        assert config_entry_param is config_entry
        called["ok"] = True

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_unload_services=unload)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_unload_feature_services(hass)

    assert called["ok"] is True


@pytest.mark.asyncio
async def test_unload_feature_services_ignores_incompatible_signature():
    hass = _make_hass(enabled_features=["default"])

    async def unload(a, b, c):  # noqa: ANN001
        raise AssertionError("Should not be called")

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_unload_services=unload)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_unload_feature_services(hass)


@pytest.mark.asyncio
async def test_unload_feature_services_catches_unload_exception():
    hass = _make_hass(enabled_features=["default"])

    async def unload(hass_param):
        raise RuntimeError("boom")

    async def fake_to_thread(fn, feature_name):
        return SimpleNamespace(async_unload_services=unload)

    with patch(
        "custom_components.ramses_extras.services_integration.asyncio.to_thread",
        side_effect=fake_to_thread,
    ):
        await async_unload_feature_services(hass)
