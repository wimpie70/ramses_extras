# tests/test_config_flow.py
"""Test config flow functionality."""

from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.config_flow import (
    RamsesExtrasConfigFlow,
    RamsesExtrasOptionsFlowHandler,
)


class TestRamsesExtrasConfigFlow:
    """Test RamsesExtrasConfigFlow class."""

    def test_async_get_options_flow(self):
        """Test getting options flow handler."""
        mock_config_entry = MagicMock()

        options_flow = RamsesExtrasConfigFlow.async_get_options_flow(mock_config_entry)

        assert isinstance(options_flow, RamsesExtrasOptionsFlowHandler)
        assert options_flow._config_entry == mock_config_entry


class TestRamsesExtrasOptionsFlowHandler:
    """Test RamsesExtrasOptionsFlowHandler class."""

    def test_init(self):
        """Test initialization of options flow handler."""
        mock_config_entry = MagicMock()

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        assert options_flow._config_entry == mock_config_entry
        assert options_flow._pending_data is None
        assert options_flow._entity_manager is None
        assert options_flow._config_flow_helper is None
        assert options_flow._feature_changes_detected is False
