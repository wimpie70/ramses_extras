"""Command framework for Ramses Extras.

This module provides centralized command management with feature ownership,
device-type organization, and conflict resolution.
"""

from .registry import CommandRegistry

__all__ = ["CommandRegistry"]
