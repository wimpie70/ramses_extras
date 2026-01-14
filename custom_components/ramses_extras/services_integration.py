"""Service integration for Ramses Extras.

This module ONLY handles Home Assistant service registration orchestration.
Feature service handlers live in per-feature services.py modules.

Pattern mirrors websocket_integration.py:
- Determine enabled features
- Import each feature's services module (if any)
- Call its async setup/unload functions

Notes:
- Services are registered under the integration domain (ramses_extras) to keep
  a single HA service namespace.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .feature_utils import get_enabled_feature_names

_LOGGER = logging.getLogger(__name__)


def _import_services_module(feature_name: str) -> Any:
    services_module_path = (
        f"custom_components.ramses_extras.features.{feature_name}.services"
    )
    return importlib.import_module(services_module_path)


async def async_register_feature_services(hass: HomeAssistant) -> None:
    """Register services for all enabled features."""

    enabled_feature_names = get_enabled_feature_names(hass)
    config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
    _LOGGER.info("Registering feature services for: %s", enabled_feature_names)

    for feature_name in enabled_feature_names:
        try:
            services_module = await asyncio.to_thread(
                _import_services_module,
                feature_name,
            )
        except ImportError as error:
            if "services" in str(error):
                _LOGGER.debug(
                    "Feature '%s' has no services module",
                    feature_name,
                )
            else:
                _LOGGER.warning(
                    "Could not import services module for feature '%s': %s",
                    feature_name,
                    error,
                )
            continue

        setup = getattr(services_module, "async_setup_services", None)
        if callable(setup):
            try:
                param_count = len(inspect.signature(setup).parameters)
                if param_count == 1:
                    await setup(hass)
                elif param_count == 2:
                    await setup(hass, config_entry)
                else:
                    _LOGGER.error(
                        "Service setup for feature '%s' has an incompatible signature",
                        feature_name,
                    )
            except Exception as error:
                _LOGGER.error(
                    "Error registering services for feature '%s': %s",
                    feature_name,
                    error,
                )
        else:
            _LOGGER.debug(
                "Feature '%s' services module has no async_setup_services()",
                feature_name,
            )


async def async_unload_feature_services(hass: HomeAssistant) -> None:
    """Unload services for all enabled features."""

    enabled_feature_names = get_enabled_feature_names(hass)
    config_entry = hass.data.get(DOMAIN, {}).get("config_entry")
    _LOGGER.info("Unloading feature services for: %s", enabled_feature_names)

    for feature_name in enabled_feature_names:
        try:
            services_module = await asyncio.to_thread(
                _import_services_module,
                feature_name,
            )
        except ImportError:
            continue

        unload = getattr(services_module, "async_unload_services", None)
        if callable(unload):
            try:
                param_count = len(inspect.signature(unload).parameters)
                if param_count == 1:
                    await unload(hass)
                elif param_count == 2:
                    await unload(hass, config_entry)
                else:
                    _LOGGER.error(
                        "Service unload for feature '%s' has an incompatible signature",
                        feature_name,
                    )
            except Exception as error:
                _LOGGER.error(
                    "Error unloading services for feature '%s': %s",
                    feature_name,
                    error,
                )


__all__ = [
    "async_register_feature_services",
    "async_unload_feature_services",
]
