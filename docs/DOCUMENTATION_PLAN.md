# Ramses Extras Documentation Plan & Gap Analysis

**Created:** March 31, 2026
**Status:** Active - Implementation in Progress
**Scope:** FAN Configuration, Sensor Control, Zones, Remote Binding

---

## Executive Summary

This document catalogs the current documentation state for the Ramses Extras project, identifies gaps, and provides an implementation roadmap. The FAN Configuration feature (evolved from `sensor_control`) is the primary focus area requiring user-facing documentation.

---

## 📚 Current Documentation Inventory

### ✅ Well-Maintained Architecture Docs

| Document | Lines | Status | Purpose |
|----------|-------|--------|---------|
| `FAN_CONTROL_ARCHITECTURE.md` | 581 | ✅ Current | Fan speed arbitration, transport monitoring, manual override model |
| `FAN_CONFIGURATION_SCHEMA_DRAFT.md` | 440 | ⚠️ Needs update | YAML schema, config strategy (marked implemented but has outdated status) |
| `ZONES_IMPLEMENTATION_PLAN.md` | 475 | ✅ Current | Zone data model, phased implementation plan |
| `CONFIGURATION_STRATEGY.md` | 499 | ⚠️ Needs update | Hybrid config model, phased plan (phases 1-4 complete) |
| `REMOTE_BINDING_IMPLEMENTATION_PLAN.md` | 360 | ✅ Current | REM→FAN binding architecture |
| `REMOTE_BINDING_EXAMPLES.md` | 333 | ✅ Current | Practical YAML configuration examples |
| `RAMSES_EXTRAS_ARCHITECTURE.md` | 2300 | ✅ Current | Overall system architecture v0.15.2 |
| `CO2_CONTROL_DESIGN.md` | 650 | ⚠️ Outdated | CO2 feature design (implementation differs from doc) |

### Documentation by Category

| Category | Count | Assessment |
|----------|-------|------------|
| **Architecture & Design** | 8 | ✅ Well covered |
| **Implementation Plans** | 4 | ✅ Well covered |
| **User Guides** | 0 | ❌ **Critical gap** |
| **Examples** | 1 | ⚠️ Needs expansion |
| **Troubleshooting** | 0 | ❌ Missing |
| **Developer Guides** | 0 | ⚠️ Nice to have |

---

## ❌ Critical Documentation Gaps

### Priority 1: User-Facing Documentation (HIGH)

| Missing Document | User Impact | Content Needed |
|------------------|-------------|----------------|
| `FAN_CONFIGURATION_USER_GUIDE.md` | Users cannot understand config flow menu structure | Menu walkthrough, internal fan sensors, zones, REM binding |
| `ZONES_USER_GUIDE.md` | Users don't know how to configure zones | ORCON vs custom valves, min/max positions, zone setup |
| `TROUBLESHOOTING.md` | Issues scattered across multiple docs | Consolidated diagnostic steps, common errors, fixes |

### Priority 2: Configuration Documentation (MEDIUM)

| Missing Document | User Impact | Content Needed |
|------------------|-------------|----------------|
| `YAML_IMPORT_EXPORT_GUIDE.md` | Export/import features underutilized | Strict YAML format, migration, validation |
| `INTERNAL_FAN_SENSORS_GUIDE.md` | New internal sensors feature undocumented | CO2 + absolute humidity consolidation |
| `MIGRATION_GUIDE.md` | Users unaware of config evolution | Legacy→canonical transition, what changes |

### Priority 3: Developer Documentation (LOW)

| Missing Document | Audience | Content |
|------------------|----------|---------|
| `FEATURE_DEVELOPER_GUIDE.md` | Contributors | Adding features to FAN Configuration framework |
| `DEVICE_HANDLER_PROTOCOL.md` | Contributors | `SensorControlDeviceHandler` protocol reference |
| `CONFIG_FLOW_PATTERNS.md` | Contributors | Reusable patterns for FAN-oriented flows |

---

## 🔄 Documents Needing Updates

### Status Text Updates Required

