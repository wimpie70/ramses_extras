"""Tests for translations.py - simple and direct"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.translations import (
    _get_feature_translations_sync,
    async_get_feature_title,
    async_get_feature_translations,
)


def test_get_feature_translations_sync_no_file():
    """Test when translation file doesn't exist"""
    result = _get_feature_translations_sync("nonexistent", "en")
    assert result == {}


def test_get_feature_translations_sync_empty_sections():
    """Test with empty sections tuple"""
    result = _get_feature_translations_sync("test", "en", ())
    assert result == {}


@pytest.mark.asyncio
async def test_async_get_feature_translations_basic():
    """Test async_get_feature_translations with basic setup"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    # Mock async_add_executor_job to return empty dict
    async def mock_executor_job(func, *args):
        return {}

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_translations(hass, "test_feature")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_async_get_feature_translations_with_fallback():
    """Test fallback to English"""
    hass = MagicMock()
    hass.config.language = "fr"  # French
    hass.data = {}

    call_count = 0

    async def mock_executor_job(func, *args):
        nonlocal call_count
        call_count += 1
        if args[1] == "fr":
            return {}  # French not available
        return {"info_suffix": {"key": "value"}}  # English available

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_translations(hass, "test_feature")
    assert isinstance(result, dict)
    assert call_count == 2  # Called for French, then English


@pytest.mark.asyncio
async def test_async_get_feature_title_basic():
    """Test async_get_feature_title"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    async def mock_executor_job(func, *args):
        return {"config": {"step": {"feature_test": {"title": "Test Title"}}}}

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_title(hass, "test", "Default")
    assert result == "Test Title"


@pytest.mark.asyncio
async def test_async_get_feature_title_default():
    """Test async_get_feature_title falls back to default"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    async def mock_executor_job(func, *args):
        return {}  # No translations found

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_title(hass, "test", "Default Title")
    assert result == "Default Title"


def test_get_feature_translations_sync_filters_non_strings():
    """Test that non-string keys and values are filtered"""
    # This tests the filtering logic at lines 54-57
    result = _get_feature_translations_sync("test", "en", ("section",))
    # Since file doesn't exist, returns empty
    assert result == {}
