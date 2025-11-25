"""Entity management utilities for config flow operations.

This module provides centralized entity management for the Ramses Extras
config flow, replacing scattered list management with a clean, efficient
EntityManager class.
"""

import asyncio
import importlib
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from .core import (
    EntityHelpers,
    _singularize_entity_type,
    generate_entity_patterns_for_feature,
    get_feature_entity_mappings,
)

_LOGGER = logging.getLogger(__name__)


class EntityInfo(TypedDict):
    """Information about a possible entity."""

    exists_already: bool  # Whether entity currently exists in HA
    enabled_by_feature: bool  # Whether entity should exist based on enabled features
    feature_id: str  # Which feature creates this entity
    entity_type: str  # sensor, switch, automation, card, etc.
    entity_name: str  # Base entity name


class EntityManager:
    """Centralized entity management for config flow operations.

    This class replaces scattered list management with a clean API for:
    - Building complete entity catalogs
    - Generating clean removal/creation lists
    - Efficient bulk entity operations
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize EntityManager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self.all_possible_entities: dict[str, EntityInfo] = {}
        self.current_features: dict[str, bool] = {}
        self.target_features: dict[str, bool] = {}

    async def build_entity_catalog(
        self,
        available_features: dict[str, dict[str, Any]],
        current_features: dict[str, bool],
        target_features: dict[str, bool] | None = None,
    ) -> None:
        """Build complete entity catalog with existence and feature status.

        This method scans all possible entities and determines:
        1. Which entities currently exist in Home Assistant
        2. Which entities should exist based on enabled features

        Args:
            available_features: All available features configuration
            current_features: Currently enabled features
            target_features: Target enabled features (for feature change operations)
        """
        _LOGGER.debug("Building entity catalog...")

        self.current_features = current_features.copy()
        self.target_features = (
            target_features.copy() if target_features else current_features.copy()
        )
        self.all_possible_entities = {}

        # Get all currently existing entities
        existing_entities = await self._get_all_existing_entities()

        # Scan each feature for its required entities
        for feature_id, feature_config in available_features.items():
            await self._scan_feature_entities(
                feature_id, feature_config, existing_entities
            )

        existing_count = sum(
            1 for info in self.all_possible_entities.values() if info["exists_already"]
        )
        _LOGGER.info(
            f"Entity catalog built: {len(self.all_possible_entities)} possible "
            f"entities, {existing_count} existing"
        )

    def update_feature_targets(self, target_features: dict[str, bool]) -> None:
        """Update the target features for entity comparison.

        This method updates the enabled_by_feature status for all entities
        based on the new target configuration, allowing proper comparison
        between current and target states.

        Args:
            target_features: New target feature configuration
        """
        _LOGGER.debug("Updating feature targets for entity comparison...")

        # Always update target_features when this method is called
        self.target_features = target_features.copy()

        # Update enabled_by_feature status for all entities
        for entity_id, info in self.all_possible_entities.items():
            feature_id = info["feature_id"]
            # Get the feature config to determine default_enabled
            # Import at function level to avoid blocking imports
            from custom_components.ramses_extras.const import AVAILABLE_FEATURES

            feature_config = AVAILABLE_FEATURES.get(feature_id, {})
            default_enabled = feature_config.get("default_enabled", False)
            info["enabled_by_feature"] = self.target_features.get(
                feature_id, default_enabled
            )

        _LOGGER.debug(
            f"Updated feature targets for {len(self.all_possible_entities)} entities"
        )

    async def _get_all_existing_entities(self) -> set[str]:
        """Get all entity IDs that currently exist in Home Assistant.

        Returns:
            Set of existing entity IDs
        """
        try:
            entity_registry_instance = entity_registry.async_get(self.hass)
            entities = entity_registry_instance.entities
            return {entity.entity_id for entity in entities.values()}
        except Exception as e:
            _LOGGER.warning(f"Could not get entity registry: {e}")
            return set()

    async def _scan_feature_entities(
        self,
        feature_id: str,
        feature_config: dict[str, Any],
        existing_entities: set[str],
    ) -> None:
        """Scan a specific feature for its entities.

        Args:
            feature_id: Feature identifier
            feature_config: Feature configuration
            existing_entities: Set of currently existing entity IDs
        """
        # Get enabled status for this feature
        # Only scan features that are currently enabled or will be enabled
        default_enabled = feature_config.get("default_enabled", False)
        target_enabled = self.target_features.get(feature_id, default_enabled)
        current_enabled = self.current_features.get(feature_id, default_enabled)

        # Only discover entities for features that are enabled
        feature_is_enabled = target_enabled or current_enabled

        _LOGGER.debug(
            f"Scanning feature {feature_id}: current={current_enabled}, "
            f"target={target_enabled}, enabled_for_discovery={feature_is_enabled}"
        )

        if not feature_is_enabled:
            _LOGGER.debug(f"Skipping disabled feature: {feature_id}")
            return

        # Use target features for enabled_by_feature status
        enabled_by_feature = target_enabled

        # Check if feature has card configurations - add card entities if found
        has_cards = await self._feature_has_cards(feature_id)
        if has_cards:
            await self._add_card_entities(
                feature_id, feature_config, enabled_by_feature
            )

        # All features use device entities based on required_entities
        # Get feature's supported device types from the feature module
        supported_devices = await self._get_supported_devices_from_feature(feature_id)
        await self._add_device_entities(
            feature_id, feature_config, enabled_by_feature, supported_devices
        )

    async def _add_card_entities(
        self, feature_id: str, feature_config: dict[str, Any], enabled: bool
    ) -> None:
        """Add card entities for a feature.

        Args:
            feature_id: Feature identifier
            feature_config: Feature configuration
            enabled: Whether the feature is enabled
        """
        # Cards are identified by their feature_id in the
        #  /local/ramses_extras/features/ folder
        card_path = f"local_ramses_extras_features_{feature_id}"

        self.all_possible_entities[card_path] = {
            "exists_already": False,  # Cards are file-based, not entity-based
            "enabled_by_feature": enabled,
            "feature_id": feature_id,
            "entity_type": "card",
            "entity_name": feature_id,
        }

        _LOGGER.debug(f"Added card entity: {card_path} (enabled: {enabled})")

    async def _add_device_entities(
        self,
        feature_id: str,
        feature_config: dict[str, Any],
        enabled: bool,
        supported_devices: list[str],
    ) -> None:
        """Add device-based entities for a feature.

        Args:
            feature_id: Feature identifier
            feature_config: Feature configuration
            enabled: Whether the feature is enabled
            supported_devices: List of supported device types
        """
        # Get devices for this feature
        devices = await self._get_devices_for_feature(feature_id, supported_devices)

        _LOGGER.debug(
            f"Processing {len(devices)} devices for feature {feature_id} "
            f"(enabled={enabled})"
        )

        # For each device, add its required entities (not all mapped entities)
        for device in devices:
            device_id = self._extract_device_id(device)

            # Get required entities from the feature's required_entities config
            required_entities = await self._get_required_entities_for_feature(
                feature_id
            )

            _LOGGER.debug(
                f"Device {device_id} for feature {feature_id}: "
                f"required entities: {required_entities}"
            )

            # Process each required entity type
            for entity_type, entity_names in required_entities.items():
                singular_type = entity_type  # Convert "switch" -> "switch"

                for entity_name in entity_names:
                    # Generate entity ID using the standard pattern
                    entity_id = (
                        f"{singular_type}.{entity_name}_{device_id.replace(':', '_')}"
                    )

                    # Check if entity already exists from another feature
                    existing_entities = await self._get_all_existing_entities()
                    exists_already = entity_id in existing_entities

                    # Don't overwrite if entity already tracked by another feature
                    # This prevents features from claiming ownership of shared entities
                    if entity_id in self.all_possible_entities:
                        # Entity already tracked - just update enabled status if needed
                        existing_info = self.all_possible_entities[entity_id]
                        _LOGGER.debug(
                            f"Entity {entity_id} already tracked by feature "
                            f"'{existing_info['feature_id']}', not overwriting with "
                            f"'{feature_id}'"
                        )
                        # Update enabled status if this feature enables it
                        if enabled:
                            existing_info["enabled_by_feature"] = True
                    else:
                        # New entity - add it
                        self.all_possible_entities[entity_id] = {
                            "exists_already": exists_already,
                            "enabled_by_feature": enabled,
                            "feature_id": feature_id,
                            "entity_type": singular_type,
                            "entity_name": entity_name,
                        }

                        _LOGGER.debug(
                            f"Added required entity: {entity_id} "
                            f"(type={singular_type}, exists={exists_already}, "
                            f"enabled={enabled}, feature={feature_id})"
                        )

        _LOGGER.debug(f"Added {len(devices)} device entities for feature {feature_id}")

    def _extract_device_id(self, device: Any) -> str:
        """Extract device ID from device object or string with robust error handling.

        Args:
            device: Device object or device ID string

        Returns:
            Device ID as string
        """
        # Handle device ID strings directly
        if isinstance(device, str):
            return device

        # Try multiple ways to get device ID from object
        if hasattr(device, "id"):
            return str(device.id)
        if hasattr(device, "device_id"):
            return str(device.device_id)
        if hasattr(device, "_id"):
            return str(device._id)
        if hasattr(device, "name"):
            return str(device.name)
        if hasattr(device, "__str__"):
            return str(device)
        return f"device_{id(device)}"  # Fallback to object id

    async def _get_devices_for_feature(
        self, feature_id: str, supported_devices: list[str]
    ) -> list[Any]:
        """Get devices that support a specific feature with robust error handling.

        Args:
            feature_id: Feature identifier
            supported_devices: List of supported device types

        Returns:
            List of devices
        """
        try:
            # First try to get devices from ramses_extras data
            devices_data = self.hass.data.get("ramses_extras", {}).get("devices", [])

            if not devices_data:
                _LOGGER.warning(
                    f"No devices found in ramses_extras data for feature {feature_id}, "
                    f"discovering directly"
                )
                # Try to discover devices directly as fallback
                devices_data = await self._discover_devices_direct()
                if devices_data:
                    _LOGGER.info(
                        f"Discovered {len(devices_data)} devices directly for feature "
                        f"{feature_id}"
                    )
                else:
                    _LOGGER.warning(f"No devices discovered for feature {feature_id}")

            # Filter devices by supported types
            matching_devices = []
            for device in devices_data:
                # Handle both device objects and device ID strings
                if isinstance(device, str):
                    # Device ID string - assume it's a supported type for now
                    # This is a simplified approach for device IDs
                    device_id = device
                    device_type = "HvacVentilator"  # Default type for known device IDs
                    _LOGGER.debug(
                        f"Using device ID {device_id} (assumed type: {device_type}) "
                        f"for feature {feature_id}"
                    )
                else:
                    # Device object - extract type normally
                    device_type = self._extract_device_type(device)
                    device_id = self._extract_device_id(device)

                if any(supported in device_type for supported in supported_devices):
                    matching_devices.append(device)
                    _LOGGER.debug(
                        f"Matched device {device_id} (type: {device_type}) "
                        f"for feature {feature_id}"
                    )

            _LOGGER.info(
                f"Found {len(matching_devices)} matching devices for feature "
                f"{feature_id}"
            )
            return matching_devices
        except Exception as e:
            _LOGGER.error(f"Could not get devices for feature {feature_id}: {e}")
            return []

    def _extract_device_type(self, device: Any) -> str:
        """Extract device type with robust error handling.

        Args:
            device: Device object

        Returns:
            Device type as string
        """
        try:
            if hasattr(device, "__class__"):
                class_name = device.__class__.__name__
                return str(class_name) if class_name else "UnknownDevice"
            if hasattr(device, "type"):
                return str(device.type)
            if hasattr(device, "device_type"):
                return str(device.device_type)
            return str(type(device).__name__)
        except Exception as e:
            _LOGGER.debug(f"Failed to get device type for {device}: {e}")
            # Fallback to "UnknownDevice" if device type detection fails
            return "UnknownDevice"

    async def get_broker_for_entry(self, entry: Any) -> Any:
        """Get broker for a config entry using all possible methods.

        This method supports multiple versions of ramses_cc for backwards compatibility.
        Tries all possible broker access patterns from newest to oldest.

        Args:
            entry: Config entry

        Returns:
            Broker object or None
        """
        # Method 1: hass.data["ramses_cc"][entry.entry_id] (newest)
        try:
            if (
                "ramses_cc" in self.hass.data
                and entry.entry_id in self.hass.data["ramses_cc"]
            ):
                broker = self.hass.data["ramses_cc"][entry.entry_id]
                _LOGGER.debug(f"Found broker via Method 1 for {entry.entry_id}")
                return broker
        except Exception as e:
            _LOGGER.debug(f"Method 1 failed: {e}")

        # Method 2: hass.data["ramses_cc"] directly (older structure)
        try:
            if "ramses_cc" in self.hass.data:
                data = self.hass.data["ramses_cc"]
                if isinstance(data, dict) and len(data) > 0:
                    # Try first entry
                    first_value = list(data.values())[0]
                    if hasattr(first_value, "_devices") or hasattr(
                        first_value, "devices"
                    ):
                        _LOGGER.debug(f"Found broker via Method 2 for {entry.entry_id}")
                        return first_value
        except Exception as e:
            _LOGGER.debug(f"Method 2 failed: {e}")

        # Method 3: entry.broker (older versions)
        try:
            if hasattr(entry, "broker"):
                _LOGGER.debug(f"Found broker via Method 3 for {entry.entry_id}")
                return entry.broker
        except Exception as e:
            _LOGGER.debug(f"Method 3 failed: {e}")

        # Method 4: hass.data["ramses_cc"][DOMAIN] (very old)
        try:
            if "ramses_cc" in self.hass.data:
                for key, value in self.hass.data["ramses_cc"].items():
                    if hasattr(value, "_devices") or hasattr(value, "devices"):
                        _LOGGER.debug(f"Found broker via Method 4 for {entry.entry_id}")
                        return value
        except Exception as e:
            _LOGGER.debug(f"Method 4 failed: {e}")

        return None

    async def _discover_devices_direct(self) -> list[Any]:
        """Direct device discovery as fallback for EntityManager.

        This method uses the same device discovery logic as the main integration.
        """
        try:
            # Access the broker from the ramses_cc integration
            ramses_cc_entries = self.hass.config_entries.async_entries("ramses_cc")
            if not ramses_cc_entries:
                _LOGGER.warning("No ramses_cc entries found")
                return await self._discover_devices_from_entity_registry()

            # Use the first ramses_cc entry
            entry = ramses_cc_entries[0]

            # Try to get broker using all possible methods
            broker = await self.get_broker_for_entry(entry)

            if broker is None:
                _LOGGER.warning("Could not find ramses_cc broker via any method")
                return await self._discover_devices_from_entity_registry()

            # Get devices from the broker with robust access
            devices = getattr(broker, "_devices", None)
            if devices is None:
                devices = getattr(broker, "devices", None)

            if not devices:
                _LOGGER.debug(
                    "No devices found in broker, using entity registry fallback"
                )
                return await self._discover_devices_from_entity_registry()

            _LOGGER.debug(f"Found {len(devices)} total devices in broker")

            # Filter for different device types based on feature requirements
            discovered_devices = []

            # Fan devices (HvacVentilator) for ventilation features
            fan_devices = [
                device
                for device in devices
                if hasattr(device, "__class__")
                and "HvacVentilator" in device.__class__.__name__
            ]
            discovered_devices.extend(fan_devices)

            # Sensor devices for sensor features
            sensor_devices = [
                device
                for device in devices
                if hasattr(device, "__class__")
                and (
                    "HvacController" in device.__class__.__name__
                    or "Climate" in device.__class__.__name__
                )
            ]
            discovered_devices.extend(sensor_devices)

            _LOGGER.info(f"Discovered {len(discovered_devices)} relevant devices")
            return discovered_devices

        except Exception as e:
            _LOGGER.error(f"Error in direct device discovery: {e}")
            # Fallback to entity registry discovery
            return await self._discover_devices_from_entity_registry()

    async def _find_devices_for_broker(self, broker: Any) -> list[Any]:
        """Find devices for a broker using all possible methods.

        Args:
            broker: Broker object

        Returns:
            List of devices
        """
        # Method 1: broker._devices (newest - private attribute)
        try:
            if hasattr(broker, "_devices"):
                devices = broker._devices
                if devices:
                    _LOGGER.debug(f"Found devices via Method 1: {type(devices)}")
                    return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 1 failed: {e}")

        # Method 2: broker.devices (older - public attribute)
        try:
            if hasattr(broker, "devices"):
                devices = broker.devices
                if devices:
                    _LOGGER.debug(f"Found devices via Method 2: {type(devices)}")
                    return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 2 failed: {e}")

        # Method 3: broker.client.devices (alternative structure)
        try:
            if hasattr(broker, "client") and hasattr(broker.client, "devices"):
                devices = broker.client.devices
                if devices:
                    _LOGGER.debug(f"Found devices via Method 3: {type(devices)}")
                    return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 3 failed: {e}")

        # Method 4: Any attribute containing 'devices'
        try:
            for attr_name in dir(broker):
                if "device" in attr_name.lower() and not attr_name.startswith("_"):
                    devices = getattr(broker, attr_name, None)
                    if devices:
                        _LOGGER.debug(
                            f"Found devices via Method 4 ({attr_name}): {type(devices)}"
                        )
                        return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 4 failed: {e}")

        return []

    async def _get_supported_devices_from_feature(self, feature_id: str) -> list[str]:
        """Get supported device types from the feature's own const.py module.

        Uses required_entities approach for registry building, not device mappings.

        Args:
            feature_id: Feature identifier

        Returns:
            List of supported device types
        """
        try:
            # Run the blocking import operation in a thread pool
            loop = asyncio.get_event_loop()
            required_entities = await loop.run_in_executor(
                None, self._import_required_entities, feature_id
            )

            # For entity registry building, we assume all
            # features work with HvacVentilator
            # (this is the primary device type for ramses_extras)
            # In the future, this could be expanded to support multiple device types
            supported_devices = ["HvacVentilator"]

            _LOGGER.debug(
                f"Found supported devices for {feature_id}: {supported_devices} "
                f"(required_entities: {required_entities})"
            )
            return supported_devices
        except Exception as e:
            _LOGGER.debug(f"Could not get supported devices for {feature_id}: {e}")
            # Fallback to default
            return ["HvacVentilator"]

    async def _get_required_entities_for_feature(
        self, feature_id: str
    ) -> dict[str, list[str]]:
        """Get required entities for a feature (async wrapper).

        Args:
            feature_id: Feature identifier

        Returns:
            Required entities dictionary
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._import_required_entities, feature_id
        )

    def _import_required_entities(self, feature_id: str) -> dict[str, list[str]]:
        """Import feature module and return required entities (blocking operation).

        Args:
            feature_id: Feature identifier

        Returns:
            Required entities dictionary mapping entity_type to list of entity names
        """
        # Import the feature's const module
        feature_module_path = (
            f"custom_components.ramses_extras.features.{feature_id}.const"
        )

        feature_module = importlib.import_module(feature_module_path)

        # Get the FEATURE_CONST (e.g., HUMIDITY_CONTROL_CONST) for this feature
        const_key = f"{feature_id.upper()}_CONST"
        if hasattr(feature_module, const_key):
            const_data = getattr(feature_module, const_key, {})
            result: dict[str, list[str]] = const_data.get("required_entities", {})
            return result

        # No fallback - features should use the new required_entities format
        return {}

    async def _feature_has_cards(self, feature_id: str) -> bool:
        """Check if a feature has card configurations defined.

        Args:
            feature_id: Feature identifier

        Returns:
            True if feature has card configurations, False otherwise
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._import_has_cards, feature_id)

    def _import_has_cards(self, feature_id: str) -> bool:
        """Import feature module and check for card configurations (blocking operation).

        Args:
            feature_id: Feature identifier

        Returns:
            True if feature has card configurations, False otherwise
        """
        try:
            # Import the feature's const module
            feature_module_path = (
                f"custom_components.ramses_extras.features.{feature_id}.const"
            )

            feature_module = importlib.import_module(feature_module_path)

            # Check for CARD_CONFIGS variable (e.g., HVAC_FAN_CARD_CONFIGS)
            card_configs_key = f"{feature_id.upper()}_CARD_CONFIGS"
            if hasattr(feature_module, card_configs_key):
                card_configs = getattr(feature_module, card_configs_key, [])
                return len(card_configs) > 0

            return False
        except Exception as e:
            _LOGGER.debug(f"Could not check for cards in feature {feature_id}: {e}")
            return False

    def _normalize_devices_list(self, devices: Any) -> list[Any]:
        """Normalize different device storage formats to a list.

        Args:
            devices: Devices in various formats

        Returns:
            List of devices
        """
        try:
            # Dict format: return values
            if isinstance(devices, dict):
                return list(devices.values())
            # List format: return as-is
            if isinstance(devices, list):
                return devices
            # Set format: convert to list
            if isinstance(devices, set):
                return list(devices)
            # Single device: wrap in list
            return [devices]
        except Exception as e:
            _LOGGER.debug(f"Failed to normalize devices: {e}")
            return []

    async def _discover_devices_from_entity_registry(self) -> list[str]:
        """Fallback method to discover devices from entity registry.

        Returns:
            List of device IDs
        """
        try:
            entity_registry = entity_registry.async_get(self.hass)  # noqa: F823
            device_ids = []

            # Look for ramses_cc entities across multiple domains
            relevant_domains = [
                "fan",
                "climate",
                "sensor",
                "switch",
                "number",
                "binary_sensor",
            ]

            for entity in entity_registry.entities.values():
                if (
                    entity.domain in relevant_domains
                    and entity.platform == "ramses_cc"
                    and hasattr(entity, "device_id")
                ):
                    device_id = entity.device_id
                    if device_id and device_id not in device_ids:
                        device_ids.append(device_id)

            _LOGGER.info(
                f"Found {len(device_ids)} devices via entity registry fallback: "
                f"{device_ids}"
            )
            return device_ids
        except Exception as e:
            _LOGGER.error(f"Error discovering devices from entity registry: {e}")
            return []

    def get_entities_to_remove(self) -> list[str]:
        """Get list of entities to be removed.

        Entities to remove are those that exist_already but are not enabled_by_feature.
        Only returns platform entities (sensor, switch, etc.), not cards or automations.
        Excludes entities from always-enabled features like 'default'.

        Returns:
            List of entity IDs to remove
        """
        to_remove = []
        for entity_id, info in self.all_possible_entities.items():
            # Skip entities from always-enabled features (like 'default')
            if info["feature_id"] == "default":
                continue
            if (
                info["exists_already"]
                and not info["enabled_by_feature"]
                and info["entity_type"] not in ("card", "automation")
            ):
                to_remove.append(entity_id)

        _LOGGER.info(f"Entities to remove: {len(to_remove)}")
        return to_remove

    def get_entities_to_create(self) -> list[str]:
        """Get list of entities to be created.

        Entities to create are those that are enabled_by_feature but do not
        exist_already.
        Only returns platform entities (sensor, switch, etc.), not cards or automations.

        Returns:
            List of entity IDs to create
        """
        to_create = []
        for entity_id, info in self.all_possible_entities.items():
            if (
                info["enabled_by_feature"]
                and not info["exists_already"]
                and info["entity_type"] not in ("card", "automation")
            ):
                to_create.append(entity_id)

        _LOGGER.info(f"Entities to create: {len(to_create)}")
        return to_create

    def get_entity_summary(self) -> dict[str, int]:
        """Get summary of entity catalog status.

        Only counts platform entities (sensor, switch, etc.), not cards or automations.
        Excludes entities from always-enabled features like 'default'.

        Returns:
            Dictionary with counts for different entity states
        """
        # Filter to only platform entities
        # (exclude cards and automations, and default feature)
        platform_entities = {
            entity_id: info
            for entity_id, info in self.all_possible_entities.items()
            if info["entity_type"] not in ("card", "automation")
            and info["feature_id"] != "default"
        }

        summary = {
            "total_entities": len(platform_entities),
            "existing_enabled": 0,
            "existing_disabled": 0,
            "non_existing_enabled": 0,
            "non_existing_disabled": 0,
        }

        for info in platform_entities.values():
            if info["exists_already"] and info["enabled_by_feature"]:
                summary["existing_enabled"] += 1
            elif info["exists_already"] and not info["enabled_by_feature"]:
                summary["existing_disabled"] += 1
            elif not info["exists_already"] and info["enabled_by_feature"]:
                summary["non_existing_enabled"] += 1
            else:
                summary["non_existing_disabled"] += 1

        return summary

    async def apply_entity_changes(self) -> None:
        """Apply removal and creation operations.

        This method:
        1. Removes entities that should no longer exist
        2. Creates entities that should exist
        """
        to_remove = self.get_entities_to_remove()
        to_create = self.get_entities_to_create()

        _LOGGER.info(
            f"Applying entity changes: remove {len(to_remove)}, create {len(to_create)}"
        )

        if to_remove:
            await self._remove_entities(to_remove)

        if to_create:
            await self._create_entities(to_create)

        _LOGGER.info("Entity changes applied successfully")

    async def _remove_entities(self, entity_ids: list[str]) -> None:
        """Remove specified entities.

        Args:
            entity_ids: List of entity IDs to remove
        """
        _LOGGER.info(f"Removing {len(entity_ids)} entities...")

        # Group entities by type for efficient removal
        entities_by_type: dict[str, list[str]] = {}
        for entity_id in entity_ids:
            info = self.all_possible_entities.get(entity_id)
            if not info:
                continue

            entity_type = info["entity_type"]
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            entities_by_type[entity_type].append(entity_id)

        # Remove entities by type
        for entity_type, ids in entities_by_type.items():
            try:
                if entity_type == "card":
                    await self._remove_card_entities(ids)
                elif entity_type == "automation":
                    # Automations are no longer tracked separately
                    _LOGGER.debug(f"Skipping automation entities: {ids}")
                else:
                    await self._remove_regular_entities(ids, entity_type)
            except Exception as e:
                _LOGGER.error(f"Failed to remove {entity_type} entities: {e}")

    async def _create_entities(self, entity_ids: list[str]) -> None:
        """Create specified entities.

        Args:
            entity_ids: List of entity IDs to create
        """
        _LOGGER.info(f"Creating {len(entity_ids)} entities...")

        # Note: Entity creation typically happens through integration reload
        # This method mainly updates the catalog for tracking purposes
        for entity_id in entity_ids:
            if entity_id in self.all_possible_entities:
                self.all_possible_entities[entity_id]["exists_already"] = True

    async def _remove_card_entities(self, card_ids: list[str]) -> None:
        """Remove card entities.

        Args:
            card_ids: List of card IDs to remove
        """
        # Implementation would remove card files from /local/ramses_extras/features/
        _LOGGER.info(f"Removing card entities: {card_ids}")

    async def _remove_regular_entities(
        self, entity_ids: list[str], entity_type: str
    ) -> None:
        """Remove regular entities (sensor, switch, etc.).

        Args:
            entity_ids: List of entity IDs to remove
            entity_type: Type of entities (sensor, switch, etc.)
        """
        try:
            entity_registry_instance = entity_registry.async_get(self.hass)
            removed_count = 0

            for entity_id in entity_ids:
                try:
                    entity_registry_instance.async_remove(entity_id)
                    removed_count += 1
                except Exception as e:
                    _LOGGER.warning(f"Could not remove entity {entity_id}: {e}")

            _LOGGER.info(f"Removed {removed_count} {entity_type} entities")

        except Exception as e:
            _LOGGER.error(f"Failed to remove {entity_type} entities: {e}")


# Export EntityManager and EntityInfo
__all__ = ["EntityManager", "EntityInfo"]
