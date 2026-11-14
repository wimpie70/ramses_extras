"""Recipe R164: CTL 1100 (TPI params) poll must use payload FC (issue 1373).

The 12-hourly ``1100`` TPI-params poll to an evohome controller was
sent with the generic ``00`` payload.  ``1100`` is domain-indexed and
the controller only answers its FC domain index — it silently
ignores ``RQ 1100 001 00`` (the reporter saw 29 unanswered polls over
8 days while ``FC`` is answered within 40 ms).

The fix gives device-level 1100 polls the domain payload ``FC`` for
non-BDR targets — matching ``build_get_tpi_params`` — via a shared
``_default_rq_payload`` helper (alongside 2E04's ``FF``).

This recipe shortens the CTL's poll interval via its
``polling_interval`` number entity and inspects ``RQ 1100`` frames in
the packet log: every request must carry ``FC``, never ``00``.

See: https://github.com/ramses-rf/ramses_rf/issues/1373
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    call_service,
    docker_exec_python,
    get_entities,
    load_profile_yaml,
    wait_for_transport_ready,
)


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


def _rq_1100_payloads(since_ts: str) -> list[str]:
    """Return the payloads of RQ 1100 frames to the CTL since ``since_ts``."""
    result = docker_exec_python(
        f"""
import json
from datetime import datetime
from pathlib import Path
since = datetime.fromisoformat({since_ts!r})
payloads = []
for root in ("/config", "/config/ramses_rf_logs"):
    for p in Path(root).glob("packet_log.log*"):
        try:
            for ln in p.read_text().splitlines():
                if (
                    " RQ " in ln
                    and " {CTL} " in ln
                    and " 1100 " in ln
                ):
                    try:
                        ts = datetime.fromisoformat(
                            ln.split()[0]
                        ).replace(tzinfo=None)
                    except ValueError:
                        continue
                    if ts >= since:
                        payloads.append(ln.split()[-1])
        except OSError:
            pass
print(json.dumps({{"payloads": payloads}}))
"""
    )
    return list(result.get("payloads", []))


class R164Ctl1100FcPayloadIssue1373(Recipe):
    id = "R164"
    seq = 1640
    title = "CTL 1100 poll must use domain payload FC (issue 1373)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 164: CTL 1100 poll FC payload (issue 1373)")

        # Minimal CTL profile; poll interval is shortened below via the
        # device's polling_interval number entity.
        from ..profile import minimal_ctl_yaml

        print(f"  Loading CTL profile ({CTL})...")
        await load_profile_yaml(
            ctx.token,
            minimal_ctl_yaml(),
            speed=0.01,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        # Shorten the CTL's poll interval to 8 s so 1100 polls (default
        # 12 h) actually fire within the recipe window.
        interval_entity = next(
            (
                e["entity_id"]
                for e in get_entities(ctx.token)
                if e.get("entity_id", "").startswith("number.ctl_")
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

        # Each poll task's first send is due within min(interval, 120s)
        # of task creation (the startup poll); an applied 8 s interval
        # usually lands RQ 1100 much sooner.
        ts0 = _utc_now_container()
        ctx.wait_for(
            lambda: len(_rq_1100_payloads(ts0)) >= 1,
            timeout=200,
            interval=5.0,
            msg="for an RQ 1100 poll to the CTL",
            floor=200.0,
        )

        payloads = _rq_1100_payloads(ts0)
        print(f"  RQ 1100 payloads sent to {CTL}: {payloads}")

        ctx.check(
            "CTL 1100 polling is active (requests sent)",
            len(payloads) > 0,
            f"no RQ 1100 frames to {CTL} found in packet log",
        )
        ctx.check(
            "RQ 1100 uses domain payload FC",
            all(p == "FC" for p in payloads),
            f"payloads seen: {payloads} — '00' is silently ignored by the controller",
        )
