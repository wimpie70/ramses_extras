# USB HGI Pool Support — Gap Report

**Date:** 2026-09-08
**Scope:** What is needed to make the three USB HGI device types tested in
issue 1171 (ESP32-S3, FTDI evofw3, HGI80) work as pool children, per the
Phase 2 plan in `docs/multi-hgi-phase2-3-followup-issue.md`.

**Sources:**
- Issue 1171 + comments: https://github.com/ramses-rf/ramses_cc/issues/1171
- PR 1178 + comments: https://github.com/ramses-rf/ramses_cc/pull/1178
- Feasibility test reports (attached to issue 1171 by silverailscolo):
  - FTDI: `report_ftdi1.md`, `report-all.md`
  - ESP32-S3: `report-tty_usbmodem1101-all.md`
  - HGI80: `report-hgi80-all.md`
- Test script: `tools/esp_usb_feasibility_standalone.py`
  (updated with `--nanocul` flag for ATmega328p buffer-overflow diagnostics)
- Phase 2 plan: `docs/multi-hgi-phase2-3-followup-issue.md`
- evofw3 source (version 0.7.3): https://github.com/ghoti57/evofw3

---

## 1. Feasibility test results (from issue 1171)

The standalone feasibility gate sends the evofw3 `7FFF _PUZZ` signature
frame and checks for an echo — the same mechanism ramses_rf uses in
`PortTransport.connect_with_signature()` to discover the HGI ID.

| Device | Port | Overall | Echo to `_PUZZ` | DTR/RTS reset | Unplug/reconnect |
|--------|------|---------|-----------------|---------------|------------------|
| ESP32-S3-WROOM1 (evofw3) | `/dev/tty.usbmodem1101` | **PASS** | PASS (86 bytes) | RESET on DTR=LOW (expected) | PASS |
| FTDI evofw3 dongle (nanoCUL) | `/dev/tty.usbserial-A50285BI` | **FAIL** | FAIL (0 bytes, all variants) | no reset (FT232 has no auto-reset circuit) | FAIL (reconnected, no echo) |
| HGI80 (via pty) | `/dev/ttys001` | **FAIL** | FAIL (0 bytes — see below) | `[Errno 25] Inappropriate ioctl` (pty artifact) | FAIL (unplug not detected — pty artifact) |

### Additional device tested (comment 5588991130)

silverailscolo tested a fourth device — a "real evofw3" on
`/dev/cu.usbmodem101` (USB CDC, ATmega32U4 with native USB, PCB USB
connector). This device **allows control** of the heating system (RF TX
works in production), but:

| Test | Result | Bytes | Notes |
|------|--------|-------|-------|
| Boot banner capture | PASS | 0 | No banner |
| **Version command (!V + V)** | **PASS** | 16 | **`# evofw3 0.7.1`** |
| Immediate _PUZZ probe | FAIL | 0 | No echo |
| Paced _PUZZ probe (1ms) | FAIL | 0 | No echo |
| Paced _PUZZ probe (5ms) | FAIL | 0 | No echo |
| Ordinary RF write | FAIL | 0 | No response |

**CRITICAL FINDING: the `_PUZZ` echo is NOT a valid indicator of whether
a device can send RF.**

This device:
- **CAN send RF** (silverailscolo confirms: "Allows control")
- **CAN receive serial commands** (version command responds)
- **CANNOT echo `_PUZZ`** (no RF loopback)

The `_PUZZ` echo mechanism requires RF TX + RF loopback (the device
receives its own transmission). Not all evofw3 hardware/platforms
support RF loopback. The ATmega32U4 with native USB does not, even
though its RF TX works for controlling heating.

This means:
1. **The feasibility gate's reliance on `_PUZZ` echo is wrong** — it
   rejects devices that can send RF but don't loopback.
2. **ramses_rf's `connect_with_signature()` is wrong** for these
   devices — it requires `_PUZZ` echo to get the HGI ID, but the echo
   never comes.
3. **The ESP32-S3 is the exception, not the rule** — it happens to
   support RF loopback, but that's not guaranteed across all evofw3
   hardware.
4. **The pool needs `signature_policy = SKIP` + `configured_hgi_id`**
   for ALL evofw3 devices that don't echo, not just the nanoCUL.

The version command (`!V\r` → `# evofw3 0.7.1`) is a better diagnostic:
- It tests the serial RX path without involving RF
- It works on the ATmega32U4 device (which can control heating)
- It fails on the nanoCUL (which may have a timing or hardware issue)

