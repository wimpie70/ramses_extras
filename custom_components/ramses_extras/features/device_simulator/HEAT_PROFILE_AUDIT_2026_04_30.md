# Heat Device Profiles Audit - April 30, 2026

## Summary

Reviewed heat device profiles (CTL, TRV, BDR, OTB, DHW, THM, etc.) for realism and completeness. Identified significant gaps in response coverage for CTL (controller) and other heat devices.

## Key Findings

### CTL Device (01:145038 - Evohome Controller)

**Status**: ⚠️ SEVERELY INCOMPLETE

**What ramses_cc queries** (from `Controller._setup_discovery_cmds`):
- `2E04` (system mode) - 60-minute interval ✅ Has response

**What CTL can respond to** (from `_DEV_KLASSES_HEAT[CTL]`):
- RP codes: `0002`, `0004`, `0005`, `0006`, `000A`, `000C`, `0016`, `0100`, `0404`, `0418`, `10A0`, `10E0`, `1100`, `1260`, `1290`, `12B0`, `1F09`, `1FC9`, `1F41`, `2309`, `2349`, `2E04`, `30C9`, `313F`, `3B00`

**Current responses in CTL.yaml**:
- `22D9` (unknown code - not in schema)
- `0016` (binding ack) ✅
- `3220` (OEM diagnostic) ✅
- `3EF0` (unknown code - not in schema)
- `2E04` (system mode) ✅

**Missing critical responses** (23 codes):
- `0002`, `0004`, `0005`, `0006`, `000A`, `000C`, `0100`, `0404`, `0418`, `10A0`, `10E0`, `1100`, `1260`, `1290`, `12B0`, `1F09`, `1FC9`, `1F41`, `2309`, `2349`, `30C9`, `313F`, `3B00`

### TRV Device (04:056010 - Radiator Valve)

**Status**: ✅ ADEQUATE

**What ramses_cc queries** (from `Radiator._setup_discovery_cmds`):
- `1F09` (sync) ✅ Has response
- `313F` (clock) ✅ Has response
- `0100` (locale) ✅ Has response
- `0016` (binding) ✅ Has response
- `0004` (zone name) ✅ Has response

**Current responses**: 5 entries covering all discovery codes

### BDR Device (13:237335 - Relay Box)

**Status**: ⚠️ MINIMAL

**What ramses_cc queries**: Nothing specific (faked devices skip discovery)

**Current responses**: Only `10E0` (device info) with minimal fallback

**Missing responses** (from schema):
- `0008`, `0016`, `1100`, `1FC9`, `3B00`, `3EF0`, `3EF1`

### OTB Device (10:123456 - OpenTherm Bridge)

**Status**: ⚠️ MINIMAL

**What ramses_cc queries** (from `OpenThermBridge._setup_discovery_cmds`):
- `3EF0` or `3220` (status) - varies by config
- Multiple OpenTherm message IDs (3EF0 with different payloads)

**Current responses**: Only `10E0` with minimal fallback

**Missing responses** (from schema):
- `0150`, `042F`, `1081`, `1098`, `10A0`, `10B0`, `10E1`, `1260`, `1290`, `12F0`, `1300`, `1FC9`, `1FD0`, `22D9`, `2400`, `2401`, `2410`, `2420`, `3150`, `3200`, `3210`, `3220`, `3221`, `3223`, `3EF0`, `3EF1`

### DHW Device (07:044315 - DHW Cylinder Thermostat)

**Status**: ⚠️ MINIMAL

**Current responses**: None

**Missing responses** (from schema):
- `0016`, `1060`, `10A0`, `1260`, `1FC9`

### THM Device (30:253184 - Generic Thermostat)

**Status**: ⚠️ MINIMAL

**Current responses**: None

**Missing responses** (from schema):
- `0001`, `0005`, `0008`, `0009`, `000A`, `000C`, `000E`, `0016`, `01FF`, `042F`, `1030`, `1060`, `1090`, `10E0`, `1100`, `12C0`, `1F09`, `1FC9`, `2309`, `2349`, `3110`, `3120`, `313F`, `3220`, `3B00`, `3EF0`, `3EF1`

### PRG Device (34:010943 - Room Temperature Sensor)

**Status**: ⚠️ MINIMAL

**Current responses**: None

**Missing responses** (from schema):
- `1090`, `10A0`, `3EF1`

### UFC Device (35:123456 - Underfloor Heating Controller)

**Status**: ⚠️ MINIMAL

**Current responses**: None

**Missing responses** (from schema):
- `0001`, `0005`, `000A`, `000C`, `10E0`, `22D0`, `2309`

### RFG Device (18:001234 - RF Gateway)

**Status**: ⚠️ MINIMAL

**Current responses**: None

**Missing responses** (from schema):
- `0016`, `0404`, `10E0`, `1260`, `1290`, `1FC9`, `10A0`

### Other Heat Devices (BDR, JIM, JST, OUT, RND, DTS, HCW, RFS)

**Status**: ⚠️ MINIMAL

Most have no responses defined.

## Root Cause Analysis

The heat device profiles were auto-generated from ramses_rf sources but:
1. Only populated autonomous entries (I frames)
2. Minimal or no response entries (RP frames)
3. No manual curation of realistic payloads
4. Unlike HVAC devices, heat devices weren't reviewed for completeness

## Recommendations

### Priority 1 (Critical for simulation realism)
1. **CTL.yaml**: Add 23 missing response entries
   - Focus on: `0004`, `0005`, `000A`, `000C`, `10E0`, `1100`, `1F09`, `1FC9`, `2309`, `2349`, `30C9`, `313F`
   - These are commonly queried during normal operation

2. **OTB.yaml**: Add OpenTherm bridge responses
   - Focus on: `10E0`, `3EF0`, `3220`, `1FC9`
   - These are critical for OpenTherm integration

3. **BDR.yaml**: Add relay responses
   - Focus on: `0016`, `1100`, `1FC9`, `3EF1`

### Priority 2 (Important for completeness)
4. **DHW.yaml**: Add DHW thermostat responses
5. **THM.yaml**: Add generic thermostat responses
6. **RFG.yaml**: Add gateway responses

### Priority 3 (Nice to have)
7. **PRG.yaml**: Add room sensor responses
8. **UFC.yaml**: Add UFH controller responses
9. **JIM.yaml**, **JST.yaml**: Add Jasper device responses

## Implementation Strategy

1. Extract realistic payloads from ramses_rf test fixtures and regression data
2. Use parser regexes from ramses_tx/ramses.py to validate payload formats
3. Add dynamic response fallbacks in response_templates.py for heat devices
4. Prioritize CTL and OTB as they're most commonly used in real systems

## Files to Modify

- `/home/willem/dev/ramses_extras/custom_components/ramses_extras/features/device_simulator/device_db/heat/CTL.yaml` - Add 23 responses
- `/home/willem/dev/ramses_extras/custom_components/ramses_extras/features/device_simulator/device_db/heat/OTB.yaml` - Add 15+ responses
- `/home/willem/dev/ramses_extras/custom_components/ramses_extras/features/device_simulator/device_db/heat/BDR.yaml` - Add 6 responses
- `/home/willem/dev/ramses_extras/custom_components/ramses_extras/features/device_simulator/device_db/heat/DHW.yaml` - Add 5 responses
- `/home/willem/dev/ramses_extras/custom_components/ramses_extras/features/device_simulator/response_templates.py` - Add CTL/OTB dynamic response builders

## Status

Heat device profiles are significantly less complete than HVAC profiles. This is a larger undertaking than the HVAC audit but essential for realistic simulation of heating systems.
