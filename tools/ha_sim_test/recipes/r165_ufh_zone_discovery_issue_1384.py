"""Recipe R165: UFH-only zone discovery, UFC 30C9 and 000C binds (issue 1384).

End-to-end coverage for ramses-rf/ramses_rf issue 1384 — the
reporter's UFH-only system (Evo Color + 2x HCC100 UFCs, no TRVs) saw no
zones discovered after ~14 hours, every UFC ``30C9`` dropped as
``Unexpected code for src (UFC)``, and ``LINK EXCEPTION``s whenever the
controller's ``000C`` binding table declared a UFC as a zone sensor.

The recipe loads a profile with a CTL and two UFCs but **no zones**, then:

1. Injects the controller's zone-indexed broadcasts (``2309``,
   ``30C9``, ``000A``) for zones 03-05 — each must instantiate its zone
   in ramses_rf, after which ramses_cc registers the climate entity
   (unique_id ``<ctl>_<idx>``) populated with the injected temperature.

2. Injects a UFC ``I 30C9`` per-circuit temperature broadcast — must
   not produce a new ``Unexpected code for src`` warning.

3. Injects a ``RP 000C`` reply declaring the UFC as zone 04's sensor
   (role ``04``, sub-index ``E1`` = circuit) — must not produce a new
   ``RULES/LINK EXCEPTION`` error (a UFC binds to zones via its
   circuits, never as a zone device).
"""

from __future__ import annotations

from typing import Any

