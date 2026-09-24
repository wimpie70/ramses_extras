"""Recipe R131: system-intent src fallback when HGI unknown (issue 1237).

``send_system_intent`` (``ramses_rf.systems.helpers``) fell back to the
CTL's own address as the command source whenever ``gwy.hgi`` was None
(early startup — transport up but HGI device not yet in the registry).
Every system intent targets the CTL, so the fallback produced a
self-addressed frame (``W --- 01:xxxxxx --:------ 01:xxxxxx``) that the
HGI80 silently drops — the write retried, timed out on echo and never
reached the controller.

Runs against the installed ramses_rf inside the container:

1. ``gwy.hgi`` is None → intent src is the HGI placeholder ``18:000730``
   (never the CTL id).
2. ``gwy.hgi`` set → intent src is the active HGI id.
3. The intent built to a CommandDTO yields ``18:000730 CTL --:------``,
   never a self-addressed frame.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R131SystemIntentSrcFallback(Recipe):
    id = "R131"
    seq = 1310
    title = "system-intent src fallback when HGI unknown (issue 1237)"
    tags = ("commands", "hgi", "startup", "issue-1237")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify send_system_intent never emits a self-addressed frame."""
        ctx.log_section("Recipe 131: system-intent src fallback (issue 1237)")

        result = docker_exec_python(
            """
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


async def run_tests():
    from ramses_rf.commands.builders import build_dto
    from ramses_rf.enums import Action
    from ramses_rf.systems.helpers import send_system_intent
    from ramses_tx.address import HGI_DEV_ADDR, NON_DEV_ADDR

    CTL_ID = "01:123456"
    HGI_ID = "18:123456"
    DATA = {
        "zone_index": "02",
        "mode": "permanent_override",
        "setpoint": 19.0,
    }

    def make_system(hgi):
        system = MagicMock()
        system.ctl.id = CTL_ID
        gwy = MagicMock()
        gwy.hgi = hgi
        gwy.dispatcher.send = AsyncMock(return_value="sent")
        system._gateway = gwy
        return system, gwy

    # 1. HGI unknown (early startup) -> placeholder source
    system, gwy = make_system(None)
    await send_system_intent(system, Action.SET_MODE, dict(DATA))
    intent = gwy.dispatcher.send.call_args.args[0]

    check(
        "hgi None -> intent src is HGI placeholder",
        intent.src.id == HGI_DEV_ADDR.id,
        f"src={intent.src.id}",
    )
    check(
        "hgi None -> intent src != dst",
        intent.src.id != intent.dst.id,
        f"src={intent.src.id} dst={intent.dst.id}",
    )
    check(
        "hgi None -> intent dst is CTL",
        intent.dst.id == CTL_ID,
        f"dst={intent.dst.id}",
    )

    # 2. Built CommandDTO is transmittable (not self-addressed)
    dto = build_dto(intent)
    check(
        "hgi None -> DTO addr1 is HGI placeholder",
        dto.addr1 == HGI_DEV_ADDR.id,
        f"addr1={dto.addr1}",
    )
    check(
        "hgi None -> DTO addr2 is CTL, addr3 null",
        dto.addr2 == CTL_ID and dto.addr3 == NON_DEV_ADDR.id,
        f"addr2={dto.addr2} addr3={dto.addr3}",
    )

    # 3. HGI known -> active HGI id as source
    hgi = MagicMock()
    hgi.id = HGI_ID
    system, gwy = make_system(hgi)
    await send_system_intent(system, Action.SET_MODE, dict(DATA))
    intent = gwy.dispatcher.send.call_args.args[0]

    check(
        "hgi set -> intent src is active HGI id",
        intent.src.id == HGI_ID,
        f"src={intent.src.id}",
    )
    check(
        "hgi set -> intent dst is CTL",
        intent.dst.id == CTL_ID,
        f"dst={intent.dst.id}",
    )

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(json.dumps({"passed": passed, "failed": failed, "results": results}))


asyncio.run(run_tests())
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 131 executed", False, f"error: {result['error']}")
            return

        passed = result.get("passed", 0)
        failed = result.get("failed", 0)
        checks = result.get("results", [])

        for chk in checks:
            ctx.check(chk["name"], chk["status"] == "PASS", chk["detail"])

        ctx.check(
            "All system-intent src fallback checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
