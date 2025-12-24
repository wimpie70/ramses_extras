# tests/framework/helpers/service/test_validation.py
"""Test service validation framework."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID

from custom_components.ramses_extras.framework.helpers.service.validation import (
    ServiceValidator,
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
    validate_service_call,
)


class TestValidationEnums:
    """Test validation enums."""

    def test_validation_severity_values(self):
        """Test ValidationSeverity enum values."""
        assert ValidationSeverity.INFO.value == "info"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.CRITICAL.value == "critical"

    def test_validation_category_values(self):
        """Test ValidationCategory enum values."""
        assert ValidationCategory.PARAMETER.value == "parameter"
        assert ValidationCategory.DEVICE.value == "device"
        assert ValidationCategory.ENTITY.value == "entity"
        assert ValidationCategory.PERMISSION.value == "permission"
        assert ValidationCategory.CAPABILITY.value == "capability"
        assert ValidationCategory.TIMING.value == "timing"


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_validation_result_creation_minimal(self):
        """Test creating ValidationResult with minimal parameters."""
        result = ValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            category=ValidationCategory.PARAMETER,
            message="Test message",
        )

        assert result.is_valid is True
        assert result.severity == ValidationSeverity.INFO
        assert result.category == ValidationCategory.PARAMETER
        assert result.message == "Test message"
        assert isinstance(result.details, dict)
        assert result.details == {}
        assert isinstance(result.timestamp, datetime)

    def test_validation_result_creation_full(self):
        """Test creating ValidationResult with all parameters."""
        test_timestamp = datetime(2023, 1, 1, 12, 0, 0)
        test_details = {"key": "value"}

        result = ValidationResult(
            is_valid=False,
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.DEVICE,
            message="Error message",
            details=test_details,
            timestamp=test_timestamp,
        )

        assert result.is_valid is False
        assert result.severity == ValidationSeverity.ERROR
        assert result.category == ValidationCategory.DEVICE
        assert result.message == "Error message"
        assert result.details == test_details
        assert result.timestamp == test_timestamp

    def test_validation_result_default_timestamp(self):
        """Test that ValidationResult gets current timestamp by default."""
        before = datetime.now()
        result = ValidationResult(
            is_valid=True,
            severity=ValidationSeverity.INFO,
            category=ValidationCategory.PARAMETER,
            message="Test",
        )
        after = datetime.now()

        assert before <= result.timestamp <= after


class TestServiceValidator:
    """Test ServiceValidator class."""

    def test_init(self, hass):
        """Test ServiceValidator initialization."""
        validator = ServiceValidator(hass)

        assert validator.hass == hass
        assert validator._validation_cache == {}
        assert validator._parameter_schemas == {}
        assert validator._device_patterns == {}
        assert validator._entity_patterns == {}

    def test_register_parameter_schema(self, hass):
        """Test registering parameter schema."""
        validator = ServiceValidator(hass)

        schema = {"type": "object", "properties": {"param1": {"type": "string"}}}
        validator.register_parameter_schema("test_service", schema)

        assert validator._parameter_schemas["test_service"] == schema

    def test_register_device_pattern_valid(self, hass):
        """Test registering valid device pattern."""
        validator = ServiceValidator(hass)

        pattern = r"^\d+:\d+$"
        validator.register_device_pattern("test_feature", pattern)

        assert "test_feature" in validator._device_patterns
        assert validator._device_patterns["test_feature"].pattern == pattern

    def test_register_device_pattern_invalid(self, hass, caplog):
        """Test registering invalid device pattern."""
        validator = ServiceValidator(hass)

        invalid_pattern = r"[invalid regex"
        validator.register_device_pattern("test_feature", invalid_pattern)

        # Should log error and not register pattern
        assert "test_feature" not in validator._device_patterns
        assert "Invalid device pattern" in caplog.text

    def test_register_entity_pattern_valid(self, hass):
        """Test registering valid entity pattern."""
        validator = ServiceValidator(hass)

        pattern = r"^sensor\..+$"
        validator.register_entity_pattern("sensor", pattern)

        assert "sensor" in validator._entity_patterns
        assert validator._entity_patterns["sensor"].pattern == pattern

    def test_register_entity_pattern_invalid(self, hass, caplog):
        """Test registering invalid entity pattern."""
        validator = ServiceValidator(hass)

        invalid_pattern = r"[invalid regex"
        validator.register_entity_pattern("sensor", invalid_pattern)

        # Should log error and not register pattern
        assert "sensor" not in validator._entity_patterns
        assert "Invalid entity pattern" in caplog.text

    def test_validate_service_call_basic(self, hass):
        """Test validating service call with basic parameters."""
        validator = ServiceValidator(hass)

        service_call = MagicMock()
        service_call.data = {"param1": "value1"}

        # Mock validation methods to return empty results (valid)
        with (
            pytest.mock.patch.object(validator, "_validate_parameters") as mock_params,
            pytest.mock.patch.object(validator, "_validate_device") as mock_device,
            pytest.mock.patch.object(validator, "_validate_entity") as mock_entity,
            pytest.mock.patch.object(validator, "_validate_timing") as mock_timing,
        ):  # noqa: E501
            mock_params.return_value = []
            mock_device.return_value = []
            mock_entity.return_value = []
            mock_timing.return_value = []

            results = validator.validate_service_call(service_call, "test_service")

            assert results == []
            mock_params.assert_called_once_with(service_call, "test_service")
            mock_device.assert_not_called()  # No device_id in data
            mock_entity.assert_not_called()  # No entity_id in data
            mock_timing.assert_called_once_with(service_call, "test_service")

    def test_validate_service_call_with_device_and_entity(self, hass):
        """Test validating service call with device and entity."""
        validator = ServiceValidator(hass)

        service_call = MagicMock()
        service_call.data = {
            ATTR_DEVICE_ID: "32:153289",
            ATTR_ENTITY_ID: "sensor.temperature",
            "param1": "value1",
        }

        # Mock validation methods
        with (
            pytest.mock.patch.object(validator, "_validate_parameters") as mock_params,
            pytest.mock.patch.object(validator, "_validate_device") as mock_device,
            pytest.mock.patch.object(validator, "_validate_entity") as mock_entity,
            pytest.mock.patch.object(validator, "_validate_timing") as mock_timing,
        ):  # noqa: E501
            mock_params.return_value = [
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.PARAMETER,
                    message="Param OK",
                )
            ]
            mock_device.return_value = [
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.DEVICE,
                    message="Device OK",
                )
            ]
            mock_entity.return_value = [
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.ENTITY,
                    message="Entity OK",
                )
            ]
            mock_timing.return_value = [
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.TIMING,
                    message="Timing OK",
                )
            ]

            results = validator.validate_service_call(
                service_call, "test_service", "test_feature"
            )

            assert len(results) == 4
            assert all(result.is_valid for result in results)

            # Verify all validation methods were called
            mock_params.assert_called_once_with(service_call, "test_service")
            mock_device.assert_called_once_with("32:153289", "test_feature")
            mock_entity.assert_called_once_with("sensor.temperature")
            mock_timing.assert_called_once_with(service_call, "test_service")

    def test_validate_service_call_caching(self, hass):
        """Test that validation results are cached."""
        validator = ServiceValidator(hass)

        service_call = MagicMock()
        service_call.data = {ATTR_DEVICE_ID: "32:153289"}

        # Mock validation methods
        with (
            pytest.mock.patch.object(validator, "_validate_parameters") as mock_params,
            pytest.mock.patch.object(validator, "_validate_device") as mock_device,
            pytest.mock.patch.object(validator, "_validate_timing") as mock_timing,
        ):  # noqa: E501
            mock_params.return_value = [
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.INFO,
                    category=ValidationCategory.PARAMETER,
                    message="Cached result",
                )
            ]
            mock_device.return_value = []
            mock_timing.return_value = []

            # First call
            results1 = validator.validate_service_call(service_call, "test_service")
            assert len(results1) == 1

            # Second call should use cache
            results2 = validator.validate_service_call(service_call, "test_service")
            assert results2 == results1

            # Validation methods should only be called once due to caching
            mock_params.assert_called_once()
            mock_device.assert_called_once()
            mock_timing.assert_called_once()

    def test_validate_parameters_no_schema(self, hass):
        """Test parameter validation when no schema is registered."""
        validator = ServiceValidator(hass)

        service_call = MagicMock()
        service_call.data = {"param1": "value1"}

        results = validator._validate_parameters(service_call, "test_service")

        assert results == []

    def test_validate_parameters_with_schema_valid(self, hass):
        """Test parameter validation with valid parameters."""
        validator = ServiceValidator(hass)

        # Register schema
        schema = {
            "required": ["param1"],
            "properties": {"param1": {"type": "string"}, "param2": {"type": "number"}},
        }
        validator.register_parameter_schema("test_service", schema)

        service_call = MagicMock()
        service_call.data = {"param1": "value1", "param2": 42}

        results = validator._validate_parameters(service_call, "test_service")

        # Should have no validation errors
        assert len([r for r in results if not r.is_valid]) == 0

    def test_validate_parameters_missing_required(self, hass):
        """Test parameter validation with missing required parameter."""
        validator = ServiceValidator(hass)

        # Register schema with required parameter
        schema = {"required": ["param1"], "properties": {"param1": {"type": "string"}}}
        validator.register_parameter_schema("test_service", schema)

        service_call = MagicMock()
        service_call.data = {"param2": "value2"}  # Missing param1

        results = validator._validate_parameters(service_call, "test_service")

        # Should have validation error
        errors = [r for r in results if not r.is_valid]
        assert len(errors) == 1
        assert "Required parameter 'param1' missing" in errors[0].message
        assert errors[0].category == ValidationCategory.PARAMETER
        assert errors[0].severity == ValidationSeverity.ERROR
