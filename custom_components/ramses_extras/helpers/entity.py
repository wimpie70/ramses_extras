"""Base entity class and helpers for Ramses entities with common functionality."""

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ..const import ENTITY_TYPE_CONFIGS

if TYPE_CHECKING:
    from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


class EntityHelpers:
    """Static helper methods for entity ID generation and parsing."""

    @staticmethod
    def generate_entity_id(entity_type: str, entity_name: str, device_id: str) -> str:
        """Generate a consistent entity ID from type, name, and device ID.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of the entity from config (e.g.,
            "indoor_absolute_humidity")
            device_id: Device ID in underscore format (e.g., "32_153289")

        Returns:
            Full entity ID (e.g., "sensor.indoor_absolute_humidity_32_153289")
        """
        # Map entity types to their prefixes
        type_to_prefix = {
            "sensor": "sensor",
            "switch": "switch",
            "number": "number",
            "binary_sensor": "binary_sensor",
        }

        prefix = type_to_prefix.get(entity_type, entity_type)
        return f"{prefix}.{entity_name}_{device_id}"

    @staticmethod
    def get_entity_template(entity_type: str, entity_name: str) -> str | None:
        """Get the entity template for a specific entity type and name.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of the entity from config
            (e.g., "indoor_absolute_humidity")

        Returns:
            Entity template string with {device_id} placeholder, or None if not found
        """
        configs = ENTITY_TYPE_CONFIGS.get(entity_type, {})
        entity_config = configs.get(entity_name, {})
        template = entity_config.get("entity_template")
        return template if template is not None else None

    @staticmethod
    def generate_entity_name_from_template(
        entity_type: str, entity_name: str, device_id: str
    ) -> str | None:
        """Generate a full entity ID using the configured template.

        Args:
            entity_type: Type of entity ("sensor", "switch", "number", "binary_sensor")
            entity_name: Name of the entity from config
            (e.g., "indoor_absolute_humidity")
            device_id: Device ID in underscore format (e.g., "32_153289")

        Returns:
            Full entity ID using the template, or None if template not found
        """
        template = EntityHelpers.get_entity_template(entity_type, entity_name)
        if not template:
            return None

        # Replace {device_id} placeholder with actual device ID
        entity_id_part = template.format(device_id=device_id)

        # Add the entity type prefix
        type_to_prefix = {
            "sensor": "sensor",
            "switch": "switch",
            "number": "number",
            "binary_sensor": "binary_sensor",
        }

        prefix = type_to_prefix.get(entity_type, entity_type)
        return f"{prefix}.{entity_id_part}"

    @staticmethod
    def get_all_required_entity_ids_for_device(device_id: str) -> list[str]:
        """Get all entity IDs required for a device based on its capabilities.

        Args:
            device_id: Device ID in underscore format (e.g., "32_153289")

        Returns:
            List of all required entity IDs for this device
        """
        entity_ids = []

        # For each entity type configuration
        for entity_type, configs in ENTITY_TYPE_CONFIGS.items():
            # For each entity in that type
            for entity_name in configs.keys():
                entity_id = EntityHelpers.generate_entity_name_from_template(
                    entity_type, entity_name, device_id
                )
                if entity_id:
                    entity_ids.append(entity_id)

        return entity_ids

    @staticmethod
    def cleanup_orphaned_entities(
        platform: str,
        hass: "HomeAssistant",
        devices: list[str],
        required_entities: set[str],
        all_possible_types: list[str],
    ) -> int:
        """Clean up orphaned entities from the registry.

        Args:
            platform: Platform type ('sensor', 'switch', 'binary_sensor')
            hass: Home Assistant instance
            devices: List of device IDs
            required_entities: Set of currently required entity IDs
            all_possible_types: List of all possible entity types for this platform

        Returns:
            Number of entities removed
        """
        from homeassistant.helpers import entity_registry as er

        _LOGGER.info(f"Starting {platform} cleanup for devices: {devices}")

        # Get entity registry
        if "entity_registry" not in hass.data:
            _LOGGER.warning("Entity registry not available")
            return 0

        entity_registry: er.EntityRegistry = hass.data["entity_registry"]
        _LOGGER.info(f"Entity registry available: {entity_registry is not None}")

        orphaned_entities: list[str] = []

        for entity_id, _entity_entry in entity_registry.entities.items():
            if not entity_id.startswith(f"{platform}."):
                continue

            # Extract device_id from entity_id
            # Format: {platform}.{entity_type}_{device_id} where device_id is 32_153289
            parts = entity_id.split(".")
            if len(parts) >= 2:
                entity_name_and_device = parts[1]  # entity_type_device_id

                # Check if this entity belongs to one of our devices
                for device_id in devices:
                    # Convert device_id from colon format (32:153289)
                    # to underscore format (32_153289)
                    device_id_underscore = device_id.replace(":", "_")

                    # Check if the entity belongs to this device (device_id at the end)
                    if entity_name_and_device.endswith(f"_{device_id_underscore}"):
                        # This entity belongs to our device, check if it's still needed
                        entity_type = entity_name_and_device[
                            : -len(f"_{device_id_underscore}") - 1
                        ]  # Remove "_32_153289"

                        # Check if this entity_type is still required
                        expected_entity_id = (
                            f"{platform}.{entity_type}_" + f"{device_id_underscore}"
                        )
                        if expected_entity_id not in required_entities:
                            orphaned_entities.append(entity_id)
                            _LOGGER.info(
                                "Will remove orphaned %s: %s (type: %s)",
                                platform,
                                entity_id,
                                entity_type,
                            )
                        break

        _LOGGER.info(
            f"Found {len(orphaned_entities)} orphaned {platform} entities to remove"
        )

        removed_count = 0
        for entity_id in orphaned_entities:
            try:
                entity_registry.async_remove(entity_id)
                _LOGGER.info(f"Removed orphaned {platform} entity: {entity_id}")
                removed_count += 1
            except Exception as e:
                _LOGGER.warning(f"Failed to remove {platform} entity {entity_id}: {e}")

        return removed_count

    @staticmethod
    def parse_entity_id(entity_id: str) -> tuple[str, str, str] | None:
        """Parse an entity ID to extract entity type, name, and device ID.

        Args:
            entity_id: Full entity ID
            (e.g., "sensor.indoor_absolute_humidity_32_153289")

        Returns:
            Tuple of (entity_type, entity_name, device_id) or None if parsing fails
        """
        try:
            # Split on first dot to get type and rest
            if "." not in entity_id:
                return None

            entity_type, rest = entity_id.split(".", 1)

            # Device ID patterns we expect: 32_153289, 10_456789, etc.
            # These have the pattern: digits_underscore_digits
            # We need to find this pattern at the end of the string

            # Look for device ID pattern: _ followed by digits,
            # underscore, digits at the end
            device_id_match = re.search(r"_(\d+_\d+)$", rest)
            if device_id_match:
                device_id = device_id_match.group(
                    1
                )  # The actual device ID part (e.g., "32_153289")
                # Remove the device ID and underscore from the entity name
                entity_name = rest[: device_id_match.start(0)]
            else:
                # No device ID found, return as is
                return entity_type, rest, ""

            # Validate entity type
            valid_types = {"sensor", "switch", "number", "binary_sensor"}
            if entity_type not in valid_types:
                return None

            return entity_type, entity_name, device_id

        except (ValueError, IndexError):
            return None


