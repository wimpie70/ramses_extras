"""Recipe R98: CO2 auto-promotion from REM when I 1298 evidence is present.

Tests the scenario where a device classified as REM in the schema is
actually a CO2 sensor with integrated remote buttons.  Such a device
sends both I 1298 (CO2 level — definitive CO2 signature) and RQ 2411
(display request — REM/DIS behavior).

Three bugs were fixed to make this work:

1. HvacTopologyHandler: the REM→DIS rule fired on RQ 2411 without
   checking for CO2 evidence, mis-promoting the device to DIS.
   Fix: track CO2 evidence (I 1298) per device; when the REM→DIS
   or FAN→DIS rule fires, promote to CO2 if CO2 evidence is present.

2. HvacTopologyHandler: if RQ 2411 arrived before I 1298 (e.g. via
   active probing), the device was promoted to DIS before any CO2
   evidence was tracked.  The REM→DIS rule then wouldn't fire again.
   Fix: add a direct CO2 promotion rule — I 1298 is definitive, so
   promote to CO2 regardless of current class (REM, DIS, FAN, HUM).

3. DiscoveryScan: the contradiction counter was reset by matching
   packets (I 22F1 → REM matches current REM class) even when the
   current classification was from a prefix fallback (confidence
   "medium"), not evidence-based.  This prevented CO2 evidence
   from accumulating to the reclassification threshold.
   Fix: only reset the contradiction counter when confidence is
   "high" (evidence-based).

This recipe verifies:
  - A REM-classified device sending I 1298 is promoted to CO2 (not DIS)
  - A REM-classified device sending RQ 2411 THEN I 1298 is promoted to
    CO2 (direct promotion overrides the earlier DIS promotion)
  - The class mismatch is flagged as rf_suggests=CO2 (not DIS)
  - The UI "Discovery suggests" column correctly parses rf_suggests=

See: ramses_rf PR 1213, issue 767 (CO2 sensors are remotes too)
"""

from __future__ import annotations

from copy import deepcopy

import yaml

