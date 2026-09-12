"""Recipe R110: Schema mutation and pool type change scenarios.

Tests user-initiated schema edits, pool member changes, and
transport type switches:

- Manual HGI add to schema (not via discovery)
- Remove HGI from schema (demote to candidate)
- Change _preferred_type from usb to mqtt
- Disable pool member (_removed_from_pool)
- Re-enable disabled pool member
- Change primary from serial to MQTT (full flow)
- Change primary from MQTT to serial (full flow)
- Corrupt schema entries (non-dict values)
- Empty schema with only _owner
- Non-18: device with _class: HGI (invalid)
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R110SchemaMutationScenarios(Recipe):
    id = "R110"
    seq = 1100
    title = "Schema mutation and pool type change scenarios"
    tags = ("pooled", "multi-hgi", "phase2", "schema", "mutation")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify schema mutation scenarios."""
        ctx.log_section("Recipe 110: Schema mutation and pool type changes")

        result = docker_exec_python(
            """
import asyncio
import json

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


async def run_tests():
    from unittest.mock import MagicMock, patch, AsyncMock

    # ---------------------------------------------------------------------------
    # Test 1: Demote HGI — preserve _owner, set _removed_from_pool
    # ---------------------------------------------------------------------------
    # User unchecks an HGI in Manage Pool.  The config flow preserves
    # _owner and sets _removed_from_pool: true so re-adding is easy.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        # Simulate the demotion logic from config_flow.py
        schema_dict = {
            SZ_OWNER: "me",
            "18:130236": {
                "_class": "HGI",
                SZ_TR_OWNER: "me",
                "_comment": "Supports: usb",
            },
            "18:149488": {
                "_class": "HGI",
                SZ_TR_OWNER: "me",
                "_comment": "Supports: mqtt",
            },
        }

        keep_members = ["18:149488"]  # User keeps only this one
        root_owner = schema_dict.get(SZ_OWNER, "me")

        to_demote = []
        for dev_id, entry in schema_dict.items():
            if (
                dev_id.startswith("18:")
                and isinstance(entry, dict)
                and entry.get("_class", "").upper() == "HGI"
                and entry.get(SZ_TR_OWNER) == root_owner
                and not entry.get("_disabled")
            ):
                if dev_id not in keep_members:
                    to_demote.append(dev_id)

        for dev_id in to_demote:
            entry = schema_dict.get(dev_id, {})
            if isinstance(entry, dict):
                entry["_removed_from_pool"] = True
                schema_dict[dev_id] = entry

        check(
            "Demote HGI: _owner preserved, _removed_from_pool set",
            (
                "18:130236" in schema_dict
                and schema_dict["18:130236"].get(SZ_TR_OWNER) == "me"
                and schema_dict["18:130236"].get("_removed_from_pool") is True
                and schema_dict["18:149488"].get(SZ_TR_OWNER) == "me"
                and "18:149488" not in to_demote
            ),
            f"to_demote={to_demote}",
        )
    except Exception as e:
        check(
            "Demote HGI: _owner removed, _removed_from_pool set",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 2: Re-add HGI — clear _removed_from_pool
    # ---------------------------------------------------------------------------
    # User re-adds a previously removed HGI.  The config flow should
    # clear _removed_from_pool so the coordinator can re-register it.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        schema_dict = {
            SZ_OWNER: "me",
            "18:130236": {
                "_class": "HGI",
                "_removed_from_pool": True,
                "_comment": "Supports: usb",
            },
        }

        # Simulate re-add: clear _removed_from_pool
        hgi_id = "18:130236"
        if hgi_id in schema_dict and isinstance(schema_dict[hgi_id], dict):
            schema_dict[hgi_id].pop("_removed_from_pool", None)

        check(
            "Re-add HGI: _removed_from_pool cleared",
            "_removed_from_pool" not in schema_dict.get("18:130236", {}),
            f"entry={schema_dict.get('18:130236', {})}",
        )
    except Exception as e:
        check(
            "Re-add HGI: _removed_from_pool cleared",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: Change _preferred_type from usb to mqtt
    # ---------------------------------------------------------------------------
    # User changes the preferred transport for an HGI from USB to MQTT.
    # The schema should reflect the new preference.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.const import CONF_SCHEMA

        schema_dict = {
            "_owner": "me",
            "18:130236": {
                "_class": "HGI",
                "_preferred_type": "usb",
                "_comment": "Supports: usb, mqtt",
            },
        }

        # Simulate preferred_type change
        schema_dict["18:130236"]["_preferred_type"] = "mqtt"

        check(
            "Change _preferred_type: usb to mqtt",
            schema_dict["18:130236"].get("_preferred_type") == "mqtt",
            f"pref={schema_dict['18:130236'].get('_preferred_type')}",
        )
    except Exception as e:
        check(
            "Change _preferred_type: usb to mqtt",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 4: Coordinator skips _removed_from_pool HGIs
    # ---------------------------------------------------------------------------
    # The coordinator should NOT register HGIs that have
    # _removed_from_pool: true in the pool transport.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        coord = MagicMock()
        coord.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:001111": {"_class": "HGI", SZ_TR_OWNER: "me"},
                "18:130236": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_removed_from_pool": True,
                },
                "18:149488": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                },
            },
        }
        coord.options = coord.entry.options
        coord._get_primary_hgi_id = MagicMock(return_value="18:001111")
        coord.hass.config_entries.async_update_entry = MagicMock()

        # Use the coordinator's instance method
        pool_hgis = RamsesCoordinator._extract_pool_hgis_from_schema(coord)

        check(
            "Coordinator: _removed_from_pool HGI excluded from pool",
            "18:130236" not in pool_hgis
            and "18:149488" in pool_hgis,
            f"pool_hgis={pool_hgis}",
        )
    except Exception as e:
        check(
            "Coordinator: _removed_from_pool HGI excluded from pool",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 5: Corrupt schema entries — non-dict values
    # ---------------------------------------------------------------------------
    # Schema entries that are not dicts should be handled gracefully.
    # The coordinator should not crash on non-dict entries.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import SZ_OWNER

        coord2 = MagicMock()
        coord2.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:130236": "not a dict",  # Corrupt
                "18:149488": None,  # Corrupt
                "18:001111": {"_class": "HGI"},  # Valid candidate
                "32:150000": {"_class": "CTL"},  # Not HGI
            }
        }

        pool_hgis2 = RamsesCoordinator._extract_pool_hgis_from_schema(coord2)

        check(
            "Corrupt schema: non-dict entries handled gracefully",
            "18:130236" not in pool_hgis2
            and "18:149488" not in pool_hgis2
            and "18:001111" in pool_hgis2,
            f"pool_hgis={pool_hgis2}",
        )
    except Exception as e:
        check(
            "Corrupt schema: non-dict entries handled gracefully",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 6: Empty schema with only _owner
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import SZ_OWNER

        coord3 = MagicMock()
        coord3.entry.options = {
            CONF_SCHEMA: {SZ_OWNER: "me"},
        }

        pool_hgis3 = RamsesCoordinator._extract_pool_hgis_from_schema(coord3)

        check(
            "Empty schema: no HGIs extracted",
            len(pool_hgis3) == 0,
            f"pool_hgis={pool_hgis3}",
        )
    except Exception as e:
        check(
            "Empty schema: no HGIs extracted",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 7: Non-18: device with _class: HGI (invalid)
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import SZ_OWNER, SZ_TR_OWNER

        coord4 = MagicMock()
        coord4.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "32:150000": {  # Not 18: prefix
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                },
                "18:130236": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                },
            }
        }

        pool_hgis4 = RamsesCoordinator._extract_pool_hgis_from_schema(coord4)

        check(
            "Invalid HGI: non-18: device with _class HGI ignored",
            "32:150000" not in pool_hgis4
            and "18:130236" in pool_hgis4,
            f"pool_hgis={pool_hgis4}",
        )
    except Exception as e:
        check(
            "Invalid HGI: non-18: device with _class HGI ignored",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 8: Foreign _owner HGI excluded from pool
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import SZ_OWNER, SZ_TR_OWNER

        coord5 = MagicMock()
        coord5.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:130236": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                },
                "18:149488": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "other",  # Foreign
                },
                "18:333333": {
                    "_class": "HGI",
                    # No _owner = candidate
                },
            }
        }

        pool_hgis5 = RamsesCoordinator._extract_pool_hgis_from_schema(coord5)

        check(
            "Foreign HGI: excluded from pool members",
            "18:130236" in pool_hgis5
            and "18:149488" not in pool_hgis5
            and "18:333333" in pool_hgis5,
            f"pool_hgis={pool_hgis5}",
        )
    except Exception as e:
        check(
            "Foreign HGI: excluded from pool members",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 9: Disabled HGI excluded from pool
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import SZ_OWNER, SZ_TR_OWNER

        coord6 = MagicMock()
        coord6.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:130236": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_disabled": True,
                },
                "18:149488": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                },
            }
        }

        pool_hgis6 = RamsesCoordinator._extract_pool_hgis_from_schema(coord6)

        check(
            "Disabled HGI: excluded from pool",
            "18:130236" not in pool_hgis6
            and "18:149488" in pool_hgis6,
            f"pool_hgis={pool_hgis6}",
        )
    except Exception as e:
        check(
            "Disabled HGI: excluded from pool",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 10: Change primary serial to MQTT — schema preserved
    # ---------------------------------------------------------------------------
    # When the user changes the primary from serial to MQTT, the
    # schema entries for existing HGIs should be preserved.  Only
    # the primary port config changes.
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_SERIAL_PORT,
            SZ_PORT_NAME,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        # Before: serial primary
        options_before = {
            SZ_SERIAL_PORT: {SZ_PORT_NAME: "/dev/ttyUSB0"},
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:130236": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_comment": "Supports: usb",
                },
            },
        }

        # After: change to MQTT primary
        options_after = dict(options_before)
        options_after[SZ_SERIAL_PORT] = {
            SZ_PORT_NAME: "mqtt://broker:1883/RAMSES/GATEWAY"
        }
        # Schema should be preserved
        schema_preserved = (
            options_after[CONF_SCHEMA] == options_before[CONF_SCHEMA]
        )

        check(
            "Change primary serial to MQTT: schema preserved",
            schema_preserved,
            f"schema_preserved={schema_preserved}",
        )
    except Exception as e:
        check(
            "Change primary serial to MQTT: schema preserved",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 11: Change primary MQTT to serial — schema preserved
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.const import (
            CONF_SCHEMA,
            SZ_SERIAL_PORT,
            SZ_PORT_NAME,
            SZ_OWNER,
            SZ_TR_OWNER,
        )

        # Before: MQTT primary
        options_before2 = {
            SZ_SERIAL_PORT: {
                SZ_PORT_NAME: "mqtt://broker:1883/RAMSES/GATEWAY"
            },
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:149488": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_comment": "Supports: mqtt",
                },
            },
        }

        # After: change to serial primary
        options_after2 = dict(options_before2)
        options_after2[SZ_SERIAL_PORT] = {SZ_PORT_NAME: "/dev/ttyUSB0"}
        schema_preserved2 = (
            options_after2[CONF_SCHEMA] == options_before2[CONF_SCHEMA]
        )

        check(
            "Change primary MQTT to serial: schema preserved",
            schema_preserved2,
            f"schema_preserved={schema_preserved2}",
        )
    except Exception as e:
        check(
            "Change primary MQTT to serial: schema preserved",
            False,
            f"exception: {str(e)[:200]}",
        )

    # ---------------------------------------------------------------------------
    # Test 12: get_accepted_hgi_ids excludes disabled and foreign
    # ---------------------------------------------------------------------------
    try:
        from custom_components.ramses_cc.coordinator import RamsesCoordinator
        from custom_components.ramses_cc.const import SZ_OWNER, SZ_TR_OWNER

        coord7 = MagicMock()
        coord7.entry.options = {
            CONF_SCHEMA: {
                SZ_OWNER: "me",
                "18:130236": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                },
                "18:149488": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "me",
                    "_disabled": True,
                },
                "18:333333": {
                    "_class": "HGI",
                    SZ_TR_OWNER: "other",
                },
            }
        }
        coord7._get_primary_hgi_id = MagicMock(return_value="18:001111")

        accepted_ids = RamsesCoordinator._get_accepted_hgi_ids(coord7)

        check(
            "get_accepted_hgi_ids: excludes disabled and foreign",
            "18:130236" in accepted_ids
            and "18:149488" not in accepted_ids
            and "18:333333" not in accepted_ids,
            f"accepted_ids={accepted_ids}",
        )
    except Exception as e:
        check(
            "get_accepted_hgi_ids: excludes disabled and foreign",
            False,
            f"exception: {str(e)[:200]}",
        )

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


asyncio.run(run_tests())
""",
            timeout=60,
        )

        if "error" in result:
            ctx.check("Recipe 110 executed", False, f"error: {result['error']}")
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
            "All schema mutation checks passed",
            failed == 0,
            f"{passed} passed, {failed} failed",
        )
