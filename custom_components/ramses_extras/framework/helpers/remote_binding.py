"""Remote binding registry for FAN→REM associations.

This module provides runtime management of remote bindings between REM devices
and FAN devices, following the configuration strategy defined in the REMOTE_BINDING
feature section.
"""

from __future__ import annotations

import logging
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

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._cache: dict[str, dict[str, Any]] = {}

    def _get_config_manager(self) -> ExtrasConfigManager | None:
        """Get the default feature's config manager.

        Returns:
            Config manager or None if not available
        """
        domain_data = self._hass.data.get(DOMAIN, {})
        config_entry = domain_data.get("config_entry")
        if config_entry is None:
            return None

        # Import here to avoid circular imports
        from ...framework.helpers.config.core import ExtrasConfigManager

        return ExtrasConfigManager(
            self._hass, config_entry, "default", {"enabled": False}
        )

    def get_binding_for_fan(self, device_id: str) -> dict[str, Any] | None:
        """Get the primary REM binding for a FAN device.

        Args:
            device_id: FAN device ID (canonical or legacy format)

        Returns:
            Binding dict with rem_id, role, enabled, source or None
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

        Args:
            device_id: FAN device ID

        Returns:
            REM device ID or None if no binding
        """
        binding = self.get_binding_for_fan(device_id)
        if binding is None:
            return None
        return binding.get("rem_id")

    def list_bindings(self) -> dict[str, list[dict[str, Any]]]:
        """List all FAN→REM bindings.

        Returns:
            Dict mapping FAN device IDs to lists of binding dicts
        """
        manager = self._get_config_manager()
        if manager is None:
            return {}

        # Import here to avoid circular imports
        from ...framework.helpers.config.model import (
            FEATURE_REMOTE_BINDING,
            get_fan_ids,
            get_feature_section,
        )

        section = get_feature_section(manager._config, FEATURE_REMOTE_BINDING)
        fan_ids = get_fan_ids(section)

        result: dict[str, list[dict[str, Any]]] = {}
        for fan_id in fan_ids:
            bindings = manager.get_fan_remote_bindings(fan_id)
            if bindings:
                result[fan_id] = bindings

        return result

    def is_rem_bound(self, rem_id: str) -> bool:
        """Check if a REM is bound to any FAN.

        Args:
            rem_id: REM device ID

        Returns:
            True if the REM is bound to at least one FAN
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

        Args:
            rem_id: REM device ID

        Returns:
            FAN device ID or None if not bound
        """
        normalized_rem = rem_id.replace("_", ":").strip()

        all_bindings = self.list_bindings()
        for fan_id, fan_bindings in all_bindings.items():
            for binding in fan_bindings:
                binding_rem = binding.get("rem_id", "").replace("_", ":").strip()
                if binding_rem == normalized_rem and binding.get("enabled", True):
                    return fan_id

        return None

    def invalidate_cache(self) -> None:
        """Clear the binding cache.

        Call this after config changes to ensure fresh lookups.
        """
        self._cache.clear()
        _LOGGER.debug("Remote binding cache invalidated")


def get_remote_binding_registry(hass: HomeAssistant) -> RemoteBindingRegistry:
    """Get or create the remote binding registry.

    Args:
        hass: Home Assistant instance

    Returns:
        RemoteBindingRegistry instance
    """
    domain_data = hass.data.setdefault(DOMAIN, {})

    if "remote_binding_registry" not in domain_data:
        domain_data["remote_binding_registry"] = RemoteBindingRegistry(hass)
        _LOGGER.debug("Created remote binding registry")

    return domain_data["remote_binding_registry"]  # type: ignore[no-any-return]


def async_setup_remote_binding(hass: HomeAssistant) -> None:
    """Set up remote binding infrastructure.

    Args:
        hass: Home Assistant instance
    """
    get_remote_binding_registry(hass)
    _LOGGER.info("Remote binding registry initialized")


__all__ = [
    "RemoteBindingRegistry",
    "get_remote_binding_registry",
    "async_setup_remote_binding",
]
