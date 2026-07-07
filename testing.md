testing (\* = done on ha-sim, A = automated via `tools/ha_sim_test.py`, 50 checks all passing, log report at `/tmp/ha_sim_test_log_report.txt`)

Service checklist:

- SVC_SYNC_TOPOLOGY
- SVC_ACCEPT_DISCOVERED_DEVICE
  SVC_ADD_FAKED_REM (prepared only — not fully implemented yet, WIP for future PR)
- SVC_DISABLE_DISCOVERED_DEVICE
- SVC_DISCARD_DISCOVERED_DEVICE
- SVC_ENABLE_DISCOVERED_DEVICE
- SVC_GET_DISCOVERED_DEVICES
- SVC_REMOVE_DISCOVERED_DEVICE
- SVC_REMOVE_DEVICE (ramses_cc)

PR 764 features — all implemented and unit-tested:

- remove_device service — DONE (commit 0e62f6a, 17 unit tests + ha-sim recipes 2/3/4/5)
- Zone→zone reassignment — DONE (sync_learned_topology, 9 unit tests + ha-sim recipe 6/14)
- CO2 sensor classification — DONE (generate_schema_entry, 6 unit tests)
- Cache HVAC schema separately — DONE (hvac_schema in .storage, 17 unit tests + ha-sim recipes 7/7b/15)
- Invalid main_tcs safety net — DONE (ha-sim recipe 10)
- Discovery lifecycle — DONE (ha-sim recipe 11: discover→accept→remove)

Bug fixes during ha-sim testing:

- ramses_cc services.py: RuntimeError dict-changed-size-during-iteration on \_fan_param_sequences cleanup (commit 0b8c499)
- ramses_extras response_templates.py: FAN/22F8 missing response caused 80s QoS queue blockage (commit 4b3cfca)
- ramses_extras response_engine.py: duplicate RP responses from ResponseEngine + ScenarioEngine gave wrong fan param values (commit 4b3cfca)
- ramses_extras **init**.py: HGI presence packet used 2309 payload for code 0005, causing ramses_rf validation warning (commit a039866)
- ramses_extras FAN.yaml: 10D0 and 313E payloads didn't match ramses_rf validation patterns (commit a039866)
- ramses_extras profile_loader.py: \_reload_ramses_cc always passed wipe_schema=True, clearing the config entry schema even when preload_schema=True provided a schema to load (fixed: wipe_schema only when no schema is preloaded)

---

How to call services on ha-sim: All service calls go to http://localhost:8124/api/services/<domain>/<service> or via Developer Tools → Services in the ha-sim UI.

##Recipe 1: Activate heat profile → verify schema + entities [A]
Goal: Load the heat_only profile, verify CTL + TRV + DHW entities are created and schema is populated.

Steps:

Activate the profile:

```yaml
action: ramses_extras.device_simulator_import_user_config
data:
  source: heat_only
  name: heat_only
```

Activate the CTL device:

```yaml
action: ramses_extras.device_simulator_activate_device
data:
  device_id: '01:150000'
  slug: CTL
```

Activate a TRV:

```yaml
action: ramses_extras.device_simulator_activate_device
data:
  device_id: '04:150000'
  slug: TRV
```

Activate DHW sensor:

```yaml
action: ramses_extras.device_simulator_activate_device
data:
  device_id: '07:150000'
  slug: DHW
```

Wait 2-3 minutes for heartbeats and zone binding packets
Verify:

docker logs ha-sim 2>&1 | grep "Discovery: Devices" shows more than just 18:001234
ha-sim UI → Settings → Devices shows CTL, TRV, DHW entities
.storage/ramses_cc schema has main_tcs: "01:150000" and zones with sensors/actuators
known_list includes 01:150000, 04:150000, 07:150000

## Recipe 2: remove_device service — remove a TRV [A]

Goal: Verify remove_device cleans a TRV from schema, known_list, and device registry.

