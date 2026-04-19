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
            {"rem_id": "37:111111", "enabled": False},
            {"rem_id": "37:654321", "enabled": True},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = mock_bindings
            mock_get_manager.return_value = mock_manager

            result = registry.get_binding_for_fan("32:123456")

            # Should return the first enabled binding
            assert result == mock_bindings[1]

    def test_get_binding_for_fan_all_disabled(self, registry, hass):
        """Test get_binding_for_fan returns None when all bindings disabled."""
        mock_bindings = [
            {"rem_id": "37:111111", "enabled": False},
            {"rem_id": "37:654321", "enabled": False},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = mock_bindings
            mock_get_manager.return_value = mock_manager

            result = registry.get_binding_for_fan("32:123456")

            # Should return None when all are disabled
            assert result is None

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
            "32:123456": [{"rem_id": "37:654321", "enabled": True}],
            "32:789012": [{"rem_id": "37:987654", "enabled": True}],
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


class TestRemoteBindingDiagnostics:
    """Test RemoteBindingRegistry diagnostics features."""

    def test_record_remote_activity_matched(self, registry, hass):
        """Test recording matched remote activity."""
        registry.record_remote_activity(
            rem_id="37:654321",
            fan_id="32:123456",
            command="fan_auto",
            matched=True,
        )

        # Should record last seen
        last_seen = registry.get_last_seen("37:654321")
        assert last_seen is not None

        # Should not add to unmatched traffic
        unmatched = registry.get_unmatched_traffic()
        assert len(unmatched) == 0

    def test_record_remote_activity_unmatched(self, registry, hass):
        """Test recording unmatched remote activity."""
        registry.record_remote_activity(
            rem_id="37:999999",
            fan_id="32:123456",
            command="fan_low",
            matched=False,
        )

        # Should record last seen
        last_seen = registry.get_last_seen("37:999999")
        assert last_seen is not None

        # Should add to unmatched traffic
        unmatched = registry.get_unmatched_traffic()
        assert len(unmatched) == 1
        assert unmatched[0]["rem_id"] == "37:999999"
        assert unmatched[0]["command"] == "fan_low"

    def test_get_unmatched_traffic_limit(self, registry, hass):
        """Test unmatched traffic limit."""
        # Add 10 unmatched entries
        for i in range(10):
            registry.record_remote_activity(
                rem_id=f"37:{i:06d}",
                fan_id="32:123456",
                command="fan_low",
                matched=False,
            )

        # Get with limit
        result = registry.get_unmatched_traffic(limit=5)
        assert len(result) == 5

    def test_clear_unmatched_traffic(self, registry, hass):
        """Test clearing unmatched traffic."""
        registry.record_remote_activity(
            rem_id="37:999999",
            fan_id="32:123456",
            command="fan_low",
            matched=False,
        )

        assert len(registry.get_unmatched_traffic()) == 1

        registry.clear_unmatched_traffic()

        assert len(registry.get_unmatched_traffic()) == 0

    def test_get_diagnostics(self, registry, hass):
        """Test get_diagnostics returns expected data."""
        # Add some activity
        registry.record_remote_activity(
            rem_id="37:654321",
            fan_id="32:123456",
            command="fan_auto",
            matched=True,
        )
        registry.record_remote_activity(
            rem_id="37:999999",
            fan_id="32:123456",
            command="fan_low",
            matched=False,
        )

        diagnostics = registry.get_diagnostics()

        assert "bindings_count" in diagnostics
        assert "last_seen_count" in diagnostics
        assert "unmatched_count" in diagnostics
        assert "cache_size" in diagnostics
        assert diagnostics["last_seen_count"] == 2
        assert diagnostics["unmatched_count"] == 1

    def test_unmatched_traffic_limit_100(self, registry, hass):
        """Test unmatched traffic is capped at 100 entries."""
        # Add 105 unmatched entries
        for i in range(105):
            registry.record_remote_activity(
                rem_id=f"37:{i:06d}",
                fan_id="32:123456",
                command="fan_low",
                matched=False,
            )

        result = registry.get_unmatched_traffic(limit=200)
        # Should be capped at 100
        assert len(result) == 100

    def test_detect_conflicts_no_conflict(self, registry, hass):
        """Test detect_conflicts returns empty when no conflicts."""
        all_bindings = {
            "32:111111": [{"rem_id": "37:111111", "enabled": True}],
            "32:222222": [{"rem_id": "37:222222", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings
            conflicts = registry.detect_conflicts()

            assert len(conflicts) == 0

    def test_detect_conflicts_multi_fan(self, registry, hass):
        """Test detect_conflicts finds REM bound to multiple FANs."""
        all_bindings = {
            "32:111111": [{"rem_id": "37:999999", "enabled": True}],
            "32:222222": [{"rem_id": "37:999999", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings
            conflicts = registry.detect_conflicts()

            assert len(conflicts) == 1
            assert conflicts[0]["rem_id"] == "37:999999"
            assert conflicts[0]["conflict_type"] == "multi_fan"
            assert "32:111111" in conflicts[0]["bound_fans"]
            assert "32:222222" in conflicts[0]["bound_fans"]

    def test_detect_conflicts_ignores_disabled(self, registry, hass):
        """Test detect_conflicts ignores disabled bindings."""
        all_bindings = {
            "32:111111": [{"rem_id": "37:999999", "enabled": True}],
            "32:222222": [{"rem_id": "37:999999", "enabled": False}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings
            conflicts = registry.detect_conflicts()

            # Only one enabled binding, no conflict
            assert len(conflicts) == 0

    def test_export_bindings_yaml(self, registry, hass):
        """Test export_bindings_yaml returns valid structure."""
        all_bindings = {
            "32:123456": [
                {
                    "rem_id": "37:654321",
                    "enabled": True,
                    "source": "manual_config",
                    "zone_id": "bathroom",
                    "area_id": "bathroom",
                }
            ],
            "32:789012": [
                {
                    "rem_id": "37:987654",
                    "enabled": True,
                }
            ],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings
            yaml_str = registry.export_bindings_yaml()

            assert "features" in yaml_str
            assert "remote_binding" in yaml_str
            assert "zone_id" in yaml_str
            assert "area_id" in yaml_str
            assert "bathroom" in yaml_str
            assert "32:123456" in yaml_str
            assert "37:654321" in yaml_str
            assert "REMs" in yaml_str

    def test_export_bindings_yaml_sorted(self, registry, hass):
        """Test export_bindings_yaml sorts FANs for consistency."""
        all_bindings = {
            "32:333333": [{"rem_id": "37:333333", "enabled": True}],
            "32:111111": [{"rem_id": "37:111111", "enabled": True}],
            "32:222222": [{"rem_id": "37:222222", "enabled": True}],
        }

        with patch.object(registry, "list_bindings") as mock_list:
            mock_list.return_value = all_bindings
            yaml_str = registry.export_bindings_yaml()

            # Check that output is sorted (111111 should come before 222222)
            pos1 = yaml_str.find("32:111111")
            pos2 = yaml_str.find("32:222222")
            pos3 = yaml_str.find("32:333333")
            assert pos1 < pos2 < pos3


class TestRemoteBindingRoles:
    """Test RemoteBindingRegistry role support (now simplified - all REMs equal)."""

    def test_get_bindings_for_fan_all(self, registry, hass):
        """Test get_bindings_for_fan returns all enabled bindings."""
        bindings = [
            {"rem_id": "37:111111", "enabled": True},
            {"rem_id": "37:222222", "enabled": True},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = bindings
            mock_get_manager.return_value = mock_manager

            result = registry.get_bindings_for_fan("32:123456")

            assert len(result) == 2

    def test_get_bindings_for_fan_ignores_disabled(self, registry, hass):
        """Test get_bindings_for_fan ignores disabled bindings."""
        bindings = [
            {"rem_id": "37:111111", "enabled": True},
            {"rem_id": "37:222222", "enabled": False},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = bindings
            mock_get_manager.return_value = mock_manager

            result = registry.get_bindings_for_fan("32:123456")

            assert len(result) == 1
            assert result[0]["rem_id"] == "37:111111"

    def test_get_all_rem_ids_for_fan(self, registry, hass):
        """Test get_all_rem_ids_for_fan returns all REM IDs."""
        bindings = [
            {"rem_id": "37:111111", "enabled": True},
            {"rem_id": "37:222222", "enabled": True},
        ]

        with patch.object(registry, "_get_config_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_fan_remote_bindings.return_value = bindings
            mock_get_manager.return_value = mock_manager

            result = registry.get_all_rem_ids_for_fan("32:123456")

            assert len(result) == 2
            assert "37:111111" in result
            assert "37:222222" in result


class TestBindingSuggestions:
    """Test learned binding suggestions from observed traffic."""

    def test_get_binding_suggestions_empty(self, registry, hass):
        """Test get_binding_suggestions returns empty when no traffic."""
        result = registry.get_binding_suggestions()

        assert result["total_suggestions"] == 0
        assert result["suggestions_by_fan"] == {}

    def test_get_binding_suggestions_from_unmatched(self, registry, hass):
        """Test get_binding_suggestions generates suggestions from traffic."""
        # Record 3 unmatched observations from same REM to same FAN
        for _ in range(3):
            registry.record_remote_activity(
                rem_id="37:999999",
                fan_id="32:123456",
                command="fan_low",
                matched=False,
            )

        result = registry.get_binding_suggestions()

        assert result["total_suggestions"] == 1
        assert "32:123456" in result["suggestions_by_fan"]
        suggestion = result["suggestions_by_fan"]["32:123456"][0]
        assert suggestion["rem_id"] == "37:999999"
        assert suggestion["observed_count"] == 3
        # Note: suggested_role removed - all REMs are equal now

    def test_get_binding_suggestions_below_threshold(self, registry, hass):
        """Test get_binding_suggestions only suggests with 3+ observations."""
        # Only 2 observations - below threshold
        for _ in range(2):
            registry.record_remote_activity(
                rem_id="37:999999",
                fan_id="32:123456",
                command="fan_low",
                matched=False,
            )

        result = registry.get_binding_suggestions()

        assert result["total_suggestions"] == 0

    def test_get_binding_suggestions_for_specific_fan(self, registry, hass):
        """Test get_binding_suggestions with specific fan_id filter."""
        # Record traffic for two FANs
        for _ in range(3):
            registry.record_remote_activity(
                rem_id="37:111111",
                fan_id="32:111111",
                command="fan_low",
                matched=False,
            )
        for _ in range(3):
            registry.record_remote_activity(
                rem_id="37:222222",
                fan_id="32:222222",
                command="fan_low",
                matched=False,
            )

        result = registry.get_binding_suggestions(fan_id="32:111111")

        assert result["fan_id"] == "32:111111"
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["rem_id"] == "37:111111"

    def test_get_binding_suggestions_confidence(self, registry, hass):
        """Test get_binding_suggestions confidence calculation."""
        # Record 5 observations
        for _ in range(5):
            registry.record_remote_activity(
                rem_id="37:999999",
                fan_id="32:123456",
                command="fan_low",
                matched=False,
            )

        result = registry.get_binding_suggestions()

        suggestion = result["suggestions_by_fan"]["32:123456"][0]
        assert suggestion["confidence"] == 0.5  # 5/10

    def test_get_binding_suggestions_max_confidence(self, registry, hass):
        """Test get_binding_suggestions confidence caps at 1.0."""
        # Record 20 observations (more than 10)
        for _ in range(20):
            registry.record_remote_activity(
                rem_id="37:999999",
                fan_id="32:123456",
                command="fan_low",
                matched=False,
            )

        result = registry.get_binding_suggestions()

        suggestion = result["suggestions_by_fan"]["32:123456"][0]
        assert suggestion["confidence"] == 1.0  # capped at 1.0


class TestGetLastActivityForFan:
    """Test get_last_activity_for_fan method."""

    def test_get_last_activity_empty_fan_id(self, registry, hass):
        """Test get_last_activity_for_fan with empty fan_id."""
        result = registry.get_last_activity_for_fan("")
        assert result is None

    def test_get_last_activity_whitespace_fan_id(self, registry, hass):
        """Test get_last_activity_for_fan with whitespace-only fan_id."""
        result = registry.get_last_activity_for_fan("   ")
        assert result is None

    def test_get_last_activity_no_activity(self, registry, hass):
        """Test get_last_activity_for_fan when no activity recorded."""
        result = registry.get_last_activity_for_fan("32:123456")
        assert result is None

    def test_get_last_activity_with_activity(self, registry, hass):
        """Test get_last_activity_for_fan returns recorded activity."""
        registry.record_remote_activity(
            rem_id="37:654321",
            fan_id="32:123456",
            command="fan_auto",
            matched=True,
        )

        result = registry.get_last_activity_for_fan("32:123456")

        assert result is not None
        assert result["rem_id"] == "37:654321"
        assert result["command"] == "fan_auto"

    def test_get_last_activity_normalized_underscore(self, registry, hass):
        """Test get_last_activity_for_fan normalizes underscore format."""
        registry.record_remote_activity(
            rem_id="37:654321",
            fan_id="32:123456",
            command="fan_auto",
            matched=True,
        )

        # Use underscore format
        result = registry.get_last_activity_for_fan("32_123456")

        assert result is not None
        assert result["rem_id"] == "37:654321"