class ExtrasBaseEntity(ABC):
    """Base entity class for all Ramses entities with common functionality."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        entity_type: str,
        config: dict[str, Any],
    ):
        """Initialize base Ramses entity."""
        self.hass = hass
        self._device_id = device_id  # Store device ID as string
        self._entity_type = entity_type
        self._config = config

        # Set common attributes from configuration
        self._attr_name = f"{config['name_template']} ({device_id})"
        self._attr_unique_id = f"{entity_type}_{device_id.replace(':', '_')}"
        self._attr_icon = config.get("icon")
        self._attr_entity_category = config.get("entity_category")

        self._unsub: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to Ramses RF device updates."""
        signal = f"ramses_rf_device_update_{self._device_id}"
        self._unsub = async_dispatcher_connect(self.hass, signal, self._handle_update)
        _LOGGER.debug("Subscribed to %s for %s", signal, self._attr_name)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe when removed."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _handle_update(self, *args: Any, **kwargs: Any) -> None:
        """Handle updates from Ramses RF."""
        _LOGGER.debug("Device update for %s received", self._attr_name)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common state attributes."""
        return {
            "device_id": self._device_id,
            "entity_type": self._entity_type,
        }

    @abstractmethod
    def async_write_ha_state(self) -> None:
        """Write state to Home Assistant - implemented by subclasses."""
