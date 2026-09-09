#!/usr/bin/env bash
# Test all multi-HGI pool scenarios on the hass container.
# Usage: bash test_pool_scenarios.sh [scenario_number]
set -euo pipefail

HASS_CONTAINER="hass"
CONFIG_ENTRIES="/config/.storage/core.config_entries"
LOG="/config/home-assistant.log"
WAIT_STARTUP=90
WAIT_TRAFFIC=60

# HGI IDs (discovered from previous runs)
HGI_A="18:130236"  # ESP on /dev/ttyACM0
HGI_B="18:149488"  # ESP on /dev/ttyACM1

wait_for_startup() {
    echo "  Waiting ${WAIT_STARTUP}s for HA startup..."
    sleep $WAIT_STARTUP
}

wait_for_traffic() {
    echo "  Waiting ${WAIT_TRAFFIC}s for traffic..."
    sleep $WAIT_TRAFFIC
}

check_logs() {
    local scenario="$1"
    echo "  --- Log summary for ${scenario} ---"

    # Pool configuration
    docker exec $HASS_CONTAINER grep -i "configured HGI\|Connection.*established\|excluded\|child.*online" $LOG 2>/dev/null | tail -10 | sed 's/^/  /'

    # Traffic
    local mqtt_rx=$(docker exec $HASS_CONTAINER grep -c "MqttPoolBridge: RX" $LOG 2>/dev/null || echo "0")
    local serial_rx=$(docker exec $HASS_CONTAINER grep -c "ramses_rf_logs" $LOG 2>/dev/null || echo "0")
    echo "  MQTT RX packets: ${mqtt_rx}"

    # Packet log
    echo "  Packet log (last 3):"
    docker exec $HASS_CONTAINER tail -3 /config/ramses_rf_logs/packet_log.log 2>/dev/null | sed 's/^/    /' || echo "    (no packet log)"

    # Errors
    local errors=$(docker exec $HASS_CONTAINER grep -c "PacketInvalid(Null packet)\|Traceback\|ERROR.*transport\|TransportSerialError" $LOG 2>/dev/null || echo "0")
    echo "  Errors: ${errors}"

    # Active HGI
    docker exec $HASS_CONTAINER grep "active_hgi_id" $LOG 2>/dev/null | tail -1 | sed 's/^/  /'

    echo "  --- End ${scenario} ---"
}

clear_log() {
    docker exec $HASS_CONTAINER sh -c 'echo "" > /config/home-assistant.log' 2>/dev/null || true
}

set_config() {
    local serial_port="$1"  # "mqtt_ha" or "/dev/ttyACM0" etc.
    local schema_json="$2" # JSON string for schema modifications

    docker exec $HASS_CONTAINER python3 -c "
import json
p = '${CONFIG_ENTRIES}'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] == 'ramses_cc':
        opts = e['options']
        # Set serial port
        if '${serial_port}' == 'mqtt_ha':
            opts['serial_port'] = {'port_name': 'mqtt_ha'}
            opts['mqtt_use_ha'] = True
        else:
            opts['serial_port'] = {
                'port_name': '${serial_port}',
                'baudrate': 115200,
                'dsrdtr': False,
                'rtscts': False,
                'timeout': 3,
                'xonxoff': False,
            }
            opts['mqtt_use_ha'] = True  # keep MQTT bridge for pool members
        # Apply schema modifications
        schema = opts.get('schema', {})
        mods = json.loads('''${schema_json}''')
        for dev_id, mods_dict in mods.items():
            if dev_id in schema:
                schema[dev_id].update(mods_dict)
            else:
                schema[dev_id] = mods_dict
        opts['schema'] = schema
json.dump(d, open(p, 'w'), indent=2)
print('Config set: serial_port=${serial_port}')
"
}

restart_hass() {
    docker restart $HASS_CONTAINER 2>&1 | sed 's/^/  /'
}

# ---------------------------------------------------------------------------
# Scenario 3: Both USB (no MQTT pool members)
# ---------------------------------------------------------------------------
test_scenario_3() {
    echo "=== Scenario 3: Both USB ==="
    clear_log
    # Primary on /dev/ttyACM0, additional serial port /dev/ttyACM1
    # Both HGIs marked as _preferred_type: usb
    docker exec $HASS_CONTAINER python3 -c "
import json
p = '${CONFIG_ENTRIES}'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] == 'ramses_cc':
        opts = e['options']
        opts['serial_port'] = {
            'port_name': '/dev/ttyACM0',
            'baudrate': 115200, 'dsrdtr': False, 'rtscts': False,
            'timeout': 3, 'xonxoff': False,
        }
        opts['mqtt_use_ha'] = True
        opts['additional_ports'] = ['/dev/ttyACM1']
        schema = opts.get('schema', {})
        for hgi in ['${HGI_A}', '${HGI_B}']:
            if hgi in schema:
                schema[hgi]['_preferred_type'] = 'usb'
                schema[hgi]['_comment'] = 'Supports: usb, mqtt'
        opts['schema'] = schema
