"""Recipe R83: Representative TRV sensor persistence (issue 1013)."""

from __future__ import annotations

import yaml

from ..base import Recipe, RecipeContext
from ..const import CTL
from ..helpers import (
    _get_ramses_cc_entry_id,
    call_service,
    clear_cached_state,
    get_entities,
    get_schema_retry,
    load_profile_yaml,
    wait_for,
    wait_for_transport_ready,
)


class R83RepresentativeTrvSensorPersistenceIssue1013(Recipe):
    id = "R83"
    seq = 830
    title = "Representative TRV sensor persistence (issue 1013)"

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 83: Representative TRV sensor persistence (issue 1013)")

        representative = "04:150003"
        other_trv = "04:150004"
        zone_index = "03"
        schema = {
            "main_tcs": CTL,
            CTL: {
                "_class": "CTL",
                "zones": {
                    zone_index: {
                        "class": "radiator_valve",
                        "sensor": None,
                        "actuators": [representative, other_trv],
                    }
                },
            },
            representative: {"_class": "TRV"},
            other_trv: {"_class": "TRV"},
        }
        profile = {
            "known_list": {
                CTL: {"class": "CTL"},
                representative: {"class": "TRV"},
                other_trv: {"class": "TRV"},
            },
            "_enforce_known_list": {"enabled": True},
            "_schema": schema,
        }

        clear_cached_state(ctx.log_monitor, label="R83 pre-restart")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)

        print("  Loading two-TRV profile with no configured zone sensor...")
        await load_profile_yaml(
            ctx.token,
            yaml.dump(profile, default_flow_style=False, sort_keys=False),
            speed=0.01,
            enable_eavesdrop=True,
        )
        ctx.wait_for_ramses_cc_reload(timeout=20)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)
        wait_for(
            lambda: (
                zone_index
                in get_schema_retry(max_tries=3, delay=1).get(CTL, {}).get("zones", {})
            ),
            timeout=15,
            interval=1,
            msg="for two-TRV zone schema",
            floor=3.0,
        )

        def _inject(source_id: str, payload: str) -> None:
            call_service(
                ctx.token,
                "ramses_extras",
                "device_simulator_inject_message",
                {
                    "source_id": source_id,
                    "code": "30C9",
                    "payload": payload,
                    "verb": "I",
                },
            )

        print("  Injecting controller and TRV temperatures for correlation...")
        _inject(CTL, "030834")
        ctx.wait(1, "after controller temperature")
        _inject(other_trv, "00079E")
        ctx.wait(1, "after non-representative TRV temperature")
        _inject(representative, "000834")

        def _sensor_persisted() -> bool:
            current = get_schema_retry(max_tries=3, delay=1)
            zone = current.get(CTL, {}).get("zones", {}).get(zone_index, {})
            return bool(zone.get("sensor") == representative)

        wait_for(
            _sensor_persisted,
            timeout=20,
            interval=1,
            msg="for representative TRV to persist as zone sensor",
            floor=5.0,
        )
        call_service(ctx.token, "ramses_cc", "sync_topology")
        ctx.wait(3, "for topology sync")

        current = get_schema_retry()
        zone = current.get(CTL, {}).get("zones", {}).get(zone_index, {})
        ctx.check(
            "representative TRV persisted as sensor",
            zone.get("sensor") == representative,
            f"zone={zone}",
        )
        ctx.check(
            "representative TRV remains an actuator",
            representative in zone.get("actuators", []),
            f"zone={zone}",
        )
        ctx.check(
            "other TRV remains actuator-only",
            other_trv in zone.get("actuators", []) and zone.get("sensor") != other_trv,
            f"zone={zone}",
        )

        print("  Reloading ramses_cc to verify the dual role survives...")
        entry_id = _get_ramses_cc_entry_id()
        if not entry_id:
            raise RuntimeError("ramses_cc config entry not found")
        call_service(
            ctx.token,
            "homeassistant",
            "reload_config_entry",
            {"entry_id": entry_id},
        )
        ctx.wait_for_ramses_cc_reload(timeout=30)
        ctx.refresh_token()
        wait_for_transport_ready(timeout=30)

        current = get_schema_retry()
        zone = current.get(CTL, {}).get("zones", {}).get(zone_index, {})
        ctx.check(
            "representative sensor survives reload",
            zone.get("sensor") == representative,
            f"zone={zone}",
        )
        ctx.check(
            "representative actuator role survives reload",
            representative in zone.get("actuators", []),
            f"zone={zone}",
        )

        def _climate_temperature() -> float | None:
            for entity in get_entities(ctx.token):
                if not entity.get("entity_id", "").startswith("climate."):
                    continue
                attrs = entity.get("attributes", {})
                if attrs.get("zone_index") == zone_index:
                    value = attrs.get("current_temperature")
                    return float(value) if isinstance(value, (int, float)) else None
            return None

        def _representative_baseline_ready() -> bool:
            if _climate_temperature() == 21.0:
                return True
            _inject(representative, "000834")
            call_service(ctx.token, "ramses_cc", "force_update")
            return False

        wait_for(
            _representative_baseline_ready,
            timeout=30,
            interval=2,
            msg="for representative temperature baseline",
            floor=15.0,
        )

        _inject(other_trv, "000708")
        call_service(ctx.token, "ramses_cc", "force_update")
        ctx.wait(3, "for non-representative temperature processing")
        ctx.check(
            "non-representative TRV does not overwrite zone temperature",
            _climate_temperature() == 21.0,
            f"current_temperature={_climate_temperature()}",
        )

        _inject(representative, "000898")
        call_service(ctx.token, "ramses_cc", "force_update")
        wait_for(
            lambda: _climate_temperature() == 22.0,
            timeout=20,
            interval=2,
            msg="for representative TRV temperature to hydrate climate",
            floor=10.0,
        )
        ctx.check(
            "representative TRV hydrates zone current_temperature",
            _climate_temperature() == 22.0,
            f"current_temperature={_climate_temperature()}",
        )
