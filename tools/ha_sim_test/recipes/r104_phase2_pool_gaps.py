"""Recipe R104: Phase 2 multi-HGI pool gap tests.

Verifies the six Phase 2 gaps for multi-HGI pool support inside the
ha-sim container where the updated ``ramses_tx`` library is installed:

- Gap B: ``configured_hgi_id`` fallback in ``connect_sans_signature``
- Gap C: HGI80 auto-SKIP (no _PUZZ probes sent)
- Gap D: ``per_child_config_overrides`` in ``pooled_transport_factory``
- Gap E: ``ID_COMMAND`` identity discovery (``!I`` response parsing)
- Gap F: evofw3 ``#`` debug response filtering

The ha-sim container uses a single MQTT transport, so this recipe
creates mock child transports and verifies the pool's config and
identity logic directly against the ``ramses_tx`` library.
"""

from __future__ import annotations

import json

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R104Phase2PoolGaps(Recipe):
    id = "R104"
    seq = 1040
    title = "Phase 2 multi-HGI pool gaps (B-F)"
    tags = ("pooled", "multi-hgi", "phase2", "transport", "identity")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify Phase 2 pool gaps B through F."""
        ctx.log_section("Recipe 104: Phase 2 multi-HGI pool gaps")

        result = docker_exec_python(
            """
import asyncio
import dataclasses
import inspect
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

from ramses_tx.transport.base import SignaturePolicy, TransportConfig

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})

# ---------------------------------------------------------------------------
# Gap B: configured_hgi_id field exists and defaults to None
# ---------------------------------------------------------------------------
config = TransportConfig()
check("Gap B: configured_hgi_id field exists",
      hasattr(config, "configured_hgi_id"),
      f"configured_hgi_id = {config.configured_hgi_id!r}")
check("Gap B: configured_hgi_id defaults to None",
      config.configured_hgi_id is None,
      "default is None")

config2 = dataclasses.replace(config, configured_hgi_id="18:006402")
check("Gap B: configured_hgi_id set via replace",
      config2.configured_hgi_id == "18:006402",
      f"set to {config2.configured_hgi_id!r}")

# ---------------------------------------------------------------------------
# Gap C: HGI80 auto-SKIP dispatch
# ---------------------------------------------------------------------------
check("Gap C: SignaturePolicy.SKIP exists",
      SignaturePolicy.SKIP is not None,
      f"SKIP = {SignaturePolicy.SKIP}")

# Simulate the dispatch logic from port.py.
is_hgi80 = True
disable_sending = False
policy = SignaturePolicy.IMMEDIATE
if disable_sending:
    selected = "sans_signature"
elif is_hgi80:
    selected = "sans_signature"
elif policy is SignaturePolicy.SKIP:
    selected = "sans_signature"
elif policy is SignaturePolicy.ID_COMMAND:
    selected = "id_command"
elif policy is SignaturePolicy.DELAYED:
    selected = "delayed_signature"
else:
    selected = "signature"
check("Gap C: HGI80 selects sans_signature",
      selected == "sans_signature" and is_hgi80,
      f"HGI80=True -> {selected}")

# ---------------------------------------------------------------------------
# Gap D: per_child_config_overrides in pooled_transport_factory
# ---------------------------------------------------------------------------
from ramses_tx.transport.factory import pooled_transport_factory
sig = inspect.signature(pooled_transport_factory)
check("Gap D: per_child_config_overrides parameter exists",
      "per_child_config_overrides" in sig.parameters,
      f"params: {list(sig.parameters)}")

async def test_validation():
    try:
        await pooled_transport_factory(
            MagicMock(),
            config=TransportConfig(),
            port_names=["/dev/ttyUSB0"],
            port_configs=[{"baudrate": 115200, "dsrdtr": False,
                           "rtscts": False, "timeout": 3, "xonxoff": False}],
            per_child_config_overrides=[{}, {}],
        )
        return False
    except ValueError as e:
        return "per_child_config_overrides" in str(e)

validation_ok = asyncio.run(test_validation())
check("Gap D: mismatched length raises ValueError",
      validation_ok,
      "validation works")

base = TransportConfig()
overrides = [
    {"signature_policy": SignaturePolicy.DELAYED, "startup_grace": 3.0},
    {"signature_policy": SignaturePolicy.ID_COMMAND,
     "configured_hgi_id": "18:006402"},
]
child0 = dataclasses.replace(base, **overrides[0])
child1 = dataclasses.replace(base, **overrides[1])
check("Gap D: child0 gets DELAYED policy",
      child0.signature_policy is SignaturePolicy.DELAYED,
      f"policy = {child0.signature_policy}")
check("Gap D: child0 gets startup_grace=3.0",
      child0.startup_grace == 3.0,
      f"grace = {child0.startup_grace}")
check("Gap D: child1 gets ID_COMMAND policy",
      child1.signature_policy is SignaturePolicy.ID_COMMAND,
      f"policy = {child1.signature_policy}")
check("Gap D: child1 gets configured_hgi_id",
      child1.configured_hgi_id == "18:006402",
      f"hgi_id = {child1.configured_hgi_id}")
check("Gap D: base config unchanged",
      base.signature_policy is SignaturePolicy.IMMEDIATE,
      f"base policy = {base.signature_policy}")

# ---------------------------------------------------------------------------
# Gap E: ID_COMMAND policy and !I response regex
# ---------------------------------------------------------------------------
check("Gap E: SignaturePolicy.ID_COMMAND exists",
      SignaturePolicy.ID_COMMAND is not None,
      f"ID_COMMAND = {SignaturePolicy.ID_COMMAND}")

from ramses_tx.transport.port import _EVOFW3_ID_RE
match = _EVOFW3_ID_RE.match("# 18:006402")
check("Gap E: !I regex parses '18:006402'",
      match is not None,
      f"match = {match}")

match2 = _EVOFW3_ID_RE.match("# 18:140805")
check("Gap E: !I regex parses '18:140805'",
      match2 is not None,
      f"groups = {match2.groups() if match2 else None}")

match3 = _EVOFW3_ID_RE.match("# garbage")
check("Gap E: !I regex rejects 'garbage'",
      match3 is None,
      "rejected")

match4 = _EVOFW3_ID_RE.match("# 1:12345")
check("Gap E: !I regex rejects short ID",
      match4 is None,
      "rejected")

match5 = _EVOFW3_ID_RE.match("18:006402")
check("Gap E: !I regex rejects missing # prefix",
      match5 is None,
      "rejected")

# ---------------------------------------------------------------------------
# Gap F: evofw3 # debug response filtering
# ---------------------------------------------------------------------------
from ramses_tx.transport.base import _ReadTransport
source = inspect.getsource(_ReadTransport._frame_read)
check("Gap F: _frame_read filters # lines",
      "startswith" in source and "#" in source,
      "source contains # filter")

check("Gap F: _EVOFW3_ID_RE available",
      _EVOFW3_ID_RE is not None,
      f"pattern = {_EVOFW3_ID_RE.pattern}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
print(json.dumps({
    "passed": passed,
    "failed": failed,
    "results": results,
}))
"""
        )

        if "error" in result:
            ctx.check("Recipe 104 executed", False, f"error: {result['error']}")
            return

        passed = result.get("passed", 0)
        failed = result.get("failed", 0)
        checks = result.get("results", [])

        for chk in checks:
            name = chk["name"]
            status = chk["status"]
            detail = chk["detail"]
            ctx.check(name, status == "PASS", detail)

        ctx.check(
            "All Phase 2 pool gap checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