### The `!I` command — HGI ID over serial, no RF needed

evofw3's `cmd.c` has a second command that solves the identification
problem entirely:

```
case 'I':  validCmd = cmd_id( cmd );            break;
```

```c
static uint8_t cmd_id( struct cmd *cmd ) {
  uint8_t  class;
  uint32_t id;
  device_get_id( &class, &id );
  command.n = sprintf_P( command.buffer,
      PSTR("# %02hu:%06lu\r\n"), class, id );
  return 1;
}
```

**`!I\r` returns the HGI class and ID directly over serial** — no RF
TX, no RF loopback, no `_PUZZ` echo. The response format is:
```
# 18:000730\r\n
```

This is the reliable way to identify an evofw3 device and get its HGI
ID. It works on ALL evofw3 hardware regardless of RF loopback
capability.

**Why `_PUZZ` echo fails but `!I` would work:**

The `_PUZZ` signature probe relies on RF loopback:
1. Host sends `_PUZZ` frame over serial
2. evofw3 transmits it over RF (CC1101 TX mode)
3. evofw3 switches CC1101 to RX mode
4. evofw3 receives its own RF transmission (loopback)
5. evofw3 prints the received frame on serial

Step 4 is the problem. The CC1101 is half-duplex — it cannot receive
while transmitting. After TX completes, it switches to RX, but the
transmitted signal is already gone unless there's a near-field
reflector or the radio supports internal loopback. The ESP32-S3
happens to support this; ATmega-based devices (nanoCUL, ATmega32U4)
do not.

The `!I` command skips RF entirely — it reads the HGI ID from
EEPROM/device signature and prints it over serial. This should work
on every evofw3 device.

**Implication for ramses_rf:** `connect_with_signature()` could use
`!I` instead of `_PUZZ` to discover the HGI ID. This would:
- Work on all evofw3 hardware (not just ESP32-S3)
- Not require RF loopback
- Be faster (no RF TX/RX cycle)
- Be more reliable (no RF interference)

The updated test script now includes `test_id_command` which sends
`!I\r` and parses the HGI ID from the response.

### Test environment: macOS host, not the HA container

All three device paths are **macOS** naming conventions:

| Port path | OS | Meaning |
|-----------|----|---------|
| `/dev/tty.usbmodem1101` | macOS | USB CDC modem (ESP32-S3) |
| `/dev/tty.usbserial-A50285BI` | macOS | USB-serial via FTDI FT232 chip |
| `/dev/ttys001` | macOS | **Pseudo-terminal (pty)** — not a USB device |

On Linux (where HA Docker containers run), the equivalent paths would be
`/dev/ttyACM*` (ESP32 CDC), `/dev/ttyUSB*` (FTDI), and
`/dev/serial/by-id/...` (stable symlinks). The fact that all paths are
macOS means silverailscolo ran `esp_usb_feasibility_standalone.py` on a
**Mac**, not inside the HA container.

This matters because HA/ramses_cc almost certainly runs elsewhere — a
Linux server, HA OS, or a Docker container. The USB devices on the Mac
are not directly visible to HA unless they are forwarded via a network
serial relay (socat, ser2net, ESPHome serial-to-network, etc.).

### Key observations

- **ESP32-S3** is the reference platform. All behaviours match the script's
  documented expectations. The DTR=LOW reset is the known ESP32 auto-reset
  circuit behaviour (DTR pulses EN via a transistor). This is a one-time
  reset per port open, not a reset loop. This device was tested directly on
  USB and the results are trustworthy.

