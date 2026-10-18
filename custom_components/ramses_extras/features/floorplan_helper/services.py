"""Floorplan Helper services.

Managed-regeneration surface for the ha-floorplan bundle:

- ``floorplan_export`` — regenerate files + rules, return the bundle
  (response-only service).
- ``floorplan_set_element`` — upsert/remove an element binding in the
  stored mapping.
- ``floorplan_set_icon`` — icon override per device class or entity.
- ``floorplan_assign_area`` — bind a device/zone to an HA area.
- ``floorplan_set_svg`` — switch between generated and custom SVG.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from .const import FEATURE_ID, FLOORPLAN_ICONS
from .generator import async_generate_bundle
from .mapping import (
    get_floorplan_options,
    set_area_override,
    set_element_binding,
    set_icon_override,
    set_svg_mode,
)

_LOGGER = logging.getLogger(__name__)

SVC_EXPORT = "floorplan_export"
SVC_SET_ELEMENT = "floorplan_set_element"
SVC_SET_ICON = "floorplan_set_icon"
SVC_ASSIGN_AREA = "floorplan_assign_area"
SVC_SET_SVG = "floorplan_set_svg"


def _config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the integration's config entry."""
    entry = hass.data.get(DOMAIN, {}).get("config_entry")
    if not isinstance(entry, ConfigEntry):
        raise RuntimeError("ramses_extras config entry not found")
    return entry


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register floorplan helper services."""

    async def _async_export(call: ServiceCall) -> dict[str, Any]:
        """Regenerate the floorplan bundle and return it."""
        bundle = await async_generate_bundle(hass, _config_entry(hass))
        _LOGGER.info(
            "Floorplan export complete: %d rules, %d files",
            len(bundle.get("rules", [])),
            len(bundle.get("files_written", [])),
        )
        return bundle

    async def _async_set_element(call: ServiceCall) -> dict[str, Any]:
        """Upsert an element binding (or remove it)."""
        element_id: str = call.data["element_id"]
        remove = call.data.get("remove", False)
        binding = None
        if not remove:
            binding = {
                "entity_id": call.data.get("entity_id"),
                "icon": call.data.get("icon"),
            }
            extra_rules = call.data.get("extra_rules")
            if extra_rules:
                binding["extra_rules"] = extra_rules
        section = set_element_binding(hass, _config_entry(hass), element_id, binding)
        return {
            "element_id": element_id,
            "binding": section.get("element_bindings", {}).get(element_id),
            "removed": remove,
        }

    async def _async_set_icon(call: ServiceCall) -> dict[str, Any]:
        """Set or clear an icon override."""
        target: str = call.data["target"]
        icon: str | None = call.data.get("icon") or None
        if icon is not None and icon not in FLOORPLAN_ICONS:
            raise vol.Invalid(
                f"Unknown icon '{icon}'. Available: {', '.join(FLOORPLAN_ICONS)}"
            )
        section = set_icon_override(hass, _config_entry(hass), target, icon)
        return {
            "target": target,
            "icon": icon,
            "icon_overrides": section.get("icon_overrides", {}),
        }

    async def _async_assign_area(call: ServiceCall) -> dict[str, Any]:
        """Bind a ramses device/zone to an HA area."""
        source: str = call.data["source"]
        area_id: str | None = call.data.get("area_id") or None
        section = set_area_override(hass, _config_entry(hass), source, area_id)
        return {
            "source": source,
            "area_id": area_id,
            "area_overrides": section.get("area_overrides", {}),
        }

    async def _async_set_svg(call: ServiceCall) -> dict[str, Any]:
        """Switch between generated and custom SVG."""
        custom_path = call.data.get("custom_svg_path") or None
        section = set_svg_mode(hass, _config_entry(hass), custom_path)
        return {
            "svg_mode": section.get("svg_mode"),
            "custom_svg_path": section.get("custom_svg_path"),
        }

    if not hass.services.has_service(DOMAIN, SVC_EXPORT):
        hass.services.async_register(
            DOMAIN,
            SVC_EXPORT,
            _async_export,
            schema=vol.Schema({}, extra=vol.PREVENT_EXTRA),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_ELEMENT):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_ELEMENT,
            _async_set_element,
            schema=vol.Schema(
                {
                    vol.Required("element_id"): cv.string,
                    vol.Optional("entity_id"): cv.entity_id,
                    vol.Optional("icon"): cv.string,
                    vol.Optional("extra_rules"): [cv.string],
                    vol.Optional("remove", default=False): cv.boolean,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_ICON):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_ICON,
            _async_set_icon,
            schema=vol.Schema(
                {
                    vol.Required("target"): cv.string,
                    vol.Optional("icon"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_ASSIGN_AREA):
        hass.services.async_register(
            DOMAIN,
            SVC_ASSIGN_AREA,
            _async_assign_area,
            schema=vol.Schema(
                {
                    vol.Required("source"): cv.string,
                    vol.Optional("area_id"): cv.string,
                },
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SVC_SET_SVG):
        hass.services.async_register(
            DOMAIN,
            SVC_SET_SVG,
            _async_set_svg,
            schema=vol.Schema(
                {vol.Optional("custom_svg_path"): cv.string},
                extra=vol.PREVENT_EXTRA,
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )

    _LOGGER.info("Registered floorplan_helper services")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister floorplan helper services."""
    for service in (
        SVC_EXPORT,
        SVC_SET_ELEMENT,
        SVC_SET_ICON,
        SVC_ASSIGN_AREA,
        SVC_SET_SVG,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


__all__ = ["async_setup_services", "async_unload_services"]
