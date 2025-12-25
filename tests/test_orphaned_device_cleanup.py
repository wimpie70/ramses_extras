# tests/test_orphaned_device_cleanup.py
"""Test orphaned device cleanup functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.ramses_extras import _cleanup_orphaned_devices
from custom_components.ramses_extras.const import DOMAIN


class TestOrphanedDeviceCleanup:
    """Test orphaned device cleanup functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def mock_config_entry(self):
        """Create mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        return entry

    @pytest.fixture
    def mock_device_registry(self):
        """Create mock device registry."""
        return MagicMock()

    @pytest.fixture
    def mock_entity_registry(self):
        """Create mock entity registry."""
        return MagicMock()

    @pytest.fixture
    def mock_ramses_device(self):
        """Create mock ramses_extras device."""
        device = MagicMock()
        device.id = "device_id_123"
        device.config_entries = {"test_entry_id"}
        device.identifiers = {(DOMAIN, "32:153289")}
        return device

    @pytest.fixture
    def mock_other_device(self):
        """Create mock device from other integration."""
        device = MagicMock()
        device.id = "device_id_456"
        device.config_entries = {"other_entry_id"}
        device.identifiers = {("other_domain", "18:149488")}
        return device

    @pytest.mark.asyncio
    async def test_cleanup_removes_orphaned_device(
        self,
        mock_hass,
        mock_config_entry,
        mock_device_registry,
        mock_entity_registry,
        mock_ramses_device,
    ):
        """Test that orphaned devices are removed when they have no entities."""
        # Setup mocks
        mock_device_registry.devices.values.return_value = [mock_ramses_device]
        mock_entity_registry.entities.get.return_value = []  # No entities
        mock_device_registry.async_remove_device = AsyncMock()

        await _cleanup_orphaned_devices(
            mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
        )

        # Verify device was identified as orphaned and removed
        # Entity registry lookup uses device_entry.id,
        #  device removal uses device_entry.id
        mock_entity_registry.entities.get.assert_called_with("device_id_123", [])
        mock_device_registry.async_remove_device.assert_called_once_with(
            "device_id_123"
        )

    @pytest.mark.asyncio
    async def test_cleanup_ignores_device_with_entities(
        self,
        mock_hass,
        mock_config_entry,
        mock_device_registry,
        mock_entity_registry,
        mock_ramses_device,
    ):
        """Test that devices with entities are not removed."""
        # Setup mocks - device has entities
        mock_device_registry.devices.values.return_value = [mock_ramses_device]
        mock_entity_registry.entities.get.return_value = [
            "entity_1",
            "entity_2",
        ]  # Has entities
        mock_device_registry.async_remove_device = AsyncMock()

        await _cleanup_orphaned_devices(
            mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
        )

        # Verify device was NOT removed
        mock_device_registry.async_remove_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_ignores_other_integration_devices(
        self,
        mock_hass,
        mock_config_entry,
        mock_device_registry,
        mock_entity_registry,
        mock_other_device,
    ):
        """Test that devices from other integrations are ignored."""
        # Setup mocks - device from other integration
        mock_device_registry.devices.values.return_value = [mock_other_device]
        mock_entity_registry.entities.get.return_value = []  # No entities
        mock_device_registry.async_remove_device = AsyncMock()

        await _cleanup_orphaned_devices(
            mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
        )

        # Verify device was NOT removed (not owned by ramses_extras)
        mock_device_registry.async_remove_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_ignores_device_not_owned_by_config_entry(
        self,
        mock_hass,
        mock_config_entry,
        mock_device_registry,
        mock_entity_registry,
        mock_ramses_device,
    ):
        """Test that ramses_extras devices not owned by our config entry are ignored."""
        # Setup mocks - device belongs to different config entry
        mock_ramses_device.config_entries = {"other_entry_id"}
        mock_device_registry.devices.values.return_value = [mock_ramses_device]
        mock_entity_registry.entities.get.return_value = []  # No entities
        mock_device_registry.async_remove_device = AsyncMock()

        await _cleanup_orphaned_devices(
            mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
        )

        # Verify device was NOT removed (not owned by our config entry)
        mock_device_registry.async_remove_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_handles_multiple_devices(
        self,
        mock_hass,
        mock_config_entry,
        mock_device_registry,
        mock_entity_registry,
        mock_ramses_device,
        mock_other_device,
    ):
        """Test cleanup with multiple devices (some orphaned, some not)."""
        # Create another ramses device with entities
        mock_ramses_device_with_entities = MagicMock()
        mock_ramses_device_with_entities.id = "device_id_789"
        mock_ramses_device_with_entities.config_entries = {"test_entry_id"}
        mock_ramses_device_with_entities.identifiers = {(DOMAIN, "18:149488")}

        # Setup mocks
        mock_device_registry.devices.values.return_value = [
            mock_ramses_device,  # Orphaned (no entities)
            mock_other_device,  # Other integration (ignored)
            mock_ramses_device_with_entities,  # Has entities (not orphaned)
        ]

        # Mock entity registry to return different results for different devices
        call_count = {}

        def mock_entities_get(device_id, default=None):
            call_count[device_id] = call_count.get(device_id, 0) + 1
            if device_id == "device_id_123":
                return []  # No entities - orphaned
            if device_id == "device_id_789":
                return ["entity_1"]  # Has entities - not orphaned
            return default or []

        mock_entity_registry.entities.get.side_effect = mock_entities_get
        mock_device_registry.async_remove_device = AsyncMock()

        await _cleanup_orphaned_devices(
            mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
        )

        # Verify entity registry was called for ramses devices only
        assert "device_id_123" in call_count  # Called for orphaned device
        assert "device_id_789" in call_count  # Called for device with entities
        assert (
            "device_id_456" not in call_count
        )  # Not called for other integration device

        # Verify only the orphaned device was removed
        mock_device_registry.async_remove_device.assert_called_once_with(
            "device_id_123"
        )

    @pytest.mark.asyncio
    async def test_cleanup_handles_exceptions_gracefully(
        self,
        mock_hass,
        mock_config_entry,
        mock_device_registry,
        mock_entity_registry,
        mock_ramses_device,
    ):
        """Test that cleanup handles exceptions gracefully."""
        # Setup mocks - removal fails
        mock_device_registry.devices.values.return_value = [mock_ramses_device]
        mock_entity_registry.entities.get.return_value = []  # No entities
        mock_device_registry.async_remove_device.side_effect = Exception(
            "Removal failed"
        )

        with patch("custom_components.ramses_extras._LOGGER.warning") as mock_logger:
            await _cleanup_orphaned_devices(
                mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
            )

        # Verify warning was logged for the exception
        mock_logger.assert_called_once()
        assert "Failed to remove device 32:153289: Removal failed" in str(
            mock_logger.call_args
        )

    @pytest.mark.asyncio
    async def test_cleanup_no_devices_found(
        self, mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
    ):
        """Test cleanup when no ramses_extras devices are found."""
        # Setup mocks - no devices
        mock_device_registry.devices.values.return_value = []
        mock_device_registry.async_remove_device = AsyncMock()

        await _cleanup_orphaned_devices(
            mock_hass, mock_config_entry, mock_device_registry, mock_entity_registry
        )

        # Verify no devices were removed
        mock_device_registry.async_remove_device.assert_not_called()
