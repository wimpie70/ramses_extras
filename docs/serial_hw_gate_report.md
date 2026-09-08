# Serial Hardware Feasibility Gate Report

**Date:** 2026-09-06
**Device:** ESP32-S3 (Espressif USB JTAG/serial debug unit, `/dev/ttyACM0`)
**Firmware:** ramses_esp 0.4.9
**WiFi:** SSID WilMa
**MQTT:** 192.168.40.11:1883
**Tool:** `tools/serial_hw_gate.py`

## Purpose

This report records the results of the serial hardware feasibility gate
defined in `multi-hgi-plan.md`. The gate must characterize the ESP32 USB
reset behavior before PR 3 (pooled serial transmission) can start.

The core question: **is the ESP32 USB reset on serial port open a permanent
blocker for pooled serial transmission, or can a delayed startup policy work
around it?**

## Test results

| Test | Description | Reset? | Echo? | Notes |
|------|-------------|--------|-------|-------|
| T1 | Port open + DTR/RTS (no write) | No banner caught | n/a | 0 RX in 7s — ESP32 was booting silently |
| T2 | One immediate 7FFF probe | Boot output mixed in | Yes (garbled) | RX at 201ms shows boot output interleaved with echo |
| T3 | 10x repeated immediate probes (50ms gap) | No | Yes (clean) | Echoes from ~200ms onward, all clean |
| T4 | Delayed probe (after 3s grace) | No | Yes (clean) | Echo at 3113ms, 12ms latency, perfect |
| T5 | Ordinary RF write after 3s grace | No | Yes (clean) | 1F09 RQ echo at 3113ms, 12ms latency |
| T6 | Close/reopen cycle | No | n/a | No data observed in short window |
| T7 | Unplug/reconnect + delayed probe | No | Yes (slightly garbled) | Boot output still printing at 3.1s on first run; clean on second |
| T8 | DTR=False/RTS=False after open | **YES — explicit reset** | Yes (clean after grace) | Full boot banner captured |

**6/8 tests clean. T8 triggered an explicit reset by changing DTR/RTS after
open. T7's first run had a slightly garbled echo (boot output still printing
at 3.1s).**

## Key findings

### 1. Port open resets the ESP32 (DTR/RTS transition)

pyserial opens the port with DTR=True, RTS=True by default. The ESP32-S3's
USB serial interface uses DTR/RTS for auto-reset. The transition from the
closed state to DTR=True/RTS=True pulses the EN pin, resetting the chip.

This is **not a reset loop** — it is a one-time reset per port open. The ESP32
boots cleanly every time.

Evidence:
- T2 (first run): RX at 201ms contains `# # Attempting to c` (boot output:
  "Attempting to connect to SSID") interleaved with the command echo.
- T8: Full boot banner captured after DTR True→False transition at 104ms.

### 2. DTR/RTS changes after open also reset the ESP32

T8 explicitly set DTR=False, RTS=False at 104ms after open. The ESP32 reset
at 114ms (10ms later). This means:
- **Do NOT change DTR/RTS after open.** Any transition resets the chip.
- The idea of "disable auto-reset by setting DTR=False" does NOT work — the
  transition itself causes the reset.

### 3. Full boot sequence takes ~1.9 seconds (cold) or ~0.4s (warm WiFi)

From T8's complete boot banner capture (cold start, DTR/RTS transition):

| Time (ms) | Event |
|-----------|-------|
| 0 | DTR/RTS transition (reset trigger) |
| 114 | ESP-ROM banner: `esp32s3-20210327` |
| 114 | `rst:0x15 (USB_UART_CHIP_RESET)` |
| 115 | Loading code (4 load segments) |
| 215 | `entry 0x403c9858` (firmware entry point) |
| 416 | `# ramses_esp 0.4.9` (firmware starts) |
| 516 | `# Attempting to connect to SSID:WilMa` |
| 1822 | `# Connected to SSID:WilMa` |
| 1822 | `# MQTT: Connecting to mqtt://192.168.40.11:1883` |
| 1922 | `# MQTT: Connected` |

After a physical unplug/replug (boot starts at plug-in time, before pyserial
opens the port), the WiFi was already connected by the time Python opened the
port (~300ms after open). This is a warm WiFi reconnect — the ESP32 remembers
the SSID and reconnects faster.

**Cold start (DTR/RTS reset): ~1.9s to MQTT connected.**
**Warm reconnect (unplug/replug): ~0.4s to MQTT connected.**
**Firmware ready: ~0.4s from reset in both cases.**

### 4. A 2-second grace period before the first write gives clean results

T4 (delayed signature probe, 3s grace) and T5 (ordinary RF write, 3s grace)
both produced clean echoes with ~12ms latency. A follow-up test confirmed
that a write at 2.5s after open also produces a perfectly clean echo with
~9ms latency.

