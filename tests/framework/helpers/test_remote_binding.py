"""Tests for remote binding registry."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.helpers.remote_binding import (
    RemoteBindingRegistry,
    get_remote_binding_registry,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def registry(hass):
    """Create a RemoteBindingRegistry with mocked config."""
    return RemoteBindingRegistry(hass)


class TestRemoteBindingRegistry:
    """Test RemoteBindingRegistry functionality."""

    def test_get_binding_for_fan_no_config_manager(self, registry):
        """Test get_binding_for_fan returns None when no config available."""
        result = registry.get_binding_for_fan("32:123456")
        assert result is None

    def test_get_binding_for_fan_with_binding(self, registry, hass):
        """Test get_binding_for_fan returns binding when available."""
        mock_binding = {
            "rem_id": "37:654321",
            "role": "primary",
            "enabled": True,
            "source": "manual_config",
        }

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = [mock_binding]
            mock_get_manager.return_value = mock_manager

            result = registry.get_binding_for_fan("32:123456")

            assert result == mock_binding
            mock_manager.get_fan_remote_bindings.assert_called_once_with("32:123456")

    def test_get_binding_for_fan_normalized_id(self, registry, hass):
        """Test get_binding_for_fan normalizes device IDs."""
        mock_binding = {
            "rem_id": "37:654321",
            "role": "primary",
            "enabled": True,
        }

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = [mock_binding]
            mock_get_manager.return_value = mock_manager

            # Use legacy format (underscores)
            result = registry.get_binding_for_fan("32_123456")

            assert result == mock_binding
            # Should be normalized to canonical format
            mock_manager.get_fan_remote_bindings.assert_called_once_with("32:123456")

    def test_get_binding_for_fan_disabled_binding(self, registry, hass):
        """Test get_binding_for_fan skips disabled bindings."""
        mock_bindings = [
            {"rem_id": "37:111111", "role": "secondary", "enabled": False},
            {"rem_id": "37:654321", "role": "primary", "enabled": True},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = mock_bindings
            mock_get_manager.return_value = mock_manager

            result = registry.get_binding_for_fan("32:123456")

            # Should return the first enabled binding
            assert result == mock_bindings[1]

    def test_get_rem_id_for_fan(self, registry, hass):
        """Test get_rem_id_for_fan extracts REM ID."""
        mock_binding = {
            "rem_id": "37:654321",
            "role": "primary",
            "enabled": True,
        }

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = [mock_binding]
            mock_get_manager.return_value = mock_manager

            result = registry.get_rem_id_for_fan("32:123456")

            assert result == "37:654321"

    def test_get_rem_id_for_fan_no_binding(self, registry, hass):
        """Test get_rem_id_for_fan returns None when no binding."""
        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = []
            mock_get_manager.return_value = mock_manager

            result = registry.get_rem_id_for_fan("32:123456")

            assert result is None

    def test_list_bindings(self, registry, hass):
        """Test list_bindings returns all bindings."""
        mock_bindings = {
            "32:123456": [{"rem_id": "37:654321", "role": "primary", "enabled": True}],
            "32:789012": [{"rem_id": "37:987654", "role": "primary", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = mock_bindings

            result = registry.list_bindings()

            assert result == mock_bindings

    def test_is_rem_bound_true(self, registry, hass):
        """Test is_rem_bound returns True when REM is bound."""
        all_bindings = {
            "32:123456": [{"rem_id": "37:654321", "role": "primary", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings

            result = registry.is_rem_bound("37:654321")

            assert result is True

    def test_is_rem_bound_false(self, registry, hass):
        """Test is_rem_bound returns False when REM is not bound."""
        all_bindings = {
            "32:123456": [{"rem_id": "37:654321", "role": "primary", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings

            result = registry.is_rem_bound("37:999999")

            assert result is False

    def test_is_rem_bound_disabled(self, registry, hass):
        """Test is_rem_bound returns False for disabled binding."""
        all_bindings = {
            "32:123456": [{"rem_id": "37:654321", "role": "primary", "enabled": False}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings

            result = registry.is_rem_bound("37:654321")

            assert result is False

    def test_find_fan_for_rem(self, registry, hass):
        """Test find_fan_for_rem returns correct FAN."""
        all_bindings = {
            "32:123456": [{"rem_id": "37:654321", "role": "primary", "enabled": True}],
            "32:789012": [{"rem_id": "37:987654", "role": "primary", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings

            result = registry.find_fan_for_rem("37:654321")

            assert result == "32:123456"

    def test_find_fan_for_rem_not_found(self, registry, hass):
        """Test find_fan_for_rem returns None when REM not found."""
        all_bindings = {
            "32:123456": [{"rem_id": "37:654321", "role": "primary", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings

            result = registry.find_fan_for_rem("37:999999")

            assert result is None

    def test_invalidate_cache(self, registry, hass):
        """Test invalidate_cache clears the cache."""
        # Add something to cache
        registry._cache["32:123456"] = {"rem_id": "37:654321"}

        registry.invalidate_cache()

        assert len(registry._cache) == 0

    def test_caching_behavior(self, registry, hass):
        """Test that binding results are cached."""
        mock_binding = {
            "rem_id": "37:654321",
            "role": "primary",
            "enabled": True,
        }

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = [mock_binding]
            mock_get_manager.return_value = mock_manager

            # First call should hit the manager
            result1 = registry.get_binding_for_fan("32:123456")
            assert result1 == mock_binding
            mock_manager.get_fan_remote_bindings.assert_called_once()

            # Second call should use cache
            result2 = registry.get_binding_for_fan("32:123456")
            assert result2 == mock_binding
            # Should not call manager again
            mock_manager.get_fan_remote_bindings.assert_called_once()


class TestGetRemoteBindingRegistry:
    """Test get_remote_binding_registry factory function."""

    def test_creates_new_registry(self, hass):
        """Test creates new registry when none exists."""
        result = get_remote_binding_registry(hass)

        assert isinstance(result, RemoteBindingRegistry)
        assert "remote_binding_registry" in hass.data.get(DOMAIN, {})

    def test_returns_existing_registry(self, hass):
        """Test returns existing registry if already created."""
        existing = RemoteBindingRegistry(hass)
        hass.data[DOMAIN] = {"remote_binding_registry": existing}

        result = get_remote_binding_registry(hass)

        assert result is existing
