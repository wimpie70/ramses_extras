# Device Simulator Profile Audit - Complete Summary
## April 30, 2026

---

## Executive Summary

Completed comprehensive audit of device simulator profiles for both HVAC and heat domains:

- **HVAC Devices**: ✅ FIXED - FAN now has 15 new response entries, CO2/REM/HUM/DIS adequate
- **Heat Devices**: ⚠️ NEEDS WORK - CTL severely incomplete (missing 23 responses), OTB/BDR/DHW/THM minimal

---

## HVAC Domain Status

### Completed Work

**FAN Device (32:150000)** - ✅ COMPREHENSIVE
- Added 15 new response entries covering all codes ramses_cc queries
- All payloads validated against parser regexes
- Realistic values (filter ~180 days, bypass off, medium speed)
- Dynamic response fallbacks added for 6 codes

**CO2 Device (37:120000)** - ✅ ADEQUATE
- Has responses for all codes it receives RQ for
- Realistic autonomous intervals (60s telemetry)
- Payloads from real device logs

**REM Device (37:170000)** - ✅ ADEQUATE
- Responses for all discovery codes
- Some extra entries (22F7, 2411) are RQ codes, not harmful

**HUM Device (29:120000)** - ✅ MINIMAL BUT ADEQUATE
- Humidity sensor with limited interaction
- Essential responses present

**DIS Device (37:160000)** - ✅ COMPREHENSIVE
- Full response coverage for all interaction codes

### Files Modified
1. `device_db/hvac/FAN.yaml` - Added 15 response entries
2. `response_templates.py` - Added FAN dynamic response builders

---

## Heat Domain Status

### Findings

**CTL Device (01:145038)** - ⚠️ SEVERELY INCOMPLETE
- Only 5 response entries, missing 23 critical codes
- Can respond to 28 different codes, only covers 5
- Needs: `0002`, `0004`, `0005`, `0006`, `000A`, `000C`, `0100`, `0404`, `0418`, `10A0`, `10E0`, `1100`, `1260`, `1290`, `12B0`, `1F09`, `1FC9`, `1F41`, `2309`, `2349`, `30C9`, `313F`, `3B00`

**OTB Device (10:123456)** - ⚠️ MINIMAL
- Only 1 response entry (`10E0` fallback)
- Missing 25+ OpenTherm bridge responses
- Needs: `0150`, `042F`, `1081`, `1098`, `10A0`, `10B0`, `10E1`, `1260`, `1290`, `12F0`, `1300`, `1FC9`, `1FD0`, `22D9`, `2400`, `2401`, `2410`, `2420`, `3150`, `3200`, `3210`, `3220`, `3221`, `3223`, `3EF0`, `3EF1`

**BDR Device (13:237335)** - ⚠️ MINIMAL
- Only 1 response entry
- Missing 7 codes: `0008`, `0016`, `1100`, `1FC9`, `3B00`, `3EF0`, `3EF1`

**DHW Device (07:044315)** - ⚠️ NO RESPONSES
- Missing all 5 codes: `0016`, `1060`, `10A0`, `1260`, `1FC9`

**THM Device (30:253184)** - ⚠️ NO RESPONSES
- Missing all 27 codes

**Other Heat Devices** (PRG, UFC, RFG, JIM, JST, OUT, RND, DTS, HCW, RFS) - ⚠️ MINIMAL/NONE

### Root Cause
Heat device profiles were auto-generated from ramses_rf with only autonomous entries, no manual curation of responses.

---

## Recommendations by Priority

### Phase 1: HVAC (COMPLETED ✅)
- [x] Add FAN response entries (15 codes)
- [x] Add FAN dynamic response fallbacks
- [x] Verify CO2/REM/HUM/DIS adequacy

### Phase 2: Heat Core Devices (RECOMMENDED)
- [ ] Add CTL response entries (23 codes)
- [ ] Add OTB response entries (15+ codes)
- [ ] Add BDR response entries (6 codes)
- [ ] Add DHW response entries (5 codes)
- [ ] Add CTL/OTB dynamic response fallbacks

### Phase 3: Heat Extended Devices (OPTIONAL)
- [ ] Add THM response entries (27 codes)
- [ ] Add PRG response entries (3 codes)
- [ ] Add UFC response entries (7 codes)
- [ ] Add RFG response entries (7 codes)

---

## Files Created

1. `PROFILE_AUDIT_2026_04_30.md` - HVAC audit details
2. `HEAT_PROFILE_AUDIT_2026_04_30.md` - Heat audit details
3. This summary document

---

## Next Steps

1. **Immediate**: Review this audit with user
2. **If proceeding with heat**: Start with CTL and OTB (most critical)
3. **Testing**: Run `make local-ci` after each phase to verify no regressions
4. **Validation**: All payloads must match parser regexes from ramses_tx/ramses.py

---

## Validation Status

- ✅ HVAC profiles: All YAML valid, all payloads validated
- ⚠️ Heat profiles: Audit complete, implementation pending