| Document | Current Text | Required Change |
|----------|--------------|-----------------|
| `FAN_CONFIGURATION_SCHEMA_DRAFT.md` | "should evolve toward FAN Configuration" | Mark as **COMPLETE** - UI rename done |
| `CONFIGURATION_STRATEGY.md` (line ~457) | "likely evolving...toward FAN Configuration" | Update to "completed rename to FAN Configuration" |
| `ZONES_IMPLEMENTATION_PLAN.md` | Phase 5c pending | Update or defer based on hardware testing |
| `CO2_CONTROL_DESIGN.md` | Separate `co2_control` feature | Clarify CO2 is part of `sensor_control` internal sensors |
| `RAMSES_EXTRAS_ARCHITECTURE.md` | Section 4.3 mentions `sensor_control` | Add note about FAN Configuration naming |

---

## 📋 Implementation Checklist

### Phase 1: Critical User Docs (Target: Immediate)

- [x] Create this gap analysis document (`DOCUMENTATION_PLAN.md`)
- [ ] Create `FAN_CONFIGURATION_USER_GUIDE.md`
  - [ ] Config flow menu structure
  - [ ] Device selection and feature enablement
  - [ ] Internal fan sensors configuration
  - [ ] Zone configuration walkthrough
  - [ ] Remote binding setup
- [ ] Create `TROUBLESHOOTING.md`
  - [ ] Common config flow issues
  - [ ] Sensor resolution problems
  - [ ] Zone/actuator issues
  - [ ] REM binding diagnostics

### Phase 2: Status Updates (Target: This week)

- [ ] Update `FAN_CONFIGURATION_SCHEMA_DRAFT.md` status section
- [ ] Update `CONFIGURATION_STRATEGY.md` line ~457
- [ ] Update `ZONES_IMPLEMENTATION_PLAN.md` Phase 5c status
- [ ] Add note to `RAMSES_EXTRAS_ARCHITECTURE.md` section 4.3

### Phase 3: Enhancement Docs (Target: Next sprint)

- [ ] Create `ZONES_USER_GUIDE.md`
- [ ] Create `YAML_IMPORT_EXPORT_GUIDE.md`
- [ ] Create `INTERNAL_FAN_SENSORS_GUIDE.md`
- [ ] Create `MIGRATION_GUIDE.md`

### Phase 4: Developer Docs (Target: Backlog)

- [ ] Create `FEATURE_DEVELOPER_GUIDE.md`
- [ ] Create `DEVICE_HANDLER_PROTOCOL.md`
- [ ] Consider doc restructuring into subdirectories

---

## 🗂️ Recommended Directory Structure

**Current:** All docs flat in `/docs/`

**Proposed Future Structure:**
```
docs/
├── README.md                    # Documentation index
├── DOCUMENTATION_PLAN.md        # This file
├── architecture/               # System design
│   ├── FAN_CONTROL_ARCHITECTURE.md
│   ├── CONFIGURATION_STRATEGY.md
│   └── RAMSES_EXTRAS_ARCHITECTURE.md
├── implementation/            # Implementation plans
│   ├── ZONES_IMPLEMENTATION_PLAN.md
│   ├── REMOTE_BINDING_IMPLEMENTATION_PLAN.md
│   └── CO2_CONTROL_DESIGN.md
├── user-guides/               # End-user docs ← NEW
│   ├── FAN_CONFIGURATION.md
│   ├── ZONES_SETUP.md
│   ├── REMOTE_BINDING.md
│   └── TROUBLESHOOTING.md
├── examples/                  # Configuration examples
│   ├── REMOTE_BINDING_EXAMPLES.md
│   └── YAML_EXAMPLES.md
└── developer/                 # Developer docs ← NEW
    ├── FEATURE_DEVELOPMENT.md
    └── API_REFERENCE.md
```

---

## 📊 Metrics & Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| User-facing guides | 0 | 4 |
| Architecture docs | 8 | 8 (maintain) |
| Examples | 1 | 3 |
| Troubleshooting coverage | 0% | 80% common issues |
| Outdated status text | 5 locations | 0 locations |

---

## Notes

- FAN Configuration = the UI/UX name for what was `sensor_control`
- All existing architecture docs remain accurate and valuable
- Primary gap is user onboarding, not technical design
- YAML export/import works but lacks user documentation
- Zone valves pending hardware testing (Phase 5c)

---

**Last Updated:** March 31, 2026