json.dump(d, open(p, 'w'), indent=2)
print('  Config: primary=/dev/ttyACM0, additional=/dev/ttyACM1, both USB')
"
    restart_hass
    wait_for_startup
    check_logs "Scenario 3 (both USB)"
}

# ---------------------------------------------------------------------------
# Scenario 4: Both MQTT (no USB primary)
# ---------------------------------------------------------------------------
test_scenario_4() {
    echo "=== Scenario 4: Both MQTT ==="
    clear_log
    docker exec $HASS_CONTAINER python3 -c "
import json
p = '${CONFIG_ENTRIES}'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] == 'ramses_cc':
        opts = e['options']
        opts['serial_port'] = {'port_name': 'mqtt_ha'}
        opts['mqtt_use_ha'] = True
        opts['additional_ports'] = []
        schema = opts.get('schema', {})
        for hgi in ['${HGI_A}', '${HGI_B}']:
            if hgi in schema:
                schema[hgi].pop('_preferred_type', None)
                schema[hgi]['_comment'] = 'Supports: mqtt'
        opts['schema'] = schema
json.dump(d, open(p, 'w'), indent=2)
print('  Config: primary=mqtt_ha, no additional ports, both MQTT')
"
    restart_hass
    wait_for_startup
    check_logs "Scenario 4 (both MQTT)"
}

# ---------------------------------------------------------------------------
# Scenario 5: Clean start (no ESPs, no serial, no MQTT HGIs)
# ---------------------------------------------------------------------------
test_scenario_5() {
    echo "=== Scenario 5: Clean start (no ESPs) ==="
    clear_log
    docker exec $HASS_CONTAINER python3 -c "
import json
p = '${CONFIG_ENTRIES}'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] == 'ramses_cc':
        opts = e['options']
        opts['serial_port'] = {}
        opts['mqtt_use_ha'] = True
        opts['additional_ports'] = []
        schema = opts.get('schema', {})
        for hgi in ['${HGI_A}', '${HGI_B}']:
            if hgi in schema:
                schema[hgi]['_removed_from_pool'] = True
                schema[hgi].pop('_preferred_type', None)
        opts['schema'] = schema
json.dump(d, open(p, 'w'), indent=2)
print('  Config: no serial port, no pool members')
"
    restart_hass
    wait_for_startup
    check_logs "Scenario 5 (clean start)"
}

# ---------------------------------------------------------------------------
# Scenario 6a: Disconnect USB while MQTT stays online
# ---------------------------------------------------------------------------
test_scenario_6a() {
    echo "=== Scenario 6a: Disconnect USB, MQTT stays online ==="
    echo "  (Starting from Scenario 2 state: 1 USB + 1 MQTT)"
    # First set up scenario 2 state
    clear_log
    docker exec $HASS_CONTAINER python3 -c "
import json
p = '${CONFIG_ENTRIES}'
d = json.load(open(p))
for e in d['data']['entries']:
    if e['domain'] == 'ramses_cc':
        opts = e['options']
        opts['serial_port'] = {
            'port_name': '/dev/ttyACM0',
            'baudrate': 115200, 'dsrdtr': False, 'rtscts': False,
            'timeout': 3, 'xonxoff': False,
        }
        opts['mqtt_use_ha'] = True
        opts['additional_ports'] = []
        schema = opts.get('schema', {})
        if '${HGI_A}' in schema:
            schema['${HGI_A}']['_preferred_type'] = 'usb'
            schema['${HGI_A}']['_comment'] = 'Supports: usb, mqtt'
        if '${HGI_B}' in schema:
            schema['${HGI_B}'].pop('_preferred_type', None)
            schema['${HGI_B}']['_comment'] = 'Supports: mqtt'
            schema['${HGI_B}'].pop('_removed_from_pool', None)
        opts['schema'] = schema
json.dump(d, open(p, 'w'), indent=2)
print('  Config: 1 USB + 1 MQTT')
"
    restart_hass
    wait_for_startup
    echo "  Baseline established. Now simulating USB disconnect..."
    # We can't physically disconnect, but we can check what happens
    # when the serial port disappears. For now, just log the state.
    check_logs "Scenario 6a baseline (1 USB + 1 MQTT)"
    echo "  (Physical disconnect test requires manual unplugging)"
}

# Run scenarios
if [ $# -eq 0 ]; then
    test_scenario_3
    test_scenario_4
    test_scenario_5
    test_scenario_6a
else
    case $1 in
        3) test_scenario_3 ;;
        4) test_scenario_4 ;;
        5) test_scenario_5 ;;
        6a) test_scenario_6a ;;
        *) echo "Unknown scenario: $1"; exit 1 ;;
    esac
fi

echo "=== All scenarios complete ==="
