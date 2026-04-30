# Device Simulator Profile Audit - April 30, 2026

## Summary

Reviewed device profiles (FAN.yaml, CO2.yaml, REM.yaml, HUM.yaml, DIS.yaml) for realism and completeness. Identified and fixed missing response entries for FAN device to handle all RQ codes that ramses_cc queries during discovery and normal operation.

## Findings

### FAN Device (32:150000)

**Status**: ✅ FIXED - Now comprehensive

**What ramses_cc queries (from `HvacVentilator._setup_discovery_cmds` in ramses_rf)**:
- Daily discovery:
  - `10E0` (device info) - ✅ Had response
  - `22F1` (fan mode/scheme detection) - ❌ MISSING → Added
  - `2411` (fan parameters) - ✅ Had response
- 30-minute discovery:
  - `2210` (air quality) - ❌ MISSING → Added
  - `22E0` (bypass position) - ❌ MISSING → Added
  - `22E5` (remaining minutes) - ❌ MISSING → Added
  - `22E9` (speed cap) - ❌ MISSING → Added
  - `22F2` (post heat) - ❌ MISSING → Added
  - `22F4` (pre heat) - ❌ MISSING → Added
  - `313E` (unknown HVAC) - ❌ MISSING → Added
  - `3222` (diagnostic) - ❌ MISSING → Added
- 24-hour discovery:
  - `10D0` (filter change) - ❌ MISSING → Added
  - `313F` (clock/datetime) - ❌ MISSING → Added

**Additional RP codes from schema** (not queried but good to have):
- `0001` (menu index) - ❌ MISSING → Added
- `1470` (programme scheme) - ❌ MISSING → Added
- `1F09` (sync) - ❌ MISSING → Added
- `22F7` (bypass mode) - ❌ MISSING → Added
- `31D9` (fan state) - ❌ MISSING → Added

**Changes Made**:
- Added 15 new response entries to FAN.yaml
- All payloads validated against ramses_tx parser regexes
- Payloads use realistic values (e.g., filter ~180 days, bypass off, medium speed)
- Delays set to 100ms (realistic RQ→RP latency)

### CO2 Device (37:120000)

**Status**: ✅ ADEQUATE

Has responses for:
- `22F1` (fan mode) - for CO2 to query FAN
- `31E0` (CO2 level) - autonomous + response
- `31DA` (HVAC state) - response for discovery
- `2411` (parameters) - "not supported" response
- `10E0` (device info) - autonomous

Missing from schema but not critical:
- `1298` (CO2 demand) - has autonomous, no response needed (CO2 broadcasts, doesn't respond)

### REM Device (37:170000)

**Status**: ✅ ADEQUATE

Has responses for:
- `0001`, `1470`, `313F`, `31DA`, `10E0` - all correct
- `22F7`, `2411` - these are RQ codes REM sends (not receives RP for), but having them as responses doesn't hurt

### HUM Device (29:120000)

**Status**: ⚠️ MINIMAL

Has only 2 response entries:
- `31DA` (HVAC state) - for discovery
- `10E0` (device info) - fallback

HUM is a humidity sensor with minimal interaction, so this is acceptable.

### DIS Device (37:160000)

**Status**: ✅ ADEQUATE

Has comprehensive responses including:
- Discovery codes: `313F`, `1470`, `0001`, `10E0`
- HVAC interaction: `22F7`, `31DA`, `22F1`, `22F3`, `22F8`
- Parameters: `2411`

## Realism Assessment

### Autonomous Message Intervals

**FAN.yaml** - Good mix of realistic intervals:
- `31DA` (full telemetry): 10s ✅ (realistic, was 60s before)
- `12C8` (air quality): 12s ✅ (realistic, was 60s before)
- `22F7` (bypass state): 2s with state_change trigger ✅ (realistic, randomized)
- `31D9` (fan state): 60s ✅ (reasonable baseline)
- `1FC9` (multi-code burst): 5.4s ✅ (realistic, matches real devices)

**CO2.yaml** - Reasonable:
- `31E0` (CO2 level): 60s ✅ (realistic)
- `1298` (CO2 demand): 60s ✅ (realistic)
- `10E0` (device info): 61.7s ✅ (realistic, daily discovery)

**REM.yaml** - Good:
- `1FC9` (multi-code): 5.4s ✅ (realistic)
- `1060` (button/state): 13.5s ✅ (realistic)
- `10E0` (device info): 61.7s ✅ (realistic)

### Payload Realism

**FAN payloads** - All realistic:
- `31DA`: Real captured payloads from Orcon fan (32:153289) on 2026-04-27
- `31D9`: Orcon scheme medium speed (0x0207)
- `22F1`: Orcon scheme low speed (0x0207)
- `22F7`: Bypass off (0x0000EF)
- `2411`: Real parameter responses from device traffic (37:168270 → 32:153289)
- `10E0`: Real device info from Orcon fan

**CO2 payloads** - All realistic:
- `31E0`: Real CO2 level from parsed logs (37:126776)
- `1298`: Real CO2 demand from parsed logs
- `10E0`: Real device info from regression file

**REM/DIS payloads** - All realistic:
- Sourced from regression_packets_sorted.txt
- Match parser expectations

## Unknown Entities Handling

**Current Status**:
- FAN: Now has complete response coverage for all codes ramses_cc queries
- CO2: Has responses for all codes it receives RQ for
- REM: Has responses for all codes it receives RQ for
- HUM: Minimal but adequate (humidity sensor, limited interaction)
- DIS: Comprehensive responses

**Dynamic Response Fallbacks** (in response_templates.py):
- Currently only CTL has dynamic responses (30C9, 000C, 2349)
- FAN could benefit from dynamic responses for codes without DB entries
- Recommendation: Add FAN-specific dynamic response builder for:
  - `22F1`: Return current speed based on last autonomous payload
  - `31D9`: Return current state based on last autonomous payload
  - `2411`: Already has special handling in scenario_engine.py

## Recommendations

1. ✅ **DONE**: Add missing FAN response entries (15 new codes)
2. Consider adding FAN-specific dynamic response builder in response_templates.py
3. Monitor real device traffic to refine payload values
4. Consider adding variant-specific payloads for different FAN brands (Itho, Orcon, Nuaire, Vasco)
5. REM.yaml: Consider removing 22F7/2411 responses (they're RQ codes, not RP)

## Testing

To verify the changes work correctly:
```bash
# Run device simulator with FAN profile
make local-ci  # Full test suite with coverage

# Or manually test:
cd /home/willem/dev/ramses_extras
source ~/venvs/extras/bin/activate
pytest custom_components/ramses_extras/features/device_simulator/tests/ -v
```

The simulator should now respond to all RQ codes that ramses_cc sends to FAN devices, making the simulation more realistic and complete.
