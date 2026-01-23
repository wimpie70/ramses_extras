"""Tests for cards setup helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.setup import cards


@pytest.mark.asyncio
async def test_async_get_integration_version_uses_cache(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["_integration_version"] = "1.2.3"

    with patch(
        "custom_components.ramses_extras.framework.setup.cards.async_get_integration"
    ) as get_int:
        version = await cards.async_get_integration_version(hass)

    assert version == "1.2.3"
    get_int.assert_not_called()


@pytest.mark.asyncio
async def test_async_get_integration_version_fallback(hass) -> None:
    with patch(
        "custom_components.ramses_extras.framework.setup.cards.async_get_integration",
        side_effect=RuntimeError("boom"),
    ):
        version = await cards.async_get_integration_version(hass)

    assert version == "0.0.0"
    assert hass.data[DOMAIN]["_integration_version"] == "0.0.0"


@pytest.mark.asyncio
async def test_discover_card_features_no_features_dir(tmp_path) -> None:
    # point integration dir to temporary location without features
    original_dir = cards.INTEGRATION_DIR
    cards.INTEGRATION_DIR = tmp_path
    try:
        features = await cards.discover_card_features()
    finally:
        cards.INTEGRATION_DIR = original_dir

    assert features == []


@pytest.mark.asyncio
async def test_cleanup_old_card_deployments_missing_root(hass, tmp_path) -> None:
    hass.config.config_dir = tmp_path
    # ensure no exception when www/ramses_extras missing
    await cards.cleanup_old_card_deployments(hass, "1.0.0", [])


@pytest.mark.asyncio
async def test_cleanup_old_card_deployments_removes_old_versions(
    hass, tmp_path
) -> None:
    hass.config.config_dir = tmp_path
    root = Path(tmp_path) / "www" / "ramses_extras"
    current = root / "v1.0.0"
    old = root / "v0.9.0"
    legacy = root / "helpers"
    for p in (current, old, legacy):
        p.mkdir(parents=True, exist_ok=True)

    await cards.cleanup_old_card_deployments(hass, "1.0.0", [])

    assert current.exists()
    assert not old.exists()
    assert not legacy.exists()


@pytest.mark.asyncio
async def test_copy_helper_files_missing_source(hass, tmp_path, caplog) -> None:
    hass.config.config_dir = tmp_path

    caplog.set_level("WARNING")

    with patch(
        "custom_components.ramses_extras.framework.setup.cards.INTEGRATION_DIR",
        tmp_path / "nope",
    ):
        await cards.copy_helper_files(hass)

    assert any(
        "Helper files directory not found" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_expose_feature_config_to_frontend_writes_file(hass, tmp_path) -> None:
    hass.config.config_dir = tmp_path

    entry = MagicMock()
    entry.options = {"debug_mode": True, "log_level": "info"}

    with patch(
        "custom_components.ramses_extras.framework.setup.cards.async_get_integration_version",
        return_value="1.0.0",
    ):
        dest_helpers = tmp_path / "www" / "ramses_extras" / "v1.0.0" / "helpers"
        dest_helpers.mkdir(parents=True, exist_ok=True)
        await cards.expose_feature_config_to_frontend(hass, entry)

    dest = (
        tmp_path
        / "www"
        / "ramses_extras"
        / "v1.0.0"
        / "helpers"
        / "ramses-extras-features.js"
    )
    assert dest.exists()
    content = dest.read_text()
    assert "window.ramsesExtras" in content


@pytest.mark.asyncio
async def test_register_cards_handles_error(hass, caplog) -> None:
    caplog.set_level("ERROR")

    with patch(
        "custom_components.ramses_extras.framework.setup.cards.CardRegistry.register_bootstrap",
        new=AsyncMock(side_effect=RuntimeError("fail")),
    ):
        await cards.register_cards(hass)

    assert any(
        "CardRegistry registration failed" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_copy_all_card_files_missing_source(hass, tmp_path, caplog) -> None:
    hass.config.config_dir = tmp_path

    caplog.set_level("WARNING")

    card_features = [
        {"feature_name": "foo", "source_dir": tmp_path / "nope"},
    ]

    with patch(
        "custom_components.ramses_extras.framework.setup.cards.async_get_integration_version",
        return_value="1.0.0",
    ):
        await cards.copy_all_card_files(hass, card_features)

    assert any(
        "Card source directory not found" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_copy_all_card_files_copy_error_logs(hass, tmp_path, caplog) -> None:
    hass.config.config_dir = tmp_path

    caplog.set_level("ERROR")

    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "file.js").write_text("// test")

    card_features = [
        {"feature_name": "foo", "source_dir": src},
    ]

    with (
        patch(
            "custom_components.ramses_extras.framework.setup.cards.async_get_integration_version",
            return_value="1.0.0",
        ),
        patch(
            "custom_components.ramses_extras.framework.setup.cards.shutil.copytree",
            side_effect=RuntimeError("boom"),
        ),
    ):
        await cards.copy_all_card_files(hass, card_features)

    assert any("Failed to copy card files" in msg for msg in caplog.text.splitlines())
