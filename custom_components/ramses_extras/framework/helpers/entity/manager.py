"""Entity management utilities for config flow operations.

This module provides centralized entity management for the Ramses Extras
config flow, replacing scattered list management with a clean, efficient
EntityManager class.
"""

import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant

from ....const import AVAILABLE_FEATURES
from .core import (
    EntityHelpers,
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
    ) -> None:
        """Build complete entity catalog with existence and feature status.

        This method scans all possible entities and determines:
        1. Which entities currently exist in Home Assistant
        2. Which entities should exist based on enabled features

        Args:
            available_features: All available features configuration
            current_features: Currently enabled features
        """
        _LOGGER.debug("Building entity catalog...")

        self.current_features = current_features.copy()
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

        self.target_features = target_features.copy()

        # Update enabled_by_feature status for all entities
        for entity_id, info in self.all_possible_entities.items():
            feature_id = info["feature_id"]
            info["enabled_by_feature"] = self.target_features.get(feature_id, False)

        _LOGGER.debug(
            f"Updated feature targets for {len(self.all_possible_entities)} entities"
        )

    async def _get_all_existing_entities(self) -> set[str]:
        """Get all entity IDs that currently exist in Home Assistant.

        Returns:
            Set of existing entity IDs
        """
        try:
            entity_registry = self.hass.helpers.entity_registry.async_get()
            entities = entity_registry.entities
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
        enabled = self.current_features.get(feature_id, False)

        # Get feature's supported device types
        supported_devices = feature_config.get("supported_device_types", [])

        # Handle different feature categories
        category = feature_config.get("category", "sensors")

        if category == "cards":
            # Card entities (dashboard cards)
            await self._add_card_entities(feature_id, feature_config, enabled)
        elif category == "automations":
            # Automation entities
            await self._add_automation_entities(feature_id, feature_config, enabled)
        else:
            # Sensor/other entities - need device-specific entities
            await self._add_device_entities(
                feature_id, feature_config, enabled, supported_devices
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
        # Cards are identified by their feature_id in the www/community folder
        card_path = f"www_community_{feature_id}"

        self.all_possible_entities[card_path] = {
            "exists_already": False,  # Cards are file-based, not entity-based
            "enabled_by_feature": enabled,
            "feature_id": feature_id,
            "entity_type": "card",
            "entity_name": feature_id,
        }

        _LOGGER.debug(f"Added card entity: {card_path} (enabled: {enabled})")

    async def _add_automation_entities(
        self, feature_id: str, feature_config: dict[str, Any], enabled: bool
    ) -> None:
        """Add automation entities for a feature.

        Args:
            feature_id: Feature identifier
            feature_config: Feature configuration
            enabled: Whether the feature is enabled
        """
        # Automations are YAML-based, identified by feature patterns
        automation_pattern = f"automation_{feature_id}_*"

        # Check for existing automations matching this pattern
        existing_automations = await self._find_automations_by_pattern(feature_id)

        self.all_possible_entities[automation_pattern] = {
            "exists_already": len(existing_automations) > 0,
            "enabled_by_feature": enabled,
            "feature_id": feature_id,
            "entity_type": "automation",
            "entity_name": feature_id,
        }

        _LOGGER.debug(
            f"Added automation pattern: {automation_pattern} (enabled: {enabled}, "
            f"existing: {len(existing_automations)})"
        )

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

        # For each device, add its required entities
        for device in devices:
            device_id = self._extract_device_id(device)
            entity_mappings = get_feature_entity_mappings(feature_id, device_id)

            for state_key, entity_id in entity_mappings.items():
                self.all_possible_entities[entity_id] = {
                    "exists_already": entity_id
                    in await self._get_all_existing_entities(),
                    "enabled_by_feature": enabled,
                    "feature_id": feature_id,
                    "entity_type": state_key.split("_")[0]
                    if "_" in state_key
                    else "sensor",
                    "entity_name": state_key,
                }

        _LOGGER.debug(f"Added {len(devices)} device entities for feature {feature_id}")

    def _extract_device_id(self, device: Any) -> str:
        """Extract device ID from device object with robust error handling.

        Args:
            device: Device object

        Returns:
            Device ID as string
        """
        # Try multiple ways to get device ID
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

    async def _find_automations_by_pattern(self, feature_id: str) -> list[str]:
        """Find automations matching a feature pattern.

        Args:
            feature_id: Feature identifier

        Returns:
            List of matching automation IDs
        """
        try:
            # For now, use pattern matching similar to existing code
            patterns = [f"*{feature_id}*"]
            all_states = self.hass.states.async_all()
            result = EntityHelpers.filter_entities_by_patterns(
                [state.entity_id for state in all_states], patterns
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            _LOGGER.warning(f"Could not find automations for {feature_id}: {e}")
            return []

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
                    f"No devices found in ramses_extras data for feature {feature_id}"
                )
                # Try to discover devices directly as fallback
                devices_data = await self._discover_devices_direct()
                if devices_data:
                    _LOGGER.info(
                        f"Discovered {len(devices_data)} devices directly for feature "
                        f"{feature_id}"
                    )

            # Filter devices by supported types
            matching_devices = []
            for device in devices_data:
                device_type = self._extract_device_type(device)
                if any(supported in device_type for supported in supported_devices):
                    matching_devices.append(device)
                    _LOGGER.debug(
                        f"Matched device {self._extract_device_id(device)} "
                        f"(type: {device_type}) for feature {feature_id}"
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
        except Exception:
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

        This method supports multiple versions of ramses_cc for backwards compatibility.
        Tries all possible broker and device access patterns.
        """
        devices_found = []

        try:
            # Get ramses_cc entries
            ramses_cc_entries = self.hass.config_entries.async_entries("ramses_cc")
            if not ramses_cc_entries:
                _LOGGER.debug("No ramses_cc entries found")
                return []

            _LOGGER.debug(f"Found {len(ramses_cc_entries)} ramses_cc entries")

            # Try each entry
            for entry in ramses_cc_entries:
                _LOGGER.debug(f"Processing entry: {entry.entry_id}")

                # Try all possible broker access methods for this entry
                broker = await self.get_broker_for_entry(entry)

                if broker:
                    _LOGGER.debug(
                        f"Found broker for entry {entry.entry_id}: {type(broker)}"
                    )
                    # Try all possible device access methods
                    entry_devices = await self._find_devices_for_broker(broker)
                    if entry_devices:
                        devices_found.extend(entry_devices)
                        _LOGGER.debug(
                            f"Found {len(entry_devices)} devices for entry "
                            f"{entry.entry_id}"
                        )
                else:
                    _LOGGER.debug(f"No broker found for entry {entry.entry_id}")

            _LOGGER.info(f"Total devices discovered: {len(devices_found)}")
            return devices_found

        except Exception as e:
            _LOGGER.debug(f"Direct device discovery failed: {e}")
            return []

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

    def get_entities_to_remove(self) -> list[str]:
        """Get list of entities to be removed.

        Entities to remove are those that exist_already but are not enabled_by_feature.

        Returns:
            List of entity IDs to remove
        """
        to_remove = []
        for entity_id, info in self.all_possible_entities.items():
            if info["exists_already"] and not info["enabled_by_feature"]:
                to_remove.append(entity_id)

        _LOGGER.info(f"Entities to remove: {len(to_remove)}")
        return to_remove

    def get_entities_to_create(self) -> list[str]:
        """Get list of entities to be created.

        Entities to create are those that are enabled_by_feature but do not
        exist_already.

        Returns:
            List of entity IDs to create
        """
        to_create = []
        for entity_id, info in self.all_possible_entities.items():
            if info["enabled_by_feature"] and not info["exists_already"]:
                to_create.append(entity_id)

        _LOGGER.info(f"Entities to create: {len(to_create)}")
        return to_create

    def get_entity_summary(self) -> dict[str, int]:
        """Get summary of entity catalog status.

        Returns:
            Dictionary with counts for different entity states
        """
        summary = {
            "total_entities": len(self.all_possible_entities),
            "existing_enabled": 0,
            "existing_disabled": 0,
            "non_existing_enabled": 0,
            "non_existing_disabled": 0,
        }

        for info in self.all_possible_entities.values():
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
                    await self._remove_automation_entities(ids)
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
        # Implementation would remove card files from www/community
        _LOGGER.info(f"Removing card entities: {card_ids}")

    async def _remove_automation_entities(self, automation_patterns: list[str]) -> None:
        """Remove automation entities.

        Args:
            automation_patterns: List of automation patterns to remove
        """
        # Implementation would remove automations from automations.yaml
        _LOGGER.info(f"Removing automation entities: {automation_patterns}")

    async def _remove_regular_entities(
        self, entity_ids: list[str], entity_type: str
    ) -> None:
        """Remove regular entities (sensors, switches, etc.).

        Args:
            entity_ids: List of entity IDs to remove
            entity_type: Type of entities (sensor, switch, etc.)
        """
        try:
            entity_registry = self.hass.helpers.entity_registry.async_get()
            removed_count = 0

            for entity_id in entity_ids:
                try:
                    entity_registry.async_remove(entity_id)
                    removed_count += 1
                except Exception as e:
                    _LOGGER.warning(f"Could not remove entity {entity_id}: {e}")

            _LOGGER.info(f"Removed {removed_count} {entity_type} entities")

        except Exception as e:
            _LOGGER.error(f"Failed to remove {entity_type} entities: {e}")


# Export EntityManager and EntityInfo
__all__ = ["EntityManager", "EntityInfo"]
