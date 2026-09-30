"""Recipe R136: heartbeat liveness — dropped packets don't refresh last_seen.

Regression test for https://github.com/ramses-rf/ramses_rf/issues/1255.

``DeviceBase.is_available`` / ``heartbeat_timeout`` (ramses_rf >= 0.60.7)
marks a device unavailable once ``now - _last_msg_dtm`` exceeds its
``heartbeat_timeout``.  ``_last_msg_dtm`` is only refreshed in
``process_state_updates``, which runs *after* ``validate_addresses``,
``instantiate_devices`` and ``validate_slugs`` in ``process_msg``.  Any
packet that fails those checks — e.g. a FAN sending RQ (no RQ verbs in
``CODES_BY_DEV_SLUG[FAN]``), a FAN ``I/22F3`` (empty verb dict), a REM
``RP``, or a TRV ``I/2349`` — is dropped without refreshing liveness,
even though the frame proves the device is still transmitting.

Until issue 1255 is fixed, the "invalid packet still refreshes liveness"
checks below are expected to FAIL — that failure demonstrates the bug.
"""

from __future__ import annotations

from datetime import datetime as dt

from ..base import Recipe, RecipeContext
from ..const import FAN, REM, TRV
from ..helpers import (
    call_service,
    get_entities,
    get_schema_retry,
    grep_ha_log,
    load_profile_yaml,
    wait_for_schema_populated,
    wait_for_transport_ready,
    ws_send,
)
from ..profile import mixed_yaml


def _status_eid(entities: list[dict], device_id: str) -> str | None:
    """Return the per-device status binary_sensor entity_id (issue 1210)."""
    normalized = device_id.replace(":", "_")
    for e in entities:
        eid = e.get("entity_id", "")
        if (
            eid.startswith("binary_sensor.")
            and eid.endswith("_status")
            and normalized in eid
        ):
            return eid
    return None


def _entity_state(entities: list[dict], entity_id: str) -> str | None:
    for e in entities:
        if e.get("entity_id") == entity_id:
            return e.get("state")
    return None


def _status_attrs(entities: list[dict], entity_id: str) -> dict:
    for e in entities:
        if e.get("entity_id") == entity_id:
            return e.get("attributes", {})
    return {}


def _last_seen_dtm(entities: list[dict], entity_id: str) -> dt | None:
    raw = _status_attrs(entities, entity_id).get("last_seen")
    if not raw:
        return None
    try:
        return dt.fromisoformat(raw)
    except ValueError:
        return None


