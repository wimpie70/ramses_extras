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

from ..helpers.log_once import LogOnce, LogWhen
from ..helpers.rf_config_validation import (
    BOUND_REM_WARNED_KEY,
    BOUND_REM_WARNED_MSG,
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

    The missing-bound-REM warning is emitted only once across restarts
    via the :class:`LogOnce` helper (strategy ``LogWhen.INSTALL``).
    Some FAN devices do not support a bound REM at all, so the warning
    is not actionable for those users and should not repeat on every
    restart.  The flag is cleared again as soon as a bound REM *is*
    detected, so a later regression re-warns once.  See GitHub issue 104.

    :param hass: Home Assistant instance
    """
    _LOGGER.debug("Validating ramses_cc configuration for ramses_extras")

    results = await validate_ramses_cc_config(hass)

    # Log the non-dedup warnings (send_packet, message_events, recorder).
    log_validation_results(results)

    # Handle the bound-REM warning with LogOnce dedup.
    # Warned once per install; cleared when a bound REM is detected so
    # that a future regression re-warns.
    warner = LogOnce(hass, logger=_LOGGER)

    if results.get("ramses_cc_loaded") and not results.get("has_bound_rem"):
        await warner.log(
            key=BOUND_REM_WARNED_KEY,
            msg=BOUND_REM_WARNED_MSG,
            level=logging.WARNING,
            when=LogWhen.INSTALL,
        )
    elif results.get("has_bound_rem"):
        # Situation resolved — clear the flag so a future regression
        # re-warns once.
        await warner.clear(BOUND_REM_WARNED_KEY)

    _LOGGER.debug("RF config validation complete: %s", results)
