"""Test broker retrieval functionality for EntityManager.

This module contains comprehensive unit tests for the broker retrieval methods
in EntityManager, testing backwards compatibility with different versions of ramses_cc.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestBrokerRetrieval:
    """Test cases for broker retrieval methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.entity_manager = EntityManager(self.mock_hass)

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_1_newest(self):
        """Test broker retrieval via Method 1 (newest):
        hass.data["ramses_cc"][entry.entry_id]."""
        # Setup mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_123"

        # Setup mock broker
        mock_broker = MagicMock()
        mock_broker._devices = {"device1": MagicMock(), "device2": MagicMock()}

        # Setup hass.data with newest structure
        self.mock_hass.data = {"ramses_cc": {"test_entry_123": mock_broker}}

        # Test retrieval
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_2_older_structure(self):
        """Test broker retrieval via Method 2 (older):
        hass.data["ramses_cc"] directly."""
        # Setup mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_456"

        # Setup mock broker with devices attribute
        mock_broker = MagicMock()
        mock_broker.devices = {"device1": MagicMock()}

        # Setup hass.data with older structure (direct dict)
        self.mock_hass.data = {"ramses_cc": {"some_key": mock_broker}}

        # Test retrieval
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_3_entry_broker(self):
        """Test broker retrieval via Method 3: entry.broker (older versions)."""
        # Setup mock entry with broker attribute
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_789"
        mock_entry.broker = MagicMock()

        # Setup empty hass.data (Method 1 and 2 should fail)
        self.mock_hass.data = {}

        # Test retrieval
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_entry.broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_4_very_old(self):
        """Test broker retrieval via Method 4 (very old):
        hass.data["ramses_cc"][DOMAIN]."""
        # Setup mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_old"

        # Setup mock broker
        mock_broker = MagicMock()
        mock_broker._devices = {"device1": MagicMock()}

        # Setup hass.data with very old structure
        self.mock_hass.data = {"ramses_cc": {"domain_key": mock_broker}}

        # Test retrieval
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_no_broker_found(self):
        """Test broker retrieval when no broker is found."""
        # Setup mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_no_broker"

        # Setup empty hass.data and no entry.broker
        self.mock_hass.data = {}
        mock_entry.broker = None

        # Test retrieval
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_1_exception_handling(self):
        """Test exception handling in Method 1."""
        # Setup mock entry without broker attribute
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_exception"
        del mock_entry.broker  # Ensure no broker attribute

        # Setup hass.data that will cause an exception in Method 1
        self.mock_hass.data = {
            "ramses_cc": {
                "test_entry_exception": "not_a_broker_object"
                # This will be returned directly
            }
        }

        # Test retrieval - Method 1 doesn't check for devices, so it returns the object
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        # Method 1 returns whatever is in hass.data without validation
        assert result == "not_a_broker_object"

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_fallback_order(self):
        """Test that methods are tried in the correct order (newest to oldest)."""
        # Setup mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_fallback"

        # Setup multiple potential brokers
        mock_broker_method1 = MagicMock()
        mock_broker_method1._devices = {"device1": MagicMock()}

        mock_broker_method2 = MagicMock()
        mock_broker_method2.devices = {"device2": MagicMock()}

        # Setup hass.data with both Method 1 and Method 2 available
        self.mock_hass.data = {
            "ramses_cc": {
                "test_entry_fallback": mock_broker_method1,  # Method 1
                "other_key": mock_broker_method2,  # Method 2
            }
        }

        # Test retrieval - should return Method 1 (newest)
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_broker_method1

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_2_no_devices_attr(self):
        """Test Method 2 when broker has devices attributes."""
        # Setup mock entry without broker attribute
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_no_devices"
        del mock_entry.broker  # Ensure no broker attribute

        # Setup mock broker with devices attributes
        mock_broker = MagicMock()
        mock_broker.devices = {"device1": MagicMock()}

        # Setup hass.data with older structure
        self.mock_hass.data = {"ramses_cc": {"some_key": mock_broker}}

        # Test retrieval - should match Method 2
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_broker

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_method_4_multiple_candidates(self):
        """Test Method 4 with multiple potential brokers."""
        # Setup mock entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_multiple"

        # Setup multiple mock brokers
        mock_broker1 = MagicMock()
        mock_broker1._devices = {"device1": MagicMock()}

        mock_broker2 = MagicMock()
        mock_broker2.devices = {"device2": MagicMock()}

        # Setup hass.data with multiple entries
        self.mock_hass.data = {
            "ramses_cc": {"key1": mock_broker1, "key2": mock_broker2}
        }

        # Test retrieval - should return first matching broker
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result == mock_broker1

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_empty_hass_data(self):
        """Test broker retrieval with empty hass.data."""
        # Setup mock entry without broker attribute
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_empty_data"
        del mock_entry.broker  # Ensure no broker attribute

        # Setup empty hass.data
        self.mock_hass.data = {}

        # Test retrieval
        result = await self.entity_manager.get_broker_for_entry(mock_entry)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_broker_for_entry_none_entry(self):
        """Test broker retrieval with None entry."""
        # Test retrieval with None entry
        result = await self.entity_manager.get_broker_for_entry(None)

        assert result is None