from ..base import Recipe, RecipeContext
from ..const import CTL, HGI
from ..helpers import (
    call_service,
    docker_exec_python,
    load_profile_yaml,
    wait_for_async,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import _build_yaml

_UFC_A = "02:150050"
_UFC_B = "02:150051"

# Zones created purely by broadcast discovery — no schema entries.
_ZONES = ("03", "04", "05")
_ZONE_UIDS = {f"{CTL}_{z}" for z in _ZONES}

# Injected broadcast payloads (zone_index + value elements).
# 2309 setpoints: 20.0 C for all three zones.
_P2309 = "0307D00407D00507D0"
# 30C9 temperatures: 23.45 / 23.20 / 23.03 C — distinctive values so a
# stale entity cannot false-positive on the assertion.
_P30C9 = "0309290409100508FF"
# 000A zone parameters: min 5.0 / max 20.0 / flags 00 for each zone.
_P000A = "0301F407D0000401F407D0000501F407D000"
# UFC I 30C9: circuits E1-E4 (E1/E2 have temps, E3/E4 are 7FFF=None).
_P_UFC_30C9 = "E107B1E206FBE37FFFE47FFF"
# RP 000C: zone 04, device_role 04 (zone_sensor), sub_index E1 (circuit),
# device 02:150050 (raw id bytes 0A4A22) — the UFC-as-zone-sensor bind.
_P_000C = "0404E10A4A22"

_ZONE03_TEMP = 23.45


def _profile_yaml() -> str:
    """Build a UFH-only profile: CTL + two UFCs, no zones in the schema."""
    kl = {
        HGI: {"class": "HGI"},
        CTL: {"class": "CTL"},
        _UFC_A: {"class": "UFC"},
        _UFC_B: {"class": "UFC"},
        "13:150001": {"class": "BDR"},
    }
    schema = {
        CTL: {
            "system": {"appliance_control": "13:150001"},
            "underfloor_heating": {_UFC_A: {}, _UFC_B: {}},
        },
    }
    return _build_yaml(kl, schema)


def _count_ha_log_matches(pattern: str) -> int:
    """Count pattern matches across the HA logs inside the container.

    Callers compare counts before/after an injection (delta), immune to
    log rotation and timestamp format differences.
    """
    result = docker_exec_python(
        f"""
import json, re
from pathlib import Path
count = 0
for p in Path("/config").glob("home-assistant.log*"):
    try:
        for ln in p.read_text().splitlines():
            if re.search({pattern!r}, ln):
                count += 1
    except OSError:
        pass
print(json.dumps({{"count": count}}))
"""
    )
    return int(result.get("count", 0))


def _inject(
    token: str, src: str, code: str, payload: str, verb: str, dst: str | None = None
) -> None:
    data: dict[str, Any] = {
        "source_id": src,
        "code": code,
        "payload": payload,
        "verb": verb,
    }
    if dst:
        data["dst"] = dst
    call_service(
        token,
        "ramses_extras",
        "device_simulator_inject_message",
        data,
    )


class R165UfhZoneDiscoveryIssue1384(Recipe):
    id = "R165"
    seq = 1650
    title = "UFH-only zone discovery, UFC 30C9 and 000C binds (issue 1384)"
    tags = ("ufh", "discovery", "zones", "issue_1384")

    async def _get_entity_registry(self, ctx: RecipeContext) -> list[dict[str, Any]]:
        resp: Any = await ws_send(ctx.token, {"type": "config/entity_registry/list"})
        if isinstance(resp, list):
            return resp
        entities = resp.get("entities", [])
        return entities if isinstance(entities, list) else []

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 165: UFH zone discovery & UFC traffic (1384)")

        # Drop stale zone climate entries for our indices so discovery is
        # genuinely proven by this run's injections.
        for entry in await self._get_entity_registry(ctx):
            if entry.get("unique_id") in _ZONE_UIDS and (
                entity_id := entry.get("entity_id")
            ):
                print(f"  Removing stale registry entry {entity_id}")
                await ws_send(
                    ctx.token,
                    {
                        "type": "config/entity_registry/remove",
                        "entity_id": entity_id,
                    },
                )

        print("  Loading UFH-only profile (no zones in schema)...")
        try:
            await load_profile_yaml(
                ctx.token,
                _profile_yaml(),
                speed=0.01,
                preload_schema=True,
                reload_ramses=True,
            )
        except RuntimeError as err:
            ctx.check("profile loaded", False, detail=str(err)[:200])
            return

        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        ctx.wait_for_schema_stable(timeout=15)

        # 1. Inject the controller's zone-indexed broadcasts for zones
        #    03-05: each must instantiate its zone, and ramses_cc must
        #    register the climate entities.
        print(f"  Injecting CTL 2309/30C9/000A arrays for zones {_ZONES}...")
        _inject(ctx.token, CTL, "2309", _P2309, "I")
        _inject(ctx.token, CTL, "30C9", _P30C9, "I")
        _inject(ctx.token, CTL, "000A", _P000A, "I")

        async def _zones_registered() -> bool:
            uids = {
                str(e.get("unique_id")) for e in await self._get_entity_registry(ctx)
            }
            return _ZONE_UIDS <= uids

        ready = await wait_for_async(
            _zones_registered,
            timeout=60,
            interval=2.0,
            msg=f"for zone climate entities {sorted(_ZONE_UIDS)} to register",
            floor=15.0,
        )
        ctx.check(
            "zones 03-05 discovered from CTL broadcasts (climate entities)",
            ready,
            f"expected unique_ids {sorted(_ZONE_UIDS)} in entity registry",
        )

        # The same broadcast must populate zone state — zone 03's climate
        # current_temperature is the injected 23.45 C (HA reports it at
        # 0.1-degree precision, hence the tolerance).
        async def _zone03_temp_check() -> bool:
            entities = await self._get_entity_registry(ctx)
            eid = next(
                (
                    e.get("entity_id")
                    for e in entities
                    if e.get("unique_id") == f"{CTL}_03"
                ),
                None,
            )
            if not eid:
                return False
            resp: Any = await ws_send(ctx.token, {"type": "get_states"})
            for st in resp if isinstance(resp, list) else []:
                if st.get("entity_id") != eid:
                    continue
                cur = st.get("attributes", {}).get("current_temperature")
                return isinstance(cur, (int, float)) and abs(cur - _ZONE03_TEMP) <= 0.06
            return False

        temp_ok = await wait_for_async(
            _zone03_temp_check,
            timeout=45,
            interval=2.0,
            msg="for zone 03 climate current_temperature == 23.45",
            floor=10.0,
        )
        ctx.check(
            "zone 03 climate populated with injected 30C9 temperature",
            temp_ok,
            f"expected current_temperature {_ZONE03_TEMP} on {CTL}_03 climate",
        )

        # 2. UFC I 30C9 per-circuit broadcast must not be dropped as
        #    'Unexpected code for src (UFC)'.
        print(f"  Injecting I 30C9 from UFC {_UFC_A}...")
        n0 = _count_ha_log_matches(r"Unexpected code for src")
        _inject(ctx.token, _UFC_A, "30C9", _P_UFC_30C9, "I")
        ctx.wait(6, "for UFC 30C9 to be processed", floor=4.0)
        new_unexpected = _count_ha_log_matches(r"Unexpected code for src") - n0
        ctx.check(
            "UFC I 30C9 broadcast accepted (no 'Unexpected code for src')",
            new_unexpected == 0,
            f"{new_unexpected} new 'Unexpected code for src' warnings",
        )

        # 3. RP 000C declaring the UFC as zone 04's sensor must not spam
        #    RULES/LINK EXCEPTIONs (UFCs bind to zones via circuits).
        print("  Injecting RP 000C UFC-as-zone-04-sensor reply...")
        n0 = _count_ha_log_matches(r"RULES EXCEPTION|LINK EXCEPTION")
        _inject(ctx.token, CTL, "000C", _P_000C, "RP", dst=HGI)
        ctx.wait(6, "for 000C binding to be processed", floor=4.0)
        new_exceptions = _count_ha_log_matches(r"RULES EXCEPTION|LINK EXCEPTION") - n0
        ctx.check(
            "000C UFC zone-sensor bind raises no LINK/RULES EXCEPTION",
            new_exceptions == 0,
            f"{new_exceptions} new LINK/RULES EXCEPTION errors",
        )
