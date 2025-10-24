"""Entity Manager for Ramses Extras integration."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from homeassistant.helpers import entity_registry

from ..const import AVAILABLE_FEATURES, DEVICE_ENTITY_MAPPING, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EntityManager:
    """Manages creation and removal of integration entities."""

    def __init__(self, hass: "HomeAssistant") -> None:
        """Initialize entity manager."""
        self.hass = hass
        self.entity_registry = entity_registry.async_get(hass)

    def get_required_entities_for_device(
        self, device_type: str, enabled_features: dict[str, bool]
    ) -> dict[str, list[str]]:
        """Get required entities for a device type based on enabled features."""
        required_entities: dict[str, list[str]] = {
            "sensors": [],
            "switches": [],
            "binary_sensors": [],
            "numbers": [],
        }

        if device_type not in DEVICE_ENTITY_MAPPING:
            return required_entities

        entity_mapping = DEVICE_ENTITY_MAPPING[device_type]

        # Check each feature to see what entities it requires
        for feature_key, is_enabled in enabled_features.items():
            if not is_enabled:
                continue

            feature_config = AVAILABLE_FEATURES.get(feature_key)
            if not feature_config:
                continue

            supported_types = feature_config.get("supported_device_types", [])
            # Ensure supported_types is a list of strings
            if not isinstance(supported_types, list):
                continue
            if device_type not in supported_types:
                continue

            # Add required entities for this feature
            feature_entities = feature_config.get("required_entities", {})
            if isinstance(feature_entities, dict):
                for entity_type, entity_list in feature_entities.items():
                    if entity_type in required_entities and isinstance(
                        entity_list, list
                    ):
                        required_entities[entity_type].extend(entity_list)

        # Also add entities from device mapping
        for entity_type, entity_list in entity_mapping.items():
            if entity_type in required_entities and isinstance(entity_list, list):
                required_entities[entity_type].extend(entity_list)

        # Remove duplicates
        for entity_type in required_entities:
            required_entities[entity_type] = list(set(required_entities[entity_type]))

        return required_entities

    async def cleanup_orphaned_entities(
        self, device_ids: list[str], enabled_features: dict[str, bool]
    ) -> None:
        """Remove entities that are no longer required."""
        _LOGGER.info(f"Starting entity cleanup for devices: {device_ids}")

        if not device_ids:
            return

        try:
            # Get all required entities across all devices and features
            all_required_entities = set()

            for device_id in device_ids:
                device_type = self._get_device_type(device_id)
                if not device_type:
                    continue

                required = self.get_required_entities_for_device(
                    device_type, enabled_features
                )
                for entity_type, entity_list in required.items():
                    for entity_name in entity_list:
                        # Convert entity name to full entity ID
                        full_entity_id = f"{entity_type}.{device_id}_{entity_name}"
                        all_required_entities.add(full_entity_id)

            _LOGGER.info(f"Required entities: {all_required_entities}")

            # Find orphaned entities (exist but not required)
            orphaned_entities = []

            # Check entity registry for our domain entities
            for entity_id, entity_entry in self.entity_registry.entities.items():
                if entity_entry.platform != DOMAIN:
                    continue

                # Check if entity is for one of our devices
                for device_id in device_ids:
                    if f"_{device_id}_" in entity_id or entity_id.endswith(
                        f"_{device_id}"
                    ):
                        if entity_id not in all_required_entities:
                            orphaned_entities.append(entity_id)
                            _LOGGER.info(f"Found orphaned entity: {entity_id}")

            # Remove orphaned entities
            for entity_id in orphaned_entities:
                try:
                    self.entity_registry.async_remove(entity_id)
                    _LOGGER.info(f"Removed orphaned entity: {entity_id}")
                except Exception as e:
                    _LOGGER.warning(f"Failed to remove entity {entity_id}: {e}")

            _LOGGER.info(
                f"Entity cleanup completed. Removed {len(orphaned_entities)} "
                f"orphaned entities"
            )

        except Exception as e:
            _LOGGER.error(f"Failed to cleanup entities: {e}")

    def _get_device_type(self, device_id: str) -> str:
        """Get device type for a device ID."""
        # This would need to be implemented based on how devices are discovered
        # For now, assume all devices are HvacVentilator
        return "HvacVentilator"

    def get_device_entity_mapping(self, device_type: str) -> dict[str, list[str]]:
        """Get entity mapping for a device type."""
        return DEVICE_ENTITY_MAPPING.get(device_type, {})