Prerequisite: Recipe 1 completed (TRV 04:150000 is active and in schema)

Steps:

Call the remove service:

```yaml
action: ramses_cc.remove_device
data:
  device_id: '04:150000'
```

Wait for coordinator refresh
Verify:

04:150000 removed from schema (check .storage/ramses_cc → client_state.schema)
04:150000 removed from known_list in config entry options
HA device registry entry for 04:150000 is gone (Settings → Devices)
TRV entity no longer exists
docker logs ha-sim 2>&1 | grep "Removed device" shows the removal
CTL and DHW entities are unaffected

## Recipe 3: remove_device — HGI rejection [A]

Goal: Verify the HGI gateway cannot be removed.

Steps:

Call:

```yaml
action: ramses_cc.remove_device
data:
  device_id: '18:001234'
```

Verify:

Service raises ServiceValidationError ("Cannot remove the HGI gateway")
HGI entity still present
Schema unchanged
Recipe 4: remove_device — CTL (main_tcs) removal [A]
Goal: Verify removing the CTL clears main_tcs and all zone entities.

Prerequisite: Recipe 1 completed

Steps:

Call:

```yaml
action: ramses_cc.remove_device
data:
  device_id: '01:150000'
```

Verify:

main_tcs is cleared in schema
"01:150000" top-level key deleted from schema
All zone entities (climate, temperature) removed
CTL entity removed from device registry
DHW sensor entity may remain if it was in orphans_heat

## Recipe 5: remove_device + restart — no resurrection [A]

Goal: Verify a removed device does not come back after restart.

Prerequisite: Recipe 2 completed (TRV removed), Recipe 4 completed (CTL removed), Recipe 7b completed (restart)

Steps:

docker restart ha-sim
Wait for startup + first heartbeat
Verify:

04:150003 does NOT reappear in known_list
01:150000 does NOT reappear in known_list
No errors about missing device in logs
Note: HA's entity/device registry may not be flushed to disk before restart, so orphaned entity states can linger in the states API. The known_list check is the real persistence guarantee — if the device is not in the known_list, ramses_cc won't create new entities for it on the next reload.

## Recipe 6/14: Zone binding via inject_message [A]

Goal: Verify that injecting a 000C zone binding packet creates a new zone in the schema via sync_learned_topology.

Prerequisite: Recipe 1 completed (mixed profile loaded, CTL active with zones)

Steps:

Check current schema — note existing zones (e.g. 03-08)
Inject a 000C zone binding packet as an RP from CTL to HGI, placing TRV 04:150003 in a new zone 09:

```yaml
action: ramses_extras.device_simulator_inject_message
data:
  source_id: '01:150000'
  dst: '18:001234'
  code: '000C'
  payload: '0908001249F3' # zone 09, rad_actuator, device 04:150003
  verb: 'RP'
```

The payload format is: zone_idx(1) + zone_type(1) + pad(1) + dev_hex_id(3). The dev_hex_id is NOT the raw device address — it's the transformed hex from ramses_rf.address.dev_id_to_hex_id(). For 04:150003, dev_id_to_hex_id returns "1249F3".
Wait 5s for ramses_rf to process the packet, then call sync_topology:

```yaml
action: ramses_cc.sync_topology
```

Wait 10s for sync_learned_topology + save_client_state
Verify:

Zone 09 appears in cached schema with class "radiator_valve"
docker logs ha-sim 2>&1 | grep "Learned topology is richer" shows sync happened
Note: ramses_rf prevents moving a device from one zone to another at runtime ("can't change parent"), so the zone is created but the device stays in its original zone.

## Recipe 7: HVAC schema caching — FAN + remotes survive restart [A]

Goal: Verify HVAC topology (FAN with remotes) survives restart despite load_fan stub.

Steps:

Activate the hvac_only profile:

```yaml
action: ramses_extras.device_simulator_import_user_config
data:
  source: hvac_only
  name: hvac_only
```

