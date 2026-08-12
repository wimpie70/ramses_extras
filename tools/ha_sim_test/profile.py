"""Mixed profile YAML builder (avoids docker restarts).

Matches the built-in "mixed" profile from system_config.py.
"""

from __future__ import annotations

from .const import CO2, CTL, DHW, FAN, HGI, REM

_MIXED_KL_BASE = {
    HGI: {"class": "HGI"},
    "32:150000": {"class": "FAN"},
    "37:120000": {"class": "CO2"},
    "37:170000": {"class": "REM"},
    "29:120000": {"class": "HUM"},
    "01:150000": {"class": "CTL"},
    "07:150000": {"class": "DHW"},
    "04:150000": {"class": "TRV"},
}
for _i in range(3, 9):
    _MIXED_KL_BASE[f"01:15000{_i}"] = {"class": "CTL"}
    _MIXED_KL_BASE[f"04:15000{_i}"] = {"class": "TRV"}

# Kept for backward compatibility — recipes that import MIXED_KL should
# migrate to get_mixed_kl() for instance-aware HGI IDs.
MIXED_KL = _MIXED_KL_BASE


def get_mixed_kl() -> dict:
    """Return a copy of MIXED_KL with the current instance's HGI ID.

    On instance 1 (ha-sim, HGI=18:001234) this is identical to ``MIXED_KL``.
    On parallel instances, the HGI key is replaced with the instance's HGI ID.
    """
    from .helpers import get_current_instance

    hgi_id = get_current_instance().hgi_id
    kl = dict(_MIXED_KL_BASE)
    if hgi_id != HGI and HGI in kl:
        kl[hgi_id] = kl.pop(HGI)
    return kl


_MIXED_ZONES = {}
for _i in range(3, 9):
    _MIXED_ZONES[str(_i).zfill(2)] = {
        "sensor": f"01:15000{_i}",
        "actuators": [f"04:15000{_i}"],
    }

MIXED_SCHEMA = {
    CTL: {"zones": dict(_MIXED_ZONES), "stored_hotwater": {"sensor": DHW}},
    FAN: {
        "remotes": [REM],
        "sensors": [CO2],
        "_commands": {
            "_comment": "Target the FAN for automations, not the REM",
        },
    },
    REM: {
        "_commands": {
            "_comment": "Deprecated — commands moved to FAN",
        },
    },
}


def mixed_yaml(schema_override: dict | None = None) -> str:
    """Build a YAML profile matching the mixed profile, with optional overrides."""
    import yaml as _yaml

    # Force YAML to quote strings that look like numbers (e.g. "03" not 03)
    class _QuotedDumper(_yaml.Dumper):
        pass

    def _str_representer(dumper, data):
        if data.isdigit() and len(data) > 1:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    _QuotedDumper.add_representer(str, _str_representer)

    schema = dict(MIXED_SCHEMA)
    if schema_override:
        schema.update(schema_override)
    profile = {
        "known_list": get_mixed_kl(),
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    return _yaml.dump(
        profile, Dumper=_QuotedDumper, default_flow_style=False, sort_keys=False
    )


# --- Minimal profiles --------------------------------------------------
#
# These profiles load only the devices a recipe actually needs, reducing
# ramses_cc reload time (which scales with device count).  Each helper
# returns a YAML string ready for ``load_profile_yaml``.


def _build_yaml(
    known_list: dict[str, dict[str, str]],
    schema: dict[str, dict[str, object]],
) -> str:
    """Build a YAML profile from a known_list and schema.

    :param known_list: Device known_list dict.
    :param schema: Schema dict.
    :returns: YAML string.
    """
    import yaml as _yaml

    class _QuotedDumper(_yaml.Dumper):
        pass

    def _str_representer(dumper, data):
        if data.isdigit() and len(data) > 1:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    _QuotedDumper.add_representer(str, _str_representer)

    from .helpers import get_current_instance

    hgi_id = get_current_instance().hgi_id
    kl = dict(known_list)
    if hgi_id != HGI and HGI in kl:
        kl[hgi_id] = kl.pop(HGI)

    profile = {
        "known_list": kl,
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    return _yaml.dump(
        profile, Dumper=_QuotedDumper, default_flow_style=False, sort_keys=False
    )


def minimal_ctl_yaml(
    schema_override: dict[str, dict[str, object]] | None = None,
    extra_kl: dict[str, dict[str, str]] | None = None,
) -> str:
    """Minimal profile with just CTL + HGI (2 devices).

    For recipes that only need the CTL active for heartbeats/scan engine.

    :param schema_override: Additional schema entries to merge.
    :param extra_kl: Additional known_list entries to merge.
    :returns: YAML string.
    """
    kl: dict[str, dict[str, str]] = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
    }
    if extra_kl:
        kl.update(extra_kl)
    schema: dict[str, dict[str, object]] = {CTL: {}}
    if schema_override:
        schema.update(schema_override)
    return _build_yaml(kl, schema)


def minimal_ctl_zone_yaml(
    zone_idx: str = "03",
    zone_name: str | None = None,
    sensor_id: str | None = None,
) -> str:
    """Minimal profile with CTL + one zone (2 devices).

    :param zone_idx: Zone index (e.g. "03").
    :param zone_name: Optional zone _name.
    :param sensor_id: Optional sensor device ID for the zone.
    :returns: YAML string.
    """
    zone: dict[str, object] = {"actuators": []}
    if sensor_id:
        zone["sensor"] = sensor_id
    if zone_name:
        zone["_name"] = zone_name
    schema = {CTL: {"zones": {zone_idx: zone}}}
    kl: dict[str, dict[str, str]] = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
    }
    if sensor_id:
        kl[sensor_id] = {"class": "THM"}
    return _build_yaml(kl, schema)


def minimal_hvac_yaml() -> str:
    """Minimal profile with FAN + REM + CO2 + HGI (4 devices).

    For HVAC topology recipes that only need the FAN/REM/CO2 triangle.

    :returns: YAML string.
    """
    kl = {
        HGI: {"class": "HGI"},
        FAN: {"class": "FAN"},
        REM: {"class": "REM"},
        CO2: {"class": "CO2"},
    }
    schema = {FAN: {"_class": "FAN"}}
    return _build_yaml(kl, schema)


def minimal_ctl_dhw_yaml() -> str:
    """Minimal profile with CTL + DHW + HGI (3 devices).

    DHW is nested as ``stored_hotwater.sensor`` inside the CTL entry —
    a nested location that tests device extraction logic.

    :returns: YAML string.
    """
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        DHW: {"class": "DHW"},
    }
    schema = {CTL: {"stored_hotwater": {"sensor": DHW}}}
    return _build_yaml(kl, schema)
