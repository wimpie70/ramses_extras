"""Recipe R89: BDR active state real-time update (issue 1042).

Issue 1042: BDR binary sensor (``active``) did not reflect relay state
changes in real-time.  When a 3EF0 I arrived and updated
``act_state.modulation_level``, the entity showed the old relay state
for up to 30 seconds.

The root cause was in ramses_cc's ``resolve_async_attr``: a 30-second
cooldown prevented async state readers from being re-dispatched after a
packet arrived.  The cooldown exists to prevent command floods from UI
re-renders (e.g. ``system_mode()`` dispatches a 2E04 RQ), but it also
blocked fresh data from being fetched when a packet arrived.

The fix calls ``clear_async_attr_cache(self)`` in
``_async_update_and_write_state`` before ``async_write_ha_state()``,
so the next property access dispatches the async getter fresh —
bypassing the cooldown for this one state write cycle.

The BDR's ``active`` state uses only ``act_state.modulation_level``
(from 3EF0/3EF1 packets sent by the BDR itself).  A 0008 fallback
was briefly merged but reverted in 0.60.0 because the CTL's 0008 is
a command, not a status report — see issues 1046/1047 for the
RSSI-based communication quality approach that replaces it.

This recipe verifies:
1. A BDR relay (13:) with its binary_sensor.active entity is created
   from a profile that includes the BDR in the known_list.
2. After injecting a 3EF0 I with modulation_level=100% (relay ON),
   the binary sensor state becomes ``on`` within a few seconds
   (not 30s).
3. After injecting a 3EF0 I with modulation_level=0% (relay OFF),
   the binary sensor state becomes ``off`` within a few seconds.

See: https://github.com/ramses-rf/ramses_cc/issues/1042
"""

from __future__ import annotations

import time

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    clear_cached_state,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_ramses_extras_ready,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import MIXED_SCHEMA, _build_yaml, get_mixed_kl

# BDR device ID — serial < 262144 (18-bit max) for valid hex_id conversion.
BDR_ID = "13:104201"  # heating BDR (appliance_control, FC domain)


