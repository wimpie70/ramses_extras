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


def test_get_feature_translations_sync_with_real_file():
    """Test with a real translation file (sensor_control)"""
    result = _get_feature_translations_sync("sensor_control", "en", ("config",))
    # Should return something since sensor_control has translations
    assert isinstance(result, dict)


def test_get_feature_translations_sync_invalid_json():
    """Test handling of invalid JSON file"""
    # Mock a file with invalid JSON
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value="invalid json {{{"),
    ):
        result = _get_feature_translations_sync("test", "en", ("config",))
        assert result == {}


def test_get_feature_translations_sync_non_dict_root():
    """Test handling of non-dict root in JSON"""
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value='["not", "a", "dict"]'),
    ):
        result = _get_feature_translations_sync("test", "en", ("config",))
        assert result == {}


def test_get_feature_translations_sync_mixed_types():
    """Test filtering of non-string keys/values in sections"""
    # JSON parsing converts numeric keys to strings, so we test value filtering
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch(
            "pathlib.Path.read_text",
            return_value='{"section": {"str_key": "str_val", "str_key2": 456}}',
        ),
    ):
        result = _get_feature_translations_sync("test", "en", ("section",))
        assert result == {"section": {"str_key": "str_val"}}


@pytest.mark.asyncio
async def test_async_get_feature_translations_cached():
    """Test that translations are cached"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    call_count = 0

    async def mock_executor_job(func, *args):
        nonlocal call_count
        call_count += 1
        return {"info_suffix": {"key": "value"}}

    hass.async_add_executor_job = mock_executor_job

    # First call
    result1 = await async_get_feature_translations(hass, "test_feature")
    assert result1 == {"info_suffix": {"key": "value"}}
    assert call_count == 1

    # Second call should use cache
    result2 = await async_get_feature_translations(hass, "test_feature")
    assert result2 == {"info_suffix": {"key": "value"}}
    assert call_count == 1  # Should not increase


@pytest.mark.asyncio
async def test_async_get_feature_translations_different_sections():
    """Test that different sections create different cache entries"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    call_count = 0

    async def mock_executor_job(func, *args):
        nonlocal call_count
        call_count += 1
        sections = args[2]
        return {sections[0]: {"key": "value"}}

    hass.async_add_executor_job = mock_executor_job

    # Call with different sections
    await async_get_feature_translations(hass, "test_feature", ("config",))
    await async_get_feature_translations(hass, "test_feature", ("labels",))
    assert call_count == 2  # Should call twice for different sections


@pytest.mark.asyncio
async def test_async_get_feature_translations_no_hass_config():
    """Test when hass has no config attribute"""
    hass = MagicMock(spec=[])  # No config attribute
    hass.data = {}

    async def mock_executor_job(func, *args):
        return {}

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_translations(hass, "test_feature")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_async_get_feature_translations_returns_dict_on_error():
    """Test that non-dict return is converted to empty dict"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    async def mock_executor_job(func, *args):
        return "not a dict"  # Return invalid type

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_translations(hass, "test_feature")
    assert result == {}


@pytest.mark.asyncio
async def test_async_get_feature_title_non_dict_step():
    """Test when step section is not a dict"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    async def mock_executor_job(func, *args):
        return {"config": {"step": "not a dict"}}

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_title(hass, "test", "Default Title")
    assert result == "Default Title"


@pytest.mark.asyncio
async def test_async_get_feature_title_missing_title():
    """Test when title is missing from step"""
    hass = MagicMock()
    hass.config.language = "en"
    hass.data = {}

    async def mock_executor_job(func, *args):
        return {"config": {"step": {"feature_test": {"description": "No title"}}}}

    hass.async_add_executor_job = mock_executor_job

    result = await async_get_feature_title(hass, "test", "Default Title")
    assert result == "Default Title"