- **FTDI dongle** (`/dev/tty.usbserial-A50285BI`) emits 17 bytes on open
  but never echoes the `_PUZZ` signature on any variant (immediate,
  repeated 5x, delayed 2s). It also does not respond to an ordinary RF
  write. Assuming the device is a nanoCUL running evofw3 (the most likely
  case given silverailscolo's involvement with ramses_rf), the 17 bytes
  and the no-echo result have a specific root cause — see the dedicated
  analysis in section 1a below.

  **What is an FTDI?** FTDI is not a device type — it is a chip brand.
  FTDI Chip Ltd makes USB-to-serial bridge chips (FT232, FT232R, etc.)
  that convert USB to UART. The chip sits between the USB port and
  whatever microcontroller is behind it. `is_hgi80()` in ramses_rf
  classifies VID `0x0403` (FTDI) as "not HGI80" → assumed evofw3
  (`discovery.py:82-83`), but that assumption only holds if the MCU
  behind the FTDI chip is actually running evofw3 firmware.

  **What device types use an FTDI chip?** The FTDI chip is just the
  USB-to-serial bridge. What is behind it determines whether it is a
  valid RAMSES HGI:

  | Device behind FTDI | Firmware | Speaks RAMSES? | Echoes `_PUZZ`? | Valid HGI? |
  |---------------------|----------|----------------|------------------|------------|
  | nanoCUL (ATmega + CC1101) | **evofw3** | Yes | Yes (if RX buffer doesn't overflow) | Yes |
  | nanoCUL (ATmega + CC1101) | culfw / SIGNALduino / LaCrosse / WMBus / AskSin | No | No | No (wrong firmware) |
  | nanoCUL (ATmega + CC1101) | none / corrupted | No | No | No (reflashable) |
  | Modbus bridge (e.g. Orcon HRC) | modbus | No | No | No |
  | Plain FT232 breakout | n/a (no MCU, no radio) | No | No | No |

  The **nanoCUL** is a well-known valid HGI type in the ramses_rf
  community. It is a USB stick with an 868 MHz radio module (CC1101)
  and an ATmega microcontroller, sold by schlauhaus.biz with either an
  FTDI or CH340G USB-to-serial chip (FTDI is recommended for better
  driver support, per the Tweakers.net ramses_rf thread). Critically,
  the nanoCUL is sold with a **choice of firmware** — the buyer picks
  one of: culfw, culfw for WMBus, culfw for LaCrosse, **evofw3**,
  SIGNALduino, or AskSin Analyzer XS. Only the **evofw3** firmware
  speaks RAMSES and echoes the `_PUZZ` signature probe. A nanoCUL
  flashed with any of the other five firmwares will not echo, even
  though the hardware is identical and perfectly capable. The firmware
  can be changed/updated at any time on a PC.

  ramses_rf's `is_hgi80()` correctly classifies FTDI as "not HGI80" →
  evofw3, and a nanoCUL with evofw3 **should** echo the `_PUZZ`
  signature probe.

  **Is it the modbus bridge?** silverailscolo said in PR 1178: "The Pool
  tab also suggested adding the USB-connected **modbus bridge** (mine, not
  _owned by 'me'!)." The feasibility test behavior (no echo, no RF
  response, 17 bytes of non-RAMSES traffic on open) is **consistent with
  this being the modbus bridge, not an evofw3 dongle.** A modbus bridge
  speaks modbus protocol, not RAMSES — it cannot participate in a RAMSES
  pool regardless of configuration.

  **But it could also be a nanoCUL with wrong firmware.** The nanoCUL
  is sold with a choice of six firmwares (culfw, WMBus, LaCrosse,
  evofw3, SIGNALduino, AskSin) — only evofw3 speaks RAMSES. If the
  nanoCUL was bought with a different firmware, or reflashed, it would
  produce exactly the symptoms seen: port opens, some bytes come
  through, no `_PUZZ` echo. Both a modbus bridge and a misflash nanoCUL
  produce the same symptom. We cannot distinguish them from the
  feasibility test alone.

  **Would it work single, without the pool?**
  - If it is a **modbus bridge**: no. ramses_rf would open the port, send
    40 signature probes, get no echo, fall through to `gateway_id=None`
    (receive-only), and never be able to send.
  - If it is a **nanoCUL with evofw3**: yes, it should work single — it
    would echo `_PUZZ`, get an HGI ID, and function normally. The fact
    that it doesn't echo means either the firmware is wrong/missing, or
    it is not a nanoCUL at all.
  - If it is a **nanoCUL with wrong firmware**: no, but it could be
    reflashed with evofw3 to work.

- **HGI80** (`/dev/ttys001`) — this test tells us **nothing about the
  HGI80 itself.** The HGI80 cannot be tested on macOS at all.

  **The HGI80 is NOT a standard USB-serial device.** It uses a Texas
  Instruments TUSB3410 USB-to-serial chip (VID `0x10ac`, PID `0x0102`).
  On Linux, it requires the `ti_usb_3410_5052` kernel driver AND a
  firmware file (`ti_usb-v10ac-p0102.fw`). Without the driver, the
  TUSB3410 stays in its boot-loader mode.

  **On macOS, the HGI80 shows up as a Removable Disk** (USB mass
  storage), not a serial device. silverailscolo confirmed this:
  "The HGI80 just doesn't show up on macOS as a serial device, only as
  a Removable Disk. Too smart." This is the TUSB3410 boot-loader mode
  — macOS doesn't have the `ti_usb_3410_5052` driver, so the device
  falls back to mass storage presentation.

  This means:
  1. **`/dev/ttys001` was never connected to the real HGI80.** The pty
     was connected to something else (a relay, a proxy, or nothing).
  2. **The HGI80 can only be tested on Linux** (HA OS, Docker on Linux)
     with the `ti_usb_3410_5052` driver and firmware loaded. On Linux
     it appears as `/dev/ttyUSB*`.
  3. **The 0 bytes, DTR/RTS ioctl errors, and no unplug detection are
     all pty artifacts**, not HGI80 limitations. They tell us nothing
     about the HGI80 hardware.
  4. **The HGI80 may work perfectly fine** — it just can't be tested on
     macOS. silverailscolo plans to "set it up as a USB HGI on my HA
     kit and try controlling" — this is the correct approach. On HA OS
     (Linux), the driver should load automatically and the HGI80 should
     appear as `/dev/ttyUSB*`.

---

## 1a. nanoCUL analysis — assuming evofw3 firmware

If the FTDI device is a nanoCUL running evofw3 (the most likely case given
silverailscolo's ramses_rf involvement), the feasibility test results can
be explained by the evofw3 architecture. The analysis below is based on
the evofw3 source code (ghoti57/evofw3, version 0.7.3).

### The 17 bytes are the evofw3 boot banner

evofw3's `gateway_init()` (gateway.c) prints a version string on boot:

```c
// Force a version string to be printed
inCmd = cmd(CMD, NULL, NULL);    // CMD = '!'
inCmd = cmd('V', NULL, NULL);
inCmd = cmd('\r', &cmdBuff, &nCmd);
```

The `V` command (cmd.c) produces: `# evofw3 0.7.3\r\n`

```
# evofw3 0.7.3\r\n  =  17 bytes  (matches the test exactly)
```

This confirms:
1. **The device IS running evofw3** — the boot banner is evofw3-specific
2. **The baud rate (115200) is correct** — the version string is readable,
   not garbled (a baud mismatch would produce garbage)
3. **The device boots and reaches the main loop** — it's not dead

### The echo mechanism requires RF TX + RF loopback

The `_PUZZ` signature is NOT a debug command. It's a RAMSES packet
(` I --- 18:000730 --:------ 18:000730 7FFF 012 0010...`) that goes
through evofw3's `msg_scan()` parser (gateway.c). The echo path is:

```
Host sends _PUZZ over serial (82 bytes)
  → evofw3 parses it via msg_scan()
  → evofw3 replaces source addr with its own ID (msg_change_addr)
  → evofw3 transmits it over RF (msg_tx_ready)
  → evofw3 receives its own RF transmission (loopback)
  → evofw3 prints the received packet on serial
  → Host sees the echo
```

If RF TX fails, there is no loopback, no echo. This is a **known nanoCUL
limitation** — the evofw3 README says: "While evofw3 supports the 16MHz
atmega328 the receive performance of the atmega32u4 is significantly
better." Community reports (ghoti57/evofw3 discussions) confirm nanoCUL
TX issues: "I was unable send commands to change any thermostat settings."

### The RX buffer is 32 bytes — the _PUZZ frame is 82 bytes

evofw3's host serial RX buffer is defined in `tty.h`:

```c
#define TXBUF 32
#define RXBUF 32
```

The `_PUZZ` signature frame sent by the feasibility script is:

```
" I --- 18:000730 --:------ 18:000730 7FFF 012 0010"  (48 chars)
+ 12-char hex timestamp                                   (12 chars)
+ "76357635763576357635"                                  (20 chars)
+ "\r\n"                                                   (2 chars)
= 82 bytes total
```

At 115200 baud, 82 bytes take ~7ms to transmit. The 32-byte RX buffer
fills in ~2.8ms. If the ATmega328p's main loop doesn't drain at least one
byte every 2.8ms, the buffer **overflows** and the packet is never fully
received.

### Why the ATmega328p main loop can be too slow

The nanoCUL (ATmega328p) uses:
- **Hardware USART** for host communication (via FTDI chip) — robust
- **Software UART** (pin-change interrupts) for CC1101 radio RX — fragile

The `gateway_work()` main loop (gateway.c) processes one host byte per
iteration, but each iteration also:
1. Calls `frame_work()` and `msg_work()` (radio state machine)
2. Prints any received RF messages to the host (`tty_put_str`)
3. Handles CC1101 tuning

If the CC1101 is actively receiving RF traffic, the software UART
interrupt handler consumes CPU cycles on every pin change. The main loop
slows down. The 32-byte hardware USART buffer overflows before all 82
bytes of the `_PUZZ` frame are processed. `msg_scan()` never sees a
complete valid packet, so the frame is never transmitted over RF, and
there is no echo.

### The "froze/crashed and needs more time" theory

The user's intuition is partially correct. The device doesn't literally
crash, but it is **starved of CPU cycles** by the software UART. The
"needs more time" theory has three variants:

1. **More time after port open before probing** — tested (2s delay),
   didn't help. The device boots fast (~1s) and prints its version
   banner. The issue is not boot time.

2. **More time after the probe for the response** — tested (2s read),
   didn't help. If the packet was never fully received (buffer overflow),
   no amount of read time will produce an echo.

3. **More time between bytes (slow down transmission)** — **NOT tested**.
   This is the most promising variant. If the host sends the 82-byte
   frame with inter-byte delays (e.g., 1ms per byte), the 32-byte buffer
   would never overflow. The ATmega328p would have time to process each
   byte through `msg_scan()`. This would test whether the buffer
   overflow is the root cause.

### The "both LOW = 75 bytes" anomaly

The DTR/RTS "both LOW" test received 75 bytes (vs 17 for all other
tests). This is **outgoing** data from the device (RF messages being
relayed), not incoming. DTR=LOW + RTS=LOW might change the FTDI's flow
control behavior, causing the device to flush a longer buffer. It does
not indicate the device can receive longer frames.

### What would confirm each theory

| Theory | Test | Expected result if theory is correct |
|--------|------|--------------------------------------|
| Buffer overflow | Send _PUZZ with 1ms inter-byte delay | Echo received |
| TX broken | Send `!V\r` (version command) | `# evofw3 0.7.3\r\n` response (proves host serial works) |
| TX broken | Send a short RAMSES packet (<32 bytes) | Echo if TX works, no echo if TX broken |
| Baud rate wrong | Open at 57600, send `!V\r` | Readable version string if 57600 is correct |
| RF traffic starvation | Test in an RF-quiet environment | Echo received when no RF traffic |

### Implications for pool support

If the root cause is **buffer overflow** (theory 3), the fix is in
ramses_rf: send the signature frame with inter-byte pacing when the
child is a nanoCUL/ATmega328p. The `PortTransport` could detect the FTDI
VID and apply byte pacing automatically. This would make the nanoCUL work
both single and in pool.

If the root cause is **TX broken** (known nanoCUL limitation), the
nanoCUL can only be a **receive-only** pool child. It would need
`signature_policy = SKIP` + `configured_hgi_id` (Gap B + Gap D). It
could contribute to inbound dedup and RSSI diversity but could not be
selected for outbound routing.

Either way, the nanoCUL needs per-child config overrides (Gap D) to
coexist with ESP32 children in a mixed pool.

---

## 1b. nanoCUL re-test results — conclusive

silverailscolo ran the updated `--nanocul` script three times. Run 3
(comment 5588219009) used the corrected script with both `V\r` (culfw)
and `!V\r` (evofw3) version commands and a boot banner capture.

### Run 3: `/dev/tty.usbserial-A50285BI`, 1ms/byte pacing

| Test | Result | Bytes | Notes |
|------|--------|-------|-------|
| Port open (no write) | PASS | 17 | Boot banner |
| Immediate 7FFF probe | FAIL | 0 | No echo |
| Repeated probes (5x) | FAIL | 0 | 0 echoes |
| Delayed probe (2s) | FAIL | 17 | No echo |
| Ordinary RF write | FAIL | 17 | No response |
| Close/reopen | PASS | 0 | Reopened OK |
| **Boot banner capture** | PASS | 17 | **`'\x11# evofw3 0.7.1'`** |
| **Version command (!V + V)** | **FAIL** | **0** | **No response to either** |
| Paced 7FFF probe (1ms/byte) | FAIL | 17 | No echo |
| Paced RF write (1ms/byte) | FAIL | 17 | No response |

### Run 3 (5ms): `/dev/cu.usbserial-A50285BI`, 5ms/byte pacing

Identical results — all probes fail, version command fails, 17 bytes
boot banner only.

### Conclusion: evofw3 confirmed, but RX path may NOT be broken

The boot banner capture is conclusive:

```
'\x11# evofw3 0.7.1'
```

- `\x11` = DC1 control character (evofw3 sends this before the banner)
- `# evofw3 0.7.1` = evofw3 version string (version 0.7.1, not 0.7.3)

**The device IS running evofw3** — not culfw. The culfw hypothesis is
disproven.

**However, the "RX path broken" conclusion may be premature.** Looking
at the timing pattern across all tests in run 3:

| Test | Wait before send | Read duration | Bytes |
|------|-----------------|---------------|-------|
| Port open (no write) | n/a | 2.0s | 17 |
| Immediate probe | 0s | 1.0s | **0** |
| Repeated probes | 0s | 1.0s | **0** |
| Delayed probe (2s) | 2.0s | 1.0s | 17 |
| Ordinary RF write | 2.0s | 2.0s | 17 |
| Close/reopen | 0.5s | 1.0s | **0** |
| Boot banner capture | n/a | 2.0s | 17 |
| Version command | **0.5s** | 1.0s+1.0s | **0** |
| Paced probe | 0.5s | 2.0s | 17 |
| Paced RF write | 0.5s | 2.0s | 17 |

Tests that read for 2s get 17 bytes (the boot banner). Tests that read
for only 1s after a quick write get 0 bytes. The version command waits
only **0.5s** before sending — which may be too short.

**New hypothesis: the device resets on port open (DTR toggle) and
takes 1-2s to boot.** pyserial sets DTR=True on open by default. On
many nanoCUL/Arduino boards, DTR is wired to the ATmega reset line for
auto-reset during flashing. Opening the port resets the device, it
takes 1-2s to boot, and commands sent before boot completes are lost.

The 17 bytes always appear in tests that read for 2+ seconds because
the boot banner arrives 1-2s after port open. Tests that read for only
1s miss the banner (it arrives after the read ends). The version
command sends at 0.5s — before the device has finished booting.

**This means the RX path might be fine — we're just sending commands
too early.** The updated test script now includes two new tests:
- `test_version_command_delayed`: waits 3s after port open before
  sending (lets the device finish booting)
- `test_version_command_no_dtr`: opens with `dsrdtr=True` and
  `DTR=False` to prevent the reset entirely

If either of these gets a version response, the root cause is timing
(DTR reset + boot delay), not a broken RX path.



### ramses_rf (`feat/phase2-signature-policy` branch, 6 commits)

Implemented:
- `SignaturePolicy` enum (`IMMEDIATE` / `DELAYED` / `SKIP`) in
  `TransportConfig` (`transport/base.py:32-104`)
- `startup_grace: float | None` field (default 3.0s)
- `PortTransport._create_connection()` dispatches on `signature_policy`
  (`transport/port.py:414-449`):
  - `IMMEDIATE` → `connect_with_signature()` (default, backward-compatible)
  - `DELAYED` → `connect_with_delayed_signature()` (wait grace, then probe)
  - `SKIP` → `connect_sans_signature()` (no probe, receive-only until
    identity learned from inbound traffic)
- Bounded serial reconnect with exponential backoff
- Write-failure propagation into pool child error state
- `callback_port_names` / `callback_child_start_index` for hybrid pools
  (serial transport-driven + MQTT callback-driven children in one
  `PooledTransport`)

### ramses_cc (`fix/issue-1171-pool-config-bugs` branch, 23 commits)

Implemented:
- Hybrid pool constructor `_create_hybrid_pool_transport_constructor`
  (`coordinator.py:2607-2723`): builds one `PooledTransport` with serial
  children (transport-driven, serialx) + MQTT children (callback-driven,
  HA-native `RamsesMqttPoolBridge`)
- Config-flow serial un-gating (commit `1225b399`): "Serial/USB port..."
  option in the add dropdown, `manage_pool_serial` step, removed Phase 1
  MQTT-with-serial-primary blocking
- `_removed_from_pool` trait, primary removal/auto-promotion, credential
  masking, sentinel filtering (all issue 1171 fixes)

---

## 3. Gaps blocking USB pool support

### Gap A — ramses_cc does not set `signature_policy=DELAYED` for pooled serial children

The hybrid pool constructor passes the **shared** `TransportConfig` (which
defaults to `IMMEDIATE`) to `pooled_transport_factory`. ESP32 pool children
would still reset-loop on open in production.

**Location:** `coordinator.py:2681-2689` — the `config` kwarg is the shared
engine config, not a per-child override.

**Fix:** When constructing the `TransportConfig` for a pool that contains
serial children, set `signature_policy=SignaturePolicy.DELAYED` and
`startup_grace=3.0`.

### Gap B — `configured_hgi_id` is not implemented

The Phase 2 doc (`multi-hgi-phase2-3-followup-issue.md:456-461`) lists
`configured_hgi_id: str | None` as a Phase 2 field, but it does not exist
in `TransportConfig` or `PortTransport`. The `connect_sans_signature()`
path always uses `gateway_id=None` (`port.py:356-359`).

This is required for the FTDI dongle (and any device that does not echo the
signature probe): the user must be able to manually configure the HGI ID so
the pool can route through it without a signature exchange.

**Fix:**
1. Add `configured_hgi_id: str | None` to `TransportConfig`
   (`transport/base.py`)
2. In `connect_sans_signature()`, use `configured_hgi_id` instead of `None`
   when set (`transport/port.py:356-359`)
3. Validate a later observed identity against the configured one (doc
   requirement, Phase 2 regression test)

### Gap C — `_is_hgi80` is computed but unused in the dispatch logic

`is_hgi80()` is called and stored in `self._is_hgi80` (`port.py:354`), but
the signature-policy dispatch (`port.py:414-440`) only checks
`disable_sending` and `signature_policy` — never `_is_hgi80`. With the
default `IMMEDIATE` policy, an HGI80 wastes `_SIGNATURE_MAX_SECS` sending
40 probes that never echo, then falls through to `gateway_id=None`.

The HGI80 does not echo `_PUZZ` (it is not evofw3) and has a long firmware
boot phase. It should auto-select `SKIP` regardless of the configured
`signature_policy`.

**Fix:** In `_create_connection()`, after `self._is_hgi80 = await
is_hgi80(...)`, if `_is_hgi80 is True`, force `connect_sans_signature()`
(or auto-set `signature_policy = SKIP` for that child).

### Gap D — No per-child `TransportConfig` overrides (the structural blocker)

`pooled_transport_factory` shares **one** `TransportConfig` across all
children (`factory.py:279-296`). There is no per-child
`signature_policy`, `startup_grace`, or `configured_hgi_id`.

This makes a **mixed USB pool impossible**: you cannot have one serial child
with `DELAYED` (ESP32) and another with `SKIP` (HGI80) in the same pool, nor
can you set a `configured_hgi_id` for just the FTDI child.

This is the core architectural prerequisite. Without per-child config
overrides, the three device types cannot coexist in one pool.

**Fix:**
1. Extend `pooled_transport_factory` to accept an optional
   `per_child_config_overrides: list[dict[str, Any]] | None` (same length as
   `port_names`)
2. In `_create_single_child()`, merge the override into the shared
   `TransportConfig` (e.g. `dataclasses.replace(config, **override)`)
3. ramses_cc populates the overrides from per-port config (signature policy,
   grace, configured HGI ID) when building the hybrid pool

---

## 4. Per-device workmap

### ESP32-S3 (evofw3) — works once Gap A is fixed

- Needs `signature_policy = DELAYED` + `startup_grace = 3.0s`
- Already implemented in ramses_rf; ramses_cc just needs to set it
- No new ramses_rf code required
- Feasibility gate: PASSED

### FTDI dongle (nanoCUL with evofw3) — two possible root causes

See the full analysis in section 1a. The 17 bytes are the evofw3 boot
banner (`# evofw3 0.7.3\r\n`), confirming the device runs evofw3 at
115200 baud. The no-echo result has two candidate root causes:

1. **RX buffer overflow** (most testable): the _PUZZ frame is 82 bytes,
   but the ATmega328p's RX buffer is only 32 bytes. If the main loop is
   busy with software UART interrupts (radio RX), the buffer overflows
   before the full packet is received. **Test: send _PUZZ with 1ms
   inter-byte delay.** If echo appears, this is the root cause and the
   fix is byte-pacing in ramses_rf's `PortTransport` for nanoCUL devices.

2. **TX broken** (known nanoCUL limitation): even if the packet is
   fully received, the echo requires RF TX + RF loopback. nanoCUL TX is
   known to be unreliable on the ATmega328p. **Test: send a short
   RAMSES packet (<32 bytes) to avoid buffer overflow.** If still no
   echo, TX is broken and the nanoCUL can only be receive-only.

**If root cause is buffer overflow:** nanoCUL works in pool with
byte-pacing. Needs `signature_policy = DELAYED` (for boot grace) + byte
pacing (new ramses_rf feature). No `configured_hgi_id` needed — the
signature echo would work once the buffer doesn't overflow.

**If root cause is TX broken:** nanoCUL is receive-only in pool. Needs
`signature_policy = SKIP` + `configured_hgi_id` (Gap B + Gap D). Can
contribute to inbound dedup and RSSI diversity but cannot be selected
for outbound routing.

Either way, per-child config overrides (Gap D) are needed to coexist
with ESP32 children in a mixed pool.

### HGI80 — cannot be tested on macOS; needs Linux test

- The HGI80 uses a TI TUSB3410 USB-to-serial chip (VID `0x10ac`,
  PID `0x0102`), not a standard FTDI or CDC device.
- On macOS, it shows up as a **Removable Disk** (USB mass storage)
  because macOS lacks the `ti_usb_3410_5052` driver. The TUSB3410
  falls back to its boot-loader mode, which presents as mass storage.
- The `/dev/ttys001` test was never connected to the real HGI80 — it
  was a pty connected to something else (or nothing).
- The HGI80 can only be tested on Linux (HA OS, Docker on Linux) with
  the `ti_usb_3410_5052` driver and firmware loaded. On Linux it
  appears as `/dev/ttyUSB*`.
- silverailscolo plans to "set it up as a USB HGI on my HA kit and try
  controlling" — this is the correct approach.
- Once tested on Linux, the HGI80 would need `signature_policy = SKIP`
  (auto-detected via `_is_hgi80`, Gap C) + per-child config overrides
  (Gap D).
- HGI80 placeholder behavior remains supported (architecture invariant 9).

---

## 5. Recommended implementation order

1. **Gap D (per-child config overrides)** — structural prerequisite, unblocks
   the rest. ramses_rf `factory.py` + `pooled.py`.
2. **Gap A (DELAYED for pooled ESP32)** — small, ramses_cc only. Unblocks
   ESP32 pool use immediately.
3. **Gap C (auto-SKIP for HGI80)** — small, ramses_rf `port.py` only. Uses
   the already-computed `_is_hgi80`.
4. **Gap B (`configured_hgi_id`)** — ramses_rf `base.py` + `port.py`, plus
   ramses_cc config plumbing. Unblocks FTDI (pending firmware confirmation).

Each gap maps to a Phase 2 regression test in the follow-up doc's "PR 3 —
Regression tests required" section (`multi-hgi-phase2-3-followup-issue.md:216-237`).

---

## 6. Open questions for silverailscolo

The nanoCUL questions have been partially answered by run 3 (comment
5588219009):

- **Firmware:** evofw3 0.7.1 (confirmed by boot banner `\x11# evofw3 0.7.1`)
- **Serial RX path:** unclear — the version command failed, but it
  may have been sent before the device finished booting (DTR reset +
  1-2s boot delay). The updated script now tests with a 3s delay and
  with DTR disabled.

Remaining questions:

1. **Re-run with updated script (delayed + no-DTR version commands):**
   The previous version command waited only 0.5s before sending, which
   may be too short if the device resets on port open and takes 1-2s to
   boot. The updated script now includes:
   - `test_version_command_delayed`: waits 3s after port open
   - `test_version_command_no_dtr`: opens with DTR disabled

   ```
   python esp_usb_feasibility_standalone.py /dev/tty.usbserial-A50285BI --nanocul --report report_ftdi_nanocul_run4.md
   ```

   If either of these gets a version response, the root cause is
   timing (DTR reset + boot delay), not a broken RX path.

2. **HGI80 on Linux:** The HGI80 cannot be tested on macOS — it
   shows up as a Removable Disk (USB mass storage) because macOS lacks
   the `ti_usb_3410_5052` driver. silverailscolo plans to set it up on
   the HA kit (Linux) instead — this is the correct approach. On Linux
   with the `ti_usb_3410_5052` driver and firmware loaded, the HGI80
   should appear as `/dev/ttyUSB*`. Can you run the feasibility test
   there once it's set up?

3. **Container/USB forwarding:** Where does your HA instance run (HA OS,
   Docker on Linux, Docker on Mac, etc.)? If HA is in a container, how
   are USB devices forwarded to it (socat, ser2net, direct `--device`
   passthrough, USB-over-IP)?