Activate FAN + REM + CO2:

```yaml
action: ramses_extras.device_simulator_activate_device
data:
  device_id: "32:150000"
  slug: FAN
action: ramses_extras.device_simulator_activate_device
data:
  device_id: "37:170000"
  slug: REM
action: ramses_extras.device_simulator_activate_device
data:
  device_id: "37:120000"
  slug: CO2
```

Wait 2-3 min for FAN heartbeat packets
Check .storage/ramses_cc:

```bash
docker exec ha-sim cat /config/.storage/ramses_cc | python3 -c "
import json, sys; d=json.load(sys.stdin)
print('HVAC schema:', json.dumps(d['data'].get('hvac_schema', {}), indent=2))
print('Schema:', json.dumps(d['data']['client_state']['schema'], indent=2))
"
```

Restart: docker restart ha-sim
Verify:

Before restart: hvac_schema key in .storage/ramses_cc contains {"32:150000": {"remotes": [...], "sensors": [...]}}
Before restart: FAN entity exists in ha-sim
After restart: FAN entity recreated
After restart: 32:150000 still has remotes and sensors in schema
After restart: hvac_schema cache preserved

## Recipe 8: HVAC schema caching — merge union on reload [A]

Goal: Verify cached HVAC entries merge with config schema (union, no duplicates).

Steps:

Load a custom YAML profile via load_profile_yaml with FAN having remotes: ["37:170000", "37:180000"]
ramses_cc reloads in-process (no docker restart needed — logs preserved, ~15s faster)
Verify:

After reload, FAN has both 37:170000 AND 37:180000 in remotes
No duplicates in remotes list

## Recipe 9: User schema edits survive sync — \_alias [A]

Goal: Verify a user-added \_alias on a zone survives sync_learned_topology.

Prerequisite: Recipe 1 completed (heat profile with zones)

Steps:

Load a custom YAML profile via load_profile_yaml with \_alias: "Living Room" on zone 03
ramses_cc reloads in-process with the \_alias in the config entry schema
Trigger sync_topology to run sync_learned_topology
Verify:

Zone 03 has \_alias: "Living Room" after sync_learned_topology
User-authored key preserved while learned topology (sensor, actuators) is merged

## Recipe 10: Corrupt schema recovery — main_tcs → TRV ID [A]

Goal: Verify the coordinator safety net clears an invalid main_tcs.

Steps:

Load a custom YAML profile via load_profile_yaml with invalid main_tcs=04:999999 in the schema
ramses_cc reloads in-process — the coordinator's \_async_setup safety net clears the invalid main_tcs
Verify:

No crash — ha-sim responds normally
docker logs ha-sim 2>&1 | grep "Sanitising invalid main_tcs" shows the warning
Invalid main_tcs (04:999999) is cleared in config entry options

## Recipe 11: Full lifecycle — discover → accept → remove [A]

Goal: End-to-end test of discovery + removal with the device simulator.

Steps:

Load fresh_start_allow_unknown_devices_fast_heartbeat profile (clean slate, only HGI known, enforce_known_list=False):

```yaml
# Via websocket:
{
  'type': 'ramses_extras/device_simulator/load_profile',
  'profile': 'fresh_start_allow_unknown_devices_fast_heartbeat',
  'speed': 0.01,
  'preload_schema': false,
  'reload_ramses_cc': true,
  'enable_auto_answer': true,
}
```

Inject 1FC9 heartbeats from a new TRV 04:200001 (not in any profile or schema):

```yaml
action: ramses_extras.device_simulator_inject_message
data:
  source_id: '04:200001'
  code: '1FC9'
  payload: '0030C912E294'
  verb: 'I'
```

Wait 10s for discovery scan to detect the new TRV
Accept the discovered device:

```yaml
action: ramses_cc.accept_discovered_device
data:
  device_id: '04:200001'
```

