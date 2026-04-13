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

from .const import LOGGER, SIMULATOR_HGI_ID

# Canonical simulated device IDs used across profiles.
# IDs are chosen to be clearly fake/sim-only (not real hardware).
SIM_DEVICES: dict[str, dict[str, str]] = {
    # HVAC (dev_type prefixes from ramses_tx fingerprints)
    "FAN": {"id": "32:150000", "class": "FAN"},  # 32: Orcon MVS/VMD series
    "CO2": {"id": "37:120000", "class": "CO2"},  # 37: VMS-12C39 / VMS-17C01
    "HUM": {"id": "29:120000", "class": "HUM"},  # 29: VMS-17HB01
    "REM": {"id": "37:170000", "class": "REM"},  # 37: VMI-15WSJ53
    "DIS": {"id": "37:160000", "class": "DIS"},  # 37: same family as REM
    "RFS": {"id": "30:150000", "class": "RFS"},  # 30: internet gateway / RFS
    # Heat
    "CTL": {"id": "01:150000", "class": "CTL"},  # 01: controller
    "TRV": {"id": "04:150000", "class": "TRV"},  # 04: HR92 / HR91
    "DHW": {"id": "07:150000", "class": "DHW"},  # 07: DHW sensor
    "BDR": {"id": "13:150000", "class": "BDR"},  # 13: electrical relay
    "OTB": {"id": "10:150000", "class": "OTB"},  # 10: OpenTherm bridge
    "PRG": {"id": "23:150000", "class": "PRG"},  # 23: programmer
    "UFC": {"id": "02:150000", "class": "UFC"},  # 02: UFH controller
    "OUT": {"id": "17:150000", "class": "OUT"},  # 17: outdoor sensor
    "DTS": {"id": "12:150000", "class": "DTS"},  # 12: digital thermostat
    "HCW": {"id": "03:150000", "class": "HCW"},  # 03: analog thermostat
    "RND": {"id": "34:150000", "class": "RND"},  # 34: round thermostat T87RF
    "RFG": {"id": "30:160000", "class": "RFG"},  # 30: internet gateway (RFG)
    "THM": {"id": "22:150000", "class": "THM"},  # 22: digital thermostat DT4
    "JIM": {"id": "08:150000", "class": "JIM"},  # 08: Jasper interface
    "JST": {"id": "31:150000", "class": "JST"},  # 31: Jasper thermostat
}
_HGI_ENTRY: dict[str, dict] = {SIMULATOR_HGI_ID: {"class": "HGI"}}

