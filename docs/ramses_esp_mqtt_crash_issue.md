# ramses_esp: MQTT TX topic crashes on non-JSON payload (LoadProhibited)

**Status:** Draft (not yet filed — pending review)
**Target:** https://github.com/IndaloTech/ramses_esp/issues
**Firmware:** ramses_esp v0.6.6c (also confirmed on 0.4.9 and 0.5.2)

## Summary

Publishing a non-JSON payload to the MQTT TX topic
(`RAMSES/GATEWAY/<hgi_id>/tx`) causes a `LoadProhibited` crash and reboot.
The TX topic expects JSON format `{"msg": "<frame>"}`, but raw text or
empty payloads are not rejected gracefully — they crash the JSON parser
and trigger an ESP32 software reset.

## Observed behavior

When a raw text string (not JSON) is published to the TX topic, the
firmware crashes immediately:

```
Guru Meditation Error: Core  0 panic'ed (LoadProhibited). Exception was unhandled.
Core  0 register dump:
PC      : 0x4200cf0e  PS      : 0x00060530  A0      : 0x8200cbfd  A1      : 0x3fcc37e0
A2      : 0x3fc9b260  A3      : 0x3fcc1f5b  A4      : 0x0000002f  A5      : 0x00000001
...
EXCVADDR: 0x00000010
ELF file SHA256: a3f47cd75
Rebooting...
rst:0xc (RTC_SW_CPU_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)
```

The device reboots and recovers (~1.9s boot cycle), but the crash is
unnecessary — malformed input should be rejected, not crash the device.

## Reproduction

### Setup

- ESP32-S3 USB JTAG/serial debug unit + CC1101 radio
- ramses_esp v0.6.6c
- WiFi connected, MQTT broker connected (mosquitto on 192.168.40.11:1883)
- USB serial connected (optional — crash happens with or without USB)

### Steps

1. Connect the ESP32 to WiFi and MQTT
2. Subscribe to the TX topic: `RAMSES/GATEWAY/<hgi_id>/tx`
3. Publish a raw text payload (not JSON):

```
mosquitto_pub -h 192.168.40.11 -t RAMSES/GATEWAY/18:130236/tx \
  -m 'I 18:130236 --:------ --:------ 0008 000'
```

### Expected

The firmware should reject the malformed payload with an error message
on the serial console and/or `cmd/result` topic, without crashing.

### Actual

The firmware crashes with `LoadProhibited` (`EXCVADDR: 0x00000010`) and
reboots.

### With valid JSON (no crash)

Publishing the same frame in JSON format works correctly:

```
mosquitto_pub -h 192.168.40.11 -t RAMSES/GATEWAY/18:130236/tx \
  -m '{"msg": "I 18:130236 --:------ --:------ 0008 000"}'
```

No crash, the frame is transmitted over RF.

## Impact

- **Normal ramses_cc/ramses_rf use:** No impact — ramses_rf always
  publishes JSON to the TX topic.
- **MQTT Explorer users:** The wiki recommends MQTT Explorer for testing.
  A user who publishes a raw frame string (a natural thing to try) will
  crash the device.
- **Custom integrations/scripts:** Any client that sends non-JSON to the
  TX topic will crash the device.
- **Reboot loop risk:** If a misconfigured client repeatedly publishes
  raw text, the device will enter a reboot loop.

## Suggested fix

Validate the MQTT TX payload before parsing:

1. Check that the payload is valid JSON before parsing.
2. If parsing fails, log an error (e.g. `# ERROR: invalid JSON on TX
   topic`) and publish an error result to `cmd/result`.
3. Do not attempt to access JSON fields from a null/failed parse result.
4. Consider also validating that the `msg` field exists and is a
   non-empty string.

## Environment

- Hardware: ESP32-S3 USB JTAG/serial debug unit + CC1101
- Firmware: ramses_esp v0.6.6c (also confirmed on 0.4.9, 0.5.2)
- WiFi: WPA2
- MQTT broker: mosquitto on 192.168.40.11:1883
- Topic prefix: `RAMSES/GATEWAY`
- MQTT TX topic: `RAMSES/GATEWAY/<hgi_id>/tx`

## Related

- ramses_esp issue 30: "MQTT misconfigured broker causes reboot loop"
  (fixed in v0.6.1) — a different MQTT crash path, also caused by
  unhandled error conditions.
- The `RTC_SW_CPU_RST` crash on MQTT disconnect (also observed on
  0.4.9/0.5.2) is fixed in v0.6.6c. This `LoadProhibited` crash is a
  separate issue that remains in v0.6.6c.

## Test evidence

- Test tool: `tools/hybrid_usb_mqtt_test.py`
- Full report: `docs/serial_hw_gate_report.md`
- Crash captured with USB serial monitor during MQTT TX test
