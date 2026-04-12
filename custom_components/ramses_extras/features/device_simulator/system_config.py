# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""System Configuration Profiles for Device Simulator.

Manages timeout scaling and configuration profiles for different test scenarios.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .const import LOGGER


@dataclass
class SystemConfigProfile:
    """Configuration profile for simulator behavior.

    :param name: Profile identifier
    :param description: Human-readable description
    :param timeout_scale: Multiplier for ramses_rf timeout constants
                           (0.01 = 100x faster)
    :param heartbeat_timeout_override_seconds: Optional absolute timeout override
    :param device_configs: Per-device configuration overrides
    :param scenario_hooks: Actions to take at scenario stages
    """

    name: str
    description: str = ""
    timeout_scale: float = 1.0
    heartbeat_timeout_override_seconds: float | None = None
    device_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenario_hooks: dict[str, list[str]] = field(default_factory=dict)
    speed_options: list[float] = field(default_factory=lambda: [1.0, 0.1, 0.01])

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemConfigProfile:
        """Create profile from dictionary."""
        return cls(**data)


class ConfigProfileStore:
    """Storage and management for system configuration profiles.

    Manages built-in and user-defined profiles, handles persistence
    and retrieval.
    """

    # Built-in profile names
    BUILTIN_PROFILES = {
        "normal": "Normal HVAC/heat environment",
        "hvac_only": "HVAC devices only (FAN, CO2, HUM, REM)",
        "heat_only": "Heat devices only (CTL, TRV, DHW)",
        "mixed": "Mixed heat + HVAC environment",
        "fresh_start": "Clean slate, re-discover all devices",
    }

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize the profile store.

        :param config_dir: Directory for storing user profiles
        """
        self._config_dir = config_dir or Path.home() / ".ramses_simulator"
        self._profiles: dict[str, SystemConfigProfile] = {}
        self._user_profiles_path = self._config_dir / "user_profiles.json"

        # Ensure config directory exists
        self._config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize built-in profiles
        self._init_builtin_profiles()

        # Load user profiles
        self._load_user_profiles()

    def _init_builtin_profiles(self) -> None:
        """Initialize built-in system configuration profiles."""
        self._profiles["normal"] = SystemConfigProfile(
            name="normal",
            description="Normal HVAC/heat environment, standard timeouts",
            timeout_scale=1.0,
        )

        self._profiles["hvac_only"] = SystemConfigProfile(
            name="hvac_only",
            description="HVAC devices only (FAN, CO2, HUM, REM)",
            timeout_scale=1.0,
            device_configs={
                "CTL": {"enabled": False},
                "TRV": {"enabled": False},
                "DHW": {"enabled": False},
                "PRG": {"enabled": False},
            },
        )

        self._profiles["heat_only"] = SystemConfigProfile(
            name="heat_only",
            description="Heat devices only (CTL, TRV, DHW, etc.)",
            timeout_scale=1.0,
            device_configs={
                "FAN": {"enabled": False},
                "CO2": {"enabled": False},
                "HUM": {"enabled": False},
                "REM": {"enabled": False},
            },
        )

        self._profiles["mixed"] = SystemConfigProfile(
            name="mixed",
            description="Mixed heat and HVAC environment",
            timeout_scale=1.0,
        )

        self._profiles["fresh_start"] = SystemConfigProfile(
            name="fresh_start",
            description=(
                "Clean slate: only HGI gateway known, re-discover all devices"
            ),
            timeout_scale=1.0,
            device_configs={
                "_known_list": {"18:001234": {"class": "HGI"}},
                "_clear_cache_on_load": {"enabled": True},
            },
        )

        LOGGER.debug(
            "ConfigProfileStore: initialized %d built-in profiles", len(self._profiles)
        )

    def _load_user_profiles(self) -> None:
        """Load user-defined profiles from disk."""
        if not self._user_profiles_path.exists():
            return

        try:
            with open(self._user_profiles_path, encoding="utf-8") as f:
                data = json.load(f)

            for name, profile_data in data.get("profiles", {}).items():
                self._profiles[name] = SystemConfigProfile.from_dict(profile_data)

            LOGGER.debug(
                "ConfigProfileStore: loaded %d user profiles",
                len(data.get("profiles", {})),
            )
        except (json.JSONDecodeError, OSError, TypeError):
            LOGGER.warning(
                "ConfigProfileStore: failed to load user profiles from %s",
                self._user_profiles_path,
            )

    def _save_user_profiles(self) -> None:
        """Save user-defined profiles to disk."""
        # Filter out built-in profiles
        user_profiles = {
            name: profile.to_dict()
            for name, profile in self._profiles.items()
            if name not in self.BUILTIN_PROFILES
        }

        data = {"profiles": user_profiles}

        try:
            with open(self._user_profiles_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            LOGGER.warning(
                "ConfigProfileStore: failed to save user profiles to %s",
                self._user_profiles_path,
            )

    def get_profile(self, name: str) -> SystemConfigProfile | None:
        """Get a configuration profile by name.

        :param name: Profile name
        :return: Profile or None if not found
        """
        return self._profiles.get(name)

    def list_profiles(self) -> list[str]:
        """List all available profile names.

        :return: List of profile names
        """
        return list(self._profiles.keys())

    def list_builtin_profiles(self) -> list[str]:
        """List built-in profile names.

        :return: List of built-in profile names
        """
        return list(self.BUILTIN_PROFILES.keys())

    def save_profile(self, profile: SystemConfigProfile) -> bool:
        """Save a user-defined profile.

        :param profile: Profile to save
        :return: True if saved successfully
        """
        self._profiles[profile.name] = profile
        self._save_user_profiles()
        LOGGER.debug("ConfigProfileStore: saved profile '%s'", profile.name)
        return True

    def delete_profile(self, name: str) -> bool:
        """Delete a user-defined profile.

        :param name: Profile name to delete
        :return: True if deleted, False if built-in or not found
        """
        if name in self.BUILTIN_PROFILES:
            LOGGER.warning(
                "ConfigProfileStore: cannot delete built-in profile '%s'", name
            )
            return False

        if name not in self._profiles:
            return False

        del self._profiles[name]
        self._save_user_profiles()
        LOGGER.debug("ConfigProfileStore: deleted profile '%s'", name)
        return True

    def export_profile(self, name: str) -> dict[str, Any] | None:
        """Export a profile as dictionary (for bug reports/sharing).

        :param name: Profile name
        :return: Profile dict or None if not found
        """
        profile = self._profiles.get(name)
        if profile:
            return profile.to_dict()
        return None

    def import_profile(self, data: dict[str, Any], name: str | None = None) -> bool:
        """Import a profile from dictionary.

        :param data: Profile data
        :param name: Optional new name for the profile
        :return: True if imported successfully
        """
        try:
            profile = SystemConfigProfile.from_dict(data)
            if name:
                profile.name = name
            return self.save_profile(profile)
        except (TypeError, ValueError):
            LOGGER.warning("ConfigProfileStore: failed to import profile")
            return False


# Module-level storage for original timeout values
_original_timeout_values: dict[str, float] | None = None


def apply_timeout_scale(scale: float) -> bool:
    """Apply timeout scaling to ramses_rf constants.

    Patches ramses_rf.const module constants to scale timeouts.
    This should be called before ramses_cc processes any messages.

    :param scale: Scale factor (0.01 = 100x faster, 1.0 = normal)
    :return: True if applied successfully
    """
    global _original_timeout_values

    try:
        # Import ramses_rf constants module
        from ramses_rf.const import (
            DEFAULT_HEARTBEAT_INTERVAL,
            DEFAULT_HEARTBEAT_TIMEOUT,
        )

        # Store original values if not already stored
        if _original_timeout_values is None:
            _original_timeout_values = {
                "DEFAULT_HEARTBEAT_INTERVAL": DEFAULT_HEARTBEAT_INTERVAL,
                "DEFAULT_HEARTBEAT_TIMEOUT": DEFAULT_HEARTBEAT_TIMEOUT,
            }

        # Apply scaling
        import ramses_rf.const as const_module

        const_module.DEFAULT_HEARTBEAT_INTERVAL = (
            _original_timeout_values["DEFAULT_HEARTBEAT_INTERVAL"] * scale
        )
        const_module.DEFAULT_HEARTBEAT_TIMEOUT = (
            _original_timeout_values["DEFAULT_HEARTBEAT_TIMEOUT"] * scale
        )

        LOGGER.info(
            "SystemConfig: applied timeout scale %.3f (interval=%.1fs, timeout=%.1fs)",
            scale,
            const_module.DEFAULT_HEARTBEAT_INTERVAL,
            const_module.DEFAULT_HEARTBEAT_TIMEOUT,
        )
        return True

    except ImportError:
        LOGGER.warning("SystemConfig: could not import ramses_rf.const for patching")
        return False
    except Exception:
        LOGGER.exception("SystemConfig: failed to apply timeout scale")
        return False


def restore_default_timeouts() -> bool:
    """Restore original ramses_rf timeout values.

    :return: True if restored successfully
    """
    if not hasattr(apply_timeout_scale, "_original_values"):
        LOGGER.debug("SystemConfig: no original values to restore")
        return False

    try:
        import ramses_rf.const as const_module

        original = apply_timeout_scale._original_values
        const_module.DEFAULT_HEARTBEAT_INTERVAL = original["DEFAULT_HEARTBEAT_INTERVAL"]
        const_module.DEFAULT_HEARTBEAT_TIMEOUT = original["DEFAULT_HEARTBEAT_TIMEOUT"]

        LOGGER.info("SystemConfig: restored default timeouts")
        return True

    except Exception:
        LOGGER.exception("SystemConfig: failed to restore timeouts")
        return False
