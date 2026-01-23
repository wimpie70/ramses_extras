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
