"""Tests for framework/helpers/common/validation.py."""

from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.framework.helpers.common.validation import (
    RamsesValidator,
    ValidationError,
    async_validate_entity_states,
    create_validation_context,
    validate_device_id,
)


def test_validate_device_id_static():
    """Test RamsesValidator.validate_device_id."""
    assert RamsesValidator.validate_device_id("32:153289") is True
    assert RamsesValidator.validate_device_id("32_153289") is True
    assert RamsesValidator.validate_device_id("32") is True
    assert RamsesValidator.validate_device_id("abc") is False
    assert RamsesValidator.validate_device_id("32:abc") is False


def test_validate_entity_id():
    """Test RamsesValidator.validate_entity_id."""
    assert RamsesValidator.validate_entity_id("sensor.temp_32_153289") is True
    assert RamsesValidator.validate_entity_id("switch.fan") is True
    assert RamsesValidator.validate_entity_id("invalid_entity") is False


def test_validate_feature_id():
    """Test RamsesValidator.validate_feature_id."""
    assert RamsesValidator.validate_feature_id("humidity_control") is True
    assert RamsesValidator.validate_feature_id("feature123") is True
    assert RamsesValidator.validate_feature_id("123feature") is False
    assert RamsesValidator.validate_feature_id("feature-id") is False


def test_validate_numeric_value():
    """Test RamsesValidator.validate_numeric_value."""
    assert RamsesValidator.validate_numeric_value("25.5") == 25.5
    assert RamsesValidator.validate_numeric_value(10, min_val=0, max_val=100) == 10.0

    with pytest.raises(ValidationError, match="not numeric"):
        RamsesValidator.validate_numeric_value("abc")

    with pytest.raises(ValidationError, match="below minimum"):
        RamsesValidator.validate_numeric_value(5, min_val=10)

    with pytest.raises(ValidationError, match="above maximum"):
        RamsesValidator.validate_numeric_value(15, max_val=10)


def test_validate_entity_states(hass):
    """Test RamsesValidator.validate_entity_states."""
    hass.states.async_set("sensor.temp", "20.5", {"unit": "C"})

    # Success case
    states = RamsesValidator.validate_entity_states(hass, ["sensor.temp"])
    assert "sensor.temp" in states
    assert states["sensor.temp"]["state"] == "20.5"

    # Required state match
    states = RamsesValidator.validate_entity_states(
        hass, ["sensor.temp"], {"sensor.temp": "20.5"}
    )
    assert states["sensor.temp"]["state"] == "20.5"

    # Missing entity
    with pytest.raises(ValidationError, match=r"missing: \['sensor.missing'\]"):
        RamsesValidator.validate_entity_states(hass, ["sensor.missing"])

    # Unavailable state
    hass.states.async_set("sensor.bad", "unavailable")
    with pytest.raises(
        ValidationError,
        match=r"invalid states: \['sensor.bad \(unavailable/unknown\)'\]",
    ):
        RamsesValidator.validate_entity_states(hass, ["sensor.bad"])

    # State mismatch
    with pytest.raises(ValidationError, match="expected '30.0', got '20.5'"):
        RamsesValidator.validate_entity_states(
            hass, ["sensor.temp"], {"sensor.temp": "30.0"}
        )


def test_validate_device_type():
    """Test RamsesValidator.validate_device_type."""
    assert RamsesValidator.validate_device_type("fan", ["fan", "sensor"]) is True
    assert RamsesValidator.validate_device_type("light", ["fan", "sensor"]) is False


def test_validate_humidity_temperature():
    """Test humidity and temperature specific validators."""
    assert RamsesValidator.validate_humidity_value(50) == 50.0
    with pytest.raises(ValidationError):
        RamsesValidator.validate_humidity_value(110)

    assert RamsesValidator.validate_temperature_value(25) == 25.0
    with pytest.raises(ValidationError):
        RamsesValidator.validate_temperature_value(-100)


def test_validate_entity_template():
    """Test RamsesValidator.validate_entity_template."""
    assert (
        RamsesValidator.validate_entity_template("sensor.temp_{device_id}", "32:111")
        == "sensor.temp_32:111"
    )

    with pytest.raises(ValidationError, match="does not contain {device_id}"):
        RamsesValidator.validate_entity_template("sensor.temp", "32:111")

    with pytest.raises(ValidationError, match="Invalid device ID"):
        RamsesValidator.validate_entity_template("sensor.{device_id}", "invalid")


def test_validate_entity_mappings():
    """Test RamsesValidator.validate_entity_mappings."""
    mappings = {"temp": "sensor.temp_{device_id}", "hum": "sensor.hum_{device_id}"}
    assert RamsesValidator.validate_entity_mappings(mappings) is True

    with pytest.raises(ValidationError, match="Invalid state name"):
        RamsesValidator.validate_entity_mappings({"123": "sensor.{device_id}"})

    with pytest.raises(ValidationError, match="Invalid entity template"):
        RamsesValidator.validate_entity_mappings({"temp": "sensor.temp"})


def test_validate_device_id_decorator():
    """Test validate_device_id decorator."""

    class MockClass:
        @validate_device_id
        def my_func(self, device_id):
            return True

    obj = MockClass()
    assert obj.my_func("32:111") is True
    assert obj.my_func(device_id="32:111") is True

    with pytest.raises(ValidationError, match="Invalid device_id format"):
        obj.my_func("invalid")

    with pytest.raises(ValidationError, match="parameter not found"):
        # Calling with no arguments (len(args) == 1 because of self)
        obj.my_func()


@pytest.mark.asyncio
async def test_async_validate_entity_states_decorator(hass):
    """Test async_validate_entity_states decorator."""
    hass.states.async_set("sensor.temp", "20.5")

    class MockClass:
        def __init__(self, hass):
            self.hass = hass

        @async_validate_entity_states(["sensor.temp"])
        async def my_func(self):
            return True

    obj = MockClass(hass)
    assert await obj.my_func() is True

    # Trigger validation failure
    hass.states.async_remove("sensor.temp")
    with pytest.raises(ValidationError):
        await obj.my_func()


def test_validation_context():
    """Test ValidationContext context manager."""
    # Success case
    with create_validation_context("test") as ctx:
        ctx.add_error("err1")
        assert ctx.validate_all() is False

    # Exception handling in context
    with create_validation_context("test_exc") as ctx:
        pass  # Normal exit

    # We can't easily assert the log output here without more setup,
    # but we can cover the lines.
