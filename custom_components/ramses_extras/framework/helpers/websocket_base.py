"""WebSocket Base Classes and Utilities.

This module provides minimal WebSocket infrastructure for Ramses Extras features.
"""

import importlib
import logging
from typing import TYPE_CHECKING, Any

from custom_components.ramses_extras.framework.helpers.device.core import (
    extract_device_id_as_string,
)

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
            feature_identifier: Either feature_id (e.g., "hello_world")
                               or const module path (e.g., "hello_world.const")
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

                # Build base result
                result = {
                    "mappings": parsed_mappings,  # Dictionary of parsed templates
                    "success": True,
                    "feature_identifier": self.feature_identifier,
                    "device_id": device_id,
                }

                # Apply sensor_control overrides if enabled and device_id provided
                if device_id and self._is_sensor_control_enabled():
                    sensor_result = await self._apply_sensor_control_overrides(
                        device_id, parsed_mappings
                    )
                    if sensor_result:
                        # Merge sensor control results
                        result.update(sensor_result)

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
        parsed_mappings = {}

        device_id_underscore = device_id.replace(":", "_")

        for state_name, entity_template in entity_mappings.items():
            # Replace {device_id} with actual device_id
            parsed_entity = entity_template.replace("{device_id}", device_id_underscore)
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
            feature_module = importlib.import_module(const_module_path)

            entity_mappings = {}
            prefixes = (
                "HELLO_WORLD_",
                "HUMIDITY_CONTROL_",
                "HVAC_FAN_CARD_",
                "SENSOR_CONTROL_",
                "",
            )

            # Single loop over attributes for efficiency and consistency
            for attr_name in dir(feature_module):
                if attr_name.startswith("__"):
                    continue

                platform = None
                for prefix in prefixes:
                    if attr_name.startswith(prefix):
                        suffix = attr_name[len(prefix) :]
                        if suffix == "SWITCH_CONFIGS":
                            platform = "switch"
                        elif suffix in ("BINARY_SENSOR_CONFIGS", "BOOLEAN_CONFIGS"):
                            platform = "binary_sensor"
                        elif suffix == "SENSOR_CONFIGS":
                            platform = "sensor"
                        elif suffix == "NUMBER_CONFIGS":
                            platform = "number"

                        if platform:
                            configs = getattr(feature_module, attr_name)
                            if isinstance(configs, dict):
                                for entity_name, config in configs.items():
                                    if (
                                        isinstance(config, dict)
                                        and "entity_template" in config
                                    ):
                                        template = config["entity_template"]
                                        entity_mappings[f"{entity_name}_state"] = (
                                            f"{platform}.{template}"
                                        )
                            break

            # Fallback: Check for entity_mappings in feature constants
            if not entity_mappings:
                for attr_name in dir(feature_module):
                    if attr_name.endswith("_CONST"):
                        feature_const = getattr(feature_module, attr_name)
                        if (
                            isinstance(feature_const, dict)
                            and "entity_mappings" in feature_const
                        ):
                            entity_mappings = feature_const["entity_mappings"]
                            break

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

    def _is_sensor_control_enabled(self) -> bool:
        """Check if sensor_control feature is enabled.

        Returns:
            True if sensor_control is enabled, False otherwise
        """
        try:
            from ...const import DOMAIN

            config_entry = self.hass.data.get(DOMAIN, {}).get("config_entry")
            if not config_entry:
                return False

            enabled_features = (
                config_entry.data.get("enabled_features")
                or config_entry.options.get("enabled_features")
                or {}
            )

            return bool(enabled_features.get("sensor_control", False))
        except Exception:
            return False

    async def _apply_sensor_control_overrides(
        self, device_id: str, base_mappings: dict[str, str]
    ) -> dict[str, Any]:
        """Apply sensor control overrides to base mappings.

        Args:
            device_id: Device ID
            base_mappings: Base entity mappings from feature

        Returns:
            Dictionary with sensor control results to merge into main response
        """
        try:
            # Import resolver to avoid circular imports
            from ...features.sensor_control.resolver import SensorControlResolver

            resolver = SensorControlResolver(self.hass)

            # Determine device type from device registry or fallback
            device_type = self._get_device_type(device_id)
            if not device_type:
                self._logger.warning(
                    f"Could not determine device type for {device_id}, "
                    "skipping sensor control overrides"
                )
                return {}

            # Get sensor control resolution
            sensor_result = await resolver.resolve_entity_mappings(
                device_id, device_type
            )

            # Merge sensor control mappings with base mappings
            # Sensor control takes precedence for supported metrics
            merged_mappings = base_mappings.copy()
            merged_mappings.update(sensor_result["mappings"])

            return {
                "mappings": merged_mappings,
                "sources": sensor_result["sources"],
                "raw_internal": sensor_result.get("raw_internal"),
                "abs_humidity_inputs": sensor_result.get("abs_humidity_inputs", {}),
            }

        except Exception as err:
            self._logger.error(f"Failed to apply sensor control overrides: {err}")
            return {}

    def _get_device_type(self, device_id: str) -> str | None:
        """Get device type for a device ID.

        This helper is resilient to different device ID formats used across the
        codebase (e.g. "32:153289" vs "32_153289"). It normalizes both the
        provided ID and stored IDs to a colon-based form before comparing.

        Args:
            device_id: Device ID as passed by the caller (may use ':' or '_')

        Returns:
            Device type (FAN, CO2, etc.) or None if not found
        """
        try:
            from ...const import DOMAIN

            devices = self.hass.data.get(DOMAIN, {}).get("devices", [])

            # Normalize incoming ID to colon form for comparison
            target_colon = str(device_id).replace("_", ":")

            for device in devices:
                if isinstance(device, dict):
                    raw_id = device.get("device_id")
                    dev_type = device.get("type")
                else:
                    raw_id = device
                    dev_type = getattr(device, "type", None)

                dev_id_str = extract_device_id_as_string(raw_id)
                dev_colon = dev_id_str.replace("_", ":")

                if dev_colon == target_colon:
                    return dev_type
        except Exception as err:
            self._logger.error(f"Failed to get device type for {device_id}: {err}")

        return None


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
            feature_module = importlib.import_module(const_module_path)

            all_entities: dict[str, dict[str, Any]] = {
                "switch": {},
                "binary_sensor": {},
                "sensor": {},
                "number": {},
            }

            prefixes = (
                "HELLO_WORLD_",
                "HUMIDITY_CONTROL_",
                "HVAC_FAN_CARD_",
                "SENSOR_CONTROL_",
                "",
            )

            # Collect configurations using suffix matching
            for attr_name in dir(feature_module):
                if attr_name.startswith("__"):
                    continue

                platform = None
                for prefix in prefixes:
                    if attr_name.startswith(prefix):
                        suffix = attr_name[len(prefix) :]
                        if suffix == "SWITCH_CONFIGS":
                            platform = "switch"
                        elif suffix in ("BINARY_SENSOR_CONFIGS", "BOOLEAN_CONFIGS"):
                            platform = "binary_sensor"
                        elif suffix == "SENSOR_CONFIGS":
                            platform = "sensor"
                        elif suffix == "NUMBER_CONFIGS":
                            platform = "number"

                        if platform:
                            configs = getattr(feature_module, attr_name)
                            if isinstance(configs, dict):
                                all_entities[platform].update(configs)
                            break

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
