"""Tests for Config Flow Helper."""

import importlib
import inspect
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers.config_flow import (
    ConfigFlowHelper,
)


class MockConfigFlow:
    """Mock Config Flow Class."""

    @staticmethod
    def get_feature_config_schema():
        """Mock schema."""

    @staticmethod
    def get_feature_info():
        """Mock info."""


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    return MagicMock()


@pytest.fixture
def config_entry():
    """Mock Config Entry."""
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    return entry


class TestConfigFlowHelper:
    """Test ConfigFlowHelper class."""

    def test_init_with_matrix_state(self, hass, config_entry):
        """Test initialization with matrix state in config entry."""
        config_entry.data = {
            "device_feature_matrix": {
                "32_153289": {"hello_world": True},
                "32:153290": {"hello_world": True},
            }
        }

        helper = ConfigFlowHelper(hass, config_entry)

        # Verify normalization and restoration
        assert helper.is_device_enabled_for_feature("32:153289", "hello_world") is True
        assert helper.is_device_enabled_for_feature("32:153290", "hello_world") is True

    def test_get_feature_config_schema(self, hass, config_entry):
        """Test generating feature config schema."""
        helper = ConfigFlowHelper(hass, config_entry)
        devices = ["32:153289", "32:153290"]

        patch_target = (
            "custom_components.ramses_extras.framework.helpers."
            "device.filter.DeviceFilter.filter_devices_for_feature"
        )
        patch_features = (
            "custom_components.ramses_extras.framework.helpers."
            "config_flow.AVAILABLE_FEATURES"
        )
        with (
            patch(patch_target, return_value=devices),
            patch(patch_features, {"hello_world": {"name": "Hello World"}}),
        ):
            schema = helper.get_feature_config_schema("hello_world", devices)
            assert "enabled_devices" in schema.schema

    def test_extract_device_id(self, hass, config_entry):
        """Test device ID extraction from various object types."""
        helper = ConfigFlowHelper(hass, config_entry)

        # String
        assert helper._extract_device_id("test_id") == "test_id"

        # Object with id
        obj_id = MagicMock(spec=["id"])
        obj_id.id = "attr_id"
        assert helper._extract_device_id(obj_id) == "attr_id"

        # Object with device_id
        obj_dev_id = MagicMock(spec=["device_id"])
        obj_dev_id.device_id = "attr_dev_id"
        assert helper._extract_device_id(obj_dev_id) == "attr_dev_id"

        # Unknown
        assert helper._extract_device_id(object()) is None

    def test_get_device_label(self, hass, config_entry):
        """Test device label generation from various object types."""
        helper = ConfigFlowHelper(hass, config_entry)

        # String
        assert helper._get_device_label("test_label") == "test_label"

        # Object with name
        obj_name = MagicMock(spec=["name"])
        obj_name.name = "Device Name"
        assert helper._get_device_label(obj_name) == "Device Name"

        # Unknown
        assert helper._get_device_label(object()) == "Unknown Device"

    def test_set_enabled_devices_for_feature(self, hass, config_entry):
        """Test enabling/disabling devices for a feature."""
        helper = ConfigFlowHelper(hass, config_entry)

        # 1. Enable devices
        helper.set_enabled_devices_for_feature(
            "hello_world", ["32_153289", "32:153290"]
        )
        assert helper.is_device_enabled_for_feature("32:153289", "hello_world") is True

        # 2. Update (which clears existing first)
        helper.set_enabled_devices_for_feature("hello_world", ["32:153290"])
        assert helper.is_device_enabled_for_feature("32:153289", "hello_world") is False
        assert helper.is_device_enabled_for_feature("32:153290", "hello_world") is True

    def test_get_all_feature_device_combinations(self, hass, config_entry):
        """Test getting all enabled combinations."""
        helper = ConfigFlowHelper(hass, config_entry)
        helper.set_enabled_devices_for_feature("hello_world", ["32:153289"])

        combinations = helper.get_all_feature_device_combinations()
        # Combination should be (device_id, feature_id)
        assert ("32:153289", "hello_world") in combinations

    def test_get_feature_device_summary(self, hass, config_entry):
        """Test generating summary text."""
        helper = ConfigFlowHelper(hass, config_entry)

        # Empty
        assert "No feature/device combinations" in helper.get_feature_device_summary()

        # With data
        patch_features = (
            "custom_components.ramses_extras.framework.helpers."
            "config_flow.AVAILABLE_FEATURES"
        )
        with patch(patch_features, {"hello_world": {"name": "Hello World"}}):
            helper.set_enabled_devices_for_feature("hello_world", ["32:153289"])
            summary = helper.get_feature_device_summary()
            assert "Hello World" in summary
            assert "1 devices" in summary

    def test_discover_feature_config_flows(self, hass, config_entry):
        """Test discovery of feature config flows."""
        mock_features = {
            "test_f": {"has_device_config": True, "name": "Test Feature"},
            "no_config": {"has_device_config": False},
            "default": {"has_device_config": True},
        }

        patch_path = "custom_components.ramses_extras.const.AVAILABLE_FEATURES"

        with patch.dict(patch_path, mock_features, clear=True):
            helper = ConfigFlowHelper(hass, config_entry)
            mock_module = MagicMock()

            with patch.object(importlib, "import_module", return_value=mock_module):
                mock_module.MockConfigFlow = MockConfigFlow

                flows = helper.discover_feature_config_flows()
                assert "test_f" in flows
                assert flows["test_f"] is MockConfigFlow
                assert "no_config" not in flows
                assert "default" not in flows

                # Test ImportError
                with patch.object(importlib, "import_module", side_effect=ImportError):
                    flows_err = helper.discover_feature_config_flows()
                    assert flows_err == {}

                # Test generic Exception
                with patch.object(
                    importlib, "import_module", side_effect=ValueError("test error")
                ):
                    flows_ex = helper.discover_feature_config_flows()
                    assert flows_ex == {}

    def test_additional_normalization_and_extraction(self, hass, config_entry):
        """Test remaining normalization and extraction cases."""
        helper = ConfigFlowHelper(hass, config_entry)

        # _normalize_device_id fallback
        assert helper._extract_device_id("32123456") == "32123456"

        # _extract_device_id for _id and name
        obj_id = MagicMock()
        obj_id._id = "attr_id"
        del obj_id.id
        del obj_id.device_id
        assert helper._extract_device_id(obj_id) == "attr_id"

        obj_name = MagicMock()
        obj_name.name = "attr_name"
        del obj_name.id
        del obj_name.device_id
        del obj_name._id
        assert helper._extract_device_id(obj_name) == "attr_name"

        # _get_device_label for device_id and id
        obj_dev_id = MagicMock()
        obj_dev_id.device_id = "label_dev_id"
        del obj_dev_id.name
        assert helper._get_device_label(obj_dev_id) == "label_dev_id"

        obj_id_label = MagicMock()
        obj_id_label.id = "label_id"
        del obj_id_label.name
        del obj_id_label.device_id
        assert helper._get_device_label(obj_id_label) == "label_id"

    def test_selection_and_matrix_state(self, hass, config_entry):
        """Test selection schemas and matrix state management."""
        helper = ConfigFlowHelper(hass, config_entry)

        # get_devices_for_feature_selection
        devices = ["dev1", "dev2"]
        with patch.object(
            helper.device_filter, "filter_devices_for_feature", return_value=devices
        ):
            assert helper.get_devices_for_feature_selection({}, devices) == devices

        # get_feature_selection_schema
        mock_features = {
            "f1": {"name": "Feature 1", "description": "Desc 1"},
            "f2": {"name": "Feature 2", "description": "Long " * 20},
            "default": {"name": "Default"},
        }
        patch_path = "custom_components.ramses_extras.framework.helpers.config_flow.AVAILABLE_FEATURES"  # noqa: E501
        with patch.dict(patch_path, mock_features, clear=True):
            schema = helper.get_feature_selection_schema({"f1": True, "f2": False})
            assert "features" in schema.schema

        # build_feature_info_text with detailed devices
        mock_features_detailed = {
            "f1": {"name": "F1", "allowed_device_slugs": ["FAN", "CO2"]},
            "f2": {"name": "F2", "allowed_device_slugs": ["*"]},
        }
        with patch.dict(patch_path, mock_features_detailed, clear=True):
            info = helper.build_feature_info_text()
            assert "FAN, CO2" in info
            assert "All device types" in info

        # Matrix state management
        state = {"32:1": {"feat": True}}
        helper.restore_matrix_state(state)
        assert helper.get_feature_device_matrix_state() == state
