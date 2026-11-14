"""Recipe R163: OTB polling must never send OpenTherm Data-ID 0 (issue 1372).

An OpenTherm ``3220`` READ-DATA request for Data-ID 0 (Master/Slave
Status) carries the master's CH/DHW enable flags in its high data
byte.  ramses cannot know the controller's real flags, so the zeroed
request (``0000000000``) reads as "CH disabled, DHW disabled" — R8810
bridges relay it to the boiler and stop the burner every poll cycle,
short-cycling the boiler.

The fix removes Data-ID 0 from ``OPENTHERM_POLL_DATA_IDS`` (status/
flame is already available via ``3EF0``) and refuses it in
``build_get_opentherm_data()``.

This recipe loads an OTB with a short ``3220`` poll interval and
inspects the packet log: status-ID ``00`` requests must never appear
while other IDs (e.g. ``19`` boiler temp) keep polling.

See: https://github.com/ramses-rf/ramses_rf/issues/1372
"""

from __future__ import annotations

import yaml

from ..base import Recipe, RecipeContext
from ..helpers import (
    call_service,
    docker_exec_python,
    get_entities,
    load_profile_yaml,
    wait_for_transport_ready,
)

OTB = "10:048456"  # reporter's R8810A bridge id


def _utc_now_container() -> str:
    """Return the current UTC time inside the container (naive ISO).

    ``container_log_timestamp()`` returns container *local* time (CET),
    while packet_log lines are UTC — mixing the two filters out every
    frame.  Use this for packet-log comparisons only.
    """
    result = docker_exec_python(
        """
import json
from datetime import datetime, timezone
now = datetime.now(timezone.utc).replace(tzinfo=None)
print(json.dumps({"ts": now.isoformat(timespec="microseconds")}))
"""
    )
    return str(result.get("ts", ""))


def _rq_3220_data_ids(since_ts: str) -> list[str]:
    """Return the OpenTherm Data-IDs of RQ 3220 frames since ``since_ts``.

    The 3220 request payload is ``00{hdr}{data_id}0000`` — the Data-ID
    is hex chars 4-5 of the 10-char payload (last log field).  The
    ``since_ts`` baseline (naive UTC) excludes historical frames from
    rotated packet logs.
    """
    result = docker_exec_python(
        f"""
import json
from datetime import datetime
from pathlib import Path
since = datetime.fromisoformat({since_ts!r})
ids = []
for root in ("/config", "/config/ramses_rf_logs"):
    for p in Path(root).glob("packet_log.log*"):
        try:
            for ln in p.read_text().splitlines():
                if (
                    " RQ " in ln
                    and " {OTB} " in ln
                    and " 3220 " in ln
                ):
                    try:
                        ts = datetime.fromisoformat(
                            ln.split()[0]
                        ).replace(tzinfo=None)
                    except ValueError:
                        continue
                    if ts >= since:
                        ids.append(ln.split()[-1][4:6])
        except OSError:
            pass
print(json.dumps({{"ids": ids}}))
"""
    )
    return list(result.get("ids", []))


class R163OtbStatusIdPollIssue1372(Recipe):
    id = "R163"
    seq = 1630
    title = "OTB polling must never send OpenTherm Data-ID 0 (issue 1372)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 163: OTB Data-ID 0 poll (issue 1372)")

        # Standalone OTB; the polling interval is shortened below via
        # the device's polling_interval number entity (per-device
        # traits in known_list are not passed through by the sim).
        profile = {
            "known_list": {
                OTB: {"class": "OTB"},
            },
            "_enforce_known_list": {"enabled": True},
        }

        print(f"  Loading OTB profile ({OTB})...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Shorten the OTB's poll interval to 8 s so several poll bursts
        # occur within the wait window (default is hourly).
        interval_entity = next(
            (
                e["entity_id"]
                for e in get_entities(ctx.token)
                if e.get("entity_id", "").startswith("number.otb_")
                and "polling_interval" in e["entity_id"]
            ),
            None,
        )
        if interval_entity:
            print(f"  Setting {interval_entity} to 8s...")
            call_service(
                ctx.token,
                "number",
                "set_value",
                {"entity_id": interval_entity, "value": 8},
            )
        else:
            print("  WARN: polling_interval entity not found")

        # Wait for a full burst of Data-IDs.  Each poll task's first
        # send is due within min(interval, 120s) of task creation (the
        # startup poll), and interval changes via the number entity do
        # not always pull next_due forward — so allow the full 120s
        # startup window plus margin; an applied 8s interval usually
        # lands a complete 12-ID burst much sooner.
        ts0 = _utc_now_container()
        ctx.wait_for(
            lambda: len(set(_rq_3220_data_ids(ts0))) >= 10,
            timeout=200,
            interval=5.0,
            msg="for a full 3220 Data-ID poll burst",
            floor=200.0,
        )

        data_ids = _rq_3220_data_ids(ts0)
        print(
            f"  RQ 3220 Data-IDs sent to {OTB}: {sorted(set(data_ids))} "
            f"({len(data_ids)} frames)"
        )

        ctx.check(
            "OTB 3220 polling is active (requests sent)",
            len(data_ids) > 0,
            f"no RQ 3220 frames to {OTB} found in packet log",
        )
        ctx.check(
            "no RQ 3220 for Data-ID 00 (Status) sent",
            "00" not in data_ids,
            f"found {data_ids.count('00')} status-ID requests "
            f"(payload 0000000000 = master flags CH/DHW off)",
        )
        ctx.check(
            "other Data-IDs still polled (telemetry intact)",
            any(i != "00" for i in data_ids),
            f"data IDs seen: {sorted(set(data_ids))}",
        )
