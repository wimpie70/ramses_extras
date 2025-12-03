"""Integration tests for config flow navigation and feature configuration."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import selector

from custom_components.ramses_extras.config_flow import RamsesExtrasOptionsFlowHandler
from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.config_flow import (
    ConfigFlowHelper,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.data = {"ramses_extras": {"devices": []}}
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return Mock(spec=ConfigEntry)


@pytest.fixture
def config_flow_handler(mock_hass, mock_config_entry):
    """Create a config flow handler instance."""
    return RamsesExtrasOptionsFlowHandler(mock_config_entry)


def test_config_flow_helper_initialization(mock_hass, mock_config_entry):
    """Test ConfigFlowHelper initialization."""
    helper = ConfigFlowHelper(mock_hass, mock_config_entry)

    assert helper.hass == mock_hass
    assert helper.config_entry == mock_config_entry
    assert helper.device_feature_matrix is not None
    assert helper.device_filter is not None


def test_get_feature_info():
    """Test getting feature information."""
    helper = ConfigFlowHelper(Mock(), Mock())

    # Test with existing feature
    feature_info = helper.get_feature_info("humidity_control")
    assert feature_info["name"] == "Humidity Control"
    assert "Automatic humidity control" in feature_info["description"]
    assert feature_info["allowed_device_slugs"] == ["FAN"]

    # Test with non-existent feature - should return default values
    feature_info = helper.get_feature_info("nonexistent")
    assert feature_info["name"] == "nonexistent"
    assert feature_info["allowed_device_slugs"] == ["*"]


def test_feature_device_matrix_operations():
    """Test feature/device matrix operations."""
    helper = ConfigFlowHelper(Mock(), Mock())

    # Test initial state
    assert helper.get_enabled_devices_for_feature("humidity_control") == []

    # Enable devices for feature
    helper.set_enabled_devices_for_feature("humidity_control", ["device1", "device2"])

    # Verify devices are enabled
    enabled_devices = helper.get_enabled_devices_for_feature("humidity_control")
    assert len(enabled_devices) == 2
    assert "device1" in enabled_devices
    assert "device2" in enabled_devices

    # Test device checking
    assert helper.is_device_enabled_for_feature("device1", "humidity_control") is True
    assert helper.is_device_enabled_for_feature("device3", "humidity_control") is False

    # Test getting all combinations
    combinations = helper.get_all_feature_device_combinations()
    assert len(combinations) == 2
    assert ("device1", "humidity_control") in combinations
    assert ("device2", "humidity_control") in combinations


def test_feature_selection_schema():
    """Test feature selection schema generation."""
    helper = ConfigFlowHelper(Mock(), Mock())

    current_features = {
        "default": True,
        "humidity_control": True,
        "hvac_fan_card": False,
        "hello_world_card": False,
    }

    schema = helper.get_feature_selection_schema(current_features)

    # Verify schema structure
    assert schema is not None
    assert "features" in schema.schema

    # Test schema validation
    test_data = {"features": ["humidity_control"]}
    result = schema(test_data)
    assert result["features"] == ["humidity_control"]


def test_device_filtering_integration():
    """Test device filtering integration."""
    helper = ConfigFlowHelper(Mock(), Mock())

    # Create mock devices
    devices = [
        Mock(slugs=["FAN"], name="Fan Device 1"),
        Mock(slugs=["REM"], name="Remote Device 1"),
        Mock(slugs=["FAN"], name="Fan Device 2"),
    ]

    # Test filtering for FAN-only feature
    feature_config = {"allowed_device_slugs": ["FAN"]}
    filtered_devices = helper.get_devices_for_feature_selection(feature_config, devices)

    assert len(filtered_devices) == 2
    # Check that the filtered devices are the expected ones
    device_names = [device.name for device in filtered_devices]
    assert "Fan Device 1" in device_names
    assert "Fan Device 2" in device_names

    # Test wildcard filtering
    feature_config = {"allowed_device_slugs": ["*"]}
    filtered_devices = helper.get_devices_for_feature_selection(feature_config, devices)

    assert len(filtered_devices) == 3


def test_matrix_state_management():
    """Test matrix state serialization/deserialization."""
    helper = ConfigFlowHelper(Mock(), Mock())

    # Set up some data
    helper.set_enabled_devices_for_feature("humidity_control", ["device1", "device2"])
    helper.set_enabled_devices_for_feature("hvac_fan_card", ["device1"])

    # Get state
    state = helper.get_feature_device_matrix_state()
    assert state == {
        "device1": {"humidity_control": True, "hvac_fan_card": True},
        "device2": {"humidity_control": True},
    }

    # Create new helper and restore state
    new_helper = ConfigFlowHelper(Mock(), Mock())
    new_helper.restore_matrix_state(state)

    # Verify state was restored
    assert new_helper.get_enabled_devices_for_feature("humidity_control") == [
        "device1",
        "device2",
    ]
    assert new_helper.get_enabled_devices_for_feature("hvac_fan_card") == ["device1"]


def test_config_flow_navigation(mock_hass, mock_config_entry):
    """Test config flow navigation between steps."""
    # Mock the async_show_form method
    with patch.object(
        RamsesExtrasOptionsFlowHandler, "async_show_form"
    ) as mock_show_form:
        handler = RamsesExtrasOptionsFlowHandler(mock_config_entry)

        # Test initial step redirects to features
        result = handler.async_step_init()
        assert result == mock_show_form.return_value

        # Test features step
        mock_show_form.reset_mock()
        result = handler.async_step_features()
        assert result == mock_show_form.return_value

        # Verify the call was made with correct parameters
        call_args = mock_show_form.call_args
        assert call_args[0][0] == "features"
        assert "data_schema" in call_args[1]
        assert "description_placeholders" in call_args[1]


def test_feature_config_step(mock_hass, mock_config_entry):
    """Test feature configuration step."""
    # Mock devices
    mock_devices = [
        Mock(slugs=["FAN"], name="Test Fan 1"),
        Mock(slugs=["FAN"], name="Test Fan 2"),
    ]

    # Mock the device discovery
    mock_hass.data = {"ramses_extras": {"devices": mock_devices}}

    with patch.object(
        RamsesExtrasOptionsFlowHandler, "async_show_form"
    ) as mock_show_form:
        handler = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        handler._selected_feature = "humidity_control"

        # Test feature config step
        result = handler.async_step_feature_config()
        assert result == mock_show_form.return_value

        # Verify the call was made with correct parameters
        call_args = mock_show_form.call_args
        assert call_args[0][0] == "feature_config"
        assert "data_schema" in call_args[1]
        assert "description_placeholders" in call_args[1]


def test_device_selection_step(mock_hass, mock_config_entry):
    """Test device selection step."""
    # Mock devices
    mock_devices = [
        Mock(slugs=["FAN"], name="Test Fan 1"),
        Mock(slugs=["FAN"], name="Test Fan 2"),
    ]

    # Mock the device discovery
    mock_hass.data = {"ramses_extras": {"devices": mock_devices}}

    with patch.object(
        RamsesExtrasOptionsFlowHandler, "async_show_form"
    ) as mock_show_form:
        handler = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        handler._selected_feature = "humidity_control"

        # Test device selection step
        result = handler.async_step_device_selection()
        assert result == mock_show_form.return_value

        # Verify the call was made with correct parameters
        call_args = mock_show_form.call_args
        assert call_args[0][0] == "device_selection"
        assert "data_schema" in call_args[1]
        assert "description_placeholders" in call_args[1]


def test_feature_device_config_storage(mock_hass, mock_config_entry):
    """Test feature/device configuration storage."""
    handler = RamsesExtrasOptionsFlowHandler(mock_config_entry)

    # Test storing device configuration
    handler._store_feature_device_config("humidity_control", ["device1", "device2"])

    # Verify it was stored in the config flow helper
    assert handler._config_flow_helper is not None
    enabled_devices = handler._config_flow_helper.get_enabled_devices_for_feature(
        "humidity_control"
    )
    assert len(enabled_devices) == 2
    assert "device1" in enabled_devices
    assert "device2" in enabled_devices


def test_entity_manager_per_device_tracking(mock_hass):
    """Test EntityManager per-device tracking capabilities."""
    from custom_components.ramses_extras.framework.helpers.entity.manager import (
        EntityManager,
    )

    manager = EntityManager(mock_hass)

    # Test device feature matrix access
    matrix = manager.get_device_feature_matrix()
    assert matrix is not None

    # Test enabling features for devices
    manager.enable_feature_for_device("device1", "humidity_control")
    manager.enable_feature_for_device("device2", "humidity_control")
    manager.enable_feature_for_device("device1", "hvac_fan_card")

    # Test getting enabled devices
    enabled_devices = manager.get_enabled_devices_for_feature("humidity_control")
    assert len(enabled_devices) == 2
    assert "device1" in enabled_devices
    assert "device2" in enabled_devices

    # Test checking device enablement
    assert manager.is_device_enabled_for_feature("device1", "humidity_control") is True
    assert manager.is_device_enabled_for_feature("device2", "hvac_fan_card") is False

    # Test getting all combinations
    combinations = manager.get_all_feature_device_combinations()
    assert len(combinations) == 3
    assert ("device1", "humidity_control") in combinations
    assert ("device2", "humidity_control") in combinations
    assert ("device1", "hvac_fan_card") in combinations


def test_matrix_state_serialization(mock_hass):
    """Test matrix state serialization and deserialization."""
    from custom_components.ramses_extras.framework.helpers.entity.manager import (
        EntityManager,
    )

    manager = EntityManager(mock_hass)

    # Set up some data
    manager.enable_feature_for_device("device1", "humidity_control")
    manager.enable_feature_for_device("device2", "humidity_control")
    manager.enable_feature_for_device("device1", "hvac_fan_card")

    # Get state
    state = manager.get_device_feature_matrix_state()
    assert state == {
        "device1": {"humidity_control": True, "hvac_fan_card": True},
        "device2": {"humidity_control": True},
    }

    # Create new manager and restore state
    new_manager = EntityManager(mock_hass)
    new_manager.restore_device_feature_matrix_state(state)

    # Verify state was restored
    assert new_manager.get_enabled_devices_for_feature("humidity_control") == [
        "device1",
        "device2",
    ]
    assert new_manager.get_enabled_devices_for_feature("hvac_fan_card") == ["device1"]