def _get_entity_state(token: str, entity_id: str) -> str | None:
    """Fetch a single entity's state from the HA API.

    :param token: HA bearer token.
    :param entity_id: The entity_id to query.
    :return: The state string, or None if the entity doesn't exist.
    """
    import json
    import urllib.error
    import urllib.request

    from ..helpers import get_current_instance

    req = urllib.request.Request(
        f"{get_current_instance().ha_url}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read()).get("state")
    except urllib.error.HTTPError, Exception:
        return None


class R89BdrActiveStateRealtimeUpdateIssue1042(Recipe):
    id = "R89"
    seq = 890
    title = "BDR active state real-time update (issue 1042)"
    tags = ("3EF1", "bdr", "active", "binary_sensor", "resolve_async_attr")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 89: BDR active state real-time update (issue 1042)")

        # 0. Ensure ramses_extras is ready (no restart — the profile load
        #    below will trigger a ramses_cc reload with the BDR in the
        #    known_list).  Restarting ha-sim would load the default config
        #    (without the BDR), causing the BDR to be filtered out after
        #    the reload.
        ctx.refresh_token()
        wait_for_ramses_extras_ready(timeout=90, msg="for ramses_extras")

        # 1. Build a custom profile with the BDR in the known_list and schema.
        #    The BDR must be in the known_list from the start so that the
        #    protocol's device_id filter (_include set) allows its packets
        #    through.  If the BDR is discovered at runtime, the filter's
        #    _include set is not updated dynamically and all packets from
        #    the BDR are excluded.
        print(f"  Building custom profile with BDR {BDR_ID}...")
        schema_r89 = dict(MIXED_SCHEMA)
        ctl_schema = dict(schema_r89.get(CTL, {}))
        ctl_schema["system"] = {"appliance_control": BDR_ID}
        schema_r89[CTL] = ctl_schema
        schema_r89[BDR_ID] = {}

        kl_r89 = get_mixed_kl()
        kl_r89[BDR_ID] = {"class": "BDR"}

        try:
            await load_profile_yaml(
                ctx.token,
                _build_yaml(kl_r89, schema_r89),
                speed=0.01,
            )
            print("  Profile loaded")
        except RuntimeError as e:
            print(f"  Profile load failed: {e}")
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Activate CTL for heartbeats
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/activate_profile_device",
                    "device_id": CTL,
                },
            )
        except RuntimeError:
            pass
        wait_for_schema_populated(timeout=20)

        # Verify BDR is in schema
        wait_for(
            lambda: BDR_ID in get_schema_retry(),
            timeout=15,
            interval=2,
            msg="for BDR to appear in schema",
        )

        # 2. Find the BDR's binary_sensor.active entity
        bdr_suffix = BDR_ID.replace(":", "_")

        def _find_bdr_active_entity() -> dict | None:
            entities = get_entities(ctx.token)
            for e in entities:
                eid = e["entity_id"]
                if (
                    eid.startswith("binary_sensor.")
                    and bdr_suffix in eid
                    and "active" in eid
                ):
                    return e
            return None

        wait_for(
            _find_bdr_active_entity,
            timeout=20,
            interval=2,
            msg="for BDR active binary_sensor entity",
        )

        entity = _find_bdr_active_entity()
        if not entity:
            ctx.check(
                "BDR active binary_sensor entity exists",
                False,
                f"no binary_sensor entity found for {BDR_ID}",
            )
            return

        entity_id = entity["entity_id"]
        print(f"  Found BDR active entity: {entity_id}")

        # 3. Inject 3EF0 I with modulation_level=100% (relay ON)
        #    3EF0 I is a valid broadcast from a BDR (boiler relay state).
        #    The CQRS ingestion pipeline processes 3EF0 to update
        #    act_state.modulation_level, which BdrSwitch.active reads.
        #    We use 3EF0 I (broadcast) rather than 3EF1 RP because in
        #    real RF the BDR sends 3EF1 RP to the gateway (HGI/18:),
        #    not to the CTL (01:) — the validator correctly rejects
        #    3EF1 RP addressed to a CTL.
        #    3EF0 3-byte payload: domain_idx(1) + modulation_level(1) +
        #    flags(1).  0xC8 = 100%, 0x00 = 0%.
        print("  Injecting 3EF0 I (modulation=100%, relay ON)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": BDR_ID,
                    "code": "3EF0",
                    "payload": "00C8FF",
                    "verb": "I",
                },
            )
            print("    3EF0 I injected (100%)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # 4. Poll for the binary sensor to turn ON
        #    Before the fix, this would take up to 30s (cooldown).
        #    After the fix, it should happen within a few seconds.
        deadline_on = time.monotonic() + 15  # 15s budget (was 30s+ before fix)
        state_on = None
        while time.monotonic() < deadline_on:
            state_on = _get_entity_state(ctx.token, entity_id)
            if state_on == "on":
                break
            time.sleep(1)

        elapsed_on = time.monotonic() - (deadline_on - 15)
        print(
            f"  BDR active state after ON inject: {state_on} (took {elapsed_on:.1f}s)"
        )

        ctx.check(
            "BDR active is 'on' after 3EF0 I with modulation=100%",
            state_on == "on",
            f"got {state_on!r} after {elapsed_on:.1f}s",
        )

        # Wait 3s to ensure the ON getter has completed and the cache is settled
        ctx.wait(3, "for ON getter to settle before OFF injection")

        # 5. Inject 3EF0 I with modulation_level=0% (relay OFF)
        print("  Injecting 3EF0 I (modulation=0%, relay OFF)...")
        try:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": BDR_ID,
                    "code": "3EF0",
                    "payload": "0000FF",
                    "verb": "I",
                },
            )
            print("    3EF0 I injected (0%)")
        except RuntimeError as e:
            print(f"    Inject failed: {str(e)[:80]}")

        # 6. Poll for the binary sensor to turn OFF
        deadline_off = time.monotonic() + 15
        state_off = None
        while time.monotonic() < deadline_off:
            state_off = _get_entity_state(ctx.token, entity_id)
            if state_off == "off":
                break
            time.sleep(1)

        elapsed_off = time.monotonic() - (deadline_off - 15)
        print(
            "  BDR active state after OFF inject: "
            f"{state_off} (took {elapsed_off:.1f}s)"
        )

        ctx.check(
            "BDR active is 'off' after 3EF0 I with modulation=0%",
            state_off == "off",
            f"got {state_off!r} after {elapsed_off:.1f}s",
        )

        # 7. Summary check: both transitions happened within 15s
        #    (before the fix, at least one would take ~30s due to cooldown)
        ctx.check(
            "Both state transitions completed within 15s (no 30s cooldown)",
            state_on == "on" and state_off == "off",
            f"on={state_on!r} off={state_off!r}",
        )

        # Note: The 0008 fallback tests (CTL demand as BDR state) were
        # removed after the fallback was reverted in 0.60.0.  The CTL's
        # 0008 is a command, not a status report — using it as the BDR's
        # active state can be inaccurate even on healthy systems.
        # See issue 1042 and issues 1046/1047 for the RSSI-based
        # communication quality approach that replaces the fallback.
