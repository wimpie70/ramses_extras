# tests/framework/base_classes/test_init.py
"""Test base_classes __init__.py imports."""

import pytest

from custom_components.ramses_extras.framework.base_classes import (
    ExtrasBaseAutomation,
    ExtrasBaseEntity,
)


class TestBaseClassesImports:
    """Test that base classes can be imported correctly."""

    def test_extras_base_entity_import(self):
        """Test that ExtrasBaseEntity can be imported."""
        # The class should be importable without errors
        assert ExtrasBaseEntity is not None
        assert hasattr(ExtrasBaseEntity, "__init__")

    def test_extras_base_automation_import(self):
        """Test that ExtrasBaseAutomation can be imported."""
        # The class should be importable without errors
        assert ExtrasBaseAutomation is not None
        assert hasattr(ExtrasBaseAutomation, "__init__")

    def test_all_exports(self):
        """Test that __all__ exports are properly defined."""
        from custom_components.ramses_extras.framework.base_classes import __all__

        expected_exports = {"ExtrasBaseEntity", "ExtrasBaseAutomation"}
        assert set(__all__) == expected_exports
