"""Mixed profile YAML builder (avoids docker restarts).

Matches the built-in "mixed" profile from system_config.py.
"""

from __future__ import annotations

from .const import CO2, CTL, DHW, FAN, REM

MIXED_KL = {
    "18:001234": {"class": "HGI"},
    "32:150000": {"class": "FAN"},
    "37:120000": {"class": "CO2"},
    "37:170000": {"class": "REM"},
    "29:120000": {"class": "HUM"},
    "01:150000": {"class": "CTL"},
    "07:150000": {"class": "DHW"},
    "04:150000": {"class": "TRV"},
}
for _i in range(3, 9):
    MIXED_KL[f"01:15000{_i}"] = {"class": "CTL"}
    MIXED_KL[f"04:15000{_i}"] = {"class": "TRV"}

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
        "known_list": dict(MIXED_KL),
        "_enforce_known_list": {"enabled": True},
        "_schema": schema,
    }
    return _yaml.dump(
        profile, Dumper=_QuotedDumper, default_flow_style=False, sort_keys=False
    )