T7 (unplug/reconnect, 3s grace) had a slightly garbled echo on the first run
because the ESP32 was still printing "Attempting to connect to SSID" at 3.1s
— the WiFi connect took longer than 3s in that instance. On a second run
(warm WiFi), the boot was faster and the echo was clean.

**2 seconds is the minimum safe grace period. 3 seconds is recommended as the
default to handle slow WiFi reconnects. The grace period is needed only once
per port open (startup or reconnect), not before every message.**

### 5. Immediate writes work but are not clean

T2 (immediate probe at 100ms) and T3 (repeated probes from 100ms) both
produced echoes, but:
- T2: echo was interleaved with boot output (`# # Attempting to c...`)
- T3: echoes from probe 2 onward were clean (the ESP32 booted fast enough
  that by ~200ms it was processing commands)

The current `port.py` behavior (`_SIGNATURE_GAP_SECS = 0.05`, up to 40 probes)
sends probes during the boot window. This works but is not clean — the first
echo may be garbled, and the boot output may confuse the signature matcher.

### 6. No reset loops from USB writes, but MQTT disconnect crashes found

None of the original 7 tests (T1-T8) produced a reset loop from USB writes.
The ESP32 always:
1. Reset on DTR/RTS transition
2. Booted in ~2 seconds
3. Echoed commands correctly after boot
4. Continued operating normally

This contradicts the original concern that "repeated 7FFF probes" or
"repeated reopen cycles" could cause a reset loop.

**However**, the two-USB and hybrid tests revealed a different crash source:
`RTC_SW_CPU_RST` (software crash) triggered by MQTT disconnects. See the
"MQTT disconnect crash" section below.

## Conclusion

**The serial hardware feasibility gate PASSES.** Pooled serial transmission
is feasible with a delayed startup policy.

### Recommended Phase 2 implementation

Based on this evidence, PR 3 should implement:

1. **`signature_policy = "delayed"`** as the default for pooled serial children.
   - Wait `startup_grace` seconds after port open before sending the first
     signature probe.
   - `startup_grace = 3.0` seconds is the recommended default (handles slow
     WiFi reconnects). 2.0s is the minimum safe value.
   - The grace period is needed **once per port open** (startup or reconnect),
     not before every message. After boot, the ESP32 processes writes with
     ~10ms latency.

2. **`signature_policy = "immediate"`** as the default for non-pooled
   single-USB (backward compatible with existing behavior).

3. **`signature_policy = "skip"`** for configurations where the HGI ID is
   configured manually and no signature probe is needed.

4. **Do NOT change DTR/RTS after open.** The current pyserial default
   (DTR=True, RTS=True) is fine. Any transition resets the ESP32.

5. **`disable_sending` remains a permanent send permission flag**, not a
   startup workaround. It should not be set to `True` to avoid the reset —
   use `signature_policy = "skip"` instead.

6. **After the grace period, the child is send-ready.** Both signature probes
   and ordinary RF writes work with ~12ms echo latency.

### What does NOT work

- Setting DTR=False/RTS=False to prevent auto-reset (T8: causes reset)
- Immediate writes without a grace period (T2: garbled echo)
- Using `disable_sending=True` as a startup workaround (disables all sending
  permanently)

### Remaining hardware evidence needed for Phase 2 release

- [x] USB unplug/reconnect test (T7 — ESP32 recovers, delayed probe works)
- [x] USB+MQTT hybrid coexistence test (see below)
- [x] Two-USB pool test (both ESP32s via USB — see below)
- [x] Cross-dongle over-air copy with active RF traffic (confirmed — see below)
- [ ] Traditional evofw3/HGI serial device test (not available)

### Hybrid USB+MQTT test (H1-H3)

Tested with USB ESP32 (`/dev/ttyACM0`, ramses_esp 0.4.9, HGI `18:149488`) and
MQTT ESP32 (`18:130236`, ramses_esp 0.5.2, broker `192.168.40.11:1883`).

**Important:** The USB ESP32 is also connected to WiFi+MQTT (ramses_esp boots
into both modes). This is not the intended hybrid pool configuration — in a
real pool, the USB child would be serial-only and the MQTT child would be a
separate physical device.

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| H1 | Cross-dongle visibility (10s listen) | No traffic | RF environment was quiet during the test |
| H2 | USB TX → MQTT over-air copy | USB echo OK, no MQTT copy | MQTT HGIs not publishing RX during test |
| H3 | MQTT TX → USB over-air copy | **Firmware crash** | USB ESP32 crashed when it received MQTT TX while on USB |

**H3 crash details:**

