"""Tests for SensorControlResolver in features/sensor_control/resolver.py."""

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.sensor_control.const import (
    INTERNAL_SENSOR_MAPPINGS,
    SUPPORTED_METRICS,
)
from custom_components.ramses_extras.features.sensor_control.resolver import (
    SensorControlResolver,
)


class TestSensorControlResolver:
    """Test cases for SensorControlResolver."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        # Ensure hass.states exists as a mock
        self.hass.states = MagicMock()
        self.resolver = SensorControlResolver(self.hass)
        self.device_id = "01:145:08"
        self.device_key = "01_145_08"
        self.device_type = "FAN"

    def test_init(self):
        """Test initialization of SensorControlResolver."""
        assert self.resolver.hass == self.hass
        assert hasattr(self.resolver, "_logger")

    @pytest.mark.asyncio
    async def test_resolve_entity_mappings_no_config(self):
        """Test resolving entity mappings when no sensor control config exists."""
        # Mock no config entry
        self.hass.data = {}

        result = await self.resolver.resolve_entity_mappings(
            self.device_id, self.device_type
        )

        assert "mappings" in result
        assert "sources" in result
        assert "raw_internal" in result
        assert "abs_humidity_inputs" in result
        assert result["abs_humidity_inputs"] == {}

    @pytest.mark.asyncio
    async def test_resolve_entity_mappings_with_config(self):
        """Test resolving entity mappings with sensor control config."""
        # Mock config entry with sensor control config
        config_entry = MagicMock()
        config_entry.options = {
            "sensor_control": {
                "sources": {
                    self.device_key: {
                        "indoor_temperature": {
                            "kind": "external_entity",
                            "entity_id": "sensor.room_temp",
                        }
                    }
                },
                "abs_humidity_inputs": {
                    self.device_key: {
                        "indoor_abs_humidity": {
                            "temperature": {"kind": "internal"},
                            "humidity": {
                                "kind": "external",
                                "entity_id": "sensor.room_humidity",
                            },
                        }
                    }
                },
            }
        }
        self.hass.data = {"ramses_extras": {"config_entry": config_entry}}

        # Mock entity existence check
        self.resolver._entity_exists = MagicMock(return_value=True)

        result = await self.resolver.resolve_entity_mappings(
            self.device_id, self.device_type
        )

        assert "mappings" in result
        assert "sources" in result
        assert result["abs_humidity_inputs"] == {
            "indoor_abs_humidity": {
                "temperature": {"kind": "internal"},
                "humidity": {"kind": "external", "entity_id": "sensor.room_humidity"},
            }
        }

    @pytest.mark.asyncio
    async def test_resolve_entity_mappings_absolute_humidity_derived(self):
        """Test resolving absolute humidity metrics when
        derived inputs are configured."""
        config_entry = MagicMock()
        config_entry.options = {
            "sensor_control": {
                "abs_humidity_inputs": {
                    self.device_key: {
                        "indoor_abs_humidity": {
                            "temperature": {"kind": "internal"},
                            "humidity": {
                                "kind": "external",
                                "entity_id": "sensor.room_humidity",
                            },
                        }
                    }
                }
            }
        }
        self.hass.data = {"ramses_extras": {"config_entry": config_entry}}

        result = await self.resolver.resolve_entity_mappings(
            self.device_id, self.device_type
        )

        # Absolute humidity should be marked as derived
        assert result["mappings"]["indoor_abs_humidity"] is None
        assert result["sources"]["indoor_abs_humidity"]["kind"] == "derived"
        assert result["sources"]["indoor_abs_humidity"]["valid"] is True

        # Outdoor should be internal (no config)
        assert result["mappings"]["outdoor_abs_humidity"] is None
        assert result["sources"]["outdoor_abs_humidity"]["kind"] == "internal"

    def test_get_sensor_control_config_no_entry(self):
        """Test getting sensor control config when no config entry exists."""
        self.hass.data = {}
        result = self.resolver._get_sensor_control_config()
        assert result is None

    def test_get_sensor_control_config_no_options(self):
        """Test getting sensor control config when config entry has no options."""
        config_entry = MagicMock()
        config_entry.options = {}
        self.hass.data = {"ramses_extras": {"config_entry": config_entry}}
        result = self.resolver._get_sensor_control_config()
        assert result is None

    def test_get_sensor_control_config_with_options(self):
        """Test getting sensor control config when options exist."""
        sensor_control_config = {"sources": {}, "abs_humidity_inputs": {}}
        config_entry = MagicMock()
        config_entry.options = {"sensor_control": sensor_control_config}
        self.hass.data = {"ramses_extras": {"config_entry": config_entry}}
        result = self.resolver._get_sensor_control_config()
        assert result == sensor_control_config

    def test_get_sensor_control_config_exception(self):
        """Test getting sensor control config with exception."""
        self.hass.data = {"ramses_extras": {"config_entry": "invalid"}}
        result = self.resolver._get_sensor_control_config()
        assert result is None

    def test_get_internal_mappings_fan_device(self):
        """Test getting internal mappings for FAN device."""
        result = self.resolver._get_internal_mappings(self.device_id, "FAN")
        assert isinstance(result, dict)
        assert "indoor_temperature" in result
        assert "outdoor_temperature" in result
        assert "indoor_humidity" in result
        assert "outdoor_humidity" in result
        assert "co2" in result
        assert result["indoor_abs_humidity"] is None
        assert result["outdoor_abs_humidity"] is None
        assert self.device_key in result["indoor_temperature"]

    def test_get_internal_mappings_unknown_device_type(self):
        """Test getting internal mappings for unknown device type."""
        result = self.resolver._get_internal_mappings(self.device_id, "UNKNOWN")
        assert isinstance(result, dict)
        for metric in SUPPORTED_METRICS:
            if not metric.endswith("_abs_humidity"):
                assert result[metric] is None

    def test_apply_override_internal_kind(self):
        """Test applying internal kind override."""
        internal_entity = "sensor.fan_indoor_temp_01_145_08"
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id=internal_entity,
            override_kind="internal",
            override_entity_id=None,
        )
        assert entity_id == internal_entity
        assert source["kind"] == "internal"
        assert source["entity_id"] == internal_entity
        assert source["valid"] is True

    def test_apply_override_external_entity_valid(self):
        """Test applying external entity override with valid entity."""
        external_entity = "sensor.room_temp"
        self.resolver._entity_exists = MagicMock(return_value=True)
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="external_entity",
            override_entity_id=external_entity,
        )
        assert entity_id == external_entity
        assert source["kind"] == "external_entity"
        assert source["entity_id"] == external_entity
        assert source["valid"] is True

    def test_apply_override_external_entity_invalid(self):
        """Test applying external entity override with invalid entity."""
        external_entity = "sensor.nonexistent"
        self.resolver._entity_exists = MagicMock(return_value=False)
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="external_entity",
            override_entity_id=external_entity,
        )
        assert entity_id is None
        assert source["kind"] == "external_entity"
        assert source["entity_id"] == external_entity
        assert source["valid"] is False

    def test_apply_override_external_entity_no_id(self):
        """Test applying external entity override with no entity ID."""
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="external_entity",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "external_entity"
        assert source["entity_id"] is None
        assert source["valid"] is False

    def test_apply_override_external_shorthand_valid(self):
        """Test applying external entity override using shorthand 'external'."""
        external_entity = "sensor.room_temp"
        self.resolver._entity_exists = MagicMock(return_value=True)
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="external",
            override_entity_id=external_entity,
        )
        assert entity_id == external_entity
        assert source["kind"] == "external"
        assert source["entity_id"] == external_entity
        assert source["valid"] is True

    def test_apply_override_none_kind(self):
        """Test applying none kind override."""
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="none",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "none"
        assert source["entity_id"] is None
        assert source["valid"] is True

    def test_apply_override_abs_humidity_invalid_kind(self):
        """Test applying invalid override kind for absolute humidity."""
        entity_id, source = self.resolver._apply_override(
            metric="indoor_abs_humidity",
            internal_entity_id=None,
            override_kind="internal",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "internal"
        assert source["valid"] is False

    def test_apply_override_derived_valid(self):
        """Test applying derived override for absolute humidity metrics."""
        entity_id, source = self.resolver._apply_override(
            metric="indoor_abs_humidity",
            internal_entity_id=None,
            override_kind="derived",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "derived"
        assert source["entity_id"] is None
        assert source["valid"] is True

    def test_apply_override_derived_invalid_for_regular_metric(self):
        """Test applying derived override for regular metrics (should fail)."""
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="derived",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "derived"
        assert source["valid"] is False

    def test_apply_override_unknown_kind(self):
        """Test applying unknown override kind."""
        entity_id, source = self.resolver._apply_override(
            metric="indoor_temperature",
            internal_entity_id="sensor.fan_indoor_temp_01_145_08",
            override_kind="unknown",
            override_entity_id=None,
        )
        assert entity_id is None
        assert source["kind"] == "unknown"
        assert source["valid"] is False

    def test_entity_exists_empty_id(self):
        """Test checking if entity exists with empty ID."""
        assert self.resolver._entity_exists("") is False
        assert self.resolver._entity_exists(None) is False

    def test_entity_exists_true(self):
        """Test checking if entity exists when it does."""
        mock_state = MagicMock()
        self.hass.states.get.return_value = mock_state
        result = self.resolver._entity_exists("sensor.test")
        assert result is True
        self.hass.states.get.assert_called_once_with("sensor.test")

    def test_entity_exists_false(self):
        """Test checking if entity exists when it doesn't."""
        self.hass.states.get.return_value = None
        result = self.resolver._entity_exists("sensor.nonexistent")
        assert result is False

    def test_entity_exists_exception(self):
        """Test checking if entity exists with exception."""
        self.hass.states.get.side_effect = Exception("State error")
        result = self.resolver._entity_exists("sensor.error")
        assert result is False

    def test_get_supported_metrics(self):
        """Test getting supported metrics."""
        result = self.resolver.get_supported_metrics()
        assert isinstance(result, list)
        assert set(result) == set(SUPPORTED_METRICS)
        assert result is not SUPPORTED_METRICS

    def test_get_supported_device_types(self):
        """Test getting supported device types."""
        result = self.resolver.get_supported_device_types()
        assert isinstance(result, list)
        assert set(result) == set(INTERNAL_SENSOR_MAPPINGS.keys())
