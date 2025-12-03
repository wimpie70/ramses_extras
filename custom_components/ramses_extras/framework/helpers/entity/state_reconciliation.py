"""State Reconciliation System for Ramses Extras framework.

This module implements the StateReconciliationSystem class which provides
continuous validation of entity state consistency across the entire system.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from .atomic_cleanup import AtomicCleanupEngine
from .creation_registry import EntityCreationRegistry

_LOGGER = logging.getLogger(__name__)


class StateInconsistency:
    """Represents a detected state inconsistency in the system."""

    def __init__(
        self,
        inconsistency_type: str,
        entity_id: str,
        severity: str,
        description: str,
        detected_at: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a state inconsistency record.

        Args:
            inconsistency_type: Type of inconsistency (orphaned, zombie, missing, etc.)
            entity_id: Entity identifier
            severity: Severity level (low, medium, high, critical)
            description: Description of the inconsistency
            detected_at: Detection timestamp (auto-generated if None)
            context: Additional context about the inconsistency
        """
        self._inconsistency_type = inconsistency_type
        self._entity_id = entity_id
        self._severity = severity
        self._description = description
        self._detected_at = detected_at or datetime.now()
        self._context = context or {}
        self._resolved = False
        self._resolved_at: datetime | None = None
        self._resolution_method: str | None = None

    @property
    def inconsistency_type(self) -> str:
        """Get the inconsistency type."""
        return self._inconsistency_type

    @property
    def entity_id(self) -> str:
        """Get the entity identifier."""
        return self._entity_id

    @property
    def severity(self) -> str:
        """Get the severity level."""
        return self._severity

    @property
    def description(self) -> str:
        """Get the description."""
        return self._description

    @property
    def detected_at(self) -> datetime:
        """Get the detection timestamp."""
        return self._detected_at

    @property
    def context(self) -> dict[str, Any]:
        """Get the context (defensive copy)."""
        return self._context.copy()

    @property
    def resolved(self) -> bool:
        """Get whether the inconsistency has been resolved."""
        return self._resolved

    @property
    def resolved_at(self) -> datetime | None:
        """Get the resolution timestamp."""
        return self._resolved_at

    @property
    def resolution_method(self) -> str | None:
        """Get the resolution method."""
        return self._resolution_method

    def mark_as_resolved(self, resolution_method: str) -> None:
        """Mark the inconsistency as resolved.

        Args:
            resolution_method: Method used to resolve the inconsistency
        """
        self._resolved = True
        self._resolved_at = datetime.now()
        self._resolution_method = resolution_method

    def to_dict(self) -> dict[str, Any]:
        """Convert inconsistency to dictionary for serialization."""
        return {
            "inconsistency_type": self._inconsistency_type,
            "entity_id": self._entity_id,
            "severity": self._severity,
            "description": self._description,
            "detected_at": self._detected_at.isoformat(),
            "context": self._context.copy(),
            "resolved": self._resolved,
            "resolved_at": self._resolved_at.isoformat() if self._resolved_at else None,
            "resolution_method": self._resolution_method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateInconsistency":
        """Create inconsistency from dictionary."""
        inconsistency = cls(
            inconsistency_type=data["inconsistency_type"],
            entity_id=data["entity_id"],
            severity=data["severity"],
            description=data["description"],
            detected_at=datetime.fromisoformat(data["detected_at"]),
            context=data["context"],
        )
        inconsistency._resolved = data["resolved"]
        inconsistency._resolved_at = (
            datetime.fromisoformat(data["resolved_at"]) if data["resolved_at"] else None
        )
        inconsistency._resolution_method = data["resolution_method"]
        return inconsistency


class StateReconciliationSystem:
    """Continuous validation of entity state consistency.

    This class provides the state reconciliation functionality for the
    foolproof entity management system, ensuring that all components
    remain consistent and automatically correcting minor issues.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        creation_registry: EntityCreationRegistry,
        cleanup_engine: AtomicCleanupEngine,
    ) -> None:
        """Initialize the StateReconciliationSystem.

        Args:
            hass: Home Assistant instance
            creation_registry: Entity creation registry
            cleanup_engine: Atomic cleanup engine
        """
        self.hass = hass
        self._creation_registry = creation_registry
        self._cleanup_engine = cleanup_engine
        self._entity_registry = entity_registry.async_get(hass)
        self._reconciliation_interval = timedelta(minutes=5)  # Default: every 5 minutes
        self._reconciliation_task: asyncio.Task | None = None
        self._inconsistency_history: list[StateInconsistency] = []
        self._active_inconsistencies: dict[str, StateInconsistency] = {}
        self._reconciliation_stats: dict[str, Any] = {}
        self._running = False

    async def start_continuous_reconciliation(self) -> None:
        """Start the continuous reconciliation process.

        This method starts a background task that runs reconciliation
        at regular intervals.
        """
        if self._running:
            _LOGGER.warning("Reconciliation system is already running")
            return

        self._running = True
        _LOGGER.info("Starting continuous state reconciliation system")

        async def reconciliation_loop() -> None:
            """Main reconciliation loop."""
            while self._running:
                try:
                    start_time = datetime.now()
                    _LOGGER.info("Starting scheduled state reconciliation...")

                    # Perform comprehensive reconciliation
                    results = await self.perform_comprehensive_reconciliation()

                    # Log results
                    self._log_reconciliation_results(results)

                    # Update statistics
                    self._update_reconciliation_statistics(results)

                    # Sleep until next reconciliation
                    next_reconciliation = start_time + self._reconciliation_interval
                    now = datetime.now()
                    sleep_time = max(0, (next_reconciliation - now).total_seconds())
                    _LOGGER.debug(
                        f"Next reconciliation scheduled in {sleep_time:.1f} seconds"
                    )

                    await asyncio.sleep(sleep_time)

                except asyncio.CancelledError:
                    _LOGGER.info("Reconciliation loop cancelled")
                    break
                except Exception as e:
                    _LOGGER.error(f"Error in reconciliation loop: {e}")
                    # Wait before retrying
                    await asyncio.sleep(60)

        # Start the background task
        self._reconciliation_task = asyncio.create_task(reconciliation_loop())

    async def stop_continuous_reconciliation(self) -> None:
        """Stop the continuous reconciliation process."""
        if not self._running:
            _LOGGER.warning("Reconciliation system is not running")
            return

        self._running = False

        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
            self._reconciliation_task = None

        _LOGGER.info("Stopped continuous state reconciliation system")

    async def perform_comprehensive_reconciliation(self) -> dict[str, Any]:
        """Perform complete state validation every 5 minutes.

        This method implements the comprehensive reconciliation process:
        1. Cross-reference HA entity registry with our creation logs
        2. Detect inconsistencies (orphaned, zombie, missing entities)
        3. Auto-correct minor issues
        4. Alert on major issues
        5. Log complete results

        Returns:
            Dictionary with comprehensive reconciliation results
        """
        _LOGGER.info("Performing comprehensive state reconciliation...")

        results: dict[str, Any] = {
            "timestamp": datetime.now(),
            "inconsistencies": [],
            "auto_corrections": [],
            "critical_issues": [],
            "statistics": {},
            "reconciliation_duration_seconds": 0.0,
        }

        start_time = datetime.now()

        try:
            # 1. Cross-reference HA entity registry with our creation logs
            ha_entities = set(self._entity_registry.entities.keys())
            creation_registry_entities = set(
                self._creation_registry._entity_index.keys()
            )

            _LOGGER.debug(
                f"HA entity registry: {len(ha_entities)} entities, "
                f"Creation registry: {len(creation_registry_entities)} entities"
            )

            # 2. Detect inconsistencies
            inconsistencies = await self._detect_state_inconsistencies(
                ha_entities, creation_registry_entities
            )
            results["inconsistencies"] = inconsistencies

            # 3. Auto-correct minor issues
            auto_corrections = await self._auto_correct_inconsistencies(inconsistencies)
            results["auto_corrections"] = auto_corrections

            # 4. Identify critical issues that require manual attention
            critical_issues = self._identify_critical_issues(inconsistencies)
            results["critical_issues"] = critical_issues

            # 5. Generate statistics
            results["statistics"] = self._generate_reconciliation_statistics(
                ha_entities,
                creation_registry_entities,
                inconsistencies,
                auto_corrections,
                critical_issues,
            )

            # Log success
            _LOGGER.info(
                f"State reconciliation completed: "
                f"{len(inconsistencies)} inconsistencies detected, "
                f"{len(auto_corrections)} auto-corrected, "
                f"{len(critical_issues)} critical issues"
            )

        except Exception as e:
            _LOGGER.error(f"Error during comprehensive reconciliation: {e}")
            results["error"] = str(e)

        finally:
            # Calculate duration
            end_time = datetime.now()
            results["reconciliation_duration_seconds"] = (
                end_time - start_time
            ).total_seconds()

        return results

    async def _detect_state_inconsistencies(
        self, ha_entities: set[str], creation_registry_entities: set[str]
    ) -> list[dict[str, Any]]:
        """Detect inconsistencies between HA registry and creation logs.

        Args:
            ha_entities: Set of entity IDs in Home Assistant registry
            creation_registry_entities: Set of entity IDs in creation registry

        Returns:
            List of detected inconsistencies
        """
        inconsistencies: list[dict[str, Any]] = []

        # Detect orphaned entities (in HA but not in creation registry)
        orphaned_entities = ha_entities - creation_registry_entities
        for entity_id in orphaned_entities:
            try:
                ha_entity = self._entity_registry.entities[entity_id]
                inconsistency = StateInconsistency(
                    inconsistency_type="orphaned_entity",
                    entity_id=entity_id,
                    severity="medium",
                    description="Entity exists in HA but not tracked "
                    "in creation registry",
                    context={
                        "ha_entity_platform": ha_entity.platform,
                        "ha_entity_device_id": ha_entity.device_id,
                        "ha_entity_disabled_by": ha_entity.disabled_by,
                    },
                )
                inconsistencies.append(inconsistency.to_dict())
                self._active_inconsistencies[entity_id] = inconsistency
                self._inconsistency_history.append(inconsistency)

                _LOGGER.warning(f"Detected orphaned entity: {entity_id}")

            except Exception as e:
                _LOGGER.error(f"Error analyzing orphaned entity {entity_id}: {e}")

        # Detect zombie entities (in creation registry but not in HA,
        #  but not marked as removed)
        zombie_entities = creation_registry_entities - ha_entities
        for entity_id in zombie_entities:
            try:
                provenance = self._creation_registry.get_creation_provenance(entity_id)
                if provenance and not provenance["verified_removed"]:
                    inconsistency = StateInconsistency(
                        inconsistency_type="zombie_entity",
                        entity_id=entity_id,
                        severity="high",
                        description="Entity tracked in creation registry but missing "
                        "from HA (not verified as removed)",
                        context={
                            "feature_id": provenance["feature_id"],
                            "device_id": provenance["device_id"],
                            "entity_type": provenance["entity_type"],
                            "creation_timestamp": provenance["timestamp"].isoformat(),
                        },
                    )
                    inconsistencies.append(inconsistency.to_dict())
                    self._active_inconsistencies[entity_id] = inconsistency
                    self._inconsistency_history.append(inconsistency)

                    _LOGGER.warning(f"Detected zombie entity: {entity_id}")

            except Exception as e:
                _LOGGER.error(f"Error analyzing zombie entity {entity_id}: {e}")

        # Detect entities marked for cleanup but still existing
        cleanup_candidates = self._creation_registry.get_cleanup_candidates()
        for entity_id in cleanup_candidates:
            if entity_id in ha_entities:
                try:
                    provenance = self._creation_registry.get_creation_provenance(
                        entity_id
                    )
                    inconsistency = StateInconsistency(
                        inconsistency_type="pending_cleanup",
                        entity_id=entity_id,
                        severity="medium",
                        description="Entity marked for cleanup but still exists in HA",
                        context={
                            "cleanup_reason": provenance["cleanup_reason"]
                            if provenance
                            else "unknown",
                            "marked_for_cleanup_at": provenance[
                                "cleanup_timestamp"
                            ].isoformat()
                            if provenance and provenance["cleanup_timestamp"]
                            else "unknown",
                        },
                    )
                    inconsistencies.append(inconsistency.to_dict())
                    self._active_inconsistencies[entity_id] = inconsistency
                    self._inconsistency_history.append(inconsistency)

                    _LOGGER.warning(f"Detected pending cleanup entity: {entity_id}")

                except Exception as e:
                    _LOGGER.error(
                        f"Error analyzing pending cleanup entity {entity_id}: {e}"
                    )

        # Detect entities with inconsistent state between registries
        common_entities = ha_entities & creation_registry_entities
        for entity_id in common_entities:
            try:
                ha_entity = self._entity_registry.entities[entity_id]
                provenance = self._creation_registry.get_creation_provenance(entity_id)

                # Check for disabled entities that should be enabled
                if (
                    ha_entity.disabled_by is not None
                    and provenance
                    and provenance["enabled_by_feature"]
                ):
                    inconsistency = StateInconsistency(
                        inconsistency_type="disabled_entity",
                        entity_id=entity_id,
                        severity="low",
                        description="Entity disabled in HA but should be enabled "
                        "according to creation registry",
                        context={
                            "disabled_by": ha_entity.disabled_by,
                            "feature_id": provenance["feature_id"],
                            "entity_type": provenance["entity_type"],
                        },
                    )
                    inconsistencies.append(inconsistency.to_dict())
                    self._active_inconsistencies[entity_id] = inconsistency
                    self._inconsistency_history.append(inconsistency)

                    _LOGGER.warning(
                        f"Detected disabled entity that should be enabled: {entity_id}"
                    )

            except Exception as e:
                _LOGGER.error(
                    f"Error analyzing entity state consistency for {entity_id}: {e}"
                )

        _LOGGER.info(f"Detected {len(inconsistencies)} state inconsistencies")
        return inconsistencies

    async def _auto_correct_inconsistencies(
        self, inconsistencies: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Auto-correct minor inconsistencies.

        Args:
            inconsistencies: List of detected inconsistencies

        Returns:
            List of auto-correction results
        """
        auto_corrections: list[dict[str, Any]] = []

        for inconsistency_data in inconsistencies:
            try:
                inconsistency = StateInconsistency.from_dict(inconsistency_data)
                entity_id = inconsistency.entity_id

                # Skip if already resolved
                if inconsistency.resolved:
                    continue

                # Auto-correct orphaned entities (remove them)
                if inconsistency.inconsistency_type == "orphaned_entity":
                    correction_result = await self._auto_correct_orphaned_entity(
                        entity_id
                    )
                    if correction_result["success"]:
                        inconsistency.mark_as_resolved("auto_removal")
                        auto_corrections.append(
                            {
                                "entity_id": entity_id,
                                "inconsistency_type": "orphaned_entity",
                                "action": "removed",
                                "success": True,
                                "message": "Orphaned entity automatically removed",
                            }
                        )

                # Auto-correct pending cleanup entities
                elif inconsistency.inconsistency_type == "pending_cleanup":
                    correction_result = await self._auto_correct_pending_cleanup(
                        entity_id
                    )
                    if correction_result["success"]:
                        inconsistency.mark_as_resolved("auto_cleanup")
                        auto_corrections.append(
                            {
                                "entity_id": entity_id,
                                "inconsistency_type": "pending_cleanup",
                                "action": "cleaned_up",
                                "success": True,
                                "message": "Pending cleanup entity automatically "
                                "cleaned up",
                            }
                        )

                # Auto-correct disabled entities that should be enabled
                elif inconsistency.inconsistency_type == "disabled_entity":
                    correction_result = await self._auto_correct_disabled_entity(
                        entity_id
                    )
                    if correction_result["success"]:
                        inconsistency.mark_as_resolved("auto_reenabled")
                        auto_corrections.append(
                            {
                                "entity_id": entity_id,
                                "inconsistency_type": "disabled_entity",
                                "action": "reenabled",  # codespell: ignore
                                "success": True,
                                "message": "Disabled entity automatically re-enabled",  # codespell: ignore  # noqa: E501
                            }
                        )

                # Update the active inconsistency record
                self._active_inconsistencies[entity_id] = inconsistency

            except Exception as e:
                _LOGGER.error(
                    f"Error auto-correcting inconsistency for entity "
                    f"{inconsistency.entity_id}: {e}"
                )
                auto_corrections.append(
                    {
                        "entity_id": inconsistency.entity_id,
                        "inconsistency_type": inconsistency.inconsistency_type,
                        "action": "auto_correction_failed",
                        "success": False,
                        "error": str(e),
                    }
                )

        _LOGGER.info(f"Auto-corrected {len(auto_corrections)} inconsistencies")
        return auto_corrections

    async def _auto_correct_orphaned_entity(self, entity_id: str) -> dict[str, Any]:
        """Auto-correct an orphaned entity by removing it.

        Args:
            entity_id: Entity identifier to correct

        Returns:
            Dictionary with correction results
        """
        try:
            _LOGGER.info(f"Auto-correcting orphaned entity: {entity_id}")

            # Use atomic cleanup to remove the orphaned entity
            cleanup_result = await self._cleanup_engine.execute_atomic_cleanup(
                [entity_id], "auto_correction_orphaned_entity"
            )

            if cleanup_result["status"] == "success":
                return {
                    "success": True,
                    "entity_id": entity_id,
                    "action": "removed",
                    "message": "Orphaned entity successfully removed",
                }
            return {
                "success": False,
                "entity_id": entity_id,
                "action": "removal_failed",
                "error": cleanup_result.get("error", "Unknown cleanup error"),
            }

        except Exception as e:
            _LOGGER.error(f"Failed to auto-correct orphaned entity {entity_id}: {e}")
            return {
                "success": False,
                "entity_id": entity_id,
                "action": "removal_failed",
                "error": str(e),
            }

    async def _auto_correct_pending_cleanup(self, entity_id: str) -> dict[str, Any]:
        """Auto-correct a pending cleanup entity.

        Args:
            entity_id: Entity identifier to correct

        Returns:
            Dictionary with correction results
        """
        try:
            _LOGGER.info(f"Auto-correcting pending cleanup entity: {entity_id}")

            # Use atomic cleanup to remove the entity
            cleanup_result = await self._cleanup_engine.execute_atomic_cleanup(
                [entity_id], "auto_correction_pending_cleanup"
            )

            if cleanup_result["status"] == "success":
                return {
                    "success": True,
                    "entity_id": entity_id,
                    "action": "cleaned_up",
                    "message": "Pending cleanup entity successfully cleaned up",
                }
            return {
                "success": False,
                "entity_id": entity_id,
                "action": "cleanup_failed",
                "error": cleanup_result.get("error", "Unknown cleanup error"),
            }

        except Exception as e:
            _LOGGER.error(
                f"Failed to auto-correct pending cleanup entity {entity_id}: {e}"
            )
            return {
                "success": False,
                "entity_id": entity_id,
                "action": "cleanup_failed",
                "error": str(e),
            }

    async def _auto_correct_disabled_entity(self, entity_id: str) -> dict[str, Any]:
        """Auto-correct a disabled entity that should be enabled.

        Args:
            entity_id: Entity identifier to correct

        Returns:
            Dictionary with correction results
        """
        try:
            _LOGGER.info(f"Auto-correcting disabled entity: {entity_id}")

            # Re-enable the entity in Home Assistant
            if entity_id in self._entity_registry.entities:
                entity_entry = self._entity_registry.entities[entity_id]
                if entity_entry.disabled_by is not None:
                    # Re-enable the entity
                    self._entity_registry.async_update_entity(
                        entity_id, disabled_by=None
                    )
                    return {
                        "success": True,
                        "entity_id": entity_id,
                        "action": "reenabled",  # codespell: ignore
                        "message": "Disabled entity successfully re-enabled",
                    }
                return {
                    "success": False,
                    "entity_id": entity_id,
                    "action": "already_enabled",
                    "message": "Entity is already enabled",
                }
            return {
                "success": False,
                "entity_id": entity_id,
                "action": "entity_not_found",
                "error": "Entity not found in HA registry",
            }

        except Exception as e:
            _LOGGER.error(f"Failed to auto-correct disabled entity {entity_id}: {e}")
            return {
                "success": False,
                "entity_id": entity_id,
                "action": "reenable_failed",
                "error": str(e),
            }

    def _identify_critical_issues(
        self, inconsistencies: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Identify critical issues that require manual attention.

        Args:
            inconsistencies: List of detected inconsistencies

        Returns:
            List of critical issues
        """
        critical_issues: list[dict[str, Any]] = []

        for inconsistency_data in inconsistencies:
            try:
                inconsistency = StateInconsistency.from_dict(inconsistency_data)

                # Zombie entities are critical (high severity)
                if (
                    inconsistency.inconsistency_type == "zombie_entity"
                    and inconsistency.severity == "high"
                ):
                    critical_issues.append(
                        {
                            "entity_id": inconsistency.entity_id,
                            "type": "zombie_entity",
                            "severity": "critical",
                            "description": f"Zombie entity detected: "
                            f"{inconsistency.description}",
                            "context": inconsistency.context,
                            "recommended_action": "Manual investigation required - "
                            "entity exists in creation registry but missing from HA",
                        }
                    )

                # Multiple inconsistencies for same entity
                entity_inconsistencies = [
                    inc
                    for inc in inconsistencies
                    if StateInconsistency.from_dict(inc).entity_id
                    == inconsistency.entity_id
                ]
                if len(entity_inconsistencies) > 1:
                    critical_issues.append(
                        {
                            "entity_id": inconsistency.entity_id,
                            "type": "multiple_inconsistencies",
                            "severity": "critical",
                            "description": f"Entity has {len(entity_inconsistencies)} "
                            "different inconsistency types",
                            "context": {
                                "inconsistency_types": [
                                    StateInconsistency.from_dict(inc).inconsistency_type
                                    for inc in entity_inconsistencies
                                ]
                            },
                            "recommended_action": "Manual investigation required - "
                            "entity has multiple inconsistency types",
                        }
                    )

            except Exception as e:
                _LOGGER.error(
                    f"Error identifying critical issues for inconsistency: {e}"
                )

        return critical_issues

    def _generate_reconciliation_statistics(
        self,
        ha_entities: set[str],
        creation_registry_entities: set[str],
        inconsistencies: list[dict[str, Any]],
        auto_corrections: list[dict[str, Any]],
        critical_issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate comprehensive reconciliation statistics.

        Args:
            ha_entities: Set of HA entity IDs
            creation_registry_entities: Set of creation registry entity IDs
            inconsistencies: List of detected inconsistencies
            auto_corrections: List of auto-correction results
            critical_issues: List of critical issues

        Returns:
            Dictionary with reconciliation statistics
        """
        # Count entities by type in HA
        ha_entity_types: dict[str, int] = {}
        for entity_id in ha_entities:
            if entity_id in self._entity_registry.entities:
                entity = self._entity_registry.entities[entity_id]
                domain = entity.domain
                ha_entity_types[domain] = ha_entity_types.get(domain, 0) + 1

        # Count entities by type in creation registry
        creation_entity_types: dict[str, int] = {}
        for entity_id in creation_registry_entities:
            provenance = self._creation_registry.get_creation_provenance(entity_id)
            if provenance:
                entity_type = provenance["entity_type"]
                creation_entity_types[entity_type] = (
                    creation_entity_types.get(entity_type, 0) + 1
                )

        # Count inconsistencies by type
        inconsistency_types: dict[str, int] = {}
        for inconsistency_data in inconsistencies:
            inconsistency = StateInconsistency.from_dict(inconsistency_data)
            inconsistency_types[inconsistency.inconsistency_type] = (
                inconsistency_types.get(inconsistency.inconsistency_type, 0) + 1
            )

        # Count auto-corrections by type
        auto_correction_types: dict[str, int] = {}
        for correction in auto_corrections:
            if correction["success"]:
                action = correction["action"]
                auto_correction_types[action] = auto_correction_types.get(action, 0) + 1

        return {
            "ha_entity_count": len(ha_entities),
            "creation_registry_entity_count": len(creation_registry_entities),
            "orphaned_entities": len(ha_entities - creation_registry_entities),
            "zombie_entities": len(creation_registry_entities - ha_entities),
            "common_entities": len(ha_entities & creation_registry_entities),
            "ha_entity_type_breakdown": ha_entity_types,
            "creation_entity_type_breakdown": creation_entity_types,
            "total_inconsistencies": len(inconsistencies),
            "inconsistency_type_breakdown": inconsistency_types,
            "total_auto_corrections": len(auto_corrections),
            "successful_auto_corrections": sum(
                1 for c in auto_corrections if c["success"]
            ),
            "failed_auto_corrections": sum(
                1 for c in auto_corrections if not c["success"]
            ),
            "auto_correction_type_breakdown": auto_correction_types,
            "total_critical_issues": len(critical_issues),
            "critical_issue_types": [issue["type"] for issue in critical_issues],
            "reconciliation_coverage": {
                "ha_coverage": len(creation_registry_entities) / len(ha_entities)
                if ha_entities
                else 0.0,
                "creation_registry_coverage": len(ha_entities)
                / len(creation_registry_entities)
                if creation_registry_entities
                else 0.0,
            },
        }

    def _log_reconciliation_results(self, results: dict[str, Any]) -> None:
        """Log comprehensive reconciliation results.

        Args:
            results: Reconciliation results to log
        """
        try:
            # Log summary
            _LOGGER.info(
                f"State reconciliation results - "
                f"Inconsistencies: {results['statistics']['total_inconsistencies']}, "
                f"Auto-corrections: "
                f"{results['statistics']['successful_auto_corrections']}, "
                f"Critical issues: {len(results['critical_issues'])}"
            )

            # Log detailed statistics
            stats = results["statistics"]
            _LOGGER.debug(
                f"Entity coverage - HA: {stats['ha_entity_count']}, "
                f"Creation Registry: {stats['creation_registry_entity_count']}, "
                f"Common: {stats['common_entities']}"
            )

            # Log inconsistency breakdown
            if stats["inconsistency_type_breakdown"]:
                _LOGGER.debug(
                    f"Inconsistency breakdown: {stats['inconsistency_type_breakdown']}"
                )

            # Log auto-correction breakdown
            if stats["auto_correction_type_breakdown"]:
                _LOGGER.debug(
                    f"Auto-correction breakdown: "
                    f"{stats['auto_correction_type_breakdown']}"
                )

        except Exception as e:
            _LOGGER.error(f"Error logging reconciliation results: {e}")

    def _update_reconciliation_statistics(self, results: dict[str, Any]) -> None:
        """Update reconciliation statistics.

        Args:
            results: Reconciliation results to update statistics with
        """
        try:
            # Update overall statistics
            self._reconciliation_stats["total_reconciliations"] = (
                self._reconciliation_stats.get("total_reconciliations", 0) + 1
            )
            self._reconciliation_stats["last_reconciliation"] = datetime.now()

            # Update inconsistency statistics
            total_inconsistencies = results["statistics"]["total_inconsistencies"]
            self._reconciliation_stats["total_inconsistencies_detected"] = (
                self._reconciliation_stats.get("total_inconsistencies_detected", 0)
                + total_inconsistencies
            )

            # Update auto-correction statistics
            successful_corrections = results["statistics"][
                "successful_auto_corrections"
            ]
            self._reconciliation_stats["total_auto_corrections"] = (
                self._reconciliation_stats.get("total_auto_corrections", 0)
                + successful_corrections
            )

            # Update critical issue statistics
            critical_issues = len(results["critical_issues"])
            self._reconciliation_stats["total_critical_issues"] = (
                self._reconciliation_stats.get("total_critical_issues", 0)
                + critical_issues
            )

            _LOGGER.debug(
                f"Updated reconciliation statistics: {self._reconciliation_stats}"
            )

        except Exception as e:
            _LOGGER.error(f"Error updating reconciliation statistics: {e}")

    def get_reconciliation_statistics(self) -> dict[str, Any]:
        """Get comprehensive reconciliation statistics.

        Returns:
            Dictionary with reconciliation statistics
        """
        return self._reconciliation_stats.copy()

    def get_active_inconsistencies(self) -> list[dict[str, Any]]:
        """Get all currently active inconsistencies.

        Returns:
            List of active inconsistencies
        """
        return [inc.to_dict() for inc in self._active_inconsistencies.values()]

    def get_inconsistency_history(self) -> list[dict[str, Any]]:
        """Get complete inconsistency history.

        Returns:
            List of all detected inconsistencies
        """
        return [inc.to_dict() for inc in self._inconsistency_history]

    def get_inconsistencies_by_entity(self, entity_id: str) -> list[dict[str, Any]]:
        """Get all inconsistencies for a specific entity.

        Args:
            entity_id: Entity identifier

        Returns:
            List of inconsistencies for the entity
        """
        return [
            inc.to_dict()
            for inc in self._inconsistency_history
            if inc.entity_id == entity_id
        ]

    async def resolve_inconsistency(
        self, entity_id: str, resolution_method: str
    ) -> bool:
        """Manually resolve an inconsistency.

        Args:
            entity_id: Entity identifier
            resolution_method: Method used to resolve the inconsistency

        Returns:
            True if resolution was successful, False otherwise
        """
        try:
            if entity_id in self._active_inconsistencies:
                inconsistency = self._active_inconsistencies[entity_id]
                inconsistency.mark_as_resolved(resolution_method)

                _LOGGER.info(
                    f"Manually resolved inconsistency for entity {entity_id} using "
                    f"{resolution_method}"
                )
                return True
            _LOGGER.warning(f"No active inconsistency found for entity {entity_id}")
            return False

        except Exception as e:
            _LOGGER.error(f"Error resolving inconsistency for entity {entity_id}: {e}")
            return False

    async def perform_emergency_reconciliation(self) -> dict[str, Any]:
        """Perform an emergency reconciliation outside the normal schedule.

        Returns:
            Dictionary with emergency reconciliation results
        """
        _LOGGER.info("Performing emergency state reconciliation...")

        # Perform comprehensive reconciliation
        results = await self.perform_comprehensive_reconciliation()

        # Add emergency flag
        results["emergency_reconciliation"] = True
        results["triggered_by"] = "manual_emergency_trigger"

        return results

    async def check_system_health(self) -> dict[str, Any]:
        """Check overall system health based on reconciliation data.

        Returns:
            Dictionary with system health assessment
        """
        health_status: dict[str, Any] = {
            "status": "healthy",
            "issues": [],
            "metrics": {},
            "recommendations": [],
        }

        try:
            # Get current statistics
            stats = self._reconciliation_stats.copy()

            # Calculate health metrics
            total_reconciliations = stats.get("total_reconciliations", 0)
            if total_reconciliations > 0:
                avg_inconsistencies = (
                    stats.get("total_inconsistencies_detected", 0)
                    / total_reconciliations
                )
                avg_corrections = (
                    stats.get("total_auto_corrections", 0) / total_reconciliations
                )
                critical_issue_rate = (
                    stats.get("total_critical_issues", 0) / total_reconciliations
                )

                health_status["metrics"] = {
                    "average_inconsistencies_per_reconciliation": avg_inconsistencies,
                    "average_corrections_per_reconciliation": avg_corrections,
                    "critical_issue_rate": critical_issue_rate,
                    "reconciliation_frequency": "every_5_minutes",
                }

                # Determine health status
                if avg_inconsistencies > 10:
                    health_status["status"] = "degraded"
                    health_status["issues"].append("High average inconsistency rate")
                if critical_issue_rate > 0.5:
                    health_status["status"] = "critical"
                    health_status["issues"].append("High critical issue rate")

                # Add recommendations
                if avg_inconsistencies > 5:
                    health_status["recommendations"].append(
                        "Investigate root cause of high inconsistency rate"
                    )
                if critical_issue_rate > 0.1:
                    health_status["recommendations"].append(
                        "Address critical issues promptly"
                    )

            _LOGGER.info(f"System health assessment: {health_status['status']}")

        except Exception as e:
            _LOGGER.error(f"Error checking system health: {e}")
            health_status["status"] = "unknown"
            health_status["issues"].append(f"Health check error: {e}")

        return health_status

    async def get_comprehensive_system_report(self) -> dict[str, Any]:
        """Get a comprehensive report of the entire system state.

        Returns:
            Dictionary with comprehensive system report
        """
        report: dict[str, Any] = {
            "timestamp": datetime.now(),
            "system_health": await self.check_system_health(),
            "reconciliation_statistics": self.get_reconciliation_statistics(),
            "active_inconsistencies": self.get_active_inconsistencies(),
            "creation_registry_statistics": self._creation_registry.get_registry_statistics(),  # noqa: E501
            "cleanup_engine_statistics": self._cleanup_engine.get_cleanup_statistics(),
        }

        return report
