"""Tests for CO2 Control config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.co2_control.config_flow import (
    _get_section_defaults,
    _persist_co2_control_settings,
    _sync_settings_to_number_entities,
    async_step_co2_control_config,
    async_validate_co2_config,
    get_co2_control_schema,
    get_zone_config_schema,
)


@pytest.fixture
def hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.states.get.return_value = MagicMock()
    return hass


def test_get_co2_control_schema(hass):
    """Test CO2 control schema generation."""
    schema = get_co2_control_schema(hass, "test_device")

    # Test default values
    assert schema({})["enabled"] is False
    assert schema({})["automation_enabled"] is False
    assert schema({})["default_threshold"] == 1000
    assert schema({})["activation_hysteresis"] == 100
    assert schema({})["deactivation_hysteresis"] == -100

    # Test custom values
    data = {
        "enabled": True,
        "automation_enabled": True,
        "default_threshold": 1200,
        "activation_hysteresis": 150,
        "deactivation_hysteresis": -150,
    }
    result = schema(data)
    assert result["enabled"] is True
    assert result["automation_enabled"] is True
    assert result["default_threshold"] == 1200
    assert result["activation_hysteresis"] == 150
    assert result["deactivation_hysteresis"] == -150


def test_get_co2_control_schema_validation(hass):
    """Test CO2 control schema validation."""
    schema = get_co2_control_schema(hass, "test_device")

    # Test threshold validation
    with pytest.raises(vol.Invalid):
        schema({"default_threshold": 300})  # Below min

    with pytest.raises(vol.Invalid):
        schema({"default_threshold": 2500})  # Above max

    # Test activation hysteresis validation
    with pytest.raises(vol.Invalid):
        schema({"activation_hysteresis": -10})  # Negative not allowed

    # Test deactivation hysteresis validation
    with pytest.raises(vol.Invalid):
        schema({"deactivation_hysteresis": 10})  # Positive not allowed


def test_get_zone_config_schema(hass):
    """Test zone configuration schema."""
    schema = get_zone_config_schema(hass)

    # Test required fields
    data = {
        "zone_id": "test_zone",
        "zone_name": "Test Zone",
        "sensor_entity": "sensor.test_co2",
    }
    result = schema(data)
    assert result["zone_id"] == "test_zone"
    assert result["zone_name"] == "Test Zone"
    assert result["sensor_entity"] == "sensor.test_co2"
    assert result["threshold"] == 1000  # Default
    assert result["enabled"] is True  # Default

    # Test with optional fields
    data = {
        "zone_id": "test_zone",
        "zone_name": "Test Zone",
        "sensor_entity": "sensor.test_co2",
        "threshold": 1200,
        "enabled": False,
    }
    result = schema(data)
    assert result["threshold"] == 1200
    assert result["enabled"] is False


def test_get_zone_config_schema_validation(hass):
    """Test zone configuration schema validation."""
    schema = get_zone_config_schema(hass)

    # Test threshold validation
    with pytest.raises(vol.Invalid):
        schema(
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.test_co2",
                "threshold": 300,  # Below min
            }
        )

    with pytest.raises(vol.Invalid):
        schema(
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.test_co2",
                "threshold": 2500,  # Above max
            }
        )


@pytest.mark.asyncio
async def test_async_validate_co2_config_valid(hass):
    """Test validation of valid CO2 config."""
    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
        "zones": [],
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors == {}


@pytest.mark.asyncio
async def test_async_validate_co2_config_threshold_out_of_range(hass):
    """Test validation with threshold out of range."""
    config = {
        "default_threshold": 300,  # Below min
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["default_threshold"] == "threshold_out_of_range"


@pytest.mark.asyncio
async def test_async_validate_co2_config_activation_hysteresis_negative(hass):
    """Test validation with negative activation hysteresis."""
    config = {
        "default_threshold": 1000,
        "activation_hysteresis": -10,  # Should be positive
        "deactivation_hysteresis": -100,
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["activation_hysteresis"] == "must_be_positive"


@pytest.mark.asyncio
async def test_async_validate_co2_config_deactivation_hysteresis_positive(hass):
    """Test validation with positive deactivation hysteresis."""
    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": 10,  # Should be negative
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["deactivation_hysteresis"] == "must_be_negative"


@pytest.mark.asyncio
async def test_async_validate_co2_config_zone_entity_not_found(hass):
    """Test validation with zone entity not found."""
    hass.states.get.return_value = None  # Entity not found

    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
        "zones": [
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.nonexistent",
            }
        ],
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors["zone_0_sensor"] == "entity_not_found"


@pytest.mark.asyncio
async def test_async_validate_co2_config_zone_entity_found(hass):
    """Test validation with zone entity found."""
    hass.states.get.return_value = MagicMock()  # Entity found

    config = {
        "default_threshold": 1000,
        "activation_hysteresis": 100,
        "deactivation_hysteresis": -100,
        "zones": [
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.existing",
            }
        ],
    }

    errors = await async_validate_co2_config(hass, config)
    assert errors == {}


@pytest.mark.asyncio
async def test_async_validate_co2_config_multiple_errors(hass):
    """Test validation with multiple errors."""
    hass.states.get.return_value = None  # Entity not found

    config = {
        "default_threshold": 300,  # Out of range
        "activation_hysteresis": -10,  # Negative
        "deactivation_hysteresis": 10,  # Positive
        "zones": [
            {
                "zone_id": "test_zone",
                "zone_name": "Test Zone",
                "sensor_entity": "sensor.nonexistent",
            }
        ],
    }

    errors = await async_validate_co2_config(hass, config)
    assert len(errors) == 4
    assert errors["default_threshold"] == "threshold_out_of_range"
    assert errors["activation_hysteresis"] == "must_be_positive"
    assert errors["deactivation_hysteresis"] == "must_be_negative"
    assert errors["zone_0_sensor"] == "entity_not_found"


@pytest.mark.asyncio
async def test_async_validate_co2_config_empty_config(hass):
    """Test validation with empty config."""
    errors = await async_validate_co2_config(hass, {})
    assert errors == {}  # Empty config should be valid


class TestGetSectionDefaults:
    """Tests for _get_section_defaults."""

    def test_with_existing_config(self):
        """Test reading defaults from existing config."""
        flow = MagicMock()
        flow._config_entry.options = {
            "co2_control": {
                "default_threshold": 800,
                "activation_hysteresis": 50,
                "deactivation_hysteresis": -50,
                "priority_over_humidity": False,
                "max_runtime_minutes": 60,
                "cooldown_period_minutes": 10,
            }
        }
        flow._config_entry.data = {}

        defaults = _get_section_defaults(flow)

        assert defaults["default_threshold"] == 800
        assert defaults["activation_hysteresis"] == 50
        assert defaults["deactivation_hysteresis"] == -50
        assert defaults["priority_over_humidity"] is False
        assert defaults["max_runtime_minutes"] == 60
        assert defaults["cooldown_period_minutes"] == 10

    def test_with_defaults(self):
        """Test defaults when config is empty."""
        flow = MagicMock()
        flow._config_entry.options = {}
        flow._config_entry.data = {}

        defaults = _get_section_defaults(flow)

        assert defaults["default_threshold"] == 1000
        assert defaults["activation_hysteresis"] == 100
        assert defaults["deactivation_hysteresis"] == -100
        assert defaults["priority_over_humidity"] is True
        assert defaults["max_runtime_minutes"] == 120
        assert defaults["cooldown_period_minutes"] == 15

    def test_with_canonical_config(self):
        """Test reading from canonical (ramses_extras.features) config."""
        flow = MagicMock()
        flow._config_entry.options = {
            "ramses_extras": {
                "features": {
                    "co2_control": {
                        "default_threshold": 600,
                        "activation_hysteresis": 25,
                        "deactivation_hysteresis": -100,
                        "priority_over_humidity": True,
                        "max_runtime_minutes": 120,
                        "cooldown_period_minutes": 15,
                    }
                }
            }
        }
        flow._config_entry.data = {}

        defaults = _get_section_defaults(flow)

        assert defaults["default_threshold"] == 600
        assert defaults["activation_hysteresis"] == 25


class TestPersistCo2ControlSettings:
    """Tests for _persist_co2_control_settings."""

    def test_persist_to_legacy_and_canonical(self):
        """Test settings are persisted to both legacy and canonical stores."""
        flow = MagicMock()
        flow._config_entry.options = {}
        flow._config_entry.data = {}
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.data = {}

        settings = {
            "default_threshold": 800,
            "activation_hysteresis": 50,
            "deactivation_hysteresis": -50,
            "priority_over_humidity": True,
            "max_runtime_minutes": 60,
            "cooldown_period_minutes": 10,
        }

        with patch(
            "custom_components.ramses_extras.features.co2_control.config_flow._sync_settings_to_number_entities"
        ):
            _persist_co2_control_settings(flow, settings)

        # Verify async_update_entry was called
        flow.hass.config_entries.async_update_entry.assert_called_once()
        call_args = flow.hass.config_entries.async_update_entry.call_args
        options = call_args.kwargs.get("options") or call_args[1].get("options")

        # Check legacy store
        assert options["co2_control"]["default_threshold"] == 800
        # Check canonical store
        assert (
            options["ramses_extras"]["features"]["co2_control"]["default_threshold"]
            == 800
        )

    def test_persist_preserves_existing_options(self):
        """Test that persisting preserves other existing options."""
        flow = MagicMock()
        flow._config_entry.options = {
            "other_feature": {"some_key": "some_value"},
            "co2_control": {"existing_key": "existing_value"},
        }
        flow._config_entry.data = {}
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.data = {}

        settings = {"default_threshold": 900}

        with patch(
            "custom_components.ramses_extras.features.co2_control.config_flow._sync_settings_to_number_entities"
        ):
            _persist_co2_control_settings(flow, settings)

        call_args = flow.hass.config_entries.async_update_entry.call_args
        options = call_args.kwargs.get("options") or call_args[1].get("options")

        # Other feature should be preserved
        assert options["other_feature"]["some_key"] == "some_value"
        # Existing co2_control key should be preserved
        assert options["co2_control"]["existing_key"] == "existing_value"
        # New setting should be added
        assert options["co2_control"]["default_threshold"] == 900

    def test_persist_calls_refresh_config_entry(self):
        """Test that _refresh_config_entry is called if available."""
        flow = MagicMock()
        flow._config_entry.options = {}
        flow._config_entry.data = {}
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.data = {}
        flow._refresh_config_entry = MagicMock()

        with patch(
            "custom_components.ramses_extras.features.co2_control.config_flow._sync_settings_to_number_entities"
        ):
            _persist_co2_control_settings(flow, {"default_threshold": 800})

        flow._refresh_config_entry.assert_called_once()


class TestSyncSettingsToNumberEntities:
    """Tests for _sync_settings_to_number_entities."""

    def test_no_entities(self):
        """Test sync when no entities exist."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}

        _sync_settings_to_number_entities(hass, {"default_threshold": 800})
        # Should not raise

    def test_no_domain_data(self):
        """Test sync when DOMAIN data doesn't exist."""
        hass = MagicMock()
        hass.data = {}

        _sync_settings_to_number_entities(hass, {"default_threshold": 800})
        # Should not raise

    def test_with_matching_entity(self):
        """Test sync updates matching entities."""
        hass = MagicMock()
        mock_entity = MagicMock()
        mock_entity.async_set_native_value = AsyncMock()

        hass.data = {
            "ramses_extras": {
                "entities": {
                    "number.co2_threshold_32_153289": mock_entity,
                }
            }
        }
        hass.loop = MagicMock()
        hass.async_create_task = MagicMock()

        _sync_settings_to_number_entities(hass, {"default_threshold": 800})

        # call_soon_threadsafe should have been called
        hass.loop.call_soon_threadsafe.assert_called_once()

    def test_with_non_matching_entity(self):
        """Test sync skips non-matching entities."""
        hass = MagicMock()
        mock_entity = MagicMock()

        hass.data = {
            "ramses_extras": {
                "entities": {
                    "number.other_entity_32_153289": mock_entity,
                }
            }
        }

        _sync_settings_to_number_entities(hass, {"default_threshold": 800})

        # Should not have called anything on the entity
        mock_entity.async_set_native_value.assert_not_called()

    def test_unknown_setting_key_skipped(self):
        """Test that unknown setting keys are skipped."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {"entities": {}}}

        _sync_settings_to_number_entities(hass, {"unknown_key": 800})
        # Should not raise


class TestAsyncStepCo2ControlConfig:
    """Tests for async_step_co2_control_config."""

    @pytest.mark.asyncio
    async def test_show_form_when_no_user_input(self):
        """Test that the form is shown when no user_input is provided."""
        flow = MagicMock()
        flow._config_entry.options = {}
        flow._config_entry.data = {}
        flow._refresh_config_entry = MagicMock()
        flow._get_config_flow_helper.return_value = MagicMock()
        flow._get_persisted_matrix_state.return_value = {}
        flow._get_all_devices.return_value = []
        flow._get_device_label.return_value = "Test Device"
        flow._extract_device_id.return_value = "32:153289"
        flow._show_matrix_based_confirmation = AsyncMock()
        flow.async_show_form = MagicMock(return_value={"type": "form"})

        result = await async_step_co2_control_config(flow, None)

        flow.async_show_form.assert_called_once()
        assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_submit_with_user_input(self):
        """Test submitting the form with user input."""
        flow = MagicMock()
        flow._config_entry.options = {}
        flow._config_entry.data = {}
        flow._refresh_config_entry = MagicMock()
        flow._get_config_flow_helper.return_value = MagicMock()
        flow._get_persisted_matrix_state.return_value = {}
        flow._get_all_devices.return_value = []
        flow._get_device_label.return_value = "Test Device"
        flow._extract_device_id.return_value = "32:153289"
        flow._show_matrix_based_confirmation = AsyncMock(
            return_value={"type": "create_entry"}
        )
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.data = {}

        user_input = {
            "enabled_devices": ["32:153289"],
            "default_threshold": 800,
            "activation_hysteresis": 50,
            "deactivation_hysteresis": -50,
            "priority_over_humidity": True,
            "max_runtime_minutes": 60,
            "cooldown_period_minutes": 10,
        }

        with patch(
            "custom_components.ramses_extras.features.co2_control.config_flow._sync_settings_to_number_entities"
        ):
            result = await async_step_co2_control_config(flow, user_input)

        flow._show_matrix_based_confirmation.assert_called_once()
        assert result["type"] == "create_entry"

    @pytest.mark.asyncio
    async def test_submit_with_defaults_for_optional_fields(self):
        """Test submitting with defaults for optional fields."""
        flow = MagicMock()
        flow._config_entry.options = {}
        flow._config_entry.data = {}
        flow._refresh_config_entry = MagicMock()
        flow._get_config_flow_helper.return_value = MagicMock()
        flow._get_persisted_matrix_state.return_value = {}
        flow._get_all_devices.return_value = []
        flow._get_device_label.return_value = "Test Device"
        flow._extract_device_id.return_value = "32:153289"
        flow._show_matrix_based_confirmation = AsyncMock(
            return_value={"type": "create_entry"}
        )
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.data = {}

        user_input = {
            "enabled_devices": [],
            "default_threshold": 1000,
            "activation_hysteresis": 100,
            "deactivation_hysteresis": -100,
            # priority_over_humidity, max_runtime_minutes, cooldown_period_minutes
            # are omitted to test defaults
        }

        with patch(
            "custom_components.ramses_extras.features.co2_control.config_flow._sync_settings_to_number_entities"
        ):
            await async_step_co2_control_config(flow, user_input)

        flow._show_matrix_based_confirmation.assert_called_once()
