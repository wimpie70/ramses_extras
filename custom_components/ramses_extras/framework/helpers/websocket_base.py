"""WebSocket Base Classes and Utilities.

This module provides minimal WebSocket infrastructure for Ramses Extras features.
"""

import asyncio
import importlib
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

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
        """Send successful response with backend version injected.

        Args:
            connection: WebSocket connection
            msg_id: Message ID for correlation
            result: Result data to send
        """
        # Inject backend version for frontend version mismatch detection
        if isinstance(result, dict):
            from ...const import DOMAIN

            version = self.hass.data.get(DOMAIN, {}).get(
                "_integration_version", "0.0.0"
            )
            result["_backend_version"] = version
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
            self._logger.debug("Executing %s for device %s", command, device_id)
        else:
            self._logger.debug("Executing %s", command)

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
                "Error executing %s for device %s: %s",
                command,
                device_id,
                error,
            )
        else:
            self._logger.error("Error executing %s: %s", command, error)


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


class GetEntityMappingsCommand(BaseWebSocketCommand):
    """Feature-centric WebSocket command to get entity mappings.

    This command retrieves entity mappings from any feature's configuration
    and returns them as a dictionary that frontend cards can use.
    Supports both feature_id and direct const module references.
    """

    def __init__(
        self,
        hass: Any,
        feature_identifier: str,
        overlay_provider: Callable[[str, dict[str, str]], Awaitable[dict[str, Any]]]
        | None = None,
    ) -> None:
        """Initialize with feature identifier (feature_id or const module path).

        Args:
            hass: Home Assistant instance
            feature_identifier: Either feature_id (e.g., "hello_world")
                               or const module path (e.g., "hello_world.const")
        """
        super().__init__(hass, feature_identifier)
        self.feature_identifier = feature_identifier
        self._overlay_provider = overlay_provider

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

                # Build base result
                result = {
                    "mappings": parsed_mappings,  # Dictionary of parsed templates
                    "success": True,
                    "feature_identifier": self.feature_identifier,
                    "device_id": device_id,
                }

                if device_id and self._overlay_provider is not None:
                    overlay_result = await self._overlay_provider(
                        device_id,
                        parsed_mappings,
                    )
                    if overlay_result:
                        result.update(overlay_result)

                # Return the complete result
                self._send_success(connection, msg["id"], result)
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
        from custom_components.ramses_extras.framework.helpers.entity.core import (
            parse_entity_mapping_templates_for_device,
        )

        parsed_mappings = parse_entity_mapping_templates_for_device(
            entity_mappings,
            device_id,
        )

        for state_name, entity_template in entity_mappings.items():
            parsed_entity = parsed_mappings.get(state_name)
            self._logger.debug(
                "Parsed %s: %s -> %s",
                state_name,
                entity_template,
                parsed_entity,
            )

        return parsed_mappings

    async def _get_entity_mappings_from_feature(self) -> dict[str, str]:
        """Get entity mappings from the feature's configuration.

        Returns:
            Dictionary of state_name to entity template mappings
        """
        try:
            from custom_components.ramses_extras.framework.helpers.entity.core import (
                build_frontend_entity_mapping_templates,
            )

            # Determine how to import the feature module
            if "." in self.feature_identifier:
                # It's a const module path, use it directly
                const_module_path = self.feature_identifier
            else:
                # It's a feature_id, construct the const module path
                const_module_path = "custom_components.ramses_extras.features."
                const_module_path += f"{self.feature_identifier}.const"

            # Import the const module for this feature
            if hasattr(self.hass, "async_add_executor_job"):
                feature_module = await self.hass.async_add_executor_job(
                    importlib.import_module,
                    const_module_path,
                )
            else:
                feature_module = await asyncio.to_thread(
                    importlib.import_module,
                    const_module_path,
                )

            feature_definition = getattr(feature_module, "FEATURE_DEFINITION", None)
            if not isinstance(feature_definition, dict):
                feature_definition = {}

            entity_mappings = build_frontend_entity_mapping_templates(
                feature_definition
            )

            self._logger.debug(
                "Found entity mappings for %s: %s",
                self.feature_identifier,
                entity_mappings,
            )
            return entity_mappings

        except Exception as error:
            self._logger.error(
                "Failed to get entity mappings for %s: %s",
                self.feature_identifier,
                error,
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
            if hasattr(self.hass, "async_add_executor_job"):
                feature_module = await self.hass.async_add_executor_job(
                    importlib.import_module,
                    const_module_path,
                )
            else:
                feature_module = await asyncio.to_thread(
                    importlib.import_module,
                    const_module_path,
                )

            feature_definition = getattr(feature_module, "FEATURE_DEFINITION", None)
            if not isinstance(feature_definition, dict):
                feature_definition = {}

            def _as_config_dict(value: Any) -> dict[str, dict[str, Any]]:
                return value if isinstance(value, dict) else {}

            all_entities: dict[str, dict[str, Any]] = {
                "switch": _as_config_dict(feature_definition.get("switch_configs")),
                "binary_sensor": _as_config_dict(
                    feature_definition.get("boolean_configs")
                ),
                "sensor": _as_config_dict(feature_definition.get("sensor_configs")),
                "number": _as_config_dict(feature_definition.get("number_configs")),
            }

            self._logger.debug(
                "Found all entities for %s: %s",
                self.feature_identifier,
                all_entities,
            )
            return all_entities

        except Exception as error:
            self._logger.error(
                "Failed to get all entities for %s: %s",
                self.feature_identifier,
                error,
            )
            return {}

    def _parse_all_entity_templates(
        self, all_entities: dict[Any, Any], device_id: str
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

        from custom_components.ramses_extras.framework.helpers.entity.core import (
            parse_entity_mapping_templates_for_device,
        )

        for platform, entities in all_entities.items():
            if not isinstance(platform, str) or not isinstance(entities, dict):
                continue
            for entity_name, config in entities.items():
                if not isinstance(entity_name, str) or not isinstance(config, dict):
                    continue

                entity_template = config.get("entity_template")
                if not isinstance(entity_template, str):
                    continue

                # Create parsed entity configuration
                parsed_config = config.copy()

                parsed_entity_template = parse_entity_mapping_templates_for_device(
                    {"_": entity_template},
                    device_id,
                )["_"]

                entity_id = parsed_entity_template
                if not entity_id.startswith(f"{platform}."):
                    entity_id = f"{platform}.{entity_id}"

                # Update the configuration with parsed entity ID
                parsed_config["entity_id"] = entity_id
                parsed_config["parsed_entity_template"] = parsed_entity_template

                # Add to parsed entities
                parsed_entities[platform][entity_name] = parsed_config

                self._logger.debug(
                    "Parsed %s.%s: %s -> %s",
                    platform,
                    entity_name,
                    entity_template,
                    parsed_entity_template,
                )

        return parsed_entities
