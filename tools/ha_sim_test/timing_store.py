"""Rolling-average recipe timing store for load balancing.

Replaces the manual ``ESTIMATED_RUNTIME`` table in ``parallel.py`` with
a JSON file that tracks the last *N* runs per recipe and computes a
rolling average.  This self-calibrates over time — no manual updates
needed when recipes are added, removed, or change duration.

File location: ``~/.local/share/ramses_extras/ha_sim_reports/recipe_timings.json``

Usage::

    from .timing_store import TimingStore

    store = TimingStore()
    est = store.get_estimate("R47")        # rolling avg, or fallback
    store.record_run("R47", 285.3)         # called after each recipe
    store.save()                            # persist to disk
"""

from __future__ import annotations

import json
import os
from pathlib import Path

#: Maximum number of recent runs to keep per recipe.
MAX_HISTORY = 5

#: Default estimate (seconds) for recipes with no history.
DEFAULT_ESTIMATE = 10

#: Fallback estimates for recipes that have never run.
#: Used when the timing file doesn't exist yet (first run).
SEED_ESTIMATES: dict[str, int] = {
    "R01": 125,
    "R02": 1,
    "R03": 1,
    "R04": 5,
    "R05": 10,
    "R06": 5,
    "R07": 1,
    "R07b": 135,
    "R08": 25,
    "R09": 25,
    "R10": 25,
    "R11": 50,
    "R12": 15,
    "R14": 5,
    "R15": 1,
    "R16": 25,
    "R17": 55,
    "R18": 5,
    "R19": 70,
    "R19b": 5,
    "R19c": 5,
    "R20": 5,
    "R21": 65,
    "R22": 20,
    "R23": 60,
    "R24": 35,
    "R25": 85,
    "R26": 95,
    "R27": 55,
    "R28": 40,
    "R29": 50,
    "R30": 105,
    "R31": 25,
    "R32": 75,
    "R33": 75,
    "R34": 40,
    "R35": 35,
    "R36": 120,
    "R37": 80,
    "R39": 1,
    "R40": 30,
    "R41": 55,
    "R42": 1,
    "R43": 1,
    "R44": 15,
    "R45": 10,
    "R46": 55,
    "R47": 285,
    "R48": 1,
    "R49": 1,
    "R50": 25,
    "R51": 1,
    "R52": 1,
    "R53": 1,
    "R54": 1,
    "R55": 1,
    "R56": 1,
    "R57": 1,
    "R58": 5,
    "R59": 15,
    "R60": 135,
    "R61": 25,
    "R62": 145,
    "R63": 295,
    "R64": 105,
    "R65": 60,
    "R66": 10,
    "R67": 300,
    "R68": 105,
    "R69": 60,
    "R70": 5,
    "R71": 100,
    "R72": 30,
}


def _default_path() -> Path:
    """Return the default timing file path."""
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "ramses_extras" / "ha_sim_reports" / "recipe_timings.json"


class TimingStore:
    """Rolling-average timing store backed by a JSON file.

    The file format is::

        {
            "R01": [123.4, 127.1, 125.0],
            "R02": [1.2, 1.1, 1.3],
            ...
        }

    Each value is a list of the last *MAX_HISTORY* run durations (seconds).
    The estimate is the mean of the stored values, or ``SEED_ESTIMATES``
    for recipes with no history.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else _default_path()
        self._data: dict[str, list[float]] = {}
        self._load()

    def _load(self) -> None:
        """Load timing data from disk (if it exists)."""
        try:
            with open(self._path) as f:
                self._data = json.load(f)
        except FileNotFoundError, json.JSONDecodeError, OSError:
            self._data = {}

    def save(self) -> None:
        """Persist timing data to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)

    def get_estimate(self, recipe_id: str) -> float:
        """Return the rolling-average estimate for *recipe_id*.

        Falls back to ``SEED_ESTIMATES`` and then ``DEFAULT_ESTIMATE``
        if there's no history.
        """
        runs = self._data.get(recipe_id, [])
        if runs:
            return sum(runs) / len(runs)
        return float(SEED_ESTIMATES.get(recipe_id, DEFAULT_ESTIMATE))

    def record_run(self, recipe_id: str, duration: float) -> None:
        """Record a new run duration for *recipe_id*.

        Keeps only the last *MAX_HISTORY* runs.
        """
        runs = self._data.get(recipe_id, [])
        runs.append(round(duration, 1))
        if len(runs) > MAX_HISTORY:
            runs = runs[-MAX_HISTORY:]
        self._data[recipe_id] = runs

    def get_all_estimates(self, recipe_ids: list[str]) -> dict[str, float]:
        """Return estimates for a list of recipe IDs."""
        return {rid: self.get_estimate(rid) for rid in recipe_ids}

    def remove_recipe(self, recipe_id: str) -> None:
        """Remove a recipe from the store (e.g. after deletion)."""
        self._data.pop(recipe_id, None)

    def known_recipes(self) -> set[str]:
        """Return the set of recipe IDs with recorded history."""
        return set(self._data.keys())