# Flat slug → device_id lookup, e.g. SIM_DEVICE_ID["FAN"] == "32:150000"
SIM_DEVICE_ID: dict[str, str] = {slug: info["id"] for slug, info in SIM_DEVICES.items()}


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
        self._state_path = self._config_dir / "simulator_state.json"
        self._active_profile: str | None = None
        self._auto_answer: bool = True

        # Ensure config directory exists
        self._config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize built-in profiles
        self._init_builtin_profiles()

        # NOTE: file I/O is deferred — call async_initialize(hass) from async context

    def _init_builtin_profiles(self) -> None:
        """Initialize built-in system configuration profiles."""
        hvac_devices = ["FAN", "CO2", "REM"]
        heat_devices = ["CTL", "TRV", "DHW"]

        fan_id = SIM_DEVICES["FAN"]["id"]
        co2_id = SIM_DEVICES["CO2"]["id"]
        rem_id = SIM_DEVICES["REM"]["id"]
        ctl_id = SIM_DEVICES["CTL"]["id"]
        trv_id = SIM_DEVICES["TRV"]["id"]
        dhw_id = SIM_DEVICES["DHW"]["id"]

        def _known_list(*types: str) -> dict[str, dict]:
            entries = {
                SIM_DEVICES[t]["id"]: {"class": t} for t in types if t in SIM_DEVICES
            }
            return {**_HGI_ENTRY, **entries}

        # HVAC schema: FAN device ID is the top-level key (SCH_DEVICE_ID_ANY → SCH_VCS).
        # remotes = REM devices, sensors = CO2/sensor devices.
        _hvac_schema: dict = {fan_id: {"remotes": [rem_id], "sensors": [co2_id]}}

        # Heat schema: CTL device ID is the top-level key (SCH_DEVICE_ID_CTL → SCH_TCS).
        # zones: zone-index → {sensor: device_id}
        # stored_hotwater: {sensor: device_id}
        _heat_schema: dict = {
            ctl_id: {
                "zones": {"00": {"sensor": trv_id}},
                "stored_hotwater": {"sensor": dhw_id},
            }
        }

        self._profiles["normal"] = SystemConfigProfile(
            name="normal",
            description="Normal HVAC/heat environment, standard timeouts",
            timeout_scale=1.0,
            device_configs={
                "_known_list": _known_list(*hvac_devices, *heat_devices),
                "_enforce_known_list": {"enabled": True},
                "_schema": {**_hvac_schema, **_heat_schema},
            },
        )

        self._profiles["hvac_only"] = SystemConfigProfile(
            name="hvac_only",
            description="HVAC devices only (FAN, CO2, REM)",
            timeout_scale=1.0,
            device_configs={
                "_known_list": _known_list(*hvac_devices),
                "_enforce_known_list": {"enabled": True},
                "_schema": _hvac_schema,
            },
        )

        self._profiles["heat_only"] = SystemConfigProfile(
            name="heat_only",
            description="Heat devices only (CTL, TRV, DHW)",
            timeout_scale=1.0,
            device_configs={
                "_known_list": _known_list(*heat_devices),
                "_enforce_known_list": {"enabled": True},
                "_schema": _heat_schema,
            },
        )

        self._profiles["mixed"] = SystemConfigProfile(
            name="mixed",
            description="Mixed heat and HVAC environment",
            timeout_scale=1.0,
            device_configs={
                "_known_list": _known_list(*hvac_devices, *heat_devices),
                "_enforce_known_list": {"enabled": True},
                "_schema": {**_hvac_schema, **_heat_schema},
            },
        )

        self._profiles["fresh_start"] = SystemConfigProfile(
            name="fresh_start",
            description=(
                "Clean slate: only HGI gateway known, re-discover all devices"
            ),
            timeout_scale=1.0,
            device_configs={
                "_known_list": _HGI_ENTRY,
                "_enforce_known_list": {"enabled": True},
            },
        )

        LOGGER.debug(
            "ConfigProfileStore: initialized %d built-in profiles", len(self._profiles)
        )

    async def async_initialize(self, hass: object) -> None:
        """Load user profiles and state from disk (runs I/O in executor)."""
        import asyncio  # noqa: PLC0415

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_user_profiles)
        await loop.run_in_executor(None, self._load_state)

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

    def _load_state(self) -> None:
        """Load persisted simulator state (last active profile) from disk."""
        if not self._state_path.exists():
            return
        try:
            with open(self._state_path, encoding="utf-8") as f:
                data = json.load(f)
            self._active_profile = data.get("active_profile")
            self._auto_answer = data.get("auto_answer", True)
            LOGGER.debug(
                "ConfigProfileStore: state loaded profile=%s auto_answer=%s",
                self._active_profile,
                self._auto_answer,
            )
        except (json.JSONDecodeError, OSError):
            LOGGER.warning("ConfigProfileStore: failed to load simulator state")

    def _save_state(self) -> None:
        """Persist current simulator state (last active profile) to disk (sync)."""
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active_profile": self._active_profile,
                        "auto_answer": self._auto_answer,
                    },
                    f,
                )
        except OSError:
            LOGGER.warning("ConfigProfileStore: failed to save simulator state")

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

    def get_auto_answer(self) -> bool:
        """Return persisted auto-answer state."""
        return self._auto_answer

    def set_auto_answer(self, enabled: bool) -> None:
        """Set auto-answer state in memory; call async_save_state to persist."""
        self._auto_answer = enabled

    def set_active_profile(self, name: str) -> None:
        """Set the active profile name in memory; call async_save_state to persist."""
        self._active_profile = name

    async def async_save_state(self) -> None:
        """Persist simulator state to disk without blocking the event loop."""
        import asyncio

        profile = self._active_profile
        auto_answer = self._auto_answer
        state_path = self._state_path

        def _write() -> None:
            try:
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "active_profile": profile,
                            "auto_answer": auto_answer,
                        },
                        f,
                    )
            except OSError:
                LOGGER.warning("ConfigProfileStore: failed to save simulator state")

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _write)

    def get_active_profile(self) -> str | None:
        """Return the last persisted active profile name."""
        return self._active_profile

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


