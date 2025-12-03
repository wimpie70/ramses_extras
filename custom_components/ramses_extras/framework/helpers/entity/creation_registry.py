"""Entity Creation Registry for Ramses Extras framework.

This module implements the EntityCreationRegistry class which provides
immutable, append-only tracking of every entity ever created in the system.
It serves as the foundation for the foolproof entity management system.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class EntityCreationRecord:
    """Immutable record representing a single entity creation event."""

    def __init__(
        self,
        entity_id: str,
        feature_id: str,
        device_id: str,
        entity_type: str,
        context: dict[str, Any],
        record_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Initialize an immutable entity creation record.

        Args:
            entity_id: The entity identifier
            feature_id: The feature that created this entity
            device_id: The device this entity belongs to
            entity_type: The type of entity (sensor, switch, etc.)
            context: Additional context about the creation
            record_id: Unique record identifier (auto-generated if None)
            timestamp: Creation timestamp (auto-generated if None)
        """
        self._entity_id = entity_id
        self._feature_id = feature_id
        self._device_id = device_id
        self._entity_type = entity_type
        self._context = context.copy()  # Make defensive copy
        self._record_id = record_id or str(uuid.uuid4())
        self._timestamp = timestamp or datetime.now()
        self._cleanup_eligible = False
        self._cleanup_reason: str | None = None
        self._cleanup_timestamp: datetime | None = None
        self._verified_removed = False
        self._verification_timestamp: datetime | None = None

    @property
    def entity_id(self) -> str:
        """Get the entity identifier."""
        return self._entity_id

    @property
    def feature_id(self) -> str:
        """Get the feature identifier."""
        return self._feature_id

    @property
    def device_id(self) -> str:
        """Get the device identifier."""
        return self._device_id

    @property
    def entity_type(self) -> str:
        """Get the entity type."""
        return self._entity_type

    @property
    def context(self) -> dict[str, Any]:
        """Get the creation context (defensive copy)."""
        return self._context.copy()

    @property
    def record_id(self) -> str:
        """Get the unique record identifier."""
        return self._record_id

    @property
    def timestamp(self) -> datetime:
        """Get the creation timestamp."""
        return self._timestamp

    @property
    def cleanup_eligible(self) -> bool:
        """Get whether this entity is eligible for cleanup."""
        return self._cleanup_eligible

    @property
    def cleanup_reason(self) -> str | None:
        """Get the cleanup reason."""
        return self._cleanup_reason

    @property
    def cleanup_timestamp(self) -> datetime | None:
        """Get the cleanup timestamp."""
        return self._cleanup_timestamp

    @property
    def verified_removed(self) -> bool:
        """Get whether removal has been verified."""
        return self._verified_removed

    @property
    def verification_timestamp(self) -> datetime | None:
        """Get the verification timestamp."""
        return self._verification_timestamp

    def mark_for_cleanup(self, reason: str) -> None:
        """Mark this entity as eligible for cleanup.

        Args:
            reason: The reason for cleanup
        """
        self._cleanup_eligible = True
        self._cleanup_reason = reason
        self._cleanup_timestamp = datetime.now()

    def verify_cleanup_completion(self) -> None:
        """Mark this entity's cleanup as verified complete."""
        self._verified_removed = True
        self._verification_timestamp = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary for serialization."""
        return {
            "record_id": self._record_id,
            "entity_id": self._entity_id,
            "feature_id": self._feature_id,
            "device_id": self._device_id,
            "entity_type": self._entity_type,
            "context": self._context.copy(),
            "timestamp": self._timestamp.isoformat(),
            "cleanup_eligible": self._cleanup_eligible,
            "cleanup_reason": self._cleanup_reason,
            "cleanup_timestamp": self._cleanup_timestamp.isoformat()
            if self._cleanup_timestamp
            else None,
            "verified_removed": self._verified_removed,
            "verification_timestamp": self._verification_timestamp.isoformat()
            if self._verification_timestamp
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityCreationRecord":
        """Create record from dictionary."""
        return cls(
            entity_id=data["entity_id"],
            feature_id=data["feature_id"],
            device_id=data["device_id"],
            entity_type=data["entity_type"],
            context=data["context"],
            record_id=data["record_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


class EntityCreationRegistry:
    """Immutable, append-only registry tracking every entity ever created.

    This class provides the foundation for the foolproof entity management system
    by maintaining a complete audit trail of all entity creations.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the EntityCreationRegistry.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._creation_log: list[EntityCreationRecord] = []  # Immutable append-only log
        self._entity_index: dict[
            str, EntityCreationRecord
        ] = {}  # entity_id -> creation_record
        self._feature_index: dict[str, list[str]] = {}  # feature_id -> [entity_ids]
        self._device_index: dict[str, list[str]] = {}  # device_id -> [entity_ids]
        self._cleanup_candidates: dict[
            str, EntityCreationRecord
        ] = {}  # entity_id -> record

    def log_entity_creation(
        self,
        entity_id: str,
        feature_id: str,
        device_id: str,
        entity_type: str,
        context: dict[str, Any],
    ) -> str:
        """Log every entity creation with full provenance.

        This method creates an immutable record with UUID, timestamp, and metadata,
        updates all indexes for fast lookup, and returns record_id for tracking.

        Args:
            entity_id: The entity identifier
            feature_id: The feature that created this entity
            device_id: The device this entity belongs to
            entity_type: The type of entity (sensor, switch, etc.)
            context: Additional context about the creation

        Returns:
            The record_id for tracking this creation event
        """
        # Create immutable record
        record = EntityCreationRecord(
            entity_id=entity_id,
            feature_id=feature_id,
            device_id=device_id,
            entity_type=entity_type,
            context=context,
        )

        # Add to immutable log (append-only)
        self._creation_log.append(record)

        # Update entity index
        self._entity_index[entity_id] = record

        # Update feature index
        if feature_id not in self._feature_index:
            self._feature_index[feature_id] = []
        if entity_id not in self._feature_index[feature_id]:
            self._feature_index[feature_id].append(entity_id)

        # Update device index
        if device_id not in self._device_index:
            self._device_index[device_id] = []
        if entity_id not in self._device_index[device_id]:
            self._device_index[device_id].append(entity_id)

        _LOGGER.info(
            f"Logged entity creation: {entity_id} (feature: {feature_id}, "
            f"device: {device_id})"
        )
        _LOGGER.debug(f"Creation context: {context}")

        return record.record_id

    def mark_for_cleanup(self, entity_id: str, reason: str) -> bool:
        """Mark entities eligible for removal.

        Args:
            entity_id: The entity identifier to mark for cleanup
            reason: The reason for cleanup

        Returns:
            True if marking was successful, False otherwise
        """
        if entity_id not in self._entity_index:
            _LOGGER.warning(f"Cannot mark non-existent entity for cleanup: {entity_id}")
            return False

        record = self._entity_index[entity_id]
        record.mark_for_cleanup(reason)

        # Add to cleanup candidates
        self._cleanup_candidates[entity_id] = record

        _LOGGER.info(f"Marked entity for cleanup: {entity_id} (reason: {reason})")
        return True

    def verify_cleanup_completion(self, entity_id: str) -> bool:
        """Confirm successful removal of an entity.

        Args:
            entity_id: The entity identifier to verify cleanup for

        Returns:
            True if verification was successful, False otherwise
        """
        if entity_id not in self._entity_index:
            _LOGGER.warning(
                f"Cannot verify cleanup for non-existent entity: {entity_id}"
            )
            return False

        record = self._entity_index[entity_id]
        record.verify_cleanup_completion()

        # Remove from cleanup candidates if present
        if entity_id in self._cleanup_candidates:
            del self._cleanup_candidates[entity_id]

        _LOGGER.info(f"Verified cleanup completion for entity: {entity_id}")
        return True

    def get_creation_provenance(self, entity_id: str) -> dict[str, Any] | None:
        """Get full audit trail for any entity.

        Args:
            entity_id: The entity identifier

        Returns:
            Complete provenance information or None if entity not found
        """
        if entity_id not in self._entity_index:
            return None

        record = self._entity_index[entity_id]
        provenance = {
            "record_id": record.record_id,
            "entity_id": record.entity_id,
            "feature_id": record.feature_id,
            "device_id": record.device_id,
            "entity_type": record.entity_type,
            "context": record.context,
            "timestamp": record.timestamp,
            "cleanup_eligible": record.cleanup_eligible,
            "cleanup_reason": record.cleanup_reason,
            "cleanup_timestamp": record.cleanup_timestamp,
            "verified_removed": record.verified_removed,
            "verification_timestamp": record.verification_timestamp,
        }

        return provenance  # noqa: RET504

    def get_entities_by_feature(self, feature_id: str) -> list[str]:
        """Get all entity IDs created by a specific feature.

        Args:
            feature_id: The feature identifier

        Returns:
            List of entity IDs created by this feature
        """
        return self._feature_index.get(feature_id, []).copy()

    def get_entities_by_device(self, device_id: str) -> list[str]:
        """Get all entity IDs created for a specific device.

        Args:
            device_id: The device identifier

        Returns:
            List of entity IDs created for this device
        """
        return self._device_index.get(device_id, []).copy()

    def get_all_creation_records(self) -> list[dict[str, Any]]:
        """Get all creation records in the registry.

        Returns:
            List of all creation records as dictionaries
        """
        return [record.to_dict() for record in self._creation_log]

    def get_cleanup_candidates(self) -> list[str]:
        """Get all entity IDs that are currently marked for cleanup.

        Returns:
            List of entity IDs marked for cleanup
        """
        return list(self._cleanup_candidates.keys())

    def get_entity_status(self, entity_id: str) -> dict[str, Any]:
        """Get comprehensive status information for an entity.

        Args:
            entity_id: The entity identifier

        Returns:
            Dictionary with entity status information
        """
        if entity_id not in self._entity_index:
            return {
                "entity_id": entity_id,
                "exists_in_registry": False,
                "message": "Entity not found in creation registry",
            }

        record = self._entity_index[entity_id]
        status = {
            "entity_id": entity_id,
            "exists_in_registry": True,
            "feature_id": record.feature_id,
            "device_id": record.device_id,
            "entity_type": record.entity_type,
            "created_at": record.timestamp,
            "cleanup_eligible": record.cleanup_eligible,
            "cleanup_reason": record.cleanup_reason,
            "verified_removed": record.verified_removed,
            "is_cleanup_candidate": entity_id in self._cleanup_candidates,
        }

        return status  # noqa: RET504

    def get_registry_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics about the registry.

        Returns:
            Dictionary with registry statistics
        """
        total_entities = len(self._creation_log)
        total_features = len(self._feature_index)
        total_devices = len(self._device_index)
        cleanup_candidates = len(self._cleanup_candidates)
        verified_removals = sum(
            1 for record in self._creation_log if record.verified_removed
        )

        # Count entities by type
        entity_type_counts: dict[str, int] = {}
        for record in self._creation_log:
            entity_type = record.entity_type
            entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + 1

        # Count entities by feature
        feature_entity_counts: dict[str, int] = {}
        for feature_id, entity_ids in self._feature_index.items():
            feature_entity_counts[feature_id] = len(entity_ids)

        return {
            "total_entities": total_entities,
            "total_features": total_features,
            "total_devices": total_devices,
            "cleanup_candidates": cleanup_candidates,
            "verified_removals": verified_removals,
            "entity_type_breakdown": entity_type_counts,
            "feature_entity_breakdown": feature_entity_counts,
            "creation_log_size": len(self._creation_log),
        }

    def validate_entity_existence(self, entity_id: str) -> bool:
        """Validate that an entity exists in the creation registry.

        Args:
            entity_id: The entity identifier

        Returns:
            True if entity exists in registry, False otherwise
        """
        return entity_id in self._entity_index

    def get_entities_requiring_cleanup(
        self, feature_id: str | None = None
    ) -> list[str]:
        """Get entities that require cleanup, optionally filtered by feature.

        Args:
            feature_id: Optional feature identifier to filter by

        Returns:
            List of entity IDs requiring cleanup
        """
        if feature_id:
            feature_entities = self.get_entities_by_feature(feature_id)
            return [
                entity_id
                for entity_id in feature_entities
                if entity_id in self._cleanup_candidates
            ]
        return list(self._cleanup_candidates.keys())

    def get_entities_requiring_verification(self) -> list[str]:
        """Get entities that have been marked for cleanup but not yet verified.

        Returns:
            List of entity IDs requiring verification
        """
        return [
            entity_id
            for entity_id, record in self._entity_index.items()
            if record.cleanup_eligible and not record.verified_removed
        ]

    async def perform_registry_integrity_check(self) -> dict[str, Any]:
        """Perform comprehensive integrity check of the registry.

        Returns:
            Dictionary with integrity check results
        """
        # Check for consistency between indexes
        integrity_issues: list[str] = []

        # Verify all entities in creation log are in entity index
        for record in self._creation_log:
            if record.entity_id not in self._entity_index:
                integrity_issues.append(
                    f"Entity {record.entity_id} in log but not in entity index"
                )

        # Verify all entities in entity index are in creation log
        for entity_id, record in self._entity_index.items():
            if record not in self._creation_log:
                integrity_issues.append(
                    f"Entity {entity_id} in index but not in creation log"
                )

        # Verify feature index consistency
        for feature_id, entity_ids in self._feature_index.items():
            for entity_id in entity_ids:
                if entity_id not in self._entity_index:
                    integrity_issues.append(
                        f"Entity {entity_id} in feature index but not in entity index"
                    )
                elif self._entity_index[entity_id].feature_id != feature_id:
                    integrity_issues.append(
                        f"Entity {entity_id} has inconsistent feature ID in indexes"
                    )

        # Verify device index consistency
        for device_id, entity_ids in self._device_index.items():
            for entity_id in entity_ids:
                if entity_id not in self._entity_index:
                    integrity_issues.append(
                        f"Entity {entity_id} in device index but not in entity index"
                    )
                elif self._entity_index[entity_id].device_id != device_id:
                    integrity_issues.append(
                        f"Entity {entity_id} has inconsistent device ID in indexes"
                    )

        integrity_status = "healthy" if not integrity_issues else "compromised"

        return {
            "status": integrity_status,
            "total_issues": len(integrity_issues),
            "issues": integrity_issues,
            "registry_size": len(self._creation_log),
            "index_consistency": {
                "entity_index_size": len(self._entity_index),
                "feature_index_size": len(self._feature_index),
                "device_index_size": len(self._device_index),
                "cleanup_candidates_size": len(self._cleanup_candidates),
            },
        }
