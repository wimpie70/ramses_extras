"""Monkey-patches for ramses_tx to work around upstream bugs.

These patches address issues in the ramses_tx protocol FSM that cause
AssertionError crashes when unsolicited broadcast packets arrive while
the FSM is in WantEcho/WantRply state but _sent_cmd is None.

Upstream issue: https://github.com/zxdavb/ramses_cc/issues/254
The assert should be a graceful log+return, not a crash.

Starting with ramses_rf 0.59.7, the upstream fix has been merged and
the method was renamed from ``pkt_rcvd`` to ``packet_rcvd``. The
``WantRply`` state was also removed (only ``WantEcho`` remains).

This module gracefully handles both old and new ramses_tx versions:
- If the method name ``pkt_rcvd`` exists, patch it (old versions)
- If the method name ``packet_rcvd`` exists, the upstream fix is
  already in place, so we skip patching (new versions >= 0.59.7)
- If ``WantRply`` doesn't exist, skip it (removed in 0.59.7+)

.. deprecated::
    The entire protocol FSM (``ramses_tx.protocol.fsm``) was deleted in
    ramses_rf PR 1174 (ramses-rf/ramses_rf#1174), so these patches are
    now a permanent no-op on ramses_rf >= 0.61.0.  The module remains
    for backward compatibility with older ramses_rf versions.  When the
    minimum ramses_rf dependency is bumped past 0.61.0, this module and
    its call site in ``__init__.py`` can be removed entirely.

    # TODO: remove this module once ramses_rf >= 0.61.0 is the minimum
    # dependency (FSM deleted in ramses-rf/ramses_rf#1174)
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

_patched = False


def apply_ramses_tx_patches() -> None:
    """Patch ramses_tx FSM states to handle _sent_cmd is None gracefully.

    Idempotent: safe to call multiple times.

    .. deprecated::
        No-op on ramses_rf >= 0.61.0 (FSM deleted in
        ramses-rf/ramses_rf#1174).  See module docstring for removal
        plan.
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


def _import_state_class(class_name: str) -> Any | None:
    """Import a FSM state class by name from ramses_tx.

    Returns the class or None if not found.
    """
    try:
        import importlib

        mod: Any = importlib.import_module("ramses_tx.protocol.fsm")
        cls = getattr(mod, class_name, None)
        if cls is not None:
            return cls
    except ImportError:
        pass

    try:
        import importlib

        mod = importlib.import_module("ramses_tx.protocol_fsm")
        cls = getattr(mod, class_name, None)
        if cls is not None:
            return cls
    except ImportError:
        pass

    return None


def _patch_state_class(class_name: str) -> None:
    """Patch a FSM state class to not crash on _sent_cmd is None.

    Handles both old (pkt_rcvd) and new (packet_rcvd) method names.
    If the new method name exists, the upstream fix is already in place
    and we skip patching.
    """
    state_class = _import_state_class(class_name)
    if state_class is None:
        _LOGGER.debug("%s not found, skipping patch", class_name)
        return

    # Try new method name first (ramses_rf >= 0.59.7)
    if hasattr(state_class, "packet_rcvd"):
        # Upstream already has the fix, no need to patch
        _LOGGER.debug(
            "%s.packet_rcvd already has upstream fix, skipping patch",
            class_name,
        )
        return

    # Fall back to old method name (ramses_rf < 0.59.7)
    original_method = getattr(state_class, "pkt_rcvd", None)
    if original_method is None:
        _LOGGER.debug(
            "%s has neither pkt_rcvd nor packet_rcvd, skipping patch",
            class_name,
        )
        return

    def patched_pkt_rcvd(self, pkt) -> None:  # type: ignore[no-untyped-def]
        if self._sent_cmd is None:
            _LOGGER.debug(
                "%s: received packet while _sent_cmd is None "
                "(unsolicited broadcast?), ignoring",
                self._context,
            )
            return
        original_method(self, pkt)

    state_class.pkt_rcvd = patched_pkt_rcvd


def _patch_want_echo() -> None:
    """Patch WantEcho to not crash on _sent_cmd is None."""
    _patch_state_class("WantEcho")


def _patch_want_rply() -> None:
    """Patch WantRply to not crash on _sent_cmd is None.

    WantRply was removed in ramses_rf 0.59.7+ (merged into WantEcho).
    This is a no-op on new versions.
    """
    state_class = _import_state_class("WantRply")
    if state_class is None:
        _LOGGER.debug("WantRply not found (removed in ramses_rf 0.59.7+), skipping")
        return

    _patch_state_class("WantRply")
