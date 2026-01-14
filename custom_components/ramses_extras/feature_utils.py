from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ENABLED_FEATURES, DOMAIN, FEATURE_ID_DEFAULT


def _get_enabled_features_raw(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
    *,
    prefer_hass_data: bool = True,
) -> Any:
    domain_data = hass.data.get(DOMAIN, {})
    if prefer_hass_data:
        enabled_features_raw = domain_data.get(CONF_ENABLED_FEATURES)
    else:
        enabled_features_raw = None

    config_entry = entry
    if config_entry is None:
        candidate = domain_data.get("config_entry")
        if candidate is not None:
            config_entry = candidate

    if enabled_features_raw is None and config_entry is not None:
        enabled_features_raw = (
            config_entry.data.get(CONF_ENABLED_FEATURES)
            or config_entry.options.get(CONF_ENABLED_FEATURES)
            or {}
        )

    return enabled_features_raw


def get_enabled_feature_names(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
    *,
    include_default: bool = True,
    prefer_hass_data: bool = True,
) -> list[str]:
    enabled_features_raw = _get_enabled_features_raw(
        hass,
        entry,
        prefer_hass_data=prefer_hass_data,
    )

    enabled_feature_names: list[str]
    if isinstance(enabled_features_raw, dict):
        enabled_feature_names = [
            name
            for name, enabled in enabled_features_raw.items()
            if isinstance(name, str) and enabled is True
        ]
    elif isinstance(enabled_features_raw, list):
        enabled_feature_names = [
            name for name in enabled_features_raw if isinstance(name, str)
        ]
    else:
        enabled_feature_names = []

    if include_default and FEATURE_ID_DEFAULT not in enabled_feature_names:
        enabled_feature_names.append(FEATURE_ID_DEFAULT)

    return enabled_feature_names


def get_enabled_features_dict(
    hass: HomeAssistant,
    entry: ConfigEntry | None = None,
    *,
    include_default: bool = True,
    prefer_hass_data: bool = True,
) -> dict[str, bool]:
    enabled_features_raw = _get_enabled_features_raw(
        hass,
        entry,
        prefer_hass_data=prefer_hass_data,
    )

    enabled_features: dict[str, bool]
    if isinstance(enabled_features_raw, dict):
        enabled_features = {
            name: bool(enabled)
            for name, enabled in enabled_features_raw.items()
            if isinstance(name, str)
        }
    elif isinstance(enabled_features_raw, list):
        enabled_features = {
            name: True for name in enabled_features_raw if isinstance(name, str)
        }
    else:
        enabled_features = {}

    if include_default:
        enabled_features.setdefault(FEATURE_ID_DEFAULT, True)

    return enabled_features