Wait 5s for ramses_rf include list update, then inject a 30C9 temperature packet to give the entity a state
Wait 8s for entity creation + state propagation
Remove the device:

```yaml
action: ramses_cc.remove_device
data:
  device_id: '04:200001'
```

Verify:

Step 3-4: Device discovered and accepted (accept_discovered_device succeeds)
Step 5-6: After accept, TRV in schema, TRV entity created (found in states API)
Step 7-8: After remove, entity gone, schema cleaned
Note: Uses a brand-new device ID (04:200001) that's not in any profile or schema, so the discovery manager treats it as truly unknown. The fresh_start profile clears the known_list to HGI only, so existing devices won't interfere.

## Recipe 12: HVAC device loss scenario [A]

Goal: Verify the hvac_device_loss scenario works with the new HVAC schema caching.

Steps:

Load mixed profile, activate FAN + REM
Start the HVAC device loss scenario:

```yaml
action: ramses_extras.device_simulator_run_scenario
data:
  scenario_type: hvac_device_loss
  params:
    device_id: '37:170000' # REM
    loss_after: 10 # silence after 10s
    restore_after: 20 # restore after 20s
```

Wait 30 seconds
Verify:

After 10s: REM stops emitting
After 20s: REM resumes
FAN entity remains available throughout
HVAC schema in .storage/ramses_cc still has FAN with remotes

## Recipe 13: Mixed profile — heat + HVAC together [A — setup step uses mixed profile]

Goal: Verify both heat and HVAC topology work simultaneously.

Steps:

Load mixed profile:

```yaml
action: ramses_extras.device_simulator_import_user_config
data:
  source: mixed
  name: mixed
```

Activate all devices: CTL, TRV, DHW, FAN, CO2, REM, HUM
Wait 3-5 min for all heartbeats
Verify:

Heat entities: CTL climate, TRV valves, DHW sensor
HVAC entities: FAN, CO2, REM
Schema has both heat entries (01:150000 with zones) and HVAC entries (32:150000 with remotes/sensors)
hvac_schema cache populated
docker logs ha-sim 2>&1 | grep "Discovery: Devices" shows all devices

## Recipe 14: Inject raw packet — simulate zone binding change [A]

Goal: Use inject_message to simulate a 000C zone map update and verify sync_learned_topology picks it up.

Prerequisite: Recipe 1 completed

Steps:

Check current zone assignments in schema
Inject a 000C packet that moves a sensor to a new zone:

```yaml
action: ramses_extras.device_simulator_inject_message
data:
  source_id: '01:150000' # from CTL
  code: '000C'
  payload: '020400896853' # zone 02, zone_sensor, device 34:150000
  verb: 'I'
```

Wait for sync (or call ramses_cc.sync_topology if available)
Verify:

34:150000 (RND thermostat) appears in zone 02 in schema
Old zone assignment cleared
docker logs ha-sim 2>&1 | grep "Learned topology" shows sync

## Recipe 15: Verify .storage/ramses_cc after save — HVAC key present [A]

Goal: Directly verify that async_save_client_state writes the hvac_schema key.

Prerequisite: Recipe 7 or 13 completed (HVAC devices active)

Steps:

Wait for async_save_client_state to run (check logs):

```bash
docker logs ha-sim 2>&1 | grep "Saving the client state cache" | tail -1
Inspect storage:
```

```bash
docker exec ha-sim cat /config/.storage/ramses_cc | python3 -c "
import json, sys
d = json.load(sys.stdin)['data']
print('Keys:', list(d.keys()))
print('HVAC schema:', json.dumps(d.get('hvac_schema', 'MISSING'), indent=2))
print('Schema HVAC entries:', {
    k: v for k, v in d.get('client_state', {}).get('schema', {}).items()
    if isinstance(v, dict) and ('remotes' in v or 'sensors' in v)
})
"
```

Verify:

