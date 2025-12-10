"""Unit tests for direct platform setup."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.ramses_extras.managers.direct_platform_setup import (
    setup_platforms_directly,
)


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    mock_hass = Mock()
    mock_hass.config_entries = Mock()
    return mock_hass


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    mock_entry = Mock()
    mock_entry.entry_id = "test_entry"
    return mock_entry


class TestDirectPlatformSetup:
    """Unit tests for direct platform setup"""

    async def test_setup_platforms_directly(self, mock_hass, mock_config_entry):
        """Test direct platform setup."""
        # Mock the internal platform setup functions
        with (
            patch(
                "custom_components.ramses_extras.managers.direct_platform_setup._setup_default_sensors"
            ) as mock_sensor_setup,
            patch(
                "custom_components.ramses_extras.managers.direct_platform_setup._setup_default_switches"
            ) as mock_switch_setup,
            patch(
                "custom_components.ramses_extras.managers.direct_platform_setup._setup_humidity_control_sensors"
            ) as mock_humidity_sensor_setup,
            patch(
                "custom_components.ramses_extras.managers.direct_platform_setup._setup_humidity_control_switches"
            ) as mock_humidity_switch_setup,
        ):
            await setup_platforms_directly(mock_hass, mock_config_entry)

            # Verify direct calls to internal functions
            mock_sensor_setup.assert_called_once_with(mock_hass, mock_config_entry)
            mock_switch_setup.assert_called_once_with(mock_hass, mock_config_entry)
            mock_humidity_sensor_setup.assert_called_once_with(
                mock_hass, mock_config_entry
            )
            mock_humidity_switch_setup.assert_called_once_with(
                mock_hass, mock_config_entry
            )

    async def test_error_handling(self, mock_hass, mock_config_entry):
        """Test error handling in platform setup."""
        with patch(
            "custom_components.ramses_extras.managers.direct_platform_setup._setup_default_sensors"
        ) as mock_sensor_setup:
            mock_sensor_setup.side_effect = Exception("Setup failed")

            # Should not raise, should log error
            with patch(
                "custom_components.ramses_extras.managers.direct_platform_setup._LOGGER"
            ) as mock_logger:
                await setup_platforms_directly(mock_hass, mock_config_entry)
                mock_logger.error.assert_called()
