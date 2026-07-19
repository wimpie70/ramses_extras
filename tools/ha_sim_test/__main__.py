"""Entry point: ``python3 -m ha_sim_test`` or ``python3 tools/ha_sim_test``.

Usage::

    python3 -m ha_sim_test              # run all recipes in seq order
    python3 -m ha_sim_test R06 R29      # run specific recipes by id
"""

from __future__ import annotations

import asyncio
import sys

from .runner import run


def main() -> None:
    recipe_ids = sys.argv[1:] or None
    asyncio.run(run(recipe_ids))


if __name__ == "__main__":
    main()
