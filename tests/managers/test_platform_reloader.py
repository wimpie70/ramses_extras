"""Tests for managers/platform_reloader.py."""

import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add the custom_components to the path for testing
sys.path.insert(0, "custom_components")

try:
    from custom_components.ramses_extras.const import DOMAIN
    from custom_components.ramses_extras.managers.platform_reloader import (
        PlatformReloader,
    )
except ImportError:
    pytest.skip(
        "Integration not properly installed for testing",
        allow_module_level=True,
    )


class TestPlatformReloader:
    """Test PlatformReloader class."""

    @pytest.fixture
    def mock_hass(self) -> Mock:
        """Create mock Home Assistant instance."""
        mock_hass = Mock()
        mock_hass.data = {"ramses_extras": {"entry_id": "test_entry_id"}}
        return mock_hass

    @pytest.fixture
    def mock_config_entry(self) -> Mock:
        """Create mock config entry."""
        mock_entry = Mock()
        mock_entry.entry_id = "test_entry_id"
        mock_entry.domain = "ramses_extras"
        return mock_entry

    def test_init(self, mock_hass: Mock, mock_config_entry: Mock) -> None:
        """Test PlatformReloader initialization."""
        with patch("homeassistant.helpers.dispatcher.async_dispatcher_connect"):
            reloader = PlatformReloader(mock_hass, mock_config_entry)

            assert reloader.hass == mock_hass
            assert reloader.config_entry == mock_config_entry

    async def test_handle_devices_added(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test handling new devices added."""
        with patch("homeassistant.helpers.dispatcher.async_dispatcher_connect"):
            reloader = PlatformReloader(mock_hass, mock_config_entry)

            # Set up initial device list
            mock_hass.data[DOMAIN] = {"devices": ["32:153289"]}

            # Mock the reload method
            with patch.object(reloader, "_reload_platforms") as mock_reload:
                await reloader._handle_devices_added(["01:123456"])

                # Should update device list
                assert "01:123456" in mock_hass.data[DOMAIN]["devices"]
                # Should call reload
                mock_reload.assert_called_once()

    async def test_handle_devices_removed(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test handling devices removed."""
        with patch("homeassistant.helpers.dispatcher.async_dispatcher_connect"):
            reloader = PlatformReloader(mock_hass, mock_config_entry)

            # Set up initial device list
            mock_hass.data[DOMAIN] = {"devices": ["32:153289", "01:123456"]}

            # Mock the cleanup and reload methods
            with patch.object(reloader, "_cleanup_removed_devices") as mock_cleanup:
                with patch.object(reloader, "_reload_platforms") as mock_reload:
                    await reloader._handle_devices_removed(["32:153289"])

                    # Should remove device from list
                    assert "32:153289" not in mock_hass.data[DOMAIN]["devices"]
                    assert "01:123456" in mock_hass.data[DOMAIN]["devices"]
                    # Should call cleanup and reload
                    mock_cleanup.assert_called_once_with(["32:153289"])
                    mock_reload.assert_called_once()

    async def test_async_reload_platforms(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test platform reloading."""
        with patch("homeassistant.helpers.dispatcher.async_dispatcher_connect"):
            reloader = PlatformReloader(mock_hass, mock_config_entry)

            # Mock the config entry reload
            mock_hass.config_entries.async_reload_platform_entry = AsyncMock()

            await reloader._reload_platforms()

            # Should reload all platforms
            assert mock_hass.config_entries.async_reload_platform_entry.call_count == 4
            # Check that all expected platforms were reloaded
            mock_reload = mock_hass.config_entries.async_reload_platform_entry
            call_args_list = mock_reload.call_args_list
            called_platforms = [call[0][1] for call in call_args_list]
            expected_platforms = ["sensor", "number", "switch", "binary_sensor"]
            for platform in expected_platforms:
                assert platform in called_platforms

    async def test_setup_listeners(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that event listeners are set up correctly."""
        with patch(
            "homeassistant.helpers.dispatcher.async_dispatcher_connect"
        ) as mock_connect:
            PlatformReloader(mock_hass, mock_config_entry)

            # Should set up listeners for all expected events
            assert mock_connect.call_count == 3

            # Check the calls
            calls = mock_connect.call_args_list
            expected_signals = [
                "ramses_extras_devices_added",
                "ramses_extras_devices_removed",
                "ramses_extras_devices_discovered",
            ]

            for call in calls:
                signal = call[0][1]  # Second argument is the signal name
                assert signal in expected_signals

    async def test_empty_device_events(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test handling empty device lists."""
        with patch("homeassistant.helpers.dispatcher.async_dispatcher_connect"):
            reloader = PlatformReloader(mock_hass, mock_config_entry)

            # Mock the reload method
            with patch.object(reloader, "_reload_platforms") as mock_reload:
                # Send empty device events
                await reloader._handle_devices_added([])
                await reloader._handle_devices_removed([])

                # Should not call reload for empty events
                mock_reload.assert_not_called()

    async def test_handle_devices_discovered(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test handling initial device discovery."""
        with patch("homeassistant.helpers.dispatcher.async_dispatcher_connect"):
            reloader = PlatformReloader(mock_hass, mock_config_entry)

            # Call the handler
            await reloader._handle_devices_discovered(["32:153289", "01:123456"])

            # Should update device list
            assert mock_hass.data[DOMAIN]["devices"] == ["32:153289", "01:123456"]
