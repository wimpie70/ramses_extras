"""Recipe R100: RSSI best-across-HGIs quality computation.

Verifies that ``compute_quality`` correctly selects the strongest RSSI
across multiple trackers (the gateway's own tracker + per-child trackers
from the PooledTransport).  This is the core of the multi-HGI RSSI
routing feature (issue 1119).

The ha-sim container uses a single MQTT transport, so this is a
structural test that creates mock RssiTrackers and verifies
``compute_quality`` picks the best RSSI, handles timezone-naive
timestamps, and returns "unknown" when no tracker has data.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R100RssiBestAcrossHgis(Recipe):
    id = "R100"
    seq = 1000
    title = "RSSI best-across-HGIs quality computation"
    tags = ("rssi", "multi-hgi", "quality", "issue-1119")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 100: RSSI best-across-HGIs")

        result = docker_exec_python(
            """
import json
from datetime import datetime as dt, timedelta as td

from ramses_tx.rssi_tracker import RssiTracker
from ramses_rf.models.state_signal import compute_quality, CommunicationQuality


def make_tracker(rssi_values: list[tuple[str, int | None]]) -> RssiTracker:
    \"\"\"Create an RssiTracker with pre-populated RSSI values.

    :param rssi_values: List of (device_id, rssi) tuples.
    \"\"\"
    tracker = RssiTracker()
    now = dt.now()
    for dev_id, rssi in rssi_values:
        if rssi is not None:
            tracker.record(dev_id, rssi, now)
    return tracker


results = {}

# Test 1: Best RSSI across 2 trackers (gateway + pool child)
tracker_gwy = make_tracker([("32:153289", -80)])
tracker_child = make_tracker([("32:153289", -41)])
quality = compute_quality("32:153289", [tracker_gwy, tracker_child])
results["best_rssi_2_trackers"] = quality.best_rssi
results["best_quality_2_trackers"] = quality.rssi_quality

# Test 2: Best RSSI across 3 trackers (gateway + 2 pool children)
tracker_gwy2 = make_tracker([("32:153289", -90)])
tracker_child1 = make_tracker([("32:153289", -55)])
tracker_child2 = make_tracker([("32:153289", -41)])
quality2 = compute_quality("32:153289", [tracker_gwy2, tracker_child1, tracker_child2])
results["best_rssi_3_trackers"] = quality2.best_rssi
results["best_quality_3_trackers"] = quality2.rssi_quality

# Test 3: No data in any tracker → unknown
empty_tracker = make_tracker([])
quality3 = compute_quality("32:153289", [empty_tracker])
results["no_data_rssi"] = quality3.best_rssi
results["no_data_quality"] = quality3.rssi_quality

# Test 4: Only one tracker has data
tracker_only_child = make_tracker([("32:153289", -60)])
empty_gwy = make_tracker([])
quality4 = compute_quality("32:153289", [empty_gwy, tracker_only_child])
results["one_tracker_rssi"] = quality4.best_rssi
results["one_tracker_quality"] = quality4.rssi_quality

# Test 5: Timezone-naive timestamps (issue 1119: dt_now() is naive,
# msg.dtm is tz-aware — mixing them caused TypeError)
tracker_naive = RssiTracker()
naive_now = dt.now()  # tz-naive
tracker_naive.record("32:153289", -50, naive_now)
tracker_aware = RssiTracker()
aware_now = dt.now(dt.now().astimezone().tzinfo)  # tz-aware
tracker_aware.record("32:153289", -70, aware_now)
try:
    quality5 = compute_quality("32:153289", [tracker_naive, tracker_aware])
    results["tz_mixed_rssi"] = quality5.best_rssi
    results["tz_mixed_ok"] = True
except TypeError as e:
    results["tz_mixed_ok"] = False
    results["tz_mixed_error"] = str(e)

# Test 6: Stale data (>24h old) is flagged stale, RSSI still returned
stale_tracker = RssiTracker()
old_time = dt.now() - td(hours=48)
stale_tracker.record("32:153289", -30, old_time)
fresh_tracker = make_tracker([("32:153289", -65)])
quality6 = compute_quality("32:153289", [stale_tracker, fresh_tracker])
results["stale_mixed_rssi"] = quality6.best_rssi
results["stale_mixed_is_stale"] = quality6.is_stale

# Test 7: All stale → is_stale=True, RSSI still returned
all_stale_tracker = RssiTracker()
old_time2 = dt.now() - td(hours=48)
all_stale_tracker.record("32:153289", -30, old_time2)
quality7 = compute_quality("32:153289", [all_stale_tracker])
results["all_stale_rssi"] = quality7.best_rssi
results["all_stale_is_stale"] = quality7.is_stale

print(json.dumps(results))
"""
        )

        ctx.check(
            "compute_quality is importable",
            "error" not in result,
            f"result={result}",
        )
        if "error" in result:
            return

        # Test 1: Best RSSI across 2 trackers
        ctx.check(
            "Best RSSI across 2 trackers is -41 (strongest)",
            result.get("best_rssi_2_trackers") == -41,
            f"rssi={result.get('best_rssi_2_trackers')}",
        )
        ctx.check(
            "Quality is 'strong' for -41 dBm",
            result.get("best_quality_2_trackers") == "strong",
            f"quality={result.get('best_quality_2_trackers')}",
        )

        # Test 2: Best RSSI across 3 trackers
        ctx.check(
            "Best RSSI across 3 trackers is -41 (strongest)",
            result.get("best_rssi_3_trackers") == -41,
            f"rssi={result.get('best_rssi_3_trackers')}",
        )

        # Test 3: No data → unknown
        ctx.check(
            "No data returns rssi=None",
            result.get("no_data_rssi") is None,
            f"rssi={result.get('no_data_rssi')}",
        )
        ctx.check(
            "No data returns quality='unknown'",
            result.get("no_data_quality") == "unknown",
            f"quality={result.get('no_data_quality')}",
        )

        # Test 4: Only one tracker has data
        ctx.check(
            "One tracker returns its RSSI (-60)",
            result.get("one_tracker_rssi") == -60,
            f"rssi={result.get('one_tracker_rssi')}",
        )

        # Test 5: Timezone-naive mix
        ctx.check(
            "TZ-naive + TZ-aware timestamps don't crash",
            result.get("tz_mixed_ok") is True,
            f"error={result.get('tz_mixed_error')}",
        )
        if result.get("tz_mixed_ok"):
            ctx.check(
                "TZ-mixed picks best RSSI (-50)",
                result.get("tz_mixed_rssi") == -50,
                f"rssi={result.get('tz_mixed_rssi')}",
            )

        # Test 6: Stale data flagged, fresh RSSI used
        ctx.check(
            "Stale+fresh mix: best RSSI is -30 (strongest, not stale-ignored)",
            result.get("stale_mixed_rssi") == -30,
            f"rssi={result.get('stale_mixed_rssi')}",
        )
        ctx.check(
            "Stale+fresh mix: is_stale=False (fresh data present)",
            result.get("stale_mixed_is_stale") is False,
            f"is_stale={result.get('stale_mixed_is_stale')}",
        )

        # Test 7: All stale → is_stale=True, RSSI still returned
        ctx.check(
            "All stale returns RSSI (-30, not dropped)",
            result.get("all_stale_rssi") == -30,
            f"rssi={result.get('all_stale_rssi')}",
        )
        ctx.check(
            "All stale: is_stale=True",
            result.get("all_stale_is_stale") is True,
            f"is_stale={result.get('all_stale_is_stale')}",
        )