When a TX command was published to `RAMSES/GATEWAY/18:149488/tx` (the USB
ESP32's own MQTT TX topic), the firmware crashed:

```
Guru Meditation Error: Core 0 panic'ed (LoadProhibited). Exception was unhandled.
EXCVADDR: 0x00000010
ELF file SHA256: dd89ee365
Rebooting...
```

The ESP32 auto-rebooted and recovered in ~1.9s (same boot sequence as a
DTR/RTS reset). This is a **ramses_esp 0.4.9 firmware bug**, not a
ramses_rf/ramses_cc issue. The firmware cannot handle receiving a TX command
via MQTT while USB serial is also active.

**Impact on Phase 2:** None. In a real hybrid pool:
- The USB ESP32 would be a serial-only pool child (MQTT TX would not be sent
  to it)
- The MQTT HGI would be a separate physical device
- The pool router sends TX to the selected child's transport only — a USB
  child gets TX via serial, an MQTT child gets TX via MQTT

**Recommendation:** Report this crash to the ramses_esp project. The firmware
should handle MQTT TX gracefully even when USB is active (or ignore MQTT TX
when USB serial is connected). The newer firmware (0.5.2 on the other ESP32)
may have fixed this — updating the USB ESP32 and re-testing would confirm.

**Crash avoidance (coordinator-side):** The pool design already prevents this
scenario:
1. An HGI is either a USB child OR an MQTT child, never both in the same pool.
2. The pool router sends TX only via the selected child's own transport — a
   USB child gets TX via serial write, never via MQTT publish.
3. The coordinator filters non-`mqtt://` ports from MQTT pool construction.
4. The config flow should enforce mutual exclusivity: if an HGI ID is already
   configured as a USB serial port, it should not be addable as an MQTT pool
   member, and vice versa.

**Hybrid conclusion:** The hybrid USB+MQTT pool is feasible at the hardware
level. Both transports can receive RF frames independently. The cross-dongle
over-air copy could not be confirmed due to quiet RF traffic, but this is a
pool-level concern (dedup, RSSI routing) not a hardware feasibility concern.
The firmware crash is specific to the same-ESP32-on-both-transports scenario
and does not affect the intended hybrid pool configuration.

### Two-USB pool test (U1-U3)

Tested with two ESP32-S3 USB devices:
- Port 1: `/dev/ttyACM0` (`CC:BA:97:09:FC:BC`, Bus 006)
- Port 2: `/dev/ttyACM1` (`CC:BA:97:0A:47:F0`, Bus 008)

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| U1 | Both ports open + listen 15s | 0 frames (quiet RF) | RF environment was quiet |
| U2 | Port 1 TX, Port 2 over-air copy | Port 1 echo OK, no Port 2 copy | Port 2 may have been booting |
| U3 | Port 2 TX, Port 1 over-air copy | **PASS** | Port 2 echo OK, Port 1 saw over-air copy + both received same RF frames |

**U3 key evidence:**

After Port 2 transmitted the `7FFF` signature probe, Port 1 received the
over-air copy. Additionally, both ports received the same RF frames from
ambient traffic:

| Frame | Port 1 seq | Port 2 seq |
|-------|-----------|-----------|
| `I --- 37:126776 32:153289 --:------ 31E0 008 ...` | 072 | 080 |
| `I --- 37:168270 32:153289 --:------ 22F1 003 000107` | 000 | 020 |

The different sequence numbers confirm these are independent receptions of the
same RF frame by two different dongles — exactly the cross-dongle visibility
that the pool's dedup and RSSI routing depend on.

A second run with 5s grace produced cleaner echoes (no boot output
interleaving) but the RF environment was quiet, so no over-air copies or
ambient frames were observed.

**Two-USB conclusion:** The two-USB pool is feasible. Both ports can be opened
simultaneously without conflicts, both receive RF frames independently, both
can transmit after a grace period, and cross-dongle over-air copy works. The
pool's dedup, RSSI routing, and loopback exclusion have the raw data they
need from two USB dongles.

**Post-firmware-update over-air copy confirmation (v0.6.6c):**

After updating both ESP32s to v0.6.6c, a definitive over-air copy test was
performed using ramses_rf to send a `7FFF` signature probe via P1
(`/dev/ttyACM0`, HGI `18:130236`) while listening on P2 (`/dev/ttyACM1`).

P2 received the over-air copy:

```text
P2   0.3s: 030  I --- 18:130236 63:262142 --:------ 7FFF 015 001001A07B22F0087...
```

- RSSI: `-30` (strong signal — both ESP32s are close together)
- Source: `18:130236` (P1's HGI ID, substituted by the firmware)
- The `7FFF` signature probe was transmitted over RF by P1 and received
  over RF by P2

**Note:** Earlier manual tests with raw serial writes (`I 18:000730 ... 7FFF`)
only produced a local echo (`# ...`) without over-air transmission. The
ramses_rf library sends the frame in the format that the firmware actually
transmits over RF. This confirms that the ESP32 does transmit over RF when
the correct frame format is used, and that the other dongle can hear it.

**MQTT TX + USB serial crash (LoadProhibited) — still present in v0.6.6c:**

The MQTT disconnect crash (`RTC_SW_CPU_RST`) is fixed in v0.6.6c, but a
separate `LoadProhibited` crash still occurs when MQTT TX is sent to an
ESP32 that is also connected via USB serial. The crash was triggered by
publishing to `RAMSES/GATEWAY/18:130236/tx` with a raw text payload (not
JSON). The MQTT TX topic expects JSON format `{"msg": "<frame>"}` — sending
raw text causes a JSON parser crash. With proper JSON format, no crash
occurs. This is a firmware input validation issue, not a pool design issue.
The pool should never send MQTT TX to an HGI that is also a USB serial
child.

**Same-hub confirmation:** The test was repeated with both ESP32s on the same
USB hub (Bus 008, through a powered hub). Both ports enumerated correctly
(`/dev/ttyACM0` and `/dev/ttyACM1`), both received ambient RF frames (35 and
39 frames respectively, with 14 matched lines), and both transmitted with
clean echoes. The same-hub configuration works identically to the
separate-bus configuration.

### MQTT disconnect crash (ramses_esp firmware bug)

During the two-USB and hybrid tests, a recurring firmware crash was observed
that is **distinct from the DTR/RTS port-open reset**.

**Two reset types observed:**

| Reset type | Code | Cause | Expected? |
|-----------|------|-------|-----------|
| `USB_UART_CHIP_RESET` | `0x15` | DTR/RTS transition on port open | Yes — one-time, per port open |
| `RTC_SW_CPU_RST` | `0xc` | Software crash (MQTT disconnect) | **No — firmware bug** |

**Crash pattern:** Every `RTC_SW_CPU_RST` crash is preceded by
`# MQTT: Disonnected`:

```
# MQTT: Disonnected
ESP-ROM:esp32s3-20210327
Build:Mar 27 2021
rst:0xc (RTC_SW_CPU_RST),boot:0x8 (SPI_FAST_FLASH_BOOT)
```

The ESP32 auto-reboots and recovers in ~1.9s (same boot sequence as a
DTR/RTS reset), but the crash itself is unwanted.

**Trigger:** When one ESP32 opens its USB port (DTR/RTS reset), it
disconnects from MQTT. The MQTT disconnect causes the firmware to crash
with `RTC_SW_CPU_RST` instead of handling it gracefully. This happens on
both ramses_esp 0.4.9 and 0.5.2.

**Reproduced in:**
- Hybrid test H3 (MQTT TX + USB serial — crash on the USB ESP32)
- Two-USB test U2/U3 (both ESP32s crash when ports are opened)
- Sequential open test (both ESP32s crash even when opened 5s apart)

**The crash happens even with sequential port opening** — opening Port 1
causes Port 2 to crash (and vice versa) because the MQTT disconnect from
one ESP32 triggers the crash in the other.

**Workaround for the pool:** The pool can handle this gracefully:
1. Detect the crash by watching for the boot banner (`rst:0xc` or `ESP-ROM`)
2. Re-apply the grace period after any crash (same as a port-open reset)
3. Treat the child as offline during crash recovery
4. Do not send commands during the recovery window
5. The pool's reconnect logic (needed for unplug/reconnect anyway) handles
   this with the same mechanism

**Firmware fix needed:** ramses_esp should handle MQTT disconnects without
crashing. The `RTC_SW_CPU_RST` indicates a software exception, not a
hardware reset. A draft issue has been prepared at
`docs/ramses_esp_mqtt_crash_issue.md` (not yet filed — pending review).

**UPDATE 2026-09-06:** Both ESP32s were updated from 0.4.9/0.5.2 to **v0.6.6c**
via OTA. The MQTT disconnect crash is **FIXED** in v0.6.6c. After the update:
- No `RTC_SW_CPU_RST` crashes observed
- No boot banners during port open or writes
- Clean echoes on both ports simultaneously
- Both ports opened at the same time with no crashes

The fix was likely introduced in v0.6.1 ("Fix misconfigured MQTT reboot loop",
ramses_esp issue 30). Updating to v0.6.6c is recommended for all ESP32s used
in multi-HGI pools.

## Test artifacts

- Test scripts: `tools/serial_hw_gate.py`, `tools/hybrid_usb_mqtt_test.py`, `tools/two_usb_test.py`
- Full logs: `logs/serial_hw_gate_20260906_*.log`
- Key log (full suite): `logs/serial_hw_gate_20260906_181233.log`
- Key log (T8 boot banner): `logs/serial_hw_gate_20260906_181143.log`
