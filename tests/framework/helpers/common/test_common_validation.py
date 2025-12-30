"""Tests for Common Validation Helper."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import State

from custom_components.ramses_extras.framework.helpers.common.validation import (
    RamsesValidator,
    ValidationContext,
    ValidationError,
    async_validate_entity_states,
    create_validation_context,
    validate_device_id,
)


@pytest.fixture
def hass():
    """Mock Home Assistant."""
    return MagicMock()


class TestRamsesValidator:
    """Test RamsesValidator class."""

    def test_validate_device_id(self):
        """Test device ID validation."""
        assert RamsesValidator.validate_device_id("32:153289") is True
        assert RamsesValidator.validate_device_id("32_153289") is True
        assert RamsesValidator.validate_device_id("32") is True
        assert RamsesValidator.validate_device_id("abc") is False
        assert RamsesValidator.validate_device_id("") is False

    def test_validate_entity_id(self):
        """Test entity ID validation."""
        assert RamsesValidator.validate_entity_id("sensor.temp_32_153289") is True
        assert RamsesValidator.validate_entity_id("switch.fan") is True
        assert RamsesValidator.validate_entity_id("invalid_id") is False

    def test_validate_feature_id(self):
        """Test feature ID validation."""
        assert RamsesValidator.validate_feature_id("hello_world") is True
        assert RamsesValidator.validate_feature_id("feature1") is True
        assert RamsesValidator.validate_feature_id("1feature") is False
        assert RamsesValidator.validate_feature_id("hello-world") is False

    def test_validate_numeric_value(self):
        """Test numeric value validation."""
        assert RamsesValidator.validate_numeric_value(10) == 10.0
        assert RamsesValidator.validate_numeric_value("10.5") == 10.5

        with pytest.raises(ValidationError, match="not numeric"):
            RamsesValidator.validate_numeric_value("abc")

        assert RamsesValidator.validate_numeric_value(10, min_val=5, max_val=15) == 10.0

        with pytest.raises(ValidationError, match="below minimum"):
            RamsesValidator.validate_numeric_value(4, min_val=5)

        with pytest.raises(ValidationError, match="above maximum"):
            RamsesValidator.validate_numeric_value(16, max_val=15)

    def test_validate_entity_states(self, hass):
        """Test entity states validation."""
        mock_state = MagicMock(spec=State)
        mock_state.state = "on"
        mock_state.attributes = {"attr": "val"}
        mock_state.last_changed = MagicMock()
        mock_state.last_updated = MagicMock()

        hass.states.get.return_value = mock_state

        # 1. Success
        result = RamsesValidator.validate_entity_states(hass, ["switch.test"])
        assert "switch.test" in result
        assert result["switch.test"]["state"] == "on"

        # 2. Missing
        hass.states.get.return_value = None
        with pytest.raises(ValidationError, match="missing"):
            RamsesValidator.validate_entity_states(hass, ["switch.test"])

        # 3. Invalid state
        mock_state.state = "unavailable"
        hass.states.get.return_value = mock_state
        with pytest.raises(ValidationError, match="invalid states"):
            RamsesValidator.validate_entity_states(hass, ["switch.test"])

        # 4. Required state mismatch
        mock_state.state = "off"
        hass.states.get.return_value = mock_state
        with pytest.raises(ValidationError, match="expected 'on'"):
            RamsesValidator.validate_entity_states(
                hass, ["switch.test"], required_states={"switch.test": "on"}
            )

    def test_validate_device_type(self):
        """Test device type validation."""
        assert RamsesValidator.validate_device_type("FAN", ["FAN", "CO2"]) is True
        assert RamsesValidator.validate_device_type("HUM", ["FAN", "CO2"]) is False

    def test_validate_humidity_value(self):
        """Test humidity value validation."""
        assert RamsesValidator.validate_humidity_value(50) == 50.0
        with pytest.raises(ValidationError, match="above maximum"):
            RamsesValidator.validate_humidity_value(101)

    def test_validate_temperature_value(self):
        """Test temperature value validation."""
        assert RamsesValidator.validate_temperature_value(20) == 20.0
        with pytest.raises(ValidationError, match="below minimum"):
            RamsesValidator.validate_temperature_value(-60)

    def test_validate_entity_template(self):
        """Test entity template validation."""
        assert (
            RamsesValidator.validate_entity_template("sensor.temp_{device_id}", "32:1")
            == "sensor.temp_32:1"
        )

        with pytest.raises(ValidationError, match="does not contain {device_id}"):
            RamsesValidator.validate_entity_template("sensor.temp", "32:1")

        with pytest.raises(ValidationError, match="Invalid device ID"):
            RamsesValidator.validate_entity_template("sensor.temp_{device_id}", "abc")

    def test_validate_entity_mappings(self):
        """Test entity mappings validation."""
        mappings = {"temp": "sensor.temp_{device_id}", "hum": "sensor.hum_{device_id}"}
        assert RamsesValidator.validate_entity_mappings(mappings) is True

        with pytest.raises(ValidationError, match="Invalid state name"):
            RamsesValidator.validate_entity_mappings({"1temp": "t"})

        with pytest.raises(ValidationError, match="Invalid entity template"):
            RamsesValidator.validate_entity_mappings({"temp": "sensor.temp"})


class TestValidationDecorators:
    """Test validation decorators."""

    def test_validate_device_id_decorator(self):
        """Test validate_device_id decorator."""

        class TestClass:
            @validate_device_id
            def my_func(self, device_id):
                return True

        obj = TestClass()
        assert obj.my_func("32:1") is True

        with pytest.raises(ValidationError, match="Invalid device_id format"):
            obj.my_func("abc")

        # Test with kwargs
        @validate_device_id
        def my_func_kwargs(self, **kwargs):
            return True

        assert my_func_kwargs(obj, device_id="32:1") is True

    @pytest.mark.asyncio
    async def test_async_validate_entity_states_decorator(self, hass):
        """Test async_validate_entity_states decorator."""

        class TestClass:
            def __init__(self, hass):
                self.hass = hass

            @async_validate_entity_states(["sensor.test"])
            async def my_func(self):
                return True

        obj = TestClass(hass)

        # Mock success
        mock_state = MagicMock(spec=State)
        mock_state.state = "on"
        hass.states.get.return_value = mock_state

        assert await obj.my_func() is True

        # Mock failure
        hass.states.get.return_value = None
        with pytest.raises(ValidationError):
            await obj.my_func()


class TestValidationContext:
    """Test ValidationContext class."""

    def test_validation_context_success(self):
        """Test successful validation context."""
        with create_validation_context("test") as ctx:
            ctx.add_error("err1")
            assert ctx.validate_all() is False

        with create_validation_context("test") as ctx:
            assert ctx.validate_all() is True

    def test_validation_context_exception(self):
        """Test validation context with exception."""
        # ValidationError handled in __exit__
        with pytest.raises(ValidationError):
            with create_validation_context("test"):
                raise ValidationError("handled")

        # Other exception handled in __exit__
        with pytest.raises(Exception, match="unexpected"):
            with create_validation_context("test"):
                raise Exception("unexpected")
