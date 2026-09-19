"""Device Status Card Feature.

Fleet overview card listing all RAMSES devices with their online
status and communication quality (RSSI, per-HGI breakdown).

The feature is global — it reads ramses_cc per-device status entities
(ramses_cc issue 1210) rather than creating entities of its own.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...framework.base_classes.base_card_manager import BaseCardManager
from .const import DEVICE_STATUS_CARD_CARD_CONFIGS
from .const import DOMAIN as DEVICE_STATUS_CARD_DOMAIN

_LOGGER = logging.getLogger(__name__)


class DeviceStatusCardManager(BaseCardManager):
    """Manages the device status card within the feature."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Device Status Card feature.

        :param hass: Home Assistant instance
        :param config_entry: Configuration entry with integration config
        :type config_entry: ConfigEntry
        """
        super().__init__(hass, config_entry, DEVICE_STATUS_CARD_DOMAIN)
        _LOGGER.info("Device Status Card manager initialized")

    def _get_card_configurations(self) -> list[dict[str, Any]]:
        """Get card configurations from the feature's const module.

        :return: List of card configuration dictionaries
        :rtype: list[dict[str, Any]]
        """
        return DEVICE_STATUS_CARD_CARD_CONFIGS


def create_device_status_card_feature(
    hass: HomeAssistant, config_entry: ConfigEntry, skip_automation_setup: bool = False
) -> dict[str, Any]:
    """Factory function to set up the Device Status Card feature.

    :param hass: Home Assistant instance
    :param config_entry: Configuration entry
    :param skip_automation_setup: If True, don't start the automation manager
        (parameter included for consistency with other features)
    :return: Device status card feature with card management capabilities
    """
    return {
        "card_manager": DeviceStatusCardManager(hass, config_entry),
        "feature_name": DEVICE_STATUS_CARD_DOMAIN,
    }


__all__ = ["DeviceStatusCardManager", "create_device_status_card_feature"]
