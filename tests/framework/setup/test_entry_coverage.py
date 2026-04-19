"""Tests for setup/entry.py to improve coverage."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.setup.entry import (
    apply_log_level_from_entry,
    initialize_entry_data,
)


class TestApplyLogLevelFromEntry:
    """Tests for apply_log_level_from_entry."""

    def test_no_log_level_option(self):
        """Test when log_level option is not set."""
        entry = MagicMock()
        entry.options = {}

        apply_log_level_from_entry(entry)

        # Should not crash

    def test_log_level_not_string(self):
        """Test when log_level is not a string."""
        entry = MagicMock()
        entry.options = {"log_level": 123}

        apply_log_level_from_entry(entry)

        # Should not crash

    def test_log_level_invalid(self):
        """Test when log_level is invalid."""
        entry = MagicMock()
        entry.options = {"log_level": "invalid"}

        apply_log_level_from_entry(entry)

        # Should not crash

    def test_log_level_debug(self):
        """Test setting debug log level."""
        entry = MagicMock()
        entry.options = {"log_level": "debug"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_info(self):
        """Test setting info log level."""
        entry = MagicMock()
        entry.options = {"log_level": "info"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_warning(self):
        """Test setting warning log level."""
        entry = MagicMock()
        entry.options = {"log_level": "warning"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_error(self):
        """Test setting error log level."""
        entry = MagicMock()
        entry.options = {"log_level": "error"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_with_whitespace(self):
        """Test log level with whitespace."""
        entry = MagicMock()
        entry.options = {"log_level": "  debug  "}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()


class TestInitializeEntryData:
    """Tests for initialize_entry_data."""

    def test_initialize_entry_data(self):
        """Test basic initialization."""
        hass = MagicMock()
        hass.data = {}
        entry = MagicMock()
        entry.entry_id = "test_entry"

        with patch(
            "custom_components.ramses_extras.framework.setup.entry.get_enabled_features_dict"
        ) as mock_get_features:
            mock_get_features.return_value = {"default": {}}

            initialize_entry_data(hass, entry)

            assert DOMAIN in hass.data
            assert "test_entry" in hass.data[DOMAIN]
            assert "enabled_features" in hass.data[DOMAIN]

    def test_initialize_entry_data_existing_domain(self):
        """Test initialization when DOMAIN already exists in hass.data."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {"existing_key": "existing_value"}}
        entry = MagicMock()
        entry.entry_id = "test_entry"

        with patch(
            "custom_components.ramses_extras.framework.setup.entry.get_enabled_features_dict"
        ) as mock_get_features:
            mock_get_features.return_value = {"default": {}}

            initialize_entry_data(hass, entry)

            assert "test_entry" in hass.data[DOMAIN]
            assert "existing_key" in hass.data[DOMAIN]  # Should preserve existing data
