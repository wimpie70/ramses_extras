"""Recipe R39: CommandDTO carries no application metadata (issue 639).

Issue 639 rule 1: "No Application Metadata in TX".
``CommandDTO`` must never contain application-layer flags such as
``is_faked``, ``expected_response``, ``device_type``, or ``wait_for_reply``.
If a virtual device should not broadcast, ``ramses_rf`` must simply not send
a ``CommandDTO``.

This recipe inspects the ``CommandDTO`` dataclass definition inside the
ha-sim container (which has the newer ramses_tx with ``dtos.py``) and
verifies that only L2/L3 fields exist.

See: https://github.com/ramses-rf/ramses_rf/issues/639
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R39CommandDtoNoAppMetadataIssue639(Recipe):
    id = "R39"
    seq = 400
    title = "CommandDTO carries no application metadata (issue 639)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 39: CommandDTO carries no application metadata")

        # Run the inspection inside the container where ramses_tx.dtos exists
        code = """
import dataclasses, json
try:
    from ramses_tx.dtos import CommandDTO
    fields = sorted(f.name for f in dataclasses.fields(CommandDTO))
    frozen = getattr(CommandDTO.__dataclass_params__, "frozen", False)
    print(json.dumps({"fields": fields, "frozen": frozen, "ok": True}))
except ImportError as e:
    print(json.dumps({"error": str(e), "ok": False}))
"""
        result = docker_exec_python(code)

        if not result.get("ok"):
            ctx.check(
                "CommandDTO importable from ramses_tx.dtos",
                False,
                result.get("error", "unknown"),
            )
            return

        ctx.check("CommandDTO importable from ramses_tx.dtos", True, "")

        field_names = set(result["fields"])

        # The allowed L2/L3 fields per issue 639
        allowed_fields = {
            "verb",
            "addr1",
            "addr2",
            "addr3",
            "code",
            "payload",
            "priority",
            "num_repeats",
        }

        ctx.check(
            "CommandDTO has exactly the allowed L2/L3 fields",
            field_names == allowed_fields,
            f"extra: {field_names - allowed_fields}, "
            f"missing: {allowed_fields - field_names}",
        )

        # Forbidden application-layer fields that must never appear
        forbidden_fields = {
            "is_faked",
            "expected_response",
            "device_type",
            "wait_for_reply",
            "device_class",
            "src",
            "dst",
            "action",
            "data",
            "intent",
        }

        found_forbidden = field_names & forbidden_fields
        ctx.check(
            "CommandDTO has no forbidden application-layer fields",
            len(found_forbidden) == 0,
            f"found: {found_forbidden}",
        )

        # Verify CommandDTO is frozen (immutable per issue 639 DTO rules)
        ctx.check(
            "CommandDTO is frozen (immutable)",
            result.get("frozen", False),
            "CommandDTO is not frozen",
        )

        print(f"  CommandDTO fields: {sorted(field_names)}")
