"""WebSocket Base Classes and Utilities.

This module provides minimal WebSocket infrastructure for Ramses Extras features.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from homeassistant.components.websocket_api import WebSocket

_LOGGER = logging.getLogger(__name__)


class BaseWebSocketCommand:
    """Base class for WebSocket commands in Ramses Extras features.

    This provides a minimal foundation for WebSocket commands while maintaining
    feature-centric organization and integration with existing systems.
    """

    def __init__(self, hass: Any, feature_name: str) -> None:
        """Initialize base WebSocket command handler.

        Args:
            hass: Home Assistant instance
            feature_name: Name of the feature this command belongs to
        """
        self.hass = hass
        self.feature_name = feature_name
        self._logger = logging.getLogger(f"{__name__}.{feature_name}")

    async def execute(self, connection: "WebSocket", msg: dict[str, Any]) -> None:
        """Execute the WebSocket command.

        Args:
            connection: WebSocket connection
            msg: WebSocket message data
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def _send_success(self, connection: "WebSocket", msg_id: Any, result: Any) -> None:
        """Send successful response.

        Args:
            connection: WebSocket connection
            msg_id: Message ID for correlation
            result: Result data to send
        """
        connection.send_result(msg_id, result)

    def _send_error(
        self, connection: "WebSocket", msg_id: Any, error_code: str, error_message: str
    ) -> None:
        """Send error response.

        Args:
            connection: WebSocket connection
            msg_id: Message ID for correlation
            error_code: Error code
            error_message: Error message
        """
        connection.send_error(msg_id, error_code, error_message)

    def _log_command(self, command: str, device_id: str | None = None) -> None:
        """Log command execution.

        Args:
            command: Command name
            device_id: Device ID if applicable
        """
        if device_id:
            self._logger.debug(f"Executing {command} for device {device_id}")
        else:
            self._logger.debug(f"Executing {command}")

    def _log_error(
        self, command: str, error: Exception, device_id: str | None = None
    ) -> None:
        """Log command error.

        Args:
            command: Command name
            error: Exception that occurred
            device_id: Device ID if applicable
        """
        if device_id:
            self._logger.error(
                f"Error executing {command} for device {device_id}: {error}"
            )
        else:
            self._logger.error(f"Error executing {command}: {error}")


class DeviceWebSocketCommand(BaseWebSocketCommand):
    """Base class for device-related WebSocket commands.

    Provides device-specific functionality and integration with ramses_cc.
    """

    def __init__(self, hass: Any, feature_name: str) -> None:
        """Initialize device WebSocket command handler.

        Args:
            hass: Home Assistant instance
            feature_name: Name of the feature this command belongs to
        """
        super().__init__(hass, feature_name)
        self._ramses_data = hass.data.get("ramses_cc", {})


# WebSocket command registry for feature-centric organization
WEBSOCKET_COMMANDS: dict[str, dict[str, Callable]] = {}


def register_websocket_command(
    feature_name: str, command_name: str, handler_class: type[BaseWebSocketCommand]
) -> None:
    """Register a WebSocket command for a feature.

    Args:
        feature_name: Name of the feature
        command_name: Name of the command
        handler_class: Handler class for the command
    """
    if feature_name not in WEBSOCKET_COMMANDS:
        WEBSOCKET_COMMANDS[feature_name] = {}
    WEBSOCKET_COMMANDS[feature_name][command_name] = handler_class
    _LOGGER.debug(
        f"Registered WebSocket command {command_name} for feature {feature_name}"
    )


def get_websocket_commands_for_feature(feature_name: str) -> dict[str, Callable]:
    """Get all WebSocket commands for a feature.

    Args:
        feature_name: Name of the feature

    Returns:
        Dictionary of command name to handler class mappings
    """
    return WEBSOCKET_COMMANDS.get(feature_name, {})


def get_all_websocket_commands() -> dict[str, dict[str, Callable]]:
    """Get all registered WebSocket commands.

    Returns:
        Dictionary of feature name to command mappings
    """
    return WEBSOCKET_COMMANDS.copy()


def discover_websocket_commands() -> list[str]:
    """Discover all features that have WebSocket commands registered.

    Returns:
        List of feature names with WebSocket commands
    """
    return list(WEBSOCKET_COMMANDS.keys())


