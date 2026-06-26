"""Command Registry for Ramses Extras.

This module provides centralized command management with feature ownership,
device-type organization, and conflict resolution.
"""

import logging
from typing import Any, Optional

_LOGGER = logging.getLogger(__name__)


class CommandRegistry:
    """Centralized registry for device commands with
     feature ownership and conflict resolution.

    Commands are registered by features and organized by device type. Duplicate command
    names are resolved with first-registration-wins policy and developer warnings.
    """

    def __init__(self) -> None:
        """Initialize the command registry."""
        # commands: {command_name: {"definition": cmd_def, "feature_id": feature_id}}
        self._commands: dict[str, dict[str, Any]] = {}

        # device_commands: {device_type: {category: {cmd_name: cmd_def}}}
        self._device_commands: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    def register_commands(
        self, feature_id: str, commands: dict[str, dict[str, Any]]
    ) -> None:
        """Register feature commands with conflict detection.

        :param feature_id: ID of the feature registering commands
        :param commands: Dictionary of command definitions {command_name: command_def}

        Command definition format:
        {
            "code": "22F1",      # Ramses code
            "verb": " I",        # Command verb
            "payload": "000307", # Command payload
            "description": "Set fan to high speed"  # Optional description
        }
        """
        _LOGGER.debug(
            f"🔧 Registering {len(commands)} commands for feature '{feature_id}'"
        )
        for cmd_name, cmd_def in commands.items():
            if cmd_name in self._commands:
                existing_feature = self._commands[cmd_name]["feature_id"]
                if existing_feature == feature_id:
                    _LOGGER.debug(
                        "Command '%s' already registered by feature '%s', skipping",
                        cmd_name,
                        feature_id,
                    )
                    continue
                _LOGGER.warning(
                    f"Command '{cmd_name}' already registered by feature '"
                    f"{existing_feature}', "
                    f"ignoring registration from feature '{feature_id}'. "
                    f"Use a different command name to override behavior."
                )
                continue

            # Register the command
            self._commands[cmd_name] = {"definition": cmd_def, "feature_id": feature_id}

            _LOGGER.debug(
                f"Registered command '{cmd_name}' from feature '{feature_id}'"
            )

        _LOGGER.debug(
            f"✅ Successfully registered {len(commands)} commands for "
            f"feature '{feature_id}'"
        )

    def register_device_commands(
        self, device_type: str, category: str, commands: dict[str, dict[str, Any]]
    ) -> None:
        """Register device-type specific commands.

        :param device_type: Device type (e.g., "HvacVentilator")
        :param category: Command category (e.g., "fan_speeds", "bypass")
        :param commands: Dictionary of command definitions
        """
        if device_type not in self._device_commands:
            self._device_commands[device_type] = {}

        if category not in self._device_commands[device_type]:
            self._device_commands[device_type][category] = {}

        # Register each command with device type prefix for uniqueness
        prefixed_commands = {}
        for cmd_name, cmd_def in commands.items():
            prefixed_name = f"{device_type.lower()}_{category}_{cmd_name}"
            prefixed_commands[prefixed_name] = cmd_def

        self._device_commands[device_type][category] = commands
        _LOGGER.debug(
            f"Registered {len(commands)} commands for {device_type}.{category}"
        )

    def get_command(self, command_name: str) -> dict[str, Any] | None:
        """Get command definition by name.

        :param command_name: Name of the command
        :return: Command definition dictionary or None if not found
        """
        command_info = self._commands.get(command_name)
        return command_info["definition"] if command_info else None

    def get_device_commands(
        self, device_type: str, category: str
    ) -> dict[str, dict[str, Any]]:
        """Get commands for a specific device type and category.

        :param device_type: Device type (e.g., "HvacVentilator")
        :param category: Command category (e.g., "fan_speeds")
        :return: Dictionary of command definitions for the category
        """
        return self._device_commands.get(device_type, {}).get(category, {})

    def list_commands_by_feature(self, feature_id: str) -> list[str]:
        """List all command names registered by a specific feature.

        :param feature_id: Feature identifier
        :return: List of command names registered by the feature
        """
        return [
            cmd_name
            for cmd_name, cmd_info in self._commands.items()
            if cmd_info["feature_id"] == feature_id
        ]

    def get_registered_commands(self) -> dict[str, dict[str, Any]]:
        """Get all registered commands with metadata.

        :return: Dictionary of all registered commands with their metadata
        """
        return self._commands.copy()

    def get_device_types(self) -> list[str]:
        """Get list of all registered device types.

        :return: List of device type names
        """
        return list(self._device_commands.keys())

    def clear_feature_commands(self, feature_id: str) -> int:
        """Remove all commands registered by a specific feature.

        :param feature_id: Feature identifier
        :return: Number of commands removed
        """
        commands_to_remove = [
            cmd_name
            for cmd_name, cmd_info in self._commands.items()
            if cmd_info["feature_id"] == feature_id
        ]

        for cmd_name in commands_to_remove:
            del self._commands[cmd_name]

        removed_count = len(commands_to_remove)
        if removed_count > 0:
            _LOGGER.debug(
                f"Removed {removed_count} commands from feature '{feature_id}'"
            )

        return removed_count


# Global registry instance
_command_registry = None


def get_command_registry() -> CommandRegistry:
    """Get the global command registry instance."""
    global _command_registry
    if _command_registry is None:
        _command_registry = CommandRegistry()
    return _command_registry


__all__ = ["CommandRegistry", "get_command_registry"]
