"""Entry point: ``python3 -m ha_sim_test`` or ``python3 tools/ha_sim_test``.

Usage::

    python3 -m ha_sim_test              # run all recipes (defaults: 0.5/0.08/3)
    python3 -m ha_sim_test R06 R29      # run specific recipes by id
    python3 -m ha_sim_test --parallel 4 --cleanup  # fast: ~9 min, 0 new fails
    python3 -m ha_sim_test --wait-scale-blind 1.0 --wait-scale-poll 1.0  # safe
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


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
    parser.add_argument(
        "--wait-scale-blind",
        type=float,
        default=None,
        metavar="FACTOR",
        help="Scale factor for fixed wait() blind sleeps (default: 0.5, or "
        "HA_SIM_TEST_WAIT_SCALE_BLIND if set). E.g. 0.5 halves all 5s/10s/..."
        " sleeps. The dominant cost is 80 calls to wait(5) totalling ~400s.",
    )
    parser.add_argument(
        "--wait-scale-poll",
        type=float,
        default=None,
        metavar="FACTOR",
        help="Scale factor for wait_for() timeout ceilings (default: 0.08, or "
        "HA_SIM_TEST_WAIT_SCALE_POLL if set). Polling returns early, so this "
        "only tightens the failure ceiling. Safe to cut aggressively on the "
        "simulator (e.g. 0.08 -> 30s ceiling becomes 2.4s).",
    )
    parser.add_argument(
        "--wait-floor-blind",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Global minimum (seconds, real time) for all blind wait() sleeps "
        "(default: 3). Protects sensitive waits (scan engine, sync, entity "
        "hydration) when using aggressive --wait-scale-blind. E.g. "
        "--wait-scale-blind 0.5 --wait-floor-blind 3 means wait(5)->3s, "
        "wait(10)->5s, wait(2)->3s.",
    )
    parser.add_argument(
        "--wait-floor-poll",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Global minimum (seconds) for all wait_for() timeout ceilings. "
        "The per-call floor= parameter (e.g. wait_for_ha_ready uses floor=10) "
        "takes the max with this.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory to write log and summary reports into. "
        "Default: user data dir (e.g. ~/.local/share/ramses_extras/"
        "ha_sim_reports on Linux).  Created if it does not exist.",
    )
    parser.add_argument(
        "--tags",
        nargs="*",
        default=None,
        metavar="TAG",
        help="Run only recipes that have at least one of the given tags. "
        "Example: --tags structural runs only structural recipes. "
        "By default, structural recipes are excluded from E2E runs "
        "(see --include-structural).",
    )
    parser.add_argument(
        "--exclude-tags",
        nargs="*",
        default=None,
        metavar="TAG",
        help="Exclude recipes that have any of the given tags. "
        "Example: --exclude-tags structural. "
        "Default: structural is excluded unless --tags or "
        "--include-structural is used.",
    )
    parser.add_argument(
        "--include-structural",
        action="store_true",
        default=False,
        help="Include structural recipes in the run (shorthand for "
        "--exclude-tags with nothing excluded).  By default, structural "
        "recipes are excluded from E2E runs because they don't need the "
        "ha-sim container.",
    )
    args = parser.parse_args()

    # Apply CLI wait-scale/floor overrides (env vars are read at import time
    # in helpers.py; CLI flags take precedence and update the module vars).
    from . import helpers

    if args.wait_scale_blind is not None:
        helpers.WAIT_SCALE_BLIND = args.wait_scale_blind
    if args.wait_scale_poll is not None:
        helpers.WAIT_SCALE_POLL = args.wait_scale_poll
    if args.wait_floor_blind is not None:
        helpers.WAIT_FLOOR_BLIND = args.wait_floor_blind
    if args.wait_floor_poll is not None:
        helpers.WAIT_FLOOR_POLL = args.wait_floor_poll

    # Apply reports-dir override before dispatching to runner/parallel.
    if args.reports_dir is not None:
        from .runner import set_reports_dir

        set_reports_dir(args.reports_dir)

    # Resolve tag-based filtering.
    # Priority: --tags > --exclude-tags > --include-structural > default
    # Default (no flags): exclude "structural" from E2E runs.
    if args.tags is not None:
        # --tags: run only recipes with at least one matching tag
        tag_filter: set[str] | None = set(args.tags)
        exclude_filter: set[str] | None = None
    elif args.exclude_tags is not None:
        # --exclude-tags: exclude recipes with any matching tag
        tag_filter = None
        exclude_filter = set(args.exclude_tags)
    elif args.include_structural:
        # --include-structural: don't exclude structural
        tag_filter = None
        exclude_filter = None
    else:
        # Default: exclude structural from E2E runs
        tag_filter = None
        exclude_filter = {"structural"}

    recipe_ids = args.recipes or None

    if args.parallel <= 1:
        from .runner import run

        asyncio.run(
            run(recipe_ids, tag_filter=tag_filter, exclude_filter=exclude_filter)
        )
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
                tag_filter=tag_filter,
                exclude_filter=exclude_filter,
            )
        )


if __name__ == "__main__":
    main()
