# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""System Configuration Profiles for Device Simulator.

Manages timeout scaling and configuration profiles for different test scenarios.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from ramses_tx.const import SZ_ACTUATORS, SZ_NAME

from .const import LOGGER, SIMULATOR_HGI_ID

# Canonical simulated device IDs used across profiles.
# IDs are chosen to be clearly fake/sim-only (not real hardware).
SIM_DEVICES: dict[str, dict[str, str]] = {
    "HGI": {"id": SIMULATOR_HGI_ID, "class": "HGI"},
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

_DEVICE_ID_SUFFIX_RE = re.compile(
    r"^(?P<prefix>\d{2}):(?P<body>\d{6})(?:_(?P<delta>\d+))?$"
)


def _normalize_device_id(device_id: str) -> str:
    """Convert pseudo IDs like '04:150000_03' into valid RAMSES addresses."""

    match = _DEVICE_ID_SUFFIX_RE.match(device_id)
    if not match:
        return device_id
    delta = match.group("delta")
    if not delta:
        return device_id
    try:
        base_value = int(match.group("body"))
        increment = int(delta)
    except TypeError, ValueError:
        return device_id
    normalized = base_value + increment
    return f"{match.group('prefix')}:{normalized:06d}"


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
    :param remove_database: Remove database file on profile activation
    :param clear_message_log: Clear in-memory message log ring buffer on profile
                             activation
    :param enable_auto_answer: Enable auto_answer when profile is loaded
    """

    name: str
    description: str = ""
    timeout_scale: float = 1.0
    heartbeat_timeout_override_seconds: float | None = None
    device_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenario_hooks: dict[str, list[str]] = field(default_factory=dict)
    source_yaml: str | None = None
    remove_database: bool = False
    clear_message_log: bool = False
    enable_auto_answer: bool = True

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
        "fresh_start_allow_unknown_devices": (
            "Clean slate with unknown device support (enforce_known_list disabled)"
        ),
        "fresh_start_allow_unknown_devices_fast_heartbeat": (
            "Clean slate with unknown device support and fast heartbeat (100x)"
        ),
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
        self._autonomous_speed: float = 1.0
        self._remove_database: bool = False
        self._answer_unknown_devices: bool = False
        self._preserve_state: bool = True

        # Ensure config directory exists
        self._config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize built-in profiles
        self._init_builtin_profiles()

        # NOTE: file I/O is deferred — call async_initialize(hass) from async context

    def _init_builtin_profiles(self) -> None:
        """Initialize built-in system configuration profiles."""
        hvac_devices = ["FAN", "CO2", "REM"]
        hvac_devices_extended = ["FAN", "CO2", "REM", "HUM"]

        fan_id = SIM_DEVICES["FAN"]["id"]
        co2_id = SIM_DEVICES["CO2"]["id"]
        rem_id = SIM_DEVICES["REM"]["id"]
        ctl_id = SIM_DEVICES["CTL"]["id"]
        trv_id = SIM_DEVICES["TRV"]["id"]
        dhw_id = SIM_DEVICES["DHW"]["id"]

        def _known_list(*types: str) -> dict[str, dict]:
            entries = {}
            for t in types:
                if t not in SIM_DEVICES:
                    continue
                entry: dict = {"class": t}
                if t == "FAN" and "REM" in types:
                    entry["bound"] = rem_id
                entries[SIM_DEVICES[t]["id"]] = entry
            return {**_HGI_ENTRY, **entries}

        multi_zone_heat: list[dict[str, Any]] = [
            {
                "zone_id": "03",
                "label": "Lounge",
                "sensor": "01:150000_03",
                "devices": ["04:150000_03"],
            },
            {
                "zone_id": "04",
                "label": "Hallway",
                "sensor": "01:150000_04",
                "devices": ["04:150000_04"],
            },
            {
                "zone_id": "05",
                "label": "Master bedroom",
                "sensor": "01:150000_05",
                "devices": ["04:150000_05"],
            },
            {
                "zone_id": "06",
                "label": "Guest bedroom",
                "sensor": "01:150000_06",
                "devices": ["04:150000_06"],
            },
            {
                "zone_id": "07",
                "label": "Kitchen",
                "sensor": "01:150000_07",
                "devices": ["04:150000_07"],
            },
            {
                "zone_id": "08",
                "label": "Office",
                "sensor": "01:150000_08",
                "devices": ["04:150000_08"],
            },
        ]

        heat_zone_known: dict[str, dict[str, Any]] = {}
        heat_zone_schema: dict[str, Any] = {}
        for zone in multi_zone_heat:
            sensor_id = _normalize_device_id(zone["sensor"])
            zone_id = zone["zone_id"]
            label = zone["label"]
            heat_zone_known[sensor_id] = {
                "class": "CTL",
                "alias": f"{label} sensor",
            }
            zone_devices = [
                _normalize_device_id(device_id) for device_id in zone.get("devices", [])
            ]
            for device_id in zone_devices:
                heat_zone_known[device_id] = {
                    "class": "TRV",
                    "alias": f"{label} valve",
                }
            heat_zone_schema[zone_id] = {
                f"_{SZ_NAME}": label,
                "sensor": sensor_id,
                SZ_ACTUATORS: zone_devices,
            }

        heat_only_known = {
            **_HGI_ENTRY,
            ctl_id: {"class": "CTL"},
            dhw_id: {"class": "DHW"},
            trv_id: {"class": "TRV"},
            **heat_zone_known,
        }

        # HVAC schema: FAN device ID is the top-level key (SCH_DEVICE_ID_ANY → SCH_VCS).
        # remotes = REM devices, sensors = CO2/sensor devices.
        _hvac_schema: dict = {fan_id: {"remotes": [rem_id], "sensors": [co2_id]}}

        # Heat schema: CTL device ID is the top-level key (SCH_DEVICE_ID_CTL → SCH_TCS).
        # zones: zone-index → {sensor: device_id}
        # stored_hotwater: {sensor: device_id}
        _heat_schema: dict = {
            ctl_id: {
                "zones": heat_zone_schema,
                "stored_hotwater": {"sensor": dhw_id},
            }
        }

        self._profiles["normal"] = SystemConfigProfile(
            name="normal",
            description="Balanced HVAC + multi-zone heat environment",
            timeout_scale=1.0,
            device_configs={
                "_known_list": {
                    **_known_list(*hvac_devices),
                    **heat_only_known,
                },
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
                "_known_list": heat_only_known,
                "_enforce_known_list": {"enabled": True},
                "_schema": _heat_schema,
            },
            remove_database=True,
        )

        self._profiles["heat_2"] = SystemConfigProfile(
            name="heat_2",
            description="Heat environment with fast heartbeat (100x)",
            timeout_scale=0.01,
            device_configs={
                "_known_list": {
                    "01:216136": {},
                    "04:034682": {},
                    "04:034684": {},
                    "04:034690": {},
                    "04:034692": {},
                    "04:034716": {},
                    "04:034720": {},
                    "04:034722": {},
                    "04:034726": {},
                    "04:036066": {},
                    "04:036068": {},
                    "04:056673": {},
                    "04:056675": {},
                    "04:056677": {},
                    "04:056679": {},
                    "04:106557": {},
                    "04:208990": {},
                    "04:208992": {},
                    "04:208994": {},
                    "04:208998": {},
                    "04:219929": {},
                    "07:050121": {},
                    "10:064873": {},
                    "13:042605": {},
                    "18:191664": {"class": "HGI"},
                    "22:012299": {},
                    "34:058721": {},
                },
                "_enforce_known_list": {"enabled": True},
            },
        )

        self._profiles["mixed"] = SystemConfigProfile(
            name="mixed",
            description="Full HVAC + extended multi-zone heat environment",
            timeout_scale=1.0,
            device_configs={
                "_known_list": {
                    **_known_list(*hvac_devices_extended),
                    **heat_only_known,
                },
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
            remove_database=True,
            clear_message_log=True,
        )

        self._profiles["fresh_start_allow_unknown_devices"] = SystemConfigProfile(
            name="fresh_start_allow_unknown_devices",
            description=(
                "Clean slate with unknown device support (enforce_known_list disabled)"
            ),
            timeout_scale=1.0,
            device_configs={
                "_known_list": _HGI_ENTRY,
                "_enforce_known_list": {"enabled": False},
            },
            remove_database=True,
            clear_message_log=True,
        )

        self._profiles["fresh_start_allow_unknown_devices_fast_heartbeat"] = (
            SystemConfigProfile(
                name="fresh_start_allow_unknown_devices_fast_heartbeat",
                description=(
                    "Clean slate with unknown device support and fast heartbeat (100x)"
                ),
                timeout_scale=0.01,
                device_configs={
                    "_known_list": _HGI_ENTRY,
                    "_enforce_known_list": {"enabled": False},
                },
                remove_database=True,
                clear_message_log=True,
            )
        )

        LOGGER.debug(
            "ConfigProfileStore: initialized %d built-in profiles", len(self._profiles)
        )

    async def async_initialize(self, hass: object) -> None:
        """Load user profiles and state from disk (runs I/O in executor)."""
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
        except json.JSONDecodeError, OSError, TypeError:
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
            self._preserve_state = data.get("preserve_state", True)
            # When preserve_state is False (Clean restart), reset auto_answer to False
            if self._preserve_state:
                self._auto_answer = data.get("auto_answer", True)
            else:
                self._auto_answer = False
            self._remove_database = data.get("remove_database", False)
            self._answer_unknown_devices = data.get("answer_unknown_devices", False)
            speed_value = data.get("autonomous_speed", 1.0)
            try:
                self._autonomous_speed = float(speed_value)
            except TypeError, ValueError:
                self._autonomous_speed = 1.0
            LOGGER.debug(
                "ConfigProfileStore: state loaded profile=%s auto_answer=%s "
                "speed=%s remove_db=%s answer_unknown=%s preserve_state=%s",
                self._active_profile,
                self._auto_answer,
                self._autonomous_speed,
                self._remove_database,
                self._answer_unknown_devices,
                self._preserve_state,
            )
        except json.JSONDecodeError, OSError:
            LOGGER.warning("ConfigProfileStore: failed to load simulator state")

    def _save_state(self) -> None:
        """Persist current simulator state (last active profile) to disk (sync)."""
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active_profile": self._active_profile,
                        "auto_answer": self._auto_answer,
                        "autonomous_speed": self._autonomous_speed,
                        "remove_database": self._remove_database,
                        "answer_unknown_devices": self._answer_unknown_devices,
                        "preserve_state": self._preserve_state,
                    },
                    f,
                )
        except OSError:
            LOGGER.warning("ConfigProfileStore: failed to save simulator state")

    def _user_profiles_payload(self) -> dict[str, Any]:
        """Return the dict that should be written to user_profiles.json."""
        return {
            "profiles": {
                name: profile.to_dict()
                for name, profile in self._profiles.items()
                if name not in self.BUILTIN_PROFILES
            }
        }

    def _save_user_profiles(self) -> None:
        """Save user-defined profiles to disk (sync helper)."""
        data = self._user_profiles_payload()

        try:
            with open(self._user_profiles_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            LOGGER.warning(
                "ConfigProfileStore: failed to save user profiles to %s",
                self._user_profiles_path,
            )

    async def async_save_user_profiles(self) -> None:
        """Persist user-defined profiles without blocking the event loop."""

        data = self._user_profiles_payload()
        path = self._user_profiles_path

        def _write() -> None:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except OSError:
                LOGGER.warning(
                    "ConfigProfileStore: failed to save user profiles to %s",
                    path,
                )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _write)

    def _schedule_user_profiles_save(self) -> None:
        """Schedule a non-blocking save, fallback to sync if no loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._save_user_profiles()
        else:
            loop.create_task(self.async_save_user_profiles())

    def get_auto_answer(self) -> bool:
        """Return persisted auto-answer state."""
        return self._auto_answer

    def set_auto_answer(self, enabled: bool) -> None:
        """Set auto-answer state in memory; call async_save_state to persist."""
        self._auto_answer = enabled

    def get_answer_unknown_devices(self) -> bool:
        """Return persisted answer_unknown_devices state."""
        return self._answer_unknown_devices

    def set_answer_unknown_devices(self, enabled: bool) -> None:
        """Set answer_unknown_devices state in memory; call async_save_state."""
        self._answer_unknown_devices = enabled

    def get_autonomous_speed(self) -> float:
        """Return persisted global autonomous-emission speed multiplier."""

        return self._autonomous_speed

    def set_autonomous_speed(self, speed: float) -> None:
        """Set the global autonomous speed multiplier (clamped)."""

        try:
            value = float(speed)
        except TypeError, ValueError:
            value = 1.0
        self._autonomous_speed = max(0.01, min(value, 100.0))

    def set_active_profile(self, name: str | None) -> None:
        """Set the active profile name in memory; call async_save_state to persist."""
        self._active_profile = name

    async def async_save_state(self) -> None:
        """Persist simulator state to disk without blocking the event loop."""
        profile = self._active_profile
        auto_answer = self._auto_answer
        autonomous_speed = self._autonomous_speed
        remove_database = self._remove_database
        answer_unknown_devices = self._answer_unknown_devices
        preserve_state = self._preserve_state
        state_path = self._state_path

        def _write() -> None:
            try:
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "active_profile": profile,
                            "auto_answer": auto_answer,
                            "autonomous_speed": autonomous_speed,
                            "remove_database": remove_database,
                            "answer_unknown_devices": answer_unknown_devices,
                            "preserve_state": preserve_state,
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

    def get_remove_database(self) -> bool:
        """Return persisted remove_database flag."""
        return self._remove_database

    def set_remove_database(self, enabled: bool) -> None:
        """Set remove_database flag in memory; call async_save_state to persist."""
        self._remove_database = enabled

    def get_preserve_state(self) -> bool:
        """Return persisted preserve_state flag."""
        return self._preserve_state

    def set_preserve_state(self, enabled: bool) -> None:
        """Set preserve_state flag in memory; call async_save_state to persist."""
        self._preserve_state = enabled

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
        self._schedule_user_profiles_save()

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
        self._schedule_user_profiles_save()

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
        except TypeError, ValueError:
            LOGGER.warning("ConfigProfileStore: failed to import profile")
            return False


# Module-level storage for original timeout values
_original_timeout_values: dict[str, float] | None = None


# Heartbeat timeout constant names in ramses_rf.const (as of current ramses_rf)
_HEARTBEAT_CONST_NAMES: Final = (
    "HEARTBEAT_TIMEOUT_DEFAULT",
    "HEARTBEAT_TIMEOUT_OTB",
    "HEARTBEAT_TIMEOUT_HGI",
)

_HEARTBEAT_CONSUMER_MODULES: Final = (
    "ramses_rf.device.base",
    "ramses_rf.device.fan",
    "ramses_rf.device.hvac",
    "ramses_rf.device.thermostat",
)


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

        # Patch ramses_rf const module
        for name, orig in _original_timeout_values.items():
            setattr(const_module, name, orig * scale)

        # Patch ramses_rf consumer modules (imported values by reference at load time)
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