class R136HeartbeatLiveness(Recipe):
    id = "R136"
    seq = 1360
    title = "Heartbeat liveness — validation-dropped packets (issue 1255)"
    tags = ("liveness", "heartbeat", "is_available", "hvac", "issue-1255")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 136: heartbeat liveness / dropped packets")

        # Ensure FAN/REM/TRV are in the schema (enforce_known_list is on,
        # so the devices must also be in known_list — mixed profile has both).
        schema = get_schema_retry()
        if FAN not in schema or REM not in schema or TRV not in schema:
            print("  FAN/REM/TRV not all in schema — loading mixed profile...")
            try:
                await load_profile_yaml(
                    ctx.token,
                    mixed_yaml(),
                    speed=0.01,
                    preload_schema=True,
                    reload_ramses=True,
                )
            except RuntimeError as e:
                print(f"  Profile load failed: {e}")
            ctx.wait_for_ramses_cc_reload(timeout=20)
            ctx.refresh_token()
            wait_for_transport_ready(timeout=30)
            wait_for_schema_populated(min_keys=5, timeout=20)

        wait_for_transport_ready(timeout=30)

        # Quiet the RF environment: pause autonomous emitters AND disable
        # global RQ->RP auto-answering.  Response traffic (e.g. FAN RP/2411
        # replying to REM polls) is device-sourced and refreshes last_seen
        # legitimately, which would mask a missing liveness refresh.
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/silence_devices",
                    "device_ids": [FAN, REM, TRV],
                    "set_suppress": False,
                },
            )
            print(f"  Silenced emitters for {[FAN, REM, TRV]}")
        except RuntimeError as e:
            print(f"  Silence failed (continuing): {str(e)[:80]}")
        try:
            await ws_send(
                ctx.token,
                {
                    "type": "ramses_extras/device_simulator/set_auto_answer",
                    "enabled": False,
                },
            )
            print("  Disabled simulator auto-answer")
        except RuntimeError as e:
            print(f"  set_auto_answer failed (continuing): {str(e)[:80]}")
        ctx.wait(2, "for emitter cancellation to take effect", floor=1.0)

        try:
            entities = get_entities(ctx.token)

            # --- Symptom context: FAN heartbeat_timeout is 15 min ----------
            fan_eid = _status_eid(entities, FAN)
            rem_eid = _status_eid(entities, REM)
            trv_eid = _status_eid(entities, TRV)

            fan_entities = [
                e["entity_id"] for e in entities if "32_150000" in e["entity_id"]
            ]
            ctx.check(
                "FAN device status entity exists",
                fan_eid is not None,
                f"entities with 32_150000: {fan_entities}",
            )
            ctx.check(
                "REM device status entity exists",
                rem_eid is not None,
            )
            ctx.check(
                "TRV device status entity exists",
                trv_eid is not None,
            )
            if not (fan_eid and rem_eid and trv_eid):
                return

            fan_timeout = _status_attrs(entities, fan_eid).get("heartbeat_timeout")
            ctx.check(
                "FAN heartbeat_timeout is 900s (the reported 15 min)",
                fan_timeout == 900.0,
                f"heartbeat_timeout={fan_timeout}",
            )

            # Verify the RF environment is actually quiet for our targets
            # before baselining (device activation can finish after the
            # silence call — a fresh emitter would restart the chatter).
            self._wait_for_quiet(ctx, [fan_eid, rem_eid, trv_eid])

            # --- FAN (HVAC): valid 31DA refreshes liveness, recovers entities
            self._check_liveness_cycle(
                ctx,
                label="FAN",
                status_eid=fan_eid,
                valid={
                    "source_id": FAN,
                    "verb": "I",
                    "code": "31DA",
                    # Real Orcon RP/31DA payload captured from packet.log
                    "payload": (
                        "00EF007FFF3A2A071205AA054D072F680000011E1E0000EFEF04DF04DF00"
                    ),
                },
                invalid=[
                    (
                        "FAN RQ/31DA (no RQ verb allowed for src FAN)",
                        {
                            "source_id": FAN,
                            "dst": REM,
                            "verb": "RQ",
                            "code": "31DA",
                            "payload": "00",
                        },
                        r"for src \(FAN\) to Tx",
                    ),
                    (
                        "FAN I/22F3 (empty verb dict in CODES_BY_DEV_SLUG)",
                        {
                            "source_id": FAN,
                            "verb": "I",
                            "code": "22F3",
                            "payload": "00023C03040000",
                        },
                        r"for src \(FAN\) to Tx",
                    ),
                ],
            )

            # After the valid 31DA the FAN must be communicating again:
            # status sensor on, and a regular FAN entity no longer
            # "unavailable" (the Tweakers symptom).
            entities = get_entities(ctx.token)
            ctx.check(
                "FAN status is on (communicating) after valid 31DA",
                _entity_state(entities, fan_eid) == "on",
                f"state={_entity_state(entities, fan_eid)}",
            )
            fan_state = _entity_state(
                entities, "binary_sensor.fan_32_150000_filter_dirty"
            )
            ctx.check(
                "FAN entity recovered from unavailable after valid 31DA",
                fan_state is not None and fan_state != "unavailable",
                f"filter_dirty state={fan_state}",
            )

            # --- REM (HVAC, 24h timeout): RP is not allowed for REM src ----
            self._check_liveness_cycle(
                ctx,
                label="REM",
                status_eid=rem_eid,
                valid={
                    "source_id": REM,
                    "verb": "I",
                    "code": "10E0",
                    # Real 10E0 device-info payload (38 bytes)
                    "payload": (
                        "000002FF1E03FFFFFFFF150807E3150407E1496E746572"
                        "6E65742047617465776179000000000000000000000000"
                    ),
                },
                invalid=[
                    (
                        "REM RP/22F1 (REM may not send RP)",
                        {
                            "source_id": REM,
                            "dst": FAN,
                            "verb": "RP",
                            "code": "22F1",
                            "payload": "000204",
                        },
                        r"for src \(REM\) to Tx",
                    ),
                ],
            )

            # --- TRV (heat, 12h timeout): I/2349 is not allowed for TRV ----
            self._check_liveness_cycle(
                ctx,
                label="TRV",
                status_eid=trv_eid,
                valid={
                    "source_id": TRV,
                    "verb": "I",
                    "code": "30C9",
                    "payload": "0007D0",  # zone_idx 00, 20.00C
                },
                invalid=[
                    (
                        "TRV I/2349 (TRV may only RQ/W 2349)",
                        {
                            "source_id": TRV,
                            "verb": "I",
                            "code": "2349",
                            "payload": "00070800FFFFFF",
                        },
                        r"for src \(TRV\) to Tx",
                    ),
                ],
            )
        finally:
            try:
                await ws_send(
                    ctx.token,
                    {
                        "type": "ramses_extras/device_simulator/set_auto_answer",
                        "enabled": True,
                    },
                )
            except RuntimeError:
                pass
            for dev_id in (FAN, REM, TRV):
                try:
                    call_service(
                        ctx.token,
                        "ramses_extras",
                        "device_simulator_resume_device",
                        {"device_id": dev_id},
                    )
                except RuntimeError:
                    pass

    # ------------------------------------------------------------------
    def _wait_for_quiet(
        self,
        ctx: RecipeContext,
        status_eids: list[str],
        rounds: int = 6,
    ) -> None:
        """Wait until last_seen stops moving for the target devices.

        Confirms the silencing actually took effect — if any target is
        still emitting (or answering), last_seen keeps advancing and the
        per-packet checks below can't isolate the injected packet.
        """
        for _ in range(rounds):
            before = {
                eid: _last_seen_dtm(get_entities(ctx.token), eid) for eid in status_eids
            }
            ctx.wait(3, "quiet-window probe", floor=2.0)
            after = {
                eid: _last_seen_dtm(get_entities(ctx.token), eid) for eid in status_eids
            }
            if before == after:
                print("  RF environment quiet for targets")
                return
            print(f"  still chattering: {before} -> {after}")
        print("  WARNING: targets still chattering — checks may be flaky")

    def _inject(self, ctx: RecipeContext, msg: dict) -> None:
        call_service(
            ctx.token,
            "ramses_extras",
            "device_simulator_inject_message",
            msg,
        )

    def _check_liveness_cycle(
        self,
        ctx: RecipeContext,
        *,
        label: str,
        status_eid: str,
        valid: dict,
        invalid: list[tuple[str, dict, str]],
    ) -> None:
        """Baseline liveness, then validation-dropped packets.

        Post-fix invariant (issue 1255): *any* frame sourced by the
        device must refresh ``last_seen`` — payload/schema validity is a
        separate concern from device liveness.
        """
        print(f"  --- {label}: establishing liveness baseline ---")
        self._inject(ctx, valid)
        ctx.wait(3, f"for {label} valid packet to be processed", floor=2.0)

        entities = get_entities(ctx.token)
        t0 = _last_seen_dtm(entities, status_eid)
        ctx.check(
            f"{label}: valid packet refreshes last_seen",
            t0 is not None,
            f"last_seen={_status_attrs(entities, status_eid).get('last_seen')}",
        )
        if t0 is None:
            return

        for desc, msg, log_fragment in invalid:
            print(f"  --- {label}: injecting invalid packet — {desc} ---")
            self._inject(ctx, msg)
            ctx.wait(3, f"for {label} invalid packet to be processed", floor=2.0)

            entities = get_entities(ctx.token)
            t1 = _last_seen_dtm(entities, status_eid)

            # Confirm the packet was dropped at slug validation — this is
            # what currently prevents the liveness refresh.  The
            # inject->dispatcher->log path can take a few seconds under
            # load, so poll briefly instead of a single grep.
            log_hits: list[str] = []
            for _ in range(4):
                log_hits = grep_ha_log(log_fragment, since_lines=8000)
                if log_hits:
                    break
                ctx.wait(2, "for drop warning to reach the log", floor=1.5)
            ctx.check(
                f"{label}: invalid packet dropped by validate_slugs ({desc})",
                bool(log_hits),
                f"log hits={len(log_hits)}",
            )

            ctx.check(
                f"{label}: dropped packet still refreshes last_seen (issue 1255)",
                t1 is not None and t1 > t0,
                f"t0={t0} t1={t1}",
            )
            t0 = t1 or t0