class GetEntityMappingsCommand(BaseWebSocketCommand):
    """Feature-centric WebSocket command to get entity mappings.

    This command retrieves entity mappings from any feature's configuration
    and returns them as a dictionary that frontend cards can use.
    Supports both feature_id and direct const module references.
    """

    def __init__(self, hass: Any, feature_identifier: str) -> None:
        """Initialize with feature identifier (feature_id or const module path).

        Args:
            hass: Home Assistant instance
            feature_identifier: Either feature_id (e.g., "hello_world_card")
                               or const module path (e.g., "hello_world_card.const")
        """
        super().__init__(hass, feature_identifier)
        self.feature_identifier = feature_identifier

    async def execute(self, connection: "WebSocket", msg: dict[str, Any]) -> None:
        """Execute the get_entity_mappings command.

        Args:
            connection: WebSocket connection
            msg: WebSocket message data containing feature identifier
        """
        self._log_command("get_entity_mappings")

        try:
            # Get device_id from message if provided
            device_id = msg.get("device_id")

            # Get entity mappings from the feature's configuration
            entity_mappings = await self._get_entity_mappings_from_feature()

            if entity_mappings:
                # Parse entity templates with device_id if provided
                if device_id:
                    parsed_mappings = self._parse_entity_templates(
                        entity_mappings, device_id
                    )
                else:
                    parsed_mappings = entity_mappings

                # Return as a clean dictionary with templates
                self._send_success(
                    connection,
                    msg["id"],
                    {
                        "mappings": parsed_mappings,  # Dictionary of parsed templates
                        "success": True,
                        "feature_identifier": self.feature_identifier,
                        "device_id": device_id,
                    },
                )
            else:
                self._send_error(
                    connection,
                    msg["id"],
                    "no_entity_mappings",
                    f"No entity mappings found for {self.feature_identifier}",
                )

        except Exception as error:
            self._log_error("get_entity_mappings", error)
            self._send_error(
                connection, msg["id"], "get_entity_mappings_failed", str(error)
            )

    def _parse_entity_templates(
        self, entity_mappings: dict[str, str], device_id: str
    ) -> dict[str, str]:
        """Parse entity templates by replacing {device_id} with actual device_id.

        Args:
            entity_mappings: Dictionary of entity mappings with templates
            device_id: Actual device ID to use for template replacement

        Returns:
            Dictionary of parsed entity mappings with actual entity IDs
        """
        parsed_mappings = {}

        for state_name, entity_template in entity_mappings.items():
            # Replace {device_id} with actual device_id
            parsed_entity = entity_template.replace("{device_id}", device_id)
            parsed_mappings[state_name] = parsed_entity

            self._logger.debug(
                f"Parsed {state_name}: {entity_template} -> {parsed_entity}"
            )

        return parsed_mappings

    async def _get_entity_mappings_from_feature(self) -> dict[str, str]:
        """Get entity mappings from the feature's configuration.

        Returns:
            Dictionary of state_name to entity template mappings
        """
        try:
            # Determine how to import the feature module
            if "." in self.feature_identifier:
                # It's a const module path, use it directly
                const_module_path = self.feature_identifier
            else:
                # It's a feature_id, construct the const module path
                const_module_path = "custom_components.ramses_extras.features."
                const_module_path += f"{self.feature_identifier}.const"

            # Import the const module for this feature
            import importlib

            feature_module = importlib.import_module(const_module_path)

            entity_mappings = {}

            # Check for switch configurations (any feature-specific naming)
            for attr_name in dir(feature_module):
                if attr_name.endswith("_SWITCH_CONFIGS") and attr_name.startswith(
                    ("HELLO_WORLD_", "HUMIDITY_CONTROL_", "")
                ):
                    switch_configs = getattr(feature_module, attr_name)
                    for entity_name, config in switch_configs.items():
                        if "entity_template" in config:
                            template = config["entity_template"]
                            entity_mappings[f"{entity_name}_state"] = (
                                f"switch.{template}"
                            )

            # Check for binary sensor configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith(
                    "_BINARY_SENSOR_CONFIGS"
                ) and attr_name.startswith(("HELLO_WORLD_", "HUMIDITY_CONTROL_", "")):
                    sensor_configs = getattr(feature_module, attr_name)
                    for entity_name, config in sensor_configs.items():
                        if "entity_template" in config:
                            template = config["entity_template"]
                            entity_mappings[f"{entity_name}_state"] = (
                                f"binary_sensor.{template}"
                            )

            # Check for sensor configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith("_SENSOR_CONFIGS") and attr_name.startswith(
                    ("HELLO_WORLD_", "HUMIDITY_CONTROL_", "")
                ):
                    sensor_configs = getattr(feature_module, attr_name)
                    for entity_name, config in sensor_configs.items():
                        if "entity_template" in config:
                            template = config["entity_template"]
                            entity_mappings[f"{entity_name}_state"] = (
                                f"sensor.{template}"
                            )

            # Check for number configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith("_NUMBER_CONFIGS") and attr_name.startswith(
                    ("HELLO_WORLD_", "HUMIDITY_CONTROL_", "")
                ):
                    number_configs = getattr(feature_module, attr_name)
                    for entity_name, config in number_configs.items():
                        if "entity_template" in config:
                            template = config["entity_template"]
                            entity_mappings[f"{entity_name}_state"] = (
                                f"number.{template}"
                            )

            self._logger.debug(
                f"Found entity mappings for {self.feature_identifier}: "
                f"{entity_mappings}"
            )
            return entity_mappings

        except Exception as error:
            self._logger.error(
                f"Failed to get entity mappings for {self.feature_identifier}: {error}"
            )
            return {}


