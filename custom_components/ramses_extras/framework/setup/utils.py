"""Utility functions for Ramses Extras setup.

This module provides utility functions for async module importing
and other setup-related operations.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any


async def import_module_in_executor(module_path: str) -> Any:
    """Import a module in an executor to avoid blocking.

    :param module_path: Path to the module to import

    :return: The imported module
    """

    def _do_import() -> Any:
        return importlib.import_module(module_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_import)
