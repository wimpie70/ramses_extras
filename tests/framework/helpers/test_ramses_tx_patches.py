"""Tests for ramses_tx FSM patches."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.helpers import ramses_tx_patches


@pytest.fixture(autouse=True)
def reset_patch_state():
    """Reset the _patched flag between tests."""
    ramses_tx_patches._patched = False
    yield
    ramses_tx_patches._patched = False


def test_apply_patches_idempotent():
    """apply_ramses_tx_patches should be idempotent."""
    with (
        patch.object(ramses_tx_patches, "_patch_want_echo") as mock_echo,
        patch.object(ramses_tx_patches, "_patch_want_rply") as mock_rply,
    ):
        ramses_tx_patches.apply_ramses_tx_patches()
        assert ramses_tx_patches._patched is True

        # Second call should be a no-op
        ramses_tx_patches.apply_ramses_tx_patches()
        mock_echo.assert_called_once()
        mock_rply.assert_called_once()


def test_apply_patches_handles_exception(caplog):
    """apply_ramses_tx_patches should log warning on failure."""
    with patch.object(
        ramses_tx_patches,
        "_patch_want_echo",
        side_effect=Exception("patch failed"),
    ):
        ramses_tx_patches.apply_ramses_tx_patches()

        assert ramses_tx_patches._patched is False
        assert "Failed to apply ramses_tx FSM patches" in caplog.text


def test_apply_patches_success_logs(caplog):
    """apply_ramses_tx_patches should log info on success."""
    caplog.set_level(logging.INFO)

    with (
        patch.object(ramses_tx_patches, "_patch_want_echo"),
        patch.object(ramses_tx_patches, "_patch_want_rply"),
    ):
        ramses_tx_patches.apply_ramses_tx_patches()

        assert ramses_tx_patches._patched is True
        assert "Applied ramses_tx FSM patches" in caplog.text


def test_patch_want_echo_import_error_first_path(caplog):
    """_patch_want_echo should handle ImportError gracefully."""
    caplog.set_level(logging.DEBUG)

    # Simulate both import paths failing
    import sys

    original_modules = sys.modules.copy()
    # Remove any existing ramses_tx modules
    for key in list(sys.modules.keys()):
        if key.startswith("ramses_tx"):
            del sys.modules[key]

    with patch.dict(
        sys.modules,
        {"ramses_tx.protocol_fsm": None, "ramses_tx.protocol.fsm": None},
    ):
        ramses_tx_patches._patch_want_echo()

    assert "WantEcho not found, skipping patch" in caplog.text
    sys.modules.clear()
    sys.modules.update(original_modules)


def test_patch_want_rply_import_error(caplog):
    """_patch_want_rply should handle ImportError gracefully."""
    caplog.set_level(logging.DEBUG)

    import sys

    original_modules = sys.modules.copy()
    for key in list(sys.modules.keys()):
        if key.startswith("ramses_tx"):
            del sys.modules[key]

    with patch.dict(
        sys.modules,
        {"ramses_tx.protocol_fsm": None, "ramses_tx.protocol.fsm": None},
    ):
        ramses_tx_patches._patch_want_rply()

    assert "WantRply not found, skipping patch" in caplog.text
    sys.modules.clear()
    sys.modules.update(original_modules)


def test_patch_want_echo_applies_patch():
    """_patch_want_echo should patch WantEcho.pkt_rcvd when available."""
    mock_want_echo = MagicMock()
    original_pkt_rcvd = MagicMock()
    mock_want_echo.pkt_rcvd = original_pkt_rcvd

    import sys

    original_modules = sys.modules.copy()

    mock_module = MagicMock()
    mock_module.WantEcho = mock_want_echo

    with patch.dict(sys.modules, {"ramses_tx.protocol_fsm": mock_module}):
        ramses_tx_patches._patch_want_echo()

        # Verify pkt_rcvd was replaced with a new callable
        assert mock_want_echo.pkt_rcvd is not original_pkt_rcvd
        assert callable(mock_want_echo.pkt_rcvd)

    sys.modules.clear()
    sys.modules.update(original_modules)


def test_patch_want_rply_applies_patch():
    """_patch_want_rply should patch WantRply.pkt_rcvd when available."""
    mock_want_rply = MagicMock()
    mock_want_rply.pkt_rcvd = MagicMock()

    import sys

    original_modules = sys.modules.copy()

    mock_module = MagicMock()
    mock_module.WantRply = mock_want_rply

    with patch.dict(sys.modules, {"ramses_tx.protocol_fsm": mock_module}):
        ramses_tx_patches._patch_want_rply()

        assert callable(mock_want_rply.pkt_rcvd)

    sys.modules.clear()
    sys.modules.update(original_modules)


def test_patched_pkt_rcvd_sent_cmd_none():
    """Patched pkt_rcvd should return early when _sent_cmd is None."""
    mock_instance = MagicMock()
    mock_instance._sent_cmd = None
    mock_instance._context = "test_context"

    original_called = MagicMock()
    mock_want_echo = MagicMock()
    mock_want_echo.pkt_rcvd = original_called

    import sys

    original_modules = sys.modules.copy()

    mock_module = MagicMock()
    mock_module.WantEcho = mock_want_echo

    with patch.dict(sys.modules, {"ramses_tx.protocol_fsm": mock_module}):
        ramses_tx_patches._patch_want_echo()

        # Call the patched function
        mock_want_echo.pkt_rcvd(mock_instance, "fake_packet")

        # Original should NOT have been called since _sent_cmd is None
        original_called.assert_not_called()

    sys.modules.clear()
    sys.modules.update(original_modules)


def test_patched_pkt_rcvd_sent_cmd_not_none():
    """Patched pkt_rcvd should call original when _sent_cmd is not None."""
    mock_instance = MagicMock()
    mock_instance._sent_cmd = MagicMock()
    mock_instance._context = "test_context"

    original_called = MagicMock()
    mock_want_echo = MagicMock()
    mock_want_echo.pkt_rcvd = original_called

    import sys

    original_modules = sys.modules.copy()

    mock_module = MagicMock()
    mock_module.WantEcho = mock_want_echo

    with patch.dict(sys.modules, {"ramses_tx.protocol_fsm": mock_module}):
        ramses_tx_patches._patch_want_echo()

        mock_want_echo.pkt_rcvd(mock_instance, "fake_packet")

        # Original SHOULD have been called
        original_called.assert_called_once_with(mock_instance, "fake_packet")

    sys.modules.clear()
    sys.modules.update(original_modules)
