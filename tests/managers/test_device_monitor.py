"""Tests for managers/device_monitor.py."""

import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add the custom_components to the path for testing
sys.path.insert(0, "custom_components")

try:
    from ramses_extras.const import DOMAIN
    from ramses_extras.managers.device_monitor import DeviceMonitor
except ImportError:
    pytest.skip(
        "Integration not properly installed for testing",
        allow_module_level=True,
    )


class TestDeviceMonitor:
    """Test DeviceMonitor class."""

    @pytest.fixture
    def mock_hass(self) -> Mock:
        """Create mock Home Assistant instance."""
        mock_hass = Mock()
        mock_hass.data = {}
        mock_hass.bus = Mock()
        mock_hass.bus.async_listen = Mock()
        return mock_hass

    @pytest.fixture
    def mock_config_entry(self) -> Mock:
        """Create mock config entry."""
        mock_entry = Mock()
        mock_entry.entry_id = "test_entry_id"
        return mock_entry

    def test_init(self, mock_hass: Mock) -> None:
        """Test DeviceMonitor initialization."""
        monitor = DeviceMonitor(mock_hass)

        assert monitor.hass == mock_hass
        assert monitor._known_devices == set()
        assert monitor._ramses_cc_available is False

    async def test_start_monitoring_no_ramses_cc(self, mock_hass: Mock) -> None:
        """Test starting monitoring when ramses_cc is not available."""
        with patch("ramses_extras.managers.device_monitor._LOGGER") as mock_logger:
            monitor = DeviceMonitor(mock_hass)

            await monitor.start_monitoring()

            assert monitor._ramses_cc_available is False
            mock_logger.warning.assert_called_once()
            mock_logger.warning.assert_called_with(
                "ramses_cc not loaded, device monitoring disabled"
            )

    async def test_start_monitoring_with_ramses_cc(self, mock_hass: Mock) -> None:
        """Test starting monitoring when ramses_cc is available."""
        # Mock the device list in hass.data (populated by device discovery)
        mock_hass.data = {DOMAIN: {"devices": ["32:153289", "01:123456"]}}

        with patch.object(mock_hass.bus, "async_listen"):
            with patch(
                "ramses_extras.managers.device_monitor.async_dispatcher_send"
            ) as mock_send:
                monitor = DeviceMonitor(mock_hass)

                await monitor.start_monitoring()

                assert monitor._ramses_cc_available is True
                assert "32:153289" in monitor._known_devices
                assert "01:123456" in monitor._known_devices
                mock_send.assert_called_once()

    async def test_handle_ramses_cc_device_event_empty(self, mock_hass: Mock) -> None:
        """Test handling empty device list from ramses_cc."""
        monitor = DeviceMonitor(mock_hass)
        monitor._known_devices = {"32:153289"}

        # Test with empty device list
        await monitor._handle_ramses_cc_device_event([])

        # Should not change known devices
        assert "32:153289" in monitor._known_devices
        assert len(monitor._known_devices) == 1

    async def test_handle_device_registry_event_remove(self, mock_hass: Mock) -> None:
        """Test handling device removal from HA device registry."""
        monitor = DeviceMonitor(mock_hass)
        monitor._known_devices = {"32:153289", "01:123456"}

        # Mock removal event
        mock_event = Mock()
        mock_event.data = {"action": "remove", "device_id": "32:153289"}

        with patch(
            "ramses_extras.managers.device_monitor.async_dispatcher_send"
        ) as mock_send:
            monitor._handle_device_registry_event(mock_event)

            assert "32:153289" not in monitor._known_devices
            assert "01:123456" in monitor._known_devices

            mock_send.assert_called_once_with(
                mock_hass, "ramses_extras_devices_removed", ["32:153289"]
            )

    async def test_handle_device_registry_event_non_remove(
        self, mock_hass: Mock
    ) -> None:
        """Test handling non-removal device registry events."""
        monitor = DeviceMonitor(mock_hass)
        monitor._known_devices = {"32:153289"}

        # Mock update event (not removal)
        mock_event = Mock()
        mock_event.data = {"action": "update", "device_id": "32:153289"}

        with patch(
            "ramses_extras.managers.device_monitor.async_dispatcher_send"
        ) as mock_send:
            monitor._handle_device_registry_event(mock_event)

            # Device should remain
            assert "32:153289" in monitor._known_devices
            # Should not send removal signal
            mock_send.assert_not_called()

    async def test_handle_device_registry_event_unknown_device(
        self, mock_hass: Mock
    ) -> None:
        """Test handling removal of unknown device."""
        monitor = DeviceMonitor(mock_hass)
        monitor._known_devices = {"32:153289"}

        # Mock removal of unknown device
        mock_event = Mock()
        mock_event.data = {"action": "remove", "device_id": "99:000001"}

        with patch(
            "ramses_extras.managers.device_monitor.async_dispatcher_send"
        ) as mock_send:
            monitor._handle_device_registry_event(mock_event)

            # Known device should remain
            assert "32:153289" in monitor._known_devices
            # Should not send removal signal for unknown device
            mock_send.assert_not_called()

    def test_setup_listeners(self, mock_hass: Mock) -> None:
        """Test that listeners are set up correctly."""
        monitor = DeviceMonitor(mock_hass)

        # Mock ramses_cc data
        mock_broker = Mock()
        mock_hass.data = {"ramses_cc": {"test_entry": mock_broker}}

        # Setup should be called during start_monitoring
        with patch.object(mock_hass.bus, "async_listen") as mock_listen:
            # Manually call setup methods to test them
            monitor._setup_ramses_cc_listeners()
            monitor._setup_device_registry_listener()

            # Should listen to ramses_cc signals for all platforms
            assert mock_hass.bus.async_listen.called
            mock_listen.assert_called_with(
                "device_registry_updated", monitor._handle_device_registry_event
            )

    async def test_is_supported_device(self, mock_hass: Mock) -> None:
        """Test device support checking."""
        monitor = DeviceMonitor(mock_hass)

        # Patch the helper functions at the module level where they are imported
        with patch("ramses_extras.helpers.device.find_ramses_device") as mock_find:
            mock_device = Mock()
            mock_device.id = "32:153289"  # Device needs an id attribute
            mock_find.return_value = mock_device

            with patch("ramses_extras.helpers.device.get_device_type") as mock_get_type:
                mock_get_type.return_value = "HvacVentilator"

                result = await monitor._is_supported_device("32:153289")
                assert result is True

                # Test unsupported device
                mock_get_type.return_value = "UnsupportedDevice"
                result = await monitor._is_supported_device("99:000001")
                assert result is False

                # Test device not found
                mock_find.return_value = None
                result = await monitor._is_supported_device("unknown:device")
                assert result is False

    async def test_error_handling_in_event_handlers(self, mock_hass: Mock) -> None:
        """Test error handling in event handlers."""
        monitor = DeviceMonitor(mock_hass)

        # Mock event that will cause an exception
        mock_event = Mock()
        mock_event.data = None  # This will cause an AttributeError

        with patch("ramses_extras.managers.device_monitor._LOGGER") as mock_logger:
            # Should not raise exception, should log error
            monitor._handle_device_registry_event(mock_event)

            mock_logger.debug.assert_called_once()

    async def test_stop_monitoring(self, mock_hass: Mock) -> None:
        """Test stopping monitoring."""
        monitor = DeviceMonitor(mock_hass)
        monitor._ramses_cc_available = True

        await monitor.stop_monitoring()

        assert monitor._ramses_cc_available is False
