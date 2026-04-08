# Ramses Extras 0.19.0 Release Notes

**Release Date:** April 8, 2026

## Overview

Version 0.19.0 introduces major new features for FAN configuration, CO2 control, and significant improvements to the HVAC Fan Card. This release also includes extensive test coverage improvements, security fixes, and GitHub workflow updates.

---

## Major New Features

### FAN Configuration (Sensor Control)

- **New Feature:** Complete FAN configuration system for managing indoor/outdoor temperature, humidity, CO2, and absolute humidity inputs
- **Config Flow:** Full configuration flow with support for:
  - Internal fan sensors (temperature, humidity, CO2, absolute humidity)
  - Area sensors with custom mappings
  - Zone management with import/export via YAML
  - REM (Remote) binding management
- **Ramses FAN Map Card:** New visualization card for FAN configuration with:
  - Live sensor values and auto-updates
  - Topology view with structured data
  - Observability features (live read-only mode)
  - REM highlighting and status indicators
  - Test bench UI with ARM checkbox and confirmation prompts

### CO2 Control

- **New Feature:** CO2-based ventilation control with multi-zone monitoring
- **Automation:** Automatic CO2 threshold monitoring and fan speed adjustment
- **Multi-zone Support:** Monitor and control multiple zones based on CO2 levels
- **Integration:** Full integration with HVAC Fan Card for visual feedback

### Fan Speed Arbiter

- **New Architecture:** Centralized arbitration system for fan speed control
- **Conflict Resolution:** Handles competing demands from humidity control, CO2 control, and manual overrides
- **Priority Management:** Intelligent prioritization of fan speed requests
- **Monitoring:** Transport monitoring for fan communication status

---

## HVAC Fan Card Improvements

### UI/UX Enhancements

- **Live Values:** Real-time sensor value display with automatic updates
- **Highlighting:** Visual indicators for triggering sensors (humidity, CO2, REM)
- **Status Indicators:** Online/offline status for fan communication
- **Design Improvements:** Better layout and information hierarchy
- **Speed Display:** Fixed speed indicator and manual overrule display

### Functional Improvements

- **Auto Control:** Enhanced auto mode with better control logic
- **Sensor Display:** Improved sensor value presentation
- **Configuration:** Better integration with sensor control configuration

---

## Infrastructure & Architecture

### Framework Improvements

- **Shared FAN-scoped Model Helpers:** New helper functions for FAN device management
- **Remote Binding Registry:** Improved REM management and binding tracking
- **Device Feature Matrix:** Better tracking of enabled features per device
- **Zone Management:** Enhanced zone configuration with YAML import/export

### Configuration System

- **YAML Import/Export:** Full support for importing and exporting zone configurations
- **Validation:** Improved configuration validation with better error messages
- **Migration:** Smooth migration paths for configuration changes

---

## Testing & Quality

### Test Coverage Improvements

- **Sensor Control Config Flow:** >95% test coverage achieved
- **WebSocket Commands:** New tests for sensor control WebSocket handlers
- **Device Type Handlers:** Tests for FAN device type handlers
- **Default Feature:** Improved test coverage for default config flow

### Code Quality

- **Type Checking:** MyPy compliance improvements
- **Linting:** Ruff formatting and linting fixes
- **Documentation:** Improved inline documentation and docstrings

---

## Security Fixes

### npm Dependencies

- **picomatch:** Updated to 2.3.2 (CVE-2024-4068 - method injection vulnerability)
- **brace-expansion:** Updated to 1.1.13 (CVE-2024-XXXX - zero-step sequence vulnerability)
- **minimatch:** Updated to 3.1.5 (security fixes)

### GitHub Actions

- **Node.js Version:** Fixed invalid Node.js version '24' → '22' in workflows
- **Workflow Reliability:** Improved workflow stability and caching

---

## Bug Fixes

### Binary Sensors

- Fixed transport state binary sensor entity ID format
- Fixed transport monitoring for device online/offline status
- Fixed binary sensor platform setup issues

### Automation

- Fixed humidity control automation logic
- Fixed CO2 threshold handling and listener issues
- Fixed automation loop causing HA breakage
- Fixed max humidity threshold (66% → 60%)

### Configuration Flow

- Fixed internal fan sensors entity validation ("Entity None is neither a valid entity ID nor a valid UUID")
- Fixed area_id and zone_id editing in config flow
- Fixed custom REM future implementation notes
- Fixed validator partial matrix bug

### Cards & UI

- Fixed HVAC Fan Card design issues
- Fixed card highlighting for triggering sensors
- Fixed speed overrule display by humidity control
- Fixed downgrading issues on cards

### Communication

- Fixed fan communication monitoring
- Fixed communication pause when disconnected from fan
- Fixed how we monitor on/offline device status

---

## Breaking Changes

None - this release maintains backward compatibility with existing configurations.

---

## Migration Notes

### For Users Upgrading from 0.17.x or 0.18.x

1. **Configuration:** Existing configurations will be automatically migrated
2. **New Features:** Enable new features via the Options Flow:
   - CO2 Control (disabled by default)
   - FAN Configuration / Sensor Control (disabled by default)
3. **Cards:** Update custom cards via the integration options if needed

### For Developers

1. **New Architecture:** Review the fan speed arbiter for integration points
2. **WebSocket API:** New endpoints available for FAN configuration
3. **Feature Development:** See `docs/FAN_CONTROL_ARCHITECTURE.md` for architecture details

---

## Known Issues

- **Fan Position Calibration:** When closing to 40%, the valve first moves to home position (0), then to 40%. This is intentional for accurate positioning but may cause brief additional movement.

---

## Documentation

- **FAN Control Architecture:** `docs/FAN_CONTROL_ARCHITECTURE.md`
- **CO2 Control Design:** `docs/CO2_CONTROL_DESIGN.md`
- **Configuration Strategy:** `docs/CONFIGURATION_STRATEGY.md`
- **Remote Binding Examples:** `docs/REMOTE_BINDING_EXAMPLES.md`
- **Zones Implementation:** `docs/ZONES_IMPLEMENTATION_PLAN.md`

---

## Full Changelog

See the [full commit history](https://github.com/wimpie70/ramses_extras/compare/0.17.4...0.19.0) for detailed changes.

---

## Contributors

Special thanks to all contributors who helped with testing, bug reports, and code contributions for this release.

---

## Support

For issues, questions, or feature requests:

- GitHub Issues: https://github.com/wimpie70/ramses_extras/issues
- Documentation: https://github.com/wimpie70/ramses_extras/wiki
