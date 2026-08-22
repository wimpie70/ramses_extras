"""Recipe R85: 000A zone config hydration (issue 1102).

Verifies that 000A (zone config) packets are ingested by the CQRS state
projector and that the climate entity's min_temp/max_temp attributes are
populated with the injected values (not falling back to hardcoded 5/35°C
defaults).

Before the fix, ZoneConfigPayload.to_dict() was missing zone_index, so
_resolve_logical_targets could not route the payload to a zone, and there
was no _update_zone_state handler in state_projector.py.  As a result,
Zone.config() always returned None and ramses_cc fell back to 5.0/35.0°C.
"""

from __future__ import annotations

import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    get_entities,
    get_schema_retry,
    wait_for,
    wait_for_transport_ready,
    ws_send,
)


class R85ZoneConfigMinMaxTempIssue1102(Recipe):
    id = "R85"
    seq = 850
    title = "000A zone config min/max temp hydration (issue 1102)"
    tags = ("000A", "zone_config", "min_temp", "max_temp", "issue_1102")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section(
            "Recipe 85: 000A zone config min/max temp hydration (issue 1102)"
        )

        # 1. Load mixed profile (CTL 01:150000 with zones 03-08)
        print("  Loading mixed profile (CTL + zones 03-08)...")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/load_profile",
                    "profile": "mixed",
                    "speed": 0.01,
                    "preload_schema": True,
                    "reload_ramses_cc": True,
                    "enable_auto_answer": True,
                },
            )
            print("  mixed profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        zone_idx = "03"
        ctl = CTL  # 01:150000

        # Wait for schema to have the zone
        wait_for(
            lambda: (
                zone_idx
                in get_schema_retry(max_tries=3, delay=1).get(ctl, {}).get("zones", {})
            ),
            timeout=15,
            interval=1,
            msg=f"for zone {zone_idx} in schema",
        )

        # Helper to find the climate entity for the zone
        def _find_climate_entity() -> dict | None:
            entities = get_entities(ctx.token)
            ctl_suffix = ctl.replace(":", "_")
            for e in entities:
                if not e["entity_id"].startswith("climate."):
                    continue
                attrs = e.get("attributes", {})
                if attrs.get("zone_index") == zone_idx:
                    return e
                if attrs.get("id") == f"{ctl}_{zone_idx}":
                    return e
            pattern = f"climate.{ctl_suffix}_{zone_idx}"
            for e in entities:
                if e["entity_id"] == pattern or e["entity_id"].startswith(pattern):
                    return e
            return None

        # Helper to get min/max temp from the climate entity
        def _get_min_max() -> tuple[float | None, float | None]:
            entity = _find_climate_entity()
            if entity is None:
                return None, None
            attrs = entity.get("attributes", {})
            return attrs.get("min_temp"), attrs.get("max_temp")

        # 2. Inject 000A with non-default bounds (15.0/25.0°C)
        #    000A I payload (6 bytes): zone_idx(1) + flags(1) +
        #    min_temp_raw(2, signed, /100) + max_temp_raw(2, signed, /100)
        #    zone_idx = 03, flags = 00
        #    min_temp = 15.0°C (raw 1500 = 0x05DC)
        #    max_temp = 25.0°C (raw 2500 = 0x09C4)
        #
        #    We use non-default bounds (not 5.0/35.0) to distinguish
        #    a successful 000A ingestion from the hardcoded fallback.
        payload = "030005DC09C4"
        print(f"  Injecting 000A from CTL {ctl} with zone {zone_idx} config...")
        print(f"    payload: {payload} (min=15.0, max=25.0)")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": ctl,
                    "code": "000A",
                    "payload": payload,
                    "verb": "I",
                },
            )
            print(f"    000A injected from {ctl} (zone {zone_idx})")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")
            ctx.check("000A injection", False, str(e)[:80])
            return

        # 3. Poll for the climate entity to show the injected values.
        #    HA refreshes entity state asynchronously after SIGNAL_UPDATE
        #    is dispatched by the coordinator.  The config property is
        #    async with a 30s cooldown, so we need to wait for the first
        #    resolution to complete.
        print("  Polling for min_temp=15.0, max_temp=25.0 (60s timeout)...")
        deadline = time.monotonic() + 60
        min_temp = max_temp = None
        while time.monotonic() < deadline:
            min_temp, max_temp = _get_min_max()
            if min_temp == 15.0 and max_temp == 25.0:
                break
            time.sleep(2)

        entity = _find_climate_entity()
        entity_id = entity["entity_id"] if entity else "?"
        print(f"  Climate entity: {entity_id}")
        print(f"    min_temp: {min_temp}")
        print(f"    max_temp: {max_temp}")

        # 4. Assert min_temp and max_temp are populated with the injected
        #    values, not the hardcoded 5.0/35.0 defaults.
        ctx.check(
            "min_temp is 15.0 (000A ingested, not default 5.0)",
            min_temp == 15.0,
            f"got {min_temp}",
        )
        ctx.check(
            "max_temp is 25.0 (000A ingested, not default 35.0)",
            max_temp == 25.0,
            f"got {max_temp}",
        )