class GetAllFeatureEntitiesCommand(BaseWebSocketCommand):
    """WebSocket command to retrieve all entities from a feature with device_id support.

    This command retrieves all entity configurations from a feature and returns them
    as parsed entity mappings that can be used from anywhere in the frontend.
    It keeps the frontend and feature clean by providing a centralized way to
    access entity information.
    """

    def __init__(self, hass: Any, feature_identifier: str) -> None:
        """Initialize with feature identifier.

        Args:
            hass: Home Assistant instance
            feature_identifier: Either feature_id or const module path
        """
        super().__init__(hass, feature_identifier)
        self.feature_identifier = feature_identifier

    async def execute(self, connection: "WebSocket", msg: dict[str, Any]) -> None:
        """Execute the get_all_feature_entities command.

        Args:
            connection: WebSocket connection
            msg: WebSocket message data containing feature_id and device_id
        """
        self._log_command("get_all_feature_entities")

        try:
            # Get required parameters
            device_id = msg.get("device_id")

            if not device_id:
                self._send_error(
                    connection,
                    msg["id"],
                    "missing_device_id",
                    "device_id parameter is required for entity template parsing",
                )
                return

            # Get all entity configurations from the feature
            all_entities = await self._get_all_entities_from_feature()

            if all_entities:
                # Parse all entity templates with the provided device_id
                parsed_entities = self._parse_all_entity_templates(
                    all_entities, device_id
                )

                self._send_success(
                    connection,
                    msg["id"],
                    {
                        "feature_id": self.feature_identifier,
                        "device_id": device_id,
                        "entities": parsed_entities,
                        "success": True,
                    },
                )
            else:
                self._send_error(
                    connection,
                    msg["id"],
                    "no_entities_found",
                    f"No entities found for feature {self.feature_identifier}",
                )

        except Exception as error:
            self._log_error("get_all_feature_entities", error)
            self._send_error(
                connection, msg["id"], "get_all_feature_entities_failed", str(error)
            )

    async def _get_all_entities_from_feature(self) -> dict[str, Any]:
        """Get all entity configurations from the feature.

        Returns:
            Dictionary containing all entity configurations by platform
        """
        try:
            # Determine how to import the feature module
            if "." in self.feature_identifier:
                # It's a const module path, use it directly
                const_module_path = self.feature_identifier
            else:
                # It's a feature_id, construct the const module path
                const_module_path = "custom_components.ramses_extras.features."
                const_module_path += f"{self.feature_identifier}.const"

            # Import the const module for this feature
            import importlib

            feature_module = importlib.import_module(const_module_path)

            all_entities: dict[str, dict[str, Any]] = {
                "switch": {},
                "binary_sensor": {},
                "sensor": {},
                "number": {},
            }

            # Collect switch configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith("_SWITCH_CONFIGS"):
                    switch_configs = getattr(feature_module, attr_name)
                    all_entities["switch"] = switch_configs

            # Collect binary sensor configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith(("_BINARY_SENSOR_CONFIGS", "_BOOLEAN_CONFIGS")):
                    sensor_configs = getattr(feature_module, attr_name)
                    all_entities["binary_sensor"].update(sensor_configs)

            # Collect sensor configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith("_SENSOR_CONFIGS"):
                    sensor_configs = getattr(feature_module, attr_name)
                    all_entities["sensor"].update(sensor_configs)

            # Collect number configurations
            for attr_name in dir(feature_module):
                if attr_name.endswith("_NUMBER_CONFIGS"):
                    number_configs = getattr(feature_module, attr_name)
                    all_entities["number"].update(number_configs)

            self._logger.debug(
                f"Found all entities for {self.feature_identifier}: {all_entities}"
            )
            return all_entities

        except Exception as error:
            self._logger.error(
                f"Failed to get all entities for {self.feature_identifier}: {error}"
            )
            return {}

    def _parse_all_entity_templates(
        self, all_entities: dict[str, Any], device_id: str
    ) -> dict[str, Any]:
        """Parse all entity templates by replacing {device_id} with actual device_id.

        Args:
            all_entities: Dictionary of all entity configurations by platform
            device_id: Actual device ID to use for template replacement

        Returns:
            Dictionary of parsed entity configurations with actual entity IDs
        """
        parsed_entities: dict[str, dict[str, Any]] = {
            "switch": {},
            "binary_sensor": {},
            "sensor": {},
            "number": {},
        }

        for platform, entities in all_entities.items():
            for entity_name, config in entities.items():
                if "entity_template" in config:
                    # Create parsed entity configuration
                    parsed_config = config.copy()

                    # Parse the entity template
                    entity_template = config["entity_template"]
                    parsed_entity_id = entity_template.replace("{device_id}", device_id)

                    # Update the configuration with parsed entity ID
                    parsed_config["entity_id"] = f"{platform}.{parsed_entity_id}"
                    parsed_config["parsed_entity_template"] = parsed_entity_id

                    # Add to parsed entities
                    parsed_entities[platform][entity_name] = parsed_config

                    self._logger.debug(
                        f"Parsed {platform}.{entity_name}: {entity_template} -> "
                        f"{parsed_entity_id}"
                    )

        return parsed_entities
