"""Floorplan Helper button platform.

Exposes ``button.floorplan_export`` — one-press regeneration of the
ha-floorplan bundle from the device page, equivalent to calling the
``ramses_extras.floorplan_export`` service (and raising the same
summary notification).

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.ramses_extras.const import register_feature_platform

from ..const import FEATURE_ID
from ..generator import async_generate_bundle
from ..services import notify_export

_LOGGER = logging.getLogger(__name__)


class FloorplanExportButton(ButtonEntity):
    """Button that regenerates the floorplan bundle.

    Deliberately carries no ``device_info``: the framework's orphaned-device
    cleanup runs before platform entities attach, and would remove a
    synthetic floorplan device (and the entity with it) on every boot.
    """

    _attr_should_poll = False
    _attr_name = "Floorplan export"
    _attr_icon = "mdi:floor-plan"
    _attr_unique_id = f"{FEATURE_ID}_export"
    _attr_has_entity_name = False

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the export button.

        :param config_entry: Integration config entry
        """
        self._config_entry = config_entry

    async def async_press(self) -> None:
        """Regenerate the bundle and notify the result."""
        bundle = await async_generate_bundle(self.hass, self._config_entry)
        notify_export(self.hass, bundle)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the floorplan export button."""
    async_add_entities([FloorplanExportButton(config_entry)])


# Platform registration happens at module import (framework convention).
register_feature_platform("button", FEATURE_ID, async_setup_entry)


__all__ = ["FloorplanExportButton", "async_setup_entry"]