# Heartbeat timeout constant names in ramses_rf.const (as of current ramses_rf)
_HEARTBEAT_CONST_NAMES = [
    "HEARTBEAT_TIMEOUT_DEFAULT",
    "HEARTBEAT_TIMEOUT_OTB",
    "HEARTBEAT_TIMEOUT_TRV",
    "HEARTBEAT_TIMEOUT_REMOTE",
    "HEARTBEAT_TIMEOUT_SENSOR",
    "GATEWAY_MESSAGE_TIMEOUT",
]

# Consumer modules that import the constants by value (must also be patched)
_HEARTBEAT_CONSUMER_MODULES = [
    "ramses_rf.device.base",
    "ramses_rf.device.heat",
    "ramses_rf.device.hvac",
]


def apply_timeout_scale(scale: float) -> bool:
    """Apply timeout scaling to ramses_rf constants.

    Patches ramses_rf.const module constants and all consumer device modules
    that import them by value, to scale timeouts.

    :param scale: Scale factor (0.01 = 100x faster, 1.0 = normal)
    :return: True if applied successfully
    """
    global _original_timeout_values

    try:
        import importlib
        import importlib.util
        import sys

        import ramses_rf.const as const_module

        # Store originals once
        if _original_timeout_values is None:
            _original_timeout_values = {
                name: getattr(const_module, name)
                for name in _HEARTBEAT_CONST_NAMES
                if hasattr(const_module, name)
            }

        if not _original_timeout_values:
            LOGGER.warning(
                "SystemConfig: no known heartbeat constants found in ramses_rf.const"
            )
            return False

        # Patch const module
        for name, orig in _original_timeout_values.items():
            setattr(const_module, name, orig * scale)

        # Patch consumer modules (they imported the values by reference at load time)
        for mod_name in _HEARTBEAT_CONSUMER_MODULES:
            mod = sys.modules.get(mod_name) or (
                importlib.import_module(mod_name)
                if importlib.util.find_spec(mod_name)
                else None
            )
            if mod is None:
                continue
            for name, orig in _original_timeout_values.items():
                if hasattr(mod, name):
                    setattr(mod, name, orig * scale)

        LOGGER.info(
            "SystemConfig: applied timeout scale %.3f (%s)",
            scale,
            ", ".join(
                f"{n}={getattr(const_module, n)}"
                for n in list(_original_timeout_values)[:2]
            ),
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
    if not _original_timeout_values:
        LOGGER.debug("SystemConfig: no original values to restore")
        return False

    try:
        import sys

        import ramses_rf.const as const_module

        for name, orig in _original_timeout_values.items():
            setattr(const_module, name, orig)

        for mod_name in _HEARTBEAT_CONSUMER_MODULES:
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            for name, orig in _original_timeout_values.items():
                if hasattr(mod, name):
                    setattr(mod, name, orig)

        LOGGER.info("SystemConfig: restored default timeouts")
        return True

    except Exception:
        LOGGER.exception("SystemConfig: failed to restore timeouts")
        return False
