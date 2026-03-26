"""Tests for ExtrasConfigManager FAN-oriented accessor methods."""

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.config.core import (
    ExtrasConfigManager,
)


class TestExtrasConfigManagerFanAccessors:
    """Test FAN-oriented accessor methods using shared helpers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        self.config_entry = MagicMock(spec=ConfigEntry)
        self.config_entry.options = {}
        self.config_entry.data = {}
        self.feature_id = "test_feature"
        self.default_config = {"enabled": False}

    def test_get_fan_zones_returns_normalized_zones(self):
        """Test get_fan_zones uses shared helper for normalized zone lookup."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        # Set up config with zones feature
        manager._config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    "zones": {
                        "FANs": {
                            "32:153289": [
                                {
                                    "zone_id": " bathroom ",
                                    "actuator": {"min_position": 15},
                                },
                                {"zone_id": "office"},
                            ]
                        }
                    }
                },
            }
        }

        zones = manager.get_fan_zones("32_153289")

        # Should return normalized zones (trimmed zone_id)
        assert len(zones) == 2
        assert zones[0]["zone_id"] == "bathroom"  # trimmed
        assert zones[0]["actuator"]["min_position"] == 15
        assert zones[1]["zone_id"] == "office"

    def test_get_fan_zone_ids_returns_unique_ids(self):
        """Test get_fan_zone_ids returns unique zone IDs."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    "zones": {
                        "FANs": {
                            "32:153289": [
                                {"zone_id": "bathroom"},
                                {"zone_id": "office"},
                                {"zone_id": "bathroom"},  # duplicate
                            ]
                        }
                    }
                },
            }
        }

        zone_ids = manager.get_fan_zone_ids("32:153289")

        # Should return unique IDs only
        assert zone_ids == ["bathroom", "office"]

    def test_get_fan_remote_bindings_normalizes_rem_ids(self):
        """Test get_fan_remote_bindings normalizes legacy remote_id values."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    "remote_binding": {
                        "FANs": {
                            "32:153289": {
                                "REMs": [
                                    {"remote_id": "37_169161", "role": "primary"},
                                    {"rem_id": "37:000002", "role": "secondary"},
                                ]
                            }
                        }
                    }
                },
            }
        }

        rems = manager.get_fan_remote_bindings("32_153289")

        # Should normalize legacy remote_id to rem_id
        assert len(rems) == 2
        assert rems[0]["rem_id"] == "37:169161"  # normalized from 37_169161
        assert rems[0]["role"] == "primary"
        assert rems[1]["rem_id"] == "37:000002"
        assert "remote_id" not in rems[0]  # legacy key removed

    def test_get_fan_remote_binding_ids_returns_unique_ids(self):
        """Test get_fan_remote_binding_ids returns unique REM IDs."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {
                    "remote_binding": {
                        "FANs": {
                            "32:153289": {
                                "REMs": [
                                    {"rem_id": "37:169161", "role": "primary"},
                                    {"rem_id": "37:169161", "role": "secondary"},
                                    {"rem_id": "37:000002"},
                                ]
                            }
                        }
                    }
                },
            }
        }

        rem_ids = manager.get_fan_remote_binding_ids("32:153289")

        # Should return unique IDs only
        assert rem_ids == ["37:169161", "37:000002"]

    def test_get_fan_zones_returns_empty_for_unknown_fan(self):
        """Test get_fan_zones returns empty list for unknown FAN."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {"zones": {"FANs": {}}},
            }
        }

        zones = manager.get_fan_zones("99:999999")

        assert zones == []

    def test_get_fan_remote_bindings_returns_empty_for_unknown_fan(self):
        """Test get_fan_remote_bindings returns empty list for unknown FAN."""
        manager = ExtrasConfigManager(
            self.hass, self.config_entry, self.feature_id, self.default_config
        )
        manager._config = {
            "ramses_extras": {
                "schema_version": 1,
                "features": {"remote_binding": {"FANs": {}}},
            }
        }

        rems = manager.get_fan_remote_bindings("99:999999")

        assert rems == []
