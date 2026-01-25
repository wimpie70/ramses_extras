"""Tests for ramses_debugger feature initialization."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.features.ramses_debugger import (
    create_ramses_debugger_feature,
)
from custom_components.ramses_extras.features.ramses_debugger.const import (
    DOMAIN as RAMSES_DEBUGGER_DOMAIN,
)


class TestCreateRamsesDebuggerFeature:
    """Test the create_ramses_debugger_feature function."""

    @pytest.fixture
    def hass(self):
        """Mock HomeAssistant instance."""
        mock_hass = MagicMock(spec=HomeAssistant)
        mock_hass.data = {}
        mock_hass.bus = MagicMock()
        mock_hass.bus.async_listen = MagicMock()
        return mock_hass

    @pytest.fixture
    def config_entry(self):
        """Mock ConfigEntry instance."""
        entry = MagicMock(spec=ConfigEntry)
        entry.options = {}
        entry.async_on_unload = MagicMock()
        return entry

    def test_create_feature_basic_initialization(self, hass, config_entry):
        """Test basic feature creation with default settings."""
        result = create_ramses_debugger_feature(hass, config_entry)

        # Verify return structure
        assert result["feature_name"] == RAMSES_DEBUGGER_DOMAIN
        assert "traffic_collector" in result

        # Verify data structure created in hass.data
        assert DOMAIN in hass.data
        assert RAMSES_DEBUGGER_DOMAIN in hass.data[DOMAIN]

        debugger_data = hass.data[DOMAIN][RAMSES_DEBUGGER_DOMAIN]
        assert "cache" in debugger_data
        assert "traffic_collector" in debugger_data

    def test_create_feature_with_cache_max_entries(self, hass, config_entry):
        """Test feature creation with custom cache max entries."""
        config_entry.options = {"ramses_debugger_cache_max_entries": 1000}

        create_ramses_debugger_feature(hass, config_entry)

        debugger_data = hass.data[DOMAIN][RAMSES_DEBUGGER_DOMAIN]
        # Cache should be created with custom max_entries
        assert "cache" in debugger_data

    def test_create_feature_with_traffic_collector_config(self, hass, config_entry):
        """Test feature creation with traffic collector configuration."""
        config_entry.options = {
            "ramses_debugger_max_flows": 50,
            "ramses_debugger_buffer_max_global": 1000,
            "ramses_debugger_buffer_max_per_flow": 100,
            "ramses_debugger_buffer_max_flows": 25,
        }

        # Mock the traffic collector to verify configuration
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.TrafficCollector"
        ) as mock_tc_class:
            from custom_components.ramses_extras.features.ramses_debugger import (
                traffic_collector,
            )

            traffic_collector_class = traffic_collector.TrafficCollector

            mock_tc_instance = MagicMock(spec=traffic_collector_class)
            mock_tc_instance.configure = MagicMock()
            mock_tc_instance.start = MagicMock()
            mock_tc_class.return_value = mock_tc_instance

            result = create_ramses_debugger_feature(hass, config_entry)

            # Verify traffic collector was created and methods called
            mock_tc_class.assert_called_once_with(hass)
            mock_tc_instance.configure.assert_called_once_with(
                max_flows=50,
                buffer_max_global=1000,
                buffer_max_per_flow=100,
                buffer_max_flows=25,
            )
            mock_tc_instance.start.assert_called_once()

            # Verify result structure
            assert result["feature_name"] == RAMSES_DEBUGGER_DOMAIN
            assert "traffic_collector" in result

    def test_create_feature_reuses_existing_instances(self, hass, config_entry):
        """Test that existing cache and traffic collector instances are reused."""
        # Pre-populate hass.data with existing instances
        from custom_components.ramses_extras.features.ramses_debugger import (
            debugger_cache,
            traffic_collector,
        )

        debugger_cache_class = debugger_cache.DebuggerCache
        traffic_collector_class = traffic_collector.TrafficCollector

        existing_cache = debugger_cache_class()
        existing_traffic_collector = MagicMock(spec=traffic_collector_class)

        hass.data = {
            DOMAIN: {
                RAMSES_DEBUGGER_DOMAIN: {
                    "cache": existing_cache,
                    "traffic_collector": existing_traffic_collector,
                }
            }
        }

        create_ramses_debugger_feature(hass, config_entry)

        debugger_data = hass.data[DOMAIN][RAMSES_DEBUGGER_DOMAIN]
        # Should reuse existing instances
        assert debugger_data["cache"] is existing_cache
        assert debugger_data["traffic_collector"] is existing_traffic_collector

        # Traffic collector should not be recreated or started again
        existing_traffic_collector.configure.assert_called_once()

    def test_create_feature_starts_traffic_collector(self, hass, config_entry):
        """Test that traffic collector is started."""
        # Mock the traffic collector to verify it was started
        with patch(
            "custom_components.ramses_extras.features.ramses_debugger.TrafficCollector"
        ) as mock_tc_class:
            from custom_components.ramses_extras.features.ramses_debugger import (
                traffic_collector,
            )

            traffic_collector_class = traffic_collector.TrafficCollector

            mock_tc_instance = MagicMock(spec=traffic_collector_class)
            mock_tc_instance.configure = MagicMock()
            mock_tc_instance.start = MagicMock()
            mock_tc_class.return_value = mock_tc_instance

            result = create_ramses_debugger_feature(hass, config_entry)

            # Verify traffic collector was created and started
            mock_tc_class.assert_called_once_with(hass)
            mock_tc_instance.start.assert_called_once()

            # Verify result structure
            assert result["feature_name"] == RAMSES_DEBUGGER_DOMAIN
            assert "traffic_collector" in result

    def test_create_feature_registers_unload_handler(self, hass, config_entry):
        """Test that traffic collector stop is registered for unload."""
        create_ramses_debugger_feature(hass, config_entry)

        # Verify async_on_unload was called
        config_entry.async_on_unload.assert_called_once()

        # Verify the callback is the traffic collector's stop method
        call_args = config_entry.async_on_unload.call_args
        stop_callback = call_args[0][0]

        debugger_data = hass.data[DOMAIN][RAMSES_DEBUGGER_DOMAIN]
        traffic_collector = debugger_data["traffic_collector"]

        # The callback should be the traffic collector's stop method
        assert stop_callback == traffic_collector.stop

    def test_create_feature_with_skip_automation_setup(self, hass, config_entry):
        """Test feature creation with skip_automation_setup flag."""
        # This parameter doesn't currently affect behavior but should be tested for
        # coverage
        result = create_ramses_debugger_feature(
            hass, config_entry, skip_automation_setup=True
        )

        # Should still create the feature normally
        assert result["feature_name"] == RAMSES_DEBUGGER_DOMAIN
        assert "traffic_collector" in result

    def test_create_feature_with_invalid_cache_max_entries(self, hass, config_entry):
        """Test feature creation with invalid cache max entries (should be ignored)."""
        config_entry.options = {"ramses_debugger_cache_max_entries": "invalid"}

        result = create_ramses_debugger_feature(hass, config_entry)

        # Should still create feature (invalid value should be ignored)
        assert result["feature_name"] == RAMSES_DEBUGGER_DOMAIN

    def test_create_feature_with_zero_cache_max_entries(self, hass, config_entry):
        """Test feature creation with zero cache max entries (should be ignored)."""
        config_entry.options = {"ramses_debugger_cache_max_entries": 0}

        result = create_ramses_debugger_feature(hass, config_entry)

        # Should still create feature (zero value should be ignored)
        assert result["feature_name"] == RAMSES_DEBUGGER_DOMAIN

    def test_create_feature_creates_domain_data_if_missing(self, hass, config_entry):
        """Test that domain data is created if it doesn't exist."""
        # hass.data is empty initially
        hass.data = {}

        create_ramses_debugger_feature(hass, config_entry)

        # Should create the full data structure
        assert DOMAIN in hass.data
        assert RAMSES_DEBUGGER_DOMAIN in hass.data[DOMAIN]

    def test_create_feature_creates_debugger_data_if_missing(self, hass, config_entry):
        """Test creation when domain exists but debugger data is missing."""
        # Domain exists but no debugger data
        hass.data = {DOMAIN: {}}

        create_ramses_debugger_feature(hass, config_entry)

        # Should create debugger data
        assert RAMSES_DEBUGGER_DOMAIN in hass.data[DOMAIN]
