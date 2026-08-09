"""ANSI color helpers for ha_sim_test console output.

All helpers are no-ops when stdout is not a TTY (e.g. when piped to a
file or CI log collector), so the output remains clean plain text in
those contexts.

Usage::

    from .colors import green, red, yellow, bold, color_status

    print(f"  {green('PASS')}: {label}")
    print(f"  {red('FAIL')}: {label} {detail}")
    print(color_status("PASS"))  # coloured "PASS"
"""

from __future__ import annotations

import sys

# Detect whether we're writing to a real terminal.  When piped (CI,
# log files, etc.) we strip all escape codes so the output stays
# clean and grep-friendly.
_IS_TTY = sys.stdout.isatty()

# ANSI escape codes ---------------------------------------------------------
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _wrap(code: str, text: str) -> str:
    """Wrap *text* in *code* + reset, or return plain if not a TTY."""
    if not _IS_TTY:
        return text
    return f"{code}{text}{_RESET}"


def green(text: str) -> str:
    """Green text."""
    return _wrap(_GREEN, text)


def red(text: str) -> str:
    """Red text."""
    return _wrap(_RED, text)


def yellow(text: str) -> str:
    """Yellow text."""
    return _wrap(_YELLOW, text)


def cyan(text: str) -> str:
    """Cyan text."""
    return _wrap(_CYAN, text)


def bold(text: str) -> str:
    """Bold text."""
    return _wrap(_BOLD, text)


def dim(text: str) -> str:
    """Dim/grey text."""
    return _wrap(_DIM, text)


def color_status(status: str) -> str:
    """Colour a status word (PASS / FAIL / SKIP / ERROR).

    :param status: One of ``PASS``, ``FAIL``, ``SKIP``, ``ERROR``
        (case-insensitive).
    :return: The status string, coloured green/red/yellow/cyan.
    """
    upper = status.upper()
    if upper == "PASS":
        return green("PASS")
    if upper == "FAIL":
        return red("FAIL")
    if upper == "SKIP":
        return yellow("SKIP")
    if upper == "ERROR":
        return red("ERROR")
    return status
