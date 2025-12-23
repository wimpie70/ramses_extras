# tests/helpers/service/test_init.py
"""Test service framework imports."""

import pytest

from custom_components.ramses_extras.framework.helpers.service import (
    ExtrasServiceManager,
    ServiceDefinition,
    ServiceExecutionContext,
    ServiceRegistrationManager,
    ServiceRegistry,
    ServiceValidator,
    ValidationResult,
    validate_service_call,
)


class TestServiceImports:
    """Test that all service framework imports are available."""

    def test_core_imports(self):
        """Test that core service classes can be imported."""
        # These should be importable without errors
        assert ExtrasServiceManager is not None
        assert ServiceExecutionContext is not None

    def test_registration_imports(self):
        """Test that registration classes can be imported."""
        assert ServiceDefinition is not None
        assert ServiceRegistrationManager is not None
        assert ServiceRegistry is not None

    def test_validation_imports(self):
        """Test that validation classes can be imported."""
        assert ServiceValidator is not None
        assert ValidationResult is not None
        assert validate_service_call is not None

    def test_all_exports(self):
        """Test that __all__ exports are properly defined."""
        # This test ensures the __all__ list in __init__.py matches the imports
        expected_exports = {
            "ExtrasServiceManager",
            "ServiceExecutionContext",
            "ServiceRegistry",
            "ServiceRegistrationManager",
            "ServiceDefinition",
            "ServiceValidator",
            "ValidationResult",
            "validate_service_call",
        }

        # Import the module and check __all__
        from custom_components.ramses_extras.framework.helpers import service

        assert hasattr(service, "__all__")
        assert set(service.__all__) == expected_exports
