"""Entry point: ``python3 -m ha_sim_test`` or ``python3 tools/ha_sim_test``.

Usage::

    python3 -m ha_sim_test              # run all recipes in seq order
    python3 -m ha_sim_test R06 R29      # run specific recipes by id
    python3 -m ha_sim_test --parallel 2 # run across 2 containers
    python3 -m ha_sim_test --parallel 4 --cleanup
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ha_sim_test",
        description="Run ha_sim_test recipes against one or more ha-sim containers.",
    )
    parser.add_argument(
        "recipes",
        nargs="*",
        help="Recipe IDs to run (default: all registered recipes)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="Run across N containers (default: 1 = sequential on ha-sim)",
    )
    parser.add_argument(
        "--container-base",
        default="ha-sim",
        help="Base container name (default: ha-sim). Instance 1 uses this name "
        "directly; instances 2+ get a suffix (e.g. ha-sim-2).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8124,
        help="Starting HA port for instance 1 (default: 8124). "
        "Instances 2+ use port+1, port+2, etc.",
    )
    parser.add_argument(
        "--assign",
        action="append",
        default=[],
        metavar="CONTAINER:R1,R2,...",
        help="Manual recipe assignment (advanced). Example: --assign ha-sim-2:R01,R02. "
        "Can be repeated. Unassigned recipes are auto-distributed.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Stop and remove parallel containers (instances 2+) and their "
        "cloned config dirs after the run. Without this flag, containers "
        "are stopped but config dirs are kept for warm restarts. "
        "Instance 1 (ha-sim) is always left running.",
    )
    args = parser.parse_args()

    recipe_ids = args.recipes or None

    if args.parallel <= 1:
        from .runner import run

        asyncio.run(run(recipe_ids))
    else:
        from .parallel import run_parallel

        asyncio.run(
            run_parallel(
                n_containers=args.parallel,
                recipe_ids=recipe_ids,
                container_base=args.container_base,
                port=args.port,
                assignments=args.assign,
                cleanup=args.cleanup,
            )
        )


if __name__ == "__main__":
    main()