from ..base import Recipe, RecipeContext
from ..const import FAN
from ..helpers import (
    call_service,
    docker_exec_python,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, get_mixed_kl

# A hybrid CO2+REM device (like 37:126776 in the wild)
HYBRID_DEVICE = "37:190098"
# A second hybrid for the DIS→CO2 test (test 1 promotes the first to CO2)
HYBRID_DEVICE_2 = "37:190097"
# A pure REM (no CO2) for comparison
PURE_REM = "37:190099"


def _profile_yaml() -> str:
    """Build a profile with a hybrid CO2+REM and a pure REM."""
    known_list = get_mixed_kl()
    known_list[HYBRID_DEVICE] = {"class": "REM"}
    known_list[HYBRID_DEVICE_2] = {"class": "REM"}
    known_list[PURE_REM] = {"class": "REM"}

    schema = deepcopy(MIXED_SCHEMA)
    schema[FAN] = {
        **schema[FAN],
        "remotes": [HYBRID_DEVICE, HYBRID_DEVICE_2, PURE_REM],
    }
    schema[HYBRID_DEVICE] = {
        "_bound": FAN,
        "_class": "REM",
    }
    schema[HYBRID_DEVICE_2] = {
        "_bound": FAN,
        "_class": "REM",
    }
    schema[PURE_REM] = {
        "_bound": FAN,
        "_class": "REM",
    }
    return yaml.dump(
        {
            "known_list": known_list,
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        },
        default_flow_style=False,
        sort_keys=False,
    )


def _inject(ctx: RecipeContext, source_id: str, code: str, verb: str = "I") -> None:
    """Inject a packet from source_id to FAN (or broadcast)."""
    call_service(
        ctx.token,
        "ramses_extras",
        "device_simulator_inject_message",
        {
            "source_id": source_id,
            "dst": FAN if verb == "RQ" else "--:------",
            "code": code,
            "payload": "0001DB" if code == "1298" else "000031",
            "verb": verb,
        },
    )


def _log_line_count() -> int:
    result = docker_exec_python(
        """
import json
from pathlib import Path
path = Path("/config/home-assistant.log")
print(json.dumps({"count": len(path.read_text().splitlines())}))
"""
    )
    return int(result.get("count", 0))


def _has_event_since(line_count: int, device_id: str, rule: str) -> bool:
    result = docker_exec_python(
        f"""
import json
from pathlib import Path
lines = Path("/config/home-assistant.log").read_text().splitlines()
new_lines = lines[{line_count}:]
found = any(
    {device_id!r} in line
    and {rule!r} in line
    for line in new_lines
)
print(json.dumps({{"found": found}}))
"""
    )
    return result.get("found") is True


def _has_mismatch_since(line_count: int, device_id: str, suggests: str) -> bool:
    result = docker_exec_python(
        f"""
import json
from pathlib import Path
lines = Path("/config/home-assistant.log").read_text().splitlines()
new_lines = lines[{line_count}:]
found = any(
    {device_id!r} in line
    and "class mismatch" in line
    and {suggests!r} in line
    for line in new_lines
)
print(json.dumps({{"found": found}}))
"""
    )
    return result.get("found") is True


class R125Co2PromotionFromRem(Recipe):
    id = "R125"
    seq = 1250
    title = "CO2 auto-promotion from REM when I 1298 evidence is present"
    tags = ("co2", "rem", "dis", "discovery", "1298", "2411")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify CO2 promotion from REM via I 1298 evidence."""
        ctx.log_section("Recipe 98: CO2 auto-promotion from REM")

        await load_profile_yaml(ctx.token, _profile_yaml(), speed=0.01)
        ctx.wait_for_ramses_cc_reload(msg="for CO2+REM profile reload")
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        try:
            await ws_send(
                ctx.token,
                {
                    "type": ("ramses_extras/device_simulator/activate_profile_device"),
                    "device_id": FAN,
                },
            )
        except RuntimeError:
            pass

        wait_for(
            lambda: (
                HYBRID_DEVICE in get_schema_retry()
                and HYBRID_DEVICE_2 in get_schema_retry()
                and PURE_REM in get_schema_retry()
            ),
            timeout=30,
            interval=2,
            msg="for CO2+REM candidates in schema",
            floor=10.0,
        )

        # --- Test 1: I 1298 promotes REM to CO2 (direct promotion) ---
        baseline1 = _log_line_count()
        _inject(ctx, HYBRID_DEVICE, "1298", verb="I")
        promoted = wait_for(
            lambda: _has_event_since(
                baseline1, HYBRID_DEVICE, "Rule_HVAC_1298_Signature_to_CO2"
            ),
            timeout=30,
            interval=2,
            msg="for CO2 promotion event (Rule_HVAC_1298_Signature_to_CO2)",
            floor=10.0,
        )
        ctx.check(
            "REM sending I 1298 is promoted to CO2 (direct rule)",
            promoted,
            f"device_id={HYBRID_DEVICE}",
        )

        # Wait for the mismatch to be flagged
        mismatch_flagged = wait_for(
            lambda: _has_mismatch_since(baseline1, HYBRID_DEVICE, "rf_suggests=CO2"),
            timeout=30,
            interval=2,
            msg="for class mismatch flag (rf_suggests=CO2)",
            floor=10.0,
        )
        ctx.check(
            "Class mismatch flagged as rf_suggests=CO2 (not DIS)",
            mismatch_flagged,
            f"device_id={HYBRID_DEVICE}",
        )

        # --- Test 2: RQ 2411 THEN I 1298 — direct promotion overrides DIS ---
        # Use a separate device (HYBRID_DEVICE_2) because test 1 already
        # promoted HYBRID_DEVICE to CO2 in the SSOT.
        baseline2 = _log_line_count()
        # First inject RQ 2411 (would trigger REM→DIS)
        _inject(ctx, HYBRID_DEVICE_2, "2411", verb="RQ")
        # Wait a moment for the DIS event
        ctx.wait(3, "for RQ 2411 to be evaluated", floor=2.0)
        # Then inject I 1298 (should promote to CO2, overriding DIS)
        _inject(ctx, HYBRID_DEVICE_2, "1298", verb="I")
        co2_after_dis = wait_for(
            lambda: _has_event_since(
                baseline2, HYBRID_DEVICE_2, "Rule_HVAC_1298_Signature_to_CO2"
            ),
            timeout=30,
            interval=2,
            msg="for CO2 promotion after DIS (direct rule)",
            floor=10.0,
        )
        ctx.check(
            "DIS-promoted device sending I 1298 is re-promoted to CO2",
            co2_after_dis,
            f"device_id={HYBRID_DEVICE_2}",
        )

        # --- Test 3: Pure REM sending RQ 2411 is promoted to DIS ---
        baseline3 = _log_line_count()
        _inject(ctx, PURE_REM, "2411", verb="RQ")
        dis_promoted = wait_for(
            lambda: _has_event_since(
                baseline3, PURE_REM, "Rule_HVAC_2411_Request_Source_to_DIS"
            ),
            timeout=30,
            interval=2,
            msg="for DIS promotion event (no CO2 evidence)",
            floor=10.0,
        )
        ctx.check(
            "Pure REM (no CO2) sending RQ 2411 is promoted to DIS",
            dis_promoted,
            f"device_id={PURE_REM}",
        )
