"""Consistency checks for declared vs. implemented WebSocket commands.

Each feature declares commands in ``FEATURE_DEFINITION["websocket_commands"]``
(a name -> command-type dict that populates the registry) *and* implements
handlers in ``features/<name>/websocket_commands.py`` (functions tagged by
``@websocket_api.websocket_command`` with ``_ws_command`` = the type string).

These tests guard against the two registries drifting apart:

- declared command types with no implementing handler (dead registry entries),
- implemented handlers whose type is not declared (never registered),
- the same command type claimed by more than one feature.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import custom_components.ramses_extras.features as features_pkg

_FEATURES_BASE = f"{features_pkg.__name__}"


def _feature_names() -> list[str]:
    return sorted(
        info.name for info in pkgutil.iter_modules(features_pkg.__path__) if info.ispkg
    )


def _declared_commands() -> dict[str, dict[str, str]]:
    """Return {feature_name: {command_name: command_type}} declarations."""
    declared: dict[str, dict[str, str]] = {}
    for feature_name in _feature_names():
        module = importlib.import_module(f"{_FEATURES_BASE}.{feature_name}.const")
        feature_definition = getattr(module, "FEATURE_DEFINITION", None)
        if not isinstance(feature_definition, dict):
            continue
        commands = feature_definition.get("websocket_commands")
        if isinstance(commands, dict) and commands:
            declared[feature_name] = dict(commands)
    return declared


def _implemented_command_types(feature_name: str) -> dict[str, str]:
    """Return {command_type: handler_name} for a feature's ws module."""
    module = importlib.import_module(
        f"{_FEATURES_BASE}.{feature_name}.websocket_commands"
    )
    handlers: dict[str, str] = {}
    for attr_name in dir(module):
        handler = getattr(module, attr_name, None)
        command_type = getattr(handler, "_ws_command", None)
        if isinstance(command_type, str):
            handlers[command_type] = attr_name
    return handlers


_DECLARED = _declared_commands()


def test_no_duplicate_command_types_across_features() -> None:
    """No two features may claim the same WebSocket command type."""
    owners: dict[str, list[str]] = {}
    for feature_name, commands in _DECLARED.items():
        for command_type in commands.values():
            owners.setdefault(command_type, []).append(feature_name)

    duplicates = {
        command_type: features
        for command_type, features in owners.items()
        if len(features) > 1
    }
    assert not duplicates, f"command types claimed by multiple features: {duplicates}"


@pytest.mark.parametrize("feature_name", sorted(_DECLARED))
def test_declared_commands_have_handlers(feature_name: str) -> None:
    """Every declared command type must have a handler in the feature module."""
    implemented = _implemented_command_types(feature_name)
    missing = {
        name: command_type
        for name, command_type in _DECLARED[feature_name].items()
        if command_type not in implemented
    }
    assert not missing, f"{feature_name}: declared commands without handlers: {missing}"


@pytest.mark.parametrize("feature_name", sorted(_DECLARED))
def test_implemented_handlers_are_declared(feature_name: str) -> None:
    """Every decorated handler must be declared in the feature's registry dict."""
    declared_types = set(_DECLARED[feature_name].values())
    undeclared = {
        command_type: handler
        for command_type, handler in _implemented_command_types(feature_name).items()
        if command_type not in declared_types
    }
    assert not undeclared, (
        f"{feature_name}: handlers missing from websocket_commands registry: "
        f"{undeclared}"
    )
