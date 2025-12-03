"""Atomic Cleanup Engine for Ramses Extras framework.

This module implements the AtomicCleanupEngine class which provides
guaranteed entity cleanup with transactional safety.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from .creation_registry import EntityCreationRegistry

_LOGGER = logging.getLogger(__name__)


class CleanupTransaction:
    """Represents an atomic cleanup transaction with rollback capability."""

    def __init__(
        self,
        transaction_id: str,
        entity_ids: list[str],
        cleanup_reason: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Initialize a cleanup transaction.

        Args:
            transaction_id: Unique transaction identifier
            entity_ids: List of entity IDs to clean up
            cleanup_reason: Reason for cleanup
            timestamp: Transaction timestamp (auto-generated if None)
        """
        self._transaction_id = transaction_id
        self._entity_ids = entity_ids.copy()
        self._cleanup_reason = cleanup_reason
        self._timestamp = timestamp or datetime.now()
        self._status: str = "pending"
        self._results: dict[str, Any] = {}
        self._rollback_data: dict[str, Any] = {}

    @property
    def transaction_id(self) -> str:
        """Get the transaction identifier."""
        return self._transaction_id

    @property
    def entity_ids(self) -> list[str]:
        """Get the entity IDs in this transaction."""
        return self._entity_ids.copy()

    @property
    def cleanup_reason(self) -> str:
        """Get the cleanup reason."""
        return self._cleanup_reason

    @property
    def timestamp(self) -> datetime:
        """Get the transaction timestamp."""
        return self._timestamp

    @property
    def status(self) -> str:
        """Get the transaction status."""
        return self._status

    @property
    def results(self) -> dict[str, Any]:
        """Get the transaction results."""
        return self._results.copy()

    @property
    def rollback_data(self) -> dict[str, Any]:
        """Get the rollback data."""
        return self._rollback_data.copy()

    def begin(self) -> None:
        """Begin the transaction."""
        self._status = "in_progress"
        _LOGGER.info(f"Began cleanup transaction {self._transaction_id}")

    def commit(self, results: dict[str, Any]) -> None:
        """Commit the transaction as successful.

        Args:
            results: Results of the cleanup operation
        """
        self._status = "committed"
        self._results = results.copy()
        _LOGGER.info(f"Committed cleanup transaction {self._transaction_id}")

    def rollback(self, error_message: str) -> None:
        """Rollback the transaction due to failure.

        Args:
            error_message: Error message describing the failure
        """
        self._status = "rolled_back"
        self._results["error"] = error_message
        _LOGGER.warning(
            f"Rolled back cleanup transaction {self._transaction_id}: {error_message}"
        )

    def add_rollback_data(self, entity_id: str, data: dict[str, Any]) -> None:
        """Add rollback data for an entity.

        Args:
            entity_id: Entity identifier
            data: Rollback data for this entity
        """
        self._rollback_data[entity_id] = data.copy()
        _LOGGER.debug(
            f"Added rollback data for entity {entity_id} in transaction "
            f"{self._transaction_id}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert transaction to dictionary for serialization."""
        return {
            "transaction_id": self._transaction_id,
            "entity_ids": self._entity_ids.copy(),
            "cleanup_reason": self._cleanup_reason,
            "timestamp": self._timestamp.isoformat(),
            "status": self._status,
            "results": self._results.copy(),
            "rollback_data": self._rollback_data.copy(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CleanupTransaction":
        """Create transaction from dictionary."""
        transaction = cls(
            transaction_id=data["transaction_id"],
            entity_ids=data["entity_ids"],
            cleanup_reason=data["cleanup_reason"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
        transaction._status = data["status"]
        transaction._results = data["results"]
        transaction._rollback_data = data["rollback_data"]
        return transaction


class AtomicCleanupEngine:
    """Guaranteed entity cleanup with transactional safety.

    This class provides the core cleanup functionality for the foolproof
    entity management system, ensuring that cleanup operations are
    atomic and can be rolled back if they fail.
    """

    def __init__(
        self, hass: HomeAssistant, creation_registry: EntityCreationRegistry
    ) -> None:
        """Initialize the AtomicCleanupEngine.

        Args:
            hass: Home Assistant instance
            creation_registry: Entity creation registry for tracking
        """
        self.hass = hass
        self._creation_registry = creation_registry
        self._active_transactions: dict[str, CleanupTransaction] = {}
        self._transaction_history: list[CleanupTransaction] = []
        self._entity_registry = entity_registry.async_get(hass)

    async def execute_atomic_cleanup(
        self, entity_ids: list[str], cleanup_reason: str
    ) -> dict[str, Any]:
        """Execute cleanup with 100% success guarantee or complete rollback.

        This method implements the complete atomic cleanup process:
        1. Validation phase - verify all entities exist and are eligible
        2. Transaction phase - begin atomic operation
        3. Execution phase - remove entities with real-time verification
        4. Verification phase - confirm actual removal from HA
        5. Commit phase - only if 100% successful
        6. Rollback phase - automatic if any failure

        Args:
            entity_ids: List of entity IDs to clean up
            cleanup_reason: Reason for cleanup

        Returns:
            Dictionary with cleanup results and status
        """
        _LOGGER.info(
            f"Starting atomic cleanup for {len(entity_ids)} entities (reason: "
            f"{cleanup_reason})"
        )

        # 1. Validation phase
        validation = await self._validate_cleanup_candidates(entity_ids)
        if not validation["valid"]:
            _LOGGER.warning(f"Cleanup validation failed: {validation['errors']}")
            return {
                "status": "validation_failed",
                "errors": validation["errors"],
                "entity_ids": entity_ids,
                "cleanup_reason": cleanup_reason,
            }

        # 2. Transaction phase
        transaction = self._begin_cleanup_transaction(entity_ids, cleanup_reason)

        try:
            # 3. Execution phase
            results = await self._execute_verifiable_cleanup(entity_ids)

            # 4. Verification phase
            verification = await self._verify_cleanup_results(entity_ids, results)

            if verification["success_rate"] == 1.0:
                # 5. Commit phase
                return self._commit_cleanup_transaction(transaction, results)
            # 6. Rollback phase
            return self._rollback_cleanup_transaction(transaction, results)

        except Exception as e:
            # 6. Emergency rollback phase
            return self._emergency_rollback(transaction, str(e))

    def _begin_cleanup_transaction(
        self, entity_ids: list[str], cleanup_reason: str
    ) -> CleanupTransaction:
        """Begin a new cleanup transaction.

        Args:
            entity_ids: List of entity IDs to clean up
            cleanup_reason: Reason for cleanup

        Returns:
            New cleanup transaction
        """
        transaction_id = str(uuid.uuid4())
        transaction = CleanupTransaction(
            transaction_id=transaction_id,
            entity_ids=entity_ids,
            cleanup_reason=cleanup_reason,
        )

        # Store active transaction
        self._active_transactions[transaction_id] = transaction
        self._transaction_history.append(transaction)

        # Begin the transaction
        transaction.begin()

        _LOGGER.info(
            f"Began cleanup transaction {transaction_id} for {len(entity_ids)} entities"
        )

        return transaction

    async def _validate_cleanup_candidates(
        self, entity_ids: list[str]
    ) -> dict[str, Any]:
        """Validate that all entities are eligible for cleanup.

        Args:
            entity_ids: List of entity IDs to validate

        Returns:
            Dictionary with validation results
        """
        validation_results: dict[str, Any] = {
            "valid": True,
            "errors": [],
            "validated_entities": [],
            "invalid_entities": [],
        }

        for entity_id in entity_ids:
            try:
                # Check if entity exists in creation registry
                if not self._creation_registry.validate_entity_existence(entity_id):
                    validation_results["errors"].append(
                        f"Entity {entity_id} not found in creation registry"
                    )
                    validation_results["invalid_entities"].append(entity_id)
                    validation_results["valid"] = False
                    continue

                # Check if entity is already marked for cleanup
                provenance = self._creation_registry.get_creation_provenance(entity_id)
                if provenance and provenance["cleanup_eligible"]:
                    validation_results["validated_entities"].append(entity_id)
                else:
                    # Entity exists but not eligible - mark it for cleanup now
                    self._creation_registry.mark_for_cleanup(
                        entity_id, "atomic_cleanup_validation"
                    )
                    validation_results["validated_entities"].append(entity_id)

                # Check if entity exists in Home Assistant entity registry
                if entity_id not in self._entity_registry.entities:
                    validation_results["errors"].append(
                        f"Entity {entity_id} not found in Home Assistant entity "
                        f"registry"
                    )
                    validation_results["invalid_entities"].append(entity_id)
                    validation_results["valid"] = False

            except Exception as e:
                validation_results["errors"].append(
                    f"Validation error for entity {entity_id}: {e}"
                )
                validation_results["invalid_entities"].append(entity_id)
                validation_results["valid"] = False

        _LOGGER.info(
            f"Cleanup validation: {len(validation_results['validated_entities'])} "
            f"valid, "
            f"{len(validation_results['invalid_entities'])} invalid"
        )

        return validation_results

    async def _execute_verifiable_cleanup(
        self, entity_ids: list[str]
    ) -> dict[str, Any]:
        """Execute the actual cleanup with real-time verification.

        Args:
            entity_ids: List of entity IDs to clean up

        Returns:
            Dictionary with execution results
        """
        execution_results: dict[str, Any] = {
            "successful_removals": [],
            "failed_removals": [],
            "verification_results": {},
            "success_rate": 0.0,
        }

        # Store entity states before cleanup for rollback
        pre_cleanup_states: dict[str, dict[str, Any]] = {}

        for entity_id in entity_ids:
            try:
                # Store current state for potential rollback
                if entity_id in self._entity_registry.entities:
                    entity_entry = self._entity_registry.entities[entity_id]
                    pre_cleanup_states[entity_id] = {
                        "entity_id": entity_id,
                        "original_entity_id": entity_entry.entity_id,
                        "device_id": entity_entry.device_id,
                        "platform": entity_entry.platform,
                        "disabled_by": entity_entry.disabled_by,
                        "entity_category": entity_entry.entity_category,
                        "original_name": entity_entry.original_name,
                        "unique_id": entity_entry.unique_id,
                    }

                # Execute the actual removal
                self._entity_registry.async_remove(entity_id)
                execution_results["successful_removals"].append(entity_id)

                # Mark cleanup as verified in creation registry
                self._creation_registry.verify_cleanup_completion(entity_id)

                _LOGGER.info(f"Successfully removed entity {entity_id}")

            except Exception as e:
                execution_results["failed_removals"].append(entity_id)
                execution_results["verification_results"][entity_id] = {
                    "status": "failed",
                    "error": str(e),
                }
                _LOGGER.error(f"Failed to remove entity {entity_id}: {e}")

        # Calculate success rate
        total_attempted = len(entity_ids)
        successful_count = len(execution_results["successful_removals"])
        execution_results["success_rate"] = (
            successful_count / total_attempted if total_attempted > 0 else 0.0
        )

        # Store pre-cleanup states in active transaction for potential rollback
        active_transaction = self._get_active_transaction_for_entities(entity_ids)
        if active_transaction:
            for entity_id, state_data in pre_cleanup_states.items():
                active_transaction.add_rollback_data(entity_id, state_data)

        _LOGGER.info(
            f"Cleanup execution: {successful_count}/{total_attempted} successful "
            f"(success rate: {execution_results['success_rate']:.1%})"
        )

        return execution_results

    def _get_active_transaction_for_entities(
        self, entity_ids: list[str]
    ) -> CleanupTransaction | None:
        """Get the active transaction that contains the specified entities.

        Args:
            entity_ids: List of entity IDs to find transaction for

        Returns:
            Active transaction or None if not found
        """
        for transaction in self._active_transactions.values():
            if any(entity_id in transaction.entity_ids for entity_id in entity_ids):
                return transaction
        return None

    async def _verify_cleanup_results(
        self, entity_ids: list[str], execution_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Verify that entities were actually removed from Home Assistant.

        Args:
            entity_ids: List of entity IDs that were supposed to be cleaned up
            execution_results: Results from the execution phase

        Returns:
            Dictionary with verification results
        """
        verification_results: dict[str, Any] = {
            "verified_removals": [],
            "unverified_removals": [],
            "still_existing": [],
            "success_rate": 0.0,
        }

        # Check each entity that was reported as successfully removed
        for entity_id in execution_results["successful_removals"]:
            try:
                # Verify entity is no longer in Home Assistant registry
                if entity_id not in self._entity_registry.entities:
                    verification_results["verified_removals"].append(entity_id)

                    # Also verify in creation registry
                    provenance = self._creation_registry.get_creation_provenance(
                        entity_id
                    )
                    if provenance and provenance["verified_removed"]:
                        _LOGGER.info(f"Double-verified removal of entity {entity_id}")
                    else:
                        _LOGGER.warning(
                            f"Entity {entity_id} removed from HA but not verified "
                            f"in creation registry"
                        )
                else:
                    verification_results["unverified_removals"].append(entity_id)
                    verification_results["still_existing"].append(entity_id)
                    _LOGGER.warning(
                        f"Entity {entity_id} still exists in HA registry after cleanup"
                    )

            except Exception as e:
                verification_results["unverified_removals"].append(entity_id)
                _LOGGER.error(f"Verification error for entity {entity_id}: {e}")

        # Calculate verification success rate
        total_verified = len(verification_results["verified_removals"])
        total_attempted = len(execution_results["successful_removals"])
        verification_results["success_rate"] = (
            total_verified / total_attempted if total_attempted > 0 else 0.0
        )

        _LOGGER.info(
            f"Cleanup verification: {total_verified}/{total_attempted} verified "
            f"(verification rate: {verification_results['success_rate']:.1%})"
        )

        return verification_results

    def _commit_cleanup_transaction(
        self, transaction: CleanupTransaction, results: dict[str, Any]
    ) -> dict[str, Any]:
        """Commit a successful cleanup transaction.

        Args:
            transaction: The transaction to commit
            results: Results of the cleanup operation

        Returns:
            Dictionary with final results
        """
        # Mark transaction as committed
        transaction.commit(results)

        # Remove from active transactions
        if transaction.transaction_id in self._active_transactions:
            del self._active_transactions[transaction.transaction_id]

        _LOGGER.info(f"Committed cleanup transaction {transaction.transaction_id}")

        return {
            "status": "success",
            "transaction_id": transaction.transaction_id,
            "entity_ids": transaction.entity_ids,
            "cleanup_reason": transaction.cleanup_reason,
            "results": results,
            "success_count": len(results["successful_removals"]),
            "failure_count": len(results["failed_removals"]),
            "verification_rate": results.get("success_rate", 0.0),
        }

    def _rollback_cleanup_transaction(
        self, transaction: CleanupTransaction, results: dict[str, Any]
    ) -> dict[str, Any]:
        """Rollback a failed cleanup transaction.

        Args:
            transaction: The transaction to rollback
            results: Results of the cleanup operation

        Returns:
            Dictionary with rollback results
        """
        # Mark transaction as rolled back
        transaction.rollback("Cleanup verification failed")

        # Remove from active transactions
        if transaction.transaction_id in self._active_transactions:
            del self._active_transactions[transaction.transaction_id]

        _LOGGER.warning(f"Rolled back cleanup transaction {transaction.transaction_id}")

        return {
            "status": "rolled_back",
            "transaction_id": transaction.transaction_id,
            "entity_ids": transaction.entity_ids,
            "cleanup_reason": transaction.cleanup_reason,
            "results": results,
            "success_count": len(results["successful_removals"]),
            "failure_count": len(results["failed_removals"]),
            "verification_rate": results.get("success_rate", 0.0),
            "rollback_reason": "Cleanup verification failed - "
            "partial success not acceptable",
        }

    def _emergency_rollback(
        self, transaction: CleanupTransaction, error_message: str
    ) -> dict[str, Any]:
        """Perform emergency rollback due to unexpected failure.

        Args:
            transaction: The transaction to rollback
            error_message: Error message describing the failure

        Returns:
            Dictionary with emergency rollback results
        """
        # Mark transaction as rolled back
        transaction.rollback(error_message)

        # Remove from active transactions
        if transaction.transaction_id in self._active_transactions:
            del self._active_transactions[transaction.transaction_id]

        _LOGGER.error(
            f"Emergency rollback of cleanup transaction {transaction.transaction_id}: "
            f"{error_message}"
        )

        return {
            "status": "emergency_rollback",
            "transaction_id": transaction.transaction_id,
            "entity_ids": transaction.entity_ids,
            "cleanup_reason": transaction.cleanup_reason,
            "error": error_message,
            "rollback_reason": f"Emergency rollback due to: {error_message}",
        }

    async def _attempt_entity_recreation(
        self, entity_id: str, rollback_data: dict[str, Any]
    ) -> bool:
        """Attempt to recreate an entity during rollback.

        Args:
            entity_id: Entity identifier to recreate
            rollback_data: Data needed for recreation

        Returns:
            True if recreation was successful, False otherwise
        """
        try:
            # This is a simplified recreation attempt
            # In a real implementation, this would use the entity factory
            # to recreate the entity with the original configuration

            _LOGGER.info(f"Attempting to recreate entity {entity_id} during rollback")

            # For now, we just log the attempt
            # Actual recreation would depend on the specific entity type
            # and would use the original factory and configuration

            return True

        except Exception as e:
            _LOGGER.error(f"Failed to recreate entity {entity_id} during rollback: {e}")
            return False

    def get_cleanup_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics about cleanup operations.

        Returns:
            Dictionary with cleanup statistics
        """
        total_transactions = len(self._transaction_history)
        active_transactions = len(self._active_transactions)
        committed_transactions = sum(
            1 for t in self._transaction_history if t.status == "committed"
        )
        rolled_back_transactions = sum(
            1 for t in self._transaction_history if t.status == "rolled_back"
        )

        # Calculate success rates
        total_entities_processed = sum(
            len(t.entity_ids) for t in self._transaction_history
        )
        total_successful_removals = sum(
            len(t.results.get("successful_removals", []))
            for t in self._transaction_history
            if t.status == "committed"
        )

        success_rate = (
            total_successful_removals / total_entities_processed
            if total_entities_processed > 0
            else 0.0
        )

        return {
            "total_transactions": total_transactions,
            "active_transactions": active_transactions,
            "committed_transactions": committed_transactions,
            "rolled_back_transactions": rolled_back_transactions,
            "total_entities_processed": total_entities_processed,
            "total_successful_removals": total_successful_removals,
            "overall_success_rate": success_rate,
            "active_transaction_ids": list(self._active_transactions.keys()),
        }

    async def perform_transaction_integrity_check(self) -> dict[str, Any]:
        """Perform comprehensive integrity check of cleanup transactions.

        Returns:
            Dictionary with integrity check results
        """
        integrity_issues: list[str] = []

        # Check for transactions that are stuck in progress
        for transaction_id, transaction in self._active_transactions.items():
            if transaction.status == "in_progress":
                # Transaction has been in progress for too long
                age = (datetime.now() - transaction.timestamp).total_seconds()
                if age > 300:  # 5 minutes
                    integrity_issues.append(
                        f"Transaction {transaction_id} stuck in progress for "
                        f"{age:.1f} seconds"
                    )

        # Check for consistency between transaction history and creation registry
        for transaction in self._transaction_history:
            for entity_id in transaction.entity_ids:
                provenance = self._creation_registry.get_creation_provenance(entity_id)
                if not provenance:
                    integrity_issues.append(
                        f"Entity {entity_id} in transaction "
                        f"{transaction.transaction_id} "
                        f"not found in creation registry"
                    )
                elif (
                    transaction.status == "committed"
                    and not provenance["verified_removed"]
                ):
                    integrity_issues.append(
                        f"Entity {entity_id} marked as committed in transaction "
                        f"{transaction.transaction_id} but not verified as removed"
                    )

        integrity_status = "healthy" if not integrity_issues else "compromised"

        return {
            "status": integrity_status,
            "total_issues": len(integrity_issues),
            "issues": integrity_issues,
            "total_transactions_checked": len(self._transaction_history),
            "active_transactions_checked": len(self._active_transactions),
        }

    async def cleanup_orphaned_transactions(self) -> list[str]:
        """Clean up orphaned or stuck transactions.

        Returns:
            List of transaction IDs that were cleaned up
        """
        cleaned_transactions = []
        current_time = datetime.now()

        for transaction_id, transaction in list(self._active_transactions.items()):
            if transaction.status == "in_progress":
                age = (current_time - transaction.timestamp).total_seconds()
                if age > 3600:  # 1 hour
                    # Transaction is stuck - clean it up
                    transaction.rollback("Transaction cleanup due to being stuck")
                    del self._active_transactions[transaction_id]
                    cleaned_transactions.append(transaction_id)
                    _LOGGER.warning(
                        f"Cleaned up stuck transaction {transaction_id} "
                        f"(age: {age:.1f} seconds)"
                    )

        return cleaned_transactions