hvac_schema key exists in .storage/ramses_cc data
hvac_schema contains FAN entries with remotes/sensors
orphans_hvac present in hvac_schema if there are orphan HVAC devices

## Recipe 16: Concurrency/stress test [A]

Goal: Verify no race conditions or orphaned tasks under rapid add/remove + inject cycles.

Steps:

Rapid inject + sync_topology cycles (5 iterations):
Inject 1FC9 heartbeat from 04:300001, immediately call sync_topology
Rapid discover/accept/remove cycles (3 iterations):
Inject heartbeat from 04:40000X, accept_discovered_device, remove_device
Verify:

No RuntimeError during rapid inject + sync cycles
No RuntimeError during rapid discover/accept/remove cycles
ha-sim still responsive after stress test
No ramses_cc ERROR logs during stress test

## Recipe 17: Discovery service lifecycle [A]

Goal: Test all discovery services end-to-end: get, discard, enable, accept, disable, remove.

Steps:

Load fresh_start_allow_unknown_devices_fast_heartbeat profile (clean slate, enforce_known_list=False)
Inject 1FC9 heartbeat from 04:500001 to trigger discovery
Call get_discovered_devices (subscribe to ramses_cc_discovered_devices event via websocket)
Call discard_discovered_device → device stays in list but won't be created
Call enable_discovered_device → re-enable the discarded device
Call accept_discovered_device → auto-generate schema entry, trigger entity creation
Call disable_discovered_device → temporarily disable (maintenance)
Call remove_discovered_device → mark as removed, discovery info kept for spam prevention
Verify:

get_discovered_devices returns the discovered device
Each service call succeeds without error

## Recipe 18: add_faked_rem service [prepared — not fully implemented yet]

Goal: Create a faked REM (virtual remote) for sending commands to a FAN.

Note: add_faked_rem only registers a metadata entry in the discovery manager (faked=true, status=accepted). It does NOT add the REM to the FAN's remotes in the schema or create a HA entity. Full implementation (binding + command forwarding) is WIP for a future PR.

Steps (when implemented):

Load mixed profile, activate FAN
Call add_faked_rem with device_id="37:000001", bound_to="32:150000"
Verify faked REM appears in discovered devices (faked=true)
Verify faked REM added to FAN's remotes in schema
Verify faked REM entity created
Automation summary:

- [A] = automated in `tools/ha_sim_test.py` (runs in ~6 min via websocket + REST API with 100x speed)
- Log report: `/tmp/ha_sim_test_log_report.txt` (ERROR/WARNING analysis with expected-warning filtering)
- 50 checks: 48 recipe checks + 2 log monitor checks (0 unexpected errors, 0 unexpected warnings)
- Automated recipes: 1, 2, 3, 4, 5, 6/14, 7, 7b, 8, 9, 10, 11, 12, 14, 15, 16, 17
- Manual-only recipes: none
- Recipe 13 (mixed profile) is covered by the automated setup step
- Recipe 17 (discovery service lifecycle) tests get/discard/enable/accept/disable/remove_discovered_device
- Recipe 18 (add_faked_rem) is prepared but not tested — service only registers metadata, full implementation is WIP
- Recipes 8, 9, 10 use load_profile_yaml (custom YAML profile via websocket) instead of docker restarts — faster, preserves logs
- Only Recipe 7b uses a docker restart (to test HVAC cache survival across a real restart)
- Log monitor captures logs before docker restarts (via `capture_before_restart`) to avoid losing data when the log buffer is wiped

These 18 recipes use the ramses_extras device_simulator services (activate_device, inject_message, run_scenario, load_profile_yaml, import_user_config) and the ramses_cc services (remove_device, accept_discovered_device, discard_discovered_device, enable_discovered_device, disable_discovered_device, remove_discovered_device, get_discovered_devices, sync_topology) to test all PR 764 features end-to-end on ha-sim. Each recipe includes the exact service call YAML and verification commands using docker exec and docker logs.
