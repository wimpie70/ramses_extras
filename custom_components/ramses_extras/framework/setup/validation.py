"""Setup step: validate ramses_cc and HA Core configuration.

Checks that ramses_cc has the necessary settings enabled for
ramses_extras features to work correctly, and logs warnings for
any missing configuration.

Called during the entry setup pipeline after device discovery
and cleanup, before feature instances are created.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from ..helpers.rf_config_validation import (
    log_validation_results,
    validate_ramses_cc_config,
)

_LOGGER = logging.getLogger(__name__)


async def validate_rf_config(hass: HomeAssistant) -> None:
    """Validate ramses_cc and HA Core configuration.

    Checks:
    - ramses_cc send_packet advanced feature enabled
    - ramses_cc message_events enabled with 31DA|10D0 regex
    - ramses_cc known_list has at least one bound REM
    - HA recorder component loaded

    Logs a WARNING for each missing item with actionable instructions.

    :param hass: Home Assistant instance
    """
    _LOGGER.debug("Validating ramses_cc configuration for ramses_extras")

    results = await validate_ramses_cc_config(hass)
    log_validation_results(results)

    _LOGGER.debug("RF config validation complete: %s", results)
