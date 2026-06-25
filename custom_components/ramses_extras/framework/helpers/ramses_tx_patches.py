"""Monkey-patches for ramses_tx to work around upstream bugs.

These patches address issues in the ramses_tx protocol FSM that cause
AssertionError crashes when unsolicited broadcast packets arrive while
the FSM is in WantEcho/WantRply state but _sent_cmd is None.

Upstream issue: https://github.com/zxdavb/ramses_cc/issues/254
The assert should be a graceful log+return, not a crash. Until the
upstream fix lands, we patch it here to prevent log spam and event-loop
disruption that slows down Home Assistant.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

_patched = False


def apply_ramses_tx_patches() -> None:
    """Patch ramses_tx FSM states to handle _sent_cmd is None gracefully.

    Idempotent: safe to call multiple times.
    """
    global _patched
    if _patched:
        return

    try:
        _patch_want_echo()
        _patch_want_rply()
    except Exception as err:
        _LOGGER.warning("Failed to apply ramses_tx FSM patches: %s", err)
        return

    _patched = True
    _LOGGER.info("Applied ramses_tx FSM patches (pkt_rcvd assert -> warning)")


def _patch_want_echo() -> None:
    """Patch WantEcho.pkt_rcvd to not crash on _sent_cmd is None."""
    try:
        from ramses_tx.protocol_fsm import WantEcho
    except ImportError:
        try:
            from ramses_tx.protocol.fsm import WantEcho
        except ImportError:
            _LOGGER.debug("WantEcho not found, skipping patch")
            return

    original_pkt_rcvd = WantEcho.pkt_rcvd

    def patched_pkt_rcvd(self, pkt) -> None:  # type: ignore[no-untyped-def]
        if self._sent_cmd is None:
            _LOGGER.debug(
                "%s: received packet while _sent_cmd is None "
                "(unsolicited broadcast?), ignoring",
                self._context,
            )
            return
        original_pkt_rcvd(self, pkt)

    WantEcho.pkt_rcvd = patched_pkt_rcvd


def _patch_want_rply() -> None:
    """Patch WantRply.pkt_rcvd to not crash on _sent_cmd is None."""
    try:
        from ramses_tx.protocol_fsm import WantRply
    except ImportError:
        try:
            from ramses_tx.protocol.fsm import WantRply
        except ImportError:
            _LOGGER.debug("WantRply not found, skipping patch")
            return

    original_pkt_rcvd = WantRply.pkt_rcvd

    def patched_pkt_rcvd(self, pkt) -> None:  # type: ignore[no-untyped-def]
        if self._sent_cmd is None:
            _LOGGER.debug(
                "%s: received packet while _sent_cmd is None "
                "(unsolicited broadcast?), ignoring",
                self._context,
            )
            return
        original_pkt_rcvd(self, pkt)

    WantRply.pkt_rcvd = patched_pkt_rcvd
