"""Remote binding registry for FAN→REM associations.

This module provides runtime management of remote bindings between REM devices
and FAN devices, following the configuration strategy defined in the REMOTE_BINDING
feature section.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ...const import DOMAIN

if TYPE_CHECKING:
    from ...framework.helpers.config.core import ExtrasConfigManager

_LOGGER = logging.getLogger(__name__)


class RemoteBindingRegistry:
    """Runtime registry for FAN→REM bindings.

    This registry provides fast in-memory lookup of bindings backed by
    the persisted remote_binding feature configuration.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the binding registry.

        :param hass: Home Assistant instance
        """
        self._hass = hass
        self._cache: dict[str, dict[str, Any]] = {}
        self._last_seen: dict[str, datetime] = {}
        self._last_activity_by_fan: dict[str, dict[str, Any]] = {}
        self._unmatched_traffic: list[dict[str, Any]] = []

    def record_remote_activity(
        self,
        rem_id: str,
        fan_id: str | None = None,
        command: str | None = None,
        matched: bool = True,
    ) -> None:
        """Record remote button press activity.

        :param rem_id: REM device ID
        :param fan_id: Target FAN device ID if known
        :param command: Command that was sent
        :param matched: Whether the REM was matched to a FAN
        """
        normalized_rem = rem_id.replace("_", ":").strip()
        now = datetime.now()

        # Update last seen timestamp
        self._last_seen[normalized_rem] = now

        # Record unmatched traffic for diagnostics
        if not matched:
            self._unmatched_traffic.append(
                {
                    "rem_id": normalized_rem,
                    "fan_id": fan_id,
                    "command": command,
                    "timestamp": now.isoformat(),
                }
            )
            # Keep only last 100 unmatched entries
            if len(self._unmatched_traffic) > 100:
                self._unmatched_traffic = self._unmatched_traffic[-100:]
            _LOGGER.debug("Unmatched remote traffic from %s", normalized_rem)

        if matched and fan_id and command:
            normalized_fan = fan_id.replace("_", ":").strip()
            if normalized_fan:
                self._last_activity_by_fan[normalized_fan] = {
                    "rem_id": normalized_rem,
                    "fan_id": normalized_fan,
                    "command": command,
                    "timestamp": now.isoformat(),
                }

    def get_last_seen(self, rem_id: str) -> datetime | None:
        """Get last seen timestamp for a REM.

        :param rem_id: REM device ID
        :return: Last seen datetime or None if never seen
        """
        normalized_rem = rem_id.replace("_", ":").strip()
        return self._last_seen.get(normalized_rem)

    def get_last_activity_for_fan(self, fan_id: str) -> dict[str, Any] | None:
        """Get the most recent remote activity for a specific FAN device.

        :param fan_id: FAN device ID
        :return: Activity dict with rem_id, command, timestamp, or None if no activity
        """
        normalized_fan = fan_id.replace("_", ":").strip()
        if not normalized_fan:
            return None
        activity = self._last_activity_by_fan.get(normalized_fan)
        return dict(activity) if isinstance(activity, dict) else None

    def get_unmatched_traffic(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent unmatched remote traffic.

        :param limit: Maximum number of entries to return
        :return: List of unmatched traffic entries
        """
        return self._unmatched_traffic[-limit:]

    def clear_unmatched_traffic(self) -> None:
        """Clear unmatched traffic history."""
        self._unmatched_traffic.clear()
        _LOGGER.debug("Unmatched traffic history cleared")

    def get_diagnostics(self) -> dict[str, Any]:
        """Get diagnostic information about bindings.

        :return: Dictionary with binding diagnostics
        """
        all_bindings = self.list_bindings()
        total_bindings = sum(len(b) for b in all_bindings.values())

        return {
            "bindings_count": len(all_bindings),
            "total_entries": total_bindings,
            "last_seen_count": len(self._last_seen),
            "unmatched_count": len(self._unmatched_traffic),
            "cache_size": len(self._cache),
        }

    def _get_config_manager(self) -> ExtrasConfigManager | None:
        """Get the default feature's config manager.

        :return: Config manager or None if not available
        """
        domain_data = self._hass.data.get(DOMAIN, {})
        config_entry = domain_data.get("config_entry")
        if config_entry is None:
            return None

        # Import here to avoid circular imports
        from ...framework.helpers.config.core import ExtrasConfigManager

        manager = ExtrasConfigManager(
            self._hass, config_entry, "default", {"enabled": False}
        )

        manager._config = manager._default_config.copy()
        if config_entry.data:
            manager._config.update(config_entry.data)
        if config_entry.options:
            manager._config.update(config_entry.options)
        return manager

    def get_binding_for_fan(self, device_id: str) -> dict[str, Any] | None:
        """Get the primary REM binding for a FAN device.

        :param device_id: FAN device ID (canonical or legacy format)
        :return: Binding dict with rem_id, role, enabled, source or None
        """
        # Normalize device ID for consistent lookup
        normalized_id = device_id.replace("_", ":").strip()

        # Check cache first
        if normalized_id in self._cache:
            return self._cache[normalized_id]

        # Load from config
        manager = self._get_config_manager()
        if manager is None:
            return None

        bindings = manager.get_fan_remote_bindings(normalized_id)
        if not bindings:
            return None

        # Return first enabled binding (primary)
        for binding in bindings:
            if binding.get("enabled", True):
                self._cache[normalized_id] = binding
                return binding

        # No enabled binding found
        return None

    def get_rem_id_for_fan(self, device_id: str) -> str | None:
        """Get the REM device ID bound to a FAN.

        :param device_id: FAN device ID
        :return: REM device ID or None if no binding
        """
        binding = self.get_binding_for_fan(device_id)
        if binding is None:
            return None
        return binding.get("rem_id")

    def list_bindings(self) -> dict[str, list[dict[str, Any]]]:
        """List all FAN→REM bindings.

        :return: Dict mapping FAN device IDs to lists of binding dicts
        """
        manager = self._get_config_manager()
        if manager is None:
            return {}

        # Import here to avoid circular imports
        from ...framework.helpers.config.model import (
            get_fan_ids,
            get_feature_section,
        )

        section = get_feature_section(manager._config, "remote_binding")
        fan_ids = get_fan_ids(section)

        result: dict[str, list[dict[str, Any]]] = {}
        for fan_id in fan_ids:
            bindings = manager.get_fan_remote_bindings(fan_id)
            if bindings:
                result[fan_id] = bindings

        return result

    def is_rem_bound(self, rem_id: str) -> bool:
        """Check if a REM is bound to any FAN.

        :param rem_id: REM device ID
        :return: True if the REM is bound to at least one FAN
        """
        normalized_rem = rem_id.replace("_", ":").strip()

        all_bindings = self.list_bindings()
        for fan_bindings in all_bindings.values():
            for binding in fan_bindings:
                binding_rem = binding.get("rem_id", "").replace("_", ":").strip()
                if binding_rem == normalized_rem and binding.get("enabled", True):
                    return True

        return False

    def find_fan_for_rem(self, rem_id: str) -> str | None:
        """Find the FAN device that a REM is bound to.

        :param rem_id: REM device ID
        :return: FAN device ID or None if not bound
        """
        normalized_rem = rem_id.replace("_", ":").strip()

        all_bindings = self.list_bindings()
        for fan_id, fan_bindings in all_bindings.items():
            for binding in fan_bindings:
                binding_rem = binding.get("rem_id", "").replace("_", ":").strip()
                if binding_rem == normalized_rem and binding.get("enabled", True):
                    return fan_id

        return None

    def detect_conflicts(self) -> list[dict[str, Any]]:
        """Detect binding conflicts where one REM is bound to multiple FANs.

        :return: List of conflict dictionaries with rem_id and list of bound FANs
        """
        conflicts: list[dict[str, Any]] = []
        all_bindings = self.list_bindings()

        # Map each REM to all FANs it's bound to
        rem_to_fans: dict[str, list[str]] = {}
        for fan_id, fan_bindings in all_bindings.items():
            for binding in fan_bindings:
                if not binding.get("enabled", True):
                    continue
                rem_id = binding.get("rem_id", "").replace("_", ":").strip()
                if rem_id:
                    if rem_id not in rem_to_fans:
                        rem_to_fans[rem_id] = []
                    rem_to_fans[rem_id].append(fan_id)

        # Find REMs bound to multiple FANs
        for rem_id, fan_list in rem_to_fans.items():
            if len(fan_list) > 1:
                conflicts.append(
                    {
                        "rem_id": rem_id,
                        "bound_fans": fan_list,
                        "conflict_type": "multi_fan",
                        "description": f"REM {rem_id} is bound to {len(fan_list)} FANs",
                    }
                )

        return conflicts

    def export_bindings_yaml(self) -> str:
        """Export all bindings as strict YAML for support/debugging.

        :return: YAML string representing the remote_binding feature section
        """
        import json

        all_bindings = self.list_bindings()

        # Build canonical feature section structure
        export_data: dict[str, Any] = {"features": {"remote_binding": {"FANs": {}}}}
        fans_section = export_data["features"]["remote_binding"]["FANs"]

        for fan_id, bindings in sorted(all_bindings.items()):
            fans_section[fan_id] = {"REMs": []}
            for binding in bindings:
                rem_entry: dict[str, Any] = {
                    "rem_id": binding.get("rem_id"),
                    "enabled": binding.get("enabled", True),
                }
                if "source" in binding:
                    rem_entry["source"] = binding["source"]
                if "zone_id" in binding:
                    rem_entry["zone_id"] = binding["zone_id"]
                if "area_id" in binding:
                    rem_entry["area_id"] = binding["area_id"]
                fans_section[fan_id]["REMs"].append(rem_entry)

        # Use JSON as a simple YAML-compatible serialization
        # For true YAML, we'd use PyYAML, but this keeps dependencies minimal
        return json.dumps(export_data, indent=2, sort_keys=True)

    def get_bindings_for_fan(self, device_id: str) -> list[dict[str, Any]]:
        """Get all enabled REM bindings for a FAN.

        :param device_id: FAN device ID
        :return: List of binding dicts
        """
        normalized_id = device_id.replace("_", ":").strip()

        manager = self._get_config_manager()
        if manager is None:
            return []

        bindings = manager.get_fan_remote_bindings(normalized_id)
        if not bindings:
            return []

        # Filter to enabled bindings only
        return [b for b in bindings if b.get("enabled", True)]

    def get_all_rem_ids_for_fan(self, device_id: str) -> list[str]:
        """Get all REM device IDs bound to a FAN.

        :param device_id: FAN device ID
        :return: List of REM device IDs
        """
        bindings = self.get_bindings_for_fan(device_id)
        return [str(b.get("rem_id")) for b in bindings if b.get("rem_id")]

    def _get_suggested_bindings(self) -> dict[str, list[dict[str, Any]]]:
        """Analyze unmatched traffic to suggest potential bindings.

        :return: Dict mapping FAN IDs to lists of suggested REM bindings
        """
        suggestions: dict[str, list[dict[str, Any]]] = {}

        # Group unmatched traffic by FAN
        fan_rems: dict[str, dict[str, dict[str, Any]]] = {}
        for entry in self._unmatched_traffic:
            fan_id = entry.get("fan_id")
            rem_id = entry.get("rem_id")
            if not fan_id or not rem_id:
                continue

            if fan_id not in fan_rems:
                fan_rems[fan_id] = {}

            if rem_id not in fan_rems[fan_id]:
                fan_rems[fan_id][rem_id] = {
                    "rem_id": rem_id,
                    "commands": [],
                    "first_seen": entry.get("timestamp"),
                    "count": 0,
                }

            fan_rems[fan_id][rem_id]["commands"].append(entry.get("command"))
            fan_rems[fan_id][rem_id]["count"] += 1

        # Build suggestions for FANs with frequent unmatched traffic
        for fan_id, rem_data in fan_rems.items():
            suggestions[fan_id] = []
            for rem_id, data in rem_data.items():
                # Only suggest if we have at least 3 observations
                if data["count"] >= 3:
                    suggestions[fan_id].append(
                        {
                            "rem_id": rem_id,
                            "observed_count": data["count"],
                            "commands_observed": list(set(data["commands"]))[-5:],
                            "confidence": min(data["count"] / 10.0, 1.0),
                        }
                    )

        return suggestions

    def get_binding_suggestions(self, fan_id: str | None = None) -> dict[str, Any]:
        """Get binding suggestions from observed traffic.

        :param fan_id: Optional FAN to filter suggestions for
        :return: Dict with suggested bindings and analysis info
        """
        all_suggestions = self._get_suggested_bindings()

        if fan_id:
            normalized = fan_id.replace("_", ":").strip()
            return {
                "fan_id": fan_id,
                "suggestions": all_suggestions.get(normalized, []),
            }

        return {
            "suggestions_by_fan": all_suggestions,
            "total_suggestions": sum(len(v) for v in all_suggestions.values()),
        }

    def invalidate_cache(self) -> None:
        """Clear the binding cache.

        Call this after config changes to ensure fresh lookups.
        """
        self._cache.clear()
        _LOGGER.debug("Remote binding cache invalidated")


def get_remote_binding_registry(hass: HomeAssistant) -> RemoteBindingRegistry:
    """Get or create the remote binding registry.

    :param hass: Home Assistant instance
    :return: RemoteBindingRegistry instance
    """
    domain_data = hass.data.setdefault(DOMAIN, {})

    if "remote_binding_registry" not in domain_data:
        domain_data["remote_binding_registry"] = RemoteBindingRegistry(hass)
        _LOGGER.debug("Created remote binding registry")

    return domain_data["remote_binding_registry"]  # type: ignore[no-any-return]


def async_setup_remote_binding(hass: HomeAssistant) -> None:
    """Set up remote binding infrastructure.

    :param hass: Home Assistant instance
    """
    get_remote_binding_registry(hass)
    _LOGGER.info("Remote binding registry initialized")


__all__ = [
    "RemoteBindingRegistry",
    "get_remote_binding_registry",
    "async_setup_remote_binding",
]
