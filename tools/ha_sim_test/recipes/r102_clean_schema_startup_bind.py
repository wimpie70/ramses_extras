"""Recipe R102: Clean-schema startup bind (issue 1119).

Verifies that ramses_cc starts up quickly with a clean schema
(only ``_owner: me``) and the MQTT pool bridge binds the protocol
immediately without waiting for an HGI to come online.

Before the fix, the pool bridge waited up to 30s for an HGI LWT
message before calling ``protocol.connection_made()``, causing the
engine's bind timeout to fire on clean-schema startup.  Now the
protocol is bound immediately when the pool is created.

This recipe:
1. Loads a minimal profile (CTL + HGI) to ensure devices exist
2. Wipes the schema to ``_owner: me`` only via clear_cached_state
3. Restarts ramses_cc
4. Checks that no bind timeout occurred in the logs
5. Checks that the primary HGI is registered in the schema
6. Publishes a second HGI online via MQTT
7. Checks that the second HGI is discovered as an ownerless candidate
8. Checks that a notification was sent for the ownerless candidate
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from ..base import Recipe, RecipeContext
from ..const import MQTT_BROKER_URL, MQTT_TOPIC_NS
from ..helpers import (
    clear_cached_state,
    get_schema_retry,
    grep_ha_log,
    wait_for_ramses_cc_reload,
    wait_for_transport_ready,
)
from ..profile import minimal_ctl_yaml

SECOND_HGI_ID = "18:007777"


def _publish_mqtt(topic: str, payload: str, retain: bool = False) -> None:
    """Publish a single message to the MQTT broker."""
    parsed = urlparse(MQTT_BROKER_URL)
    host = parsed.hostname or "localhost"
    port = int(parsed.port) if parsed.port else 1883
    username = parsed.username or ""
    password = parsed.password or ""

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"ha_sim_r102_{int(time.time())}",
        protocol=mqtt.MQTTv5,
    )
    if username:
        client.username_pw_set(username, password)
    client.connect(host, port, 60)
    client.loop_start()
    client.publish(topic, payload=payload, qos=0, retain=retain)
    client.loop_stop()
    client.disconnect()


class R102CleanSchemaStartupBind(Recipe):
    id = "R102"
    seq = 1020
    title = "Clean-schema startup bind + notification dismissal"
    tags = ("mqtt", "multi-hgi", "startup", "bind", "issue-1119")

    async def run(self, ctx: RecipeContext) -> None:
        ctx.log_section("Recipe 102: Clean-schema startup bind")

        # --- Step 1: Load a minimal profile so we have devices ---
        from ..helpers import load_profile_yaml

        yaml_profile = minimal_ctl_yaml()
        print("  Loading minimal profile (CTL + HGI)...")
        try:
            await load_profile_yaml(ctx.token, yaml_profile, speed=0.01)
        except RuntimeError:
            pass
        ctx.wait(5, "for profile to settle")

        # --- Step 2: Wipe schema + cached state ---
        # clear_cached_state deletes .storage/ramses_cc + ramses.db
        # and clears CONF_SCHEMA, forcing a clean-schema restart.
        print("  Wiping cached state for clean-schema restart...")
        clear_cached_state(ctx.log_monitor, label="R102 clean-schema")
        ctx.wait_for_ha_ready(timeout=30)
        ctx.log_monitor.reset_baseline()
        ctx.refresh_token()
        ctx.wait_for_ramses_cc_loaded(timeout=30)
        wait_for_transport_ready(timeout=30)

        # --- Step 3: Check no bind timeout in logs ---
        timeout_logs = grep_ha_log(
            r"Transport did not bind to Protocol within",
            since_lines=300,
        )
        ctx.check(
            "no bind timeout after clean-schema restart",
            len(timeout_logs) == 0,
            f"found {len(timeout_logs)} timeout log(s): " + "; ".join(timeout_logs[:3]),
        )

        # --- Step 4: Check primary HGI is registered ---
        schema_after = get_schema_retry(max_tries=5, delay=3)
        hgi_keys = [
            k
            for k in schema_after
            if isinstance(schema_after.get(k), dict)
            and schema_after[k].get("_class", "").upper() == "HGI"
        ]
        ctx.check(
            "primary HGI registered in clean schema",
            len(hgi_keys) >= 1,
            f"HGI keys={hgi_keys}, schema keys={list(schema_after.keys())[:10]}",
        )

        if hgi_keys:
            primary_hgi = hgi_keys[0]
            entry = schema_after[primary_hgi]
            ctx.check(
                f"primary HGI {primary_hgi} has _owner: me",
                isinstance(entry, dict) and entry.get("_owner") == "me",
                f"entry={entry}",
            )

        # --- Step 5: Publish a second HGI online ---
        print(f"  Publishing 'online' status for {SECOND_HGI_ID}...")
        status_topic = f"{MQTT_TOPIC_NS}/{SECOND_HGI_ID}"
        _publish_mqtt(status_topic, "online", retain=True)
        ctx.wait(8, "for MQTT status to propagate and discovery to run")

        # --- Step 6: Check second HGI discovered as ownerless candidate ---
        schema_with_second = get_schema_retry(max_tries=5, delay=3)
        ctx.check(
            f"{SECOND_HGI_ID} discovered as ownerless candidate",
            SECOND_HGI_ID in schema_with_second,
            f"schema keys={list(schema_with_second.keys())[:15]}",
        )

        if SECOND_HGI_ID in schema_with_second:
            entry = schema_with_second[SECOND_HGI_ID]
            ctx.check(
                f"{SECOND_HGI_ID} classified as HGI",
                isinstance(entry, dict) and entry.get("_class", "").upper() == "HGI",
                f"entry={entry}",
            )
            ctx.check(
                f"{SECOND_HGI_ID} has no _owner (ownerless candidate)",
                isinstance(entry, dict) and "_owner" not in entry,
                f"entry={entry}",
            )

        # --- Step 7: Trigger sync_topology and check notification ---
        # The discovery scan runs periodically, but we can trigger it
        # explicitly to speed up the notification.
        from ..helpers import call_service

        try:
            call_service(ctx.token, "ramses_cc", "sync_topology")
        except RuntimeError:
            pass
        ctx.wait(8, "for sync_topology + discovery notification")

        notif_logs = grep_ha_log(
            r"check_for_new_devices.*sending notification.*"
            + SECOND_HGI_ID.replace(":", r"\:"),
            since_lines=500,
        )
        ctx.check(
            f"notification sent for {SECOND_HGI_ID}",
            len(notif_logs) > 0,
            f"found {len(notif_logs)} notification log(s)",
        )

        # --- Cleanup: remove second HGI ---
        print(f"  Cleaning up: removing {SECOND_HGI_ID}...")
        _publish_mqtt(status_topic, "", retain=True)
        _publish_mqtt(f"{MQTT_TOPIC_NS}/{SECOND_HGI_ID}/rx", "", retain=True)
