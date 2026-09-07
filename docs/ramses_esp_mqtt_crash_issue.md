# ramses_esp: MQTT disconnect causes RTC_SW_CPU_RST crash

**Status:** RESOLVED — fixed in ramses_esp v0.6.6c (likely v0.6.1, issue 30).
No need to file — the firmware update resolves the crash. Kept as reference.

## Summary

ramses_esp crashes with `RTC_SW_CPU_RST` (software reset) when the MQTT
connection disconnects, instead of handling the disconnect gracefully.
This happens on both ramses_esp 0.4.9 and 0.5.2.

## Observed behavior

Every crash follows the same pattern — `# MQTT: Disonnected` immediately
followed by the ESP-ROM boot banner and `rst:0xc (RTC_SW_CPU_RST)`:

```
# MQTT: Disonnected
ESP-ROM:esp32s3-20210327
Build:Mar 27 2021
rst:0xc (RTC_SW_CPU_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)
Saved PC:0x40375ba4
SPIWP:0xee
mode:DIO, clock div:1
load:0x3fce3810,len:0x48c
...
entry 0x403c9858
# ramses_esp 0.5.2
# Attempting to connect to SSID:WilMa
# Connected to SSID:WilMa
# MQTT: Connecting to mqtt://192.168.40.11:1883
# MQTT: Connected
```

The ESP32 auto-reboots and recovers (~1.9s boot cycle), but the crash
itself is unwanted and disrupts operation.

## Reproduction

### Setup

- Two ESP32-S3 USB JTAG/serial debug units (CC1101 radio)
- ramses_esp 0.4.9 and 0.5.2
- Both connected to the same WiFi network and MQTT broker
- Both connected via USB to the same host

### Steps

1. Plug in both ESP32s via USB
2. Wait for both to connect to WiFi and MQTT
3. Open one ESP32's USB serial port with pyserial (which sets DTR=True/RTS=True)
4. Observe the boot output

### Expected

The opened ESP32 reboots (DTR/RTS hardware reset, `rst:0x15
USB_UART_CHIP_RESET`), disconnects from MQTT, and reconnects after boot.
The other ESP32 continues operating normally.

### Actual

The opened ESP32 reboots (DTR/RTS hardware reset), disconnects from MQTT.
Then **both ESP32s** crash with `rst:0xc (RTC_SW_CPU_RST)`:

- The opened ESP32 crashes when its MQTT connection drops during reboot
- The other ESP32 also crashes (possibly from receiving the LWT "offline"
  message, or from a broker-side event)

The crash also happens with sequential port opening (5s apart) — opening
Port 1 causes Port 2 to crash, and vice versa.

### Additional trigger: MQTT TX + USB serial

Publishing a TX command to an ESP32's MQTT `/tx` topic while it is also
connected via USB serial causes a `LoadProhibited` crash:

```
Guru Meditation Error: Core 0 panic'ed (LoadProhibited). Exception was unhandled.
EXCVADDR: 0x00000010
ELF file SHA256: dd89ee365
Rebooting...
rst:0xc (RTC_SW_CPU_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)
```

This is a separate crash path but the same underlying issue: the firmware
does not handle MQTT events gracefully when USB serial is active.

## Impact

- **Single ESP32 on USB:** The ESP32 crashes every time the USB serial port
  is opened (because the DTR/RTS reset disconnects MQTT). It recovers after
  ~1.9s, but the crash is unnecessary.
- **Two ESP32s on USB:** Both crash when either port is opened. This makes
  multi-dongle USB operation unreliable without crash recovery logic in the
  host software.
- **Hybrid USB + MQTT:** The USB-connected ESP32 crashes if it receives an
  MQTT TX command while USB is active.

## Environment

- Hardware: ESP32-S3 USB JTAG/serial debug unit + CC1101
- Firmware: ramses_esp 0.4.9 and 0.5.2
- WiFi: WPA2 (SSID WilMa)
- MQTT broker: mosquitto on 192.168.40.11:1883
- Host: Linux, pyserial 3.5
- Topic prefix: `RAMSES/GATEWAY`

## Suggested fix

The firmware should handle MQTT disconnects without crashing:

1. On MQTT disconnect, log the event and attempt reconnection — do not
   trigger a software reset.
2. On MQTT TX while USB is active, either queue the command, ignore it,
   or return an error — do not crash with `LoadProhibited`.
3. Consider ignoring MQTT TX when USB serial is connected (the USB host
   is the active controller in that scenario).

## Workaround (host-side)

The host software (ramses_rf pool) can work around this by:

1. Detecting the crash via the boot banner (`rst:0xc` or `ESP-ROM`)
2. Re-applying a grace period (~3s) after any crash
3. Treating the child as offline during crash recovery
4. Not sending commands during the recovery window

This is the same mechanism used for unplug/reconnect recovery.

## Test evidence

- Test tools: `tools/serial_hw_gate.py`, `tools/two_usb_test.py`,
  `tools/hybrid_usb_mqtt_test.py`
- Full report: `docs/serial_hw_gate_report.md`
- Test logs: `logs/serial_hw_gate_20260906_*.log`
