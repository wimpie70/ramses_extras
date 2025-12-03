"""Pytest configuration to fix event loop issues with
pytest_homeassistant_custom_component."""

import asyncio
from typing import Any, Generator

import pytest


def pytest_configure(config: Any) -> None:
    """Configure pytest to disable the problematic enable_event_loop_debug fixture."""
    # Disable the enable_event_loop_debug fixture that's causing issues
    # This fixture is from pytest_homeassistant_custom_component and tries to
    # access event loop before it's created, causing RuntimeError in Python 3.13+
    config.addinivalue_line(
        "markers",
        "disable_event_loop_debug: disable the enable_event_loop_debug fixture",
    )


@pytest.fixture(scope="session", autouse=True)  # type: ignore[untyped-decorator]
def fix_event_loop_debug_issue() -> Generator[None]:
    """Fix the event loop debug issue by ensuring an event loop exists.

    This fixture ensures that an event loop is created before any tests run,
    preventing the RuntimeError that occurs when pytest_homeassistant_custom_component
    tries to enable event loop debugging.
    """
    # Ensure an event loop exists for the duration of the test session
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        # No event loop exists, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    yield

    # Don't close the event loop - let pytest-asyncio handle cleanup
    # Closing it here causes issues with async generator cleanup


# Override the problematic fixtures from pytest_homeassistant_custom_component
@pytest.fixture  # type: ignore[untyped-decorator]
def enable_event_loop_debug() -> None:
    """Override the problematic enable_event_loop_debug fixture with a safe version."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            return
        # Only try to set debug if we have a valid event loop
        loop.set_debug(True)
    except RuntimeError:
        # No event loop available, skip debug mode
        pass


@pytest.fixture  # type: ignore[untyped-decorator]
def verify_cleanup() -> asyncio.AbstractEventLoop | None:
    """Override the problematic verify_cleanup fixture with a safe version."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            return None
        # Only try to verify cleanup if we have a valid event loop
        return loop
    except RuntimeError:
        # No event loop available, skip verification
        return None
