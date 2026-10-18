"""Floorplan Helper feature.

Generates a managed bundle for the community ha-floorplan card:
icons, a shared stylesheet, an elements SVG, and rules YAML derived
from the discovered RAMSES topology. The entity/element/icon mapping
is stored in the integration's config entry options — regeneration
re-emits the bundle, so users edit inside ramses_extras rather than
hand-editing floorplan YAML.

The feature is global: it reads ramses_cc/ramses_extras entities and
creates only optional derived binary sensors.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN as FLOORPLAN_DOMAIN

_LOGGER = logging.getLogger(__name__)


def create_floorplan_helper_feature(
    hass: HomeAssistant, config_entry: ConfigEntry, skip_automation_setup: bool = False
) -> dict[str, Any]:
    """Factory function to set up the Floorplan Helper feature.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry
    :param skip_automation_setup: If True, don't start the automation manager
        (parameter included for consistency with other features)
    :return: Floorplan helper feature descriptor
    """
    _LOGGER.info("Floorplan Helper feature initialized")
    return {
        "feature_name": FLOORPLAN_DOMAIN,
    }


__all__ = ["create_floorplan_helper_feature"]
