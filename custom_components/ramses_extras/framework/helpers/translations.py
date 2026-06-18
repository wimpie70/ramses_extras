"""Translation helpers for feature configuration flows.

Provides utilities for loading and caching translations from feature-specific
translation files (e.g., features/sensor_control/translations/en.json).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


def _get_feature_translations_sync(
    feature_id: str,
    language: str,
    sections: tuple[str, ...] = ("info_suffix",),
) -> dict[str, dict[str, str]]:
    """Synchronous helper to load translations for a feature.

    :param feature_id: The feature identifier (e.g., "sensor_control")
    :param language: Language code (e.g., "en", "nl")
    :param sections: Tuple of translation sections to load
                      (e.g., ("labels", "errors", "info_texts"))
    :return: Dictionary with section names as keys and translation dicts as values.
             Returns empty dict if file not found or invalid.
    """
    base_path = Path(__file__).parent.parent / "features" / feature_id / "translations"
    translations_path = base_path / f"{language}.json"

    if not translations_path.exists():
        translations_path = base_path / "en.json"
        if not translations_path.exists():
            return {}

    try:
        raw = json.loads(translations_path.read_text(encoding="utf-8"))
    except FileNotFoundError, json.JSONDecodeError, Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, dict[str, str]] = {}
    for section in sections:
        section_data = raw.get(section)
        if isinstance(section_data, dict):
            result[section] = {
                str(k): str(v)
                for k, v in section_data.items()
                if isinstance(k, str) and isinstance(v, str)
            }

    return result


async def async_get_feature_translations(
    hass: Any,
    feature_id: str,
    sections: tuple[str, ...] = ("info_suffix",),
) -> dict[str, dict[str, str]]:
    """Load translations for a feature with caching.

    :param hass: Home Assistant instance
    :param feature_id: The feature identifier (e.g., "sensor_control")
    :param sections: Tuple of translation sections to load
                      (default: ("info_suffix",))
                      Common sections: "labels", "errors", "info_texts", "info_suffix"
    :return: Dictionary with section names as keys and translation dicts as values.
             Falls back to English if the requested language is not available.
    """
    from ...const import DOMAIN

    language = getattr(getattr(hass, "config", None), "language", "en") or "en"
    cache_key = f"_translations_{feature_id}"
    cache = hass.data.setdefault(DOMAIN, {}).setdefault(cache_key, {})

    cache_key_full = f"{language}_{'_'.join(sections)}"
    cached = cache.get(cache_key_full)
    if isinstance(cached, dict):
        return cached

    loaded = await hass.async_add_executor_job(
        _get_feature_translations_sync, feature_id, language, sections
    )

    if not loaded and language != "en":
        loaded = await hass.async_add_executor_job(
            _get_feature_translations_sync, feature_id, "en", sections
        )

    # Ensure we return the expected type
    if not isinstance(loaded, dict):
        loaded = {}

    cache[cache_key_full] = loaded
    return loaded


async def async_get_feature_title(
    hass: Any,
    feature_id: str,
    default_title: str,
) -> str:
    """Get feature title from feature-specific translations.

    :param hass: Home Assistant instance
    :param feature_id: The feature identifier (e.g., "sensor_control")
    :param default_title: Fallback title if translation not found
    :return: Translated feature title or default_title if not found.
    """
    translations = await async_get_feature_translations(hass, feature_id, ("config",))
    config_section = translations.get("config", {})
    step_section_raw: str | dict[str, Any] = config_section.get("step", {})
    step_section: dict[str, Any] = (
        step_section_raw if isinstance(step_section_raw, dict) else {}
    )
    feature_step = step_section.get(f"feature_{feature_id}", {})
    title = feature_step.get("title")
    return title if isinstance(title, str) and title else default_title
