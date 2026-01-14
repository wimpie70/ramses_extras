from __future__ import annotations

import asyncio
import importlib
from typing import Any


async def import_module_in_executor(module_path: str) -> Any:
    def _do_import() -> Any:
        return importlib.import_module(module_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_import)
