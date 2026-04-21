# Ramses Extras 0.19.3 Release Notes

**Release Date:** April 18, 2026

## Overview

Version 0.19.3 is a major pre-release featuring the complete implementation of the Device Simulator (Phase 8), including full UI cards, profile management, response engine, and real-time message monitoring. This release also includes extensive test infrastructure fixes, deployment improvements, and documentation enhancements.

---

## Device Simulator Improvements

### Infrastructure

- **Ramses Message Stream:** New message stream listener for real-time RAMSES message monitoring
- **Ramses Debugger:** Updated debugger tools for the new message stream listener
- **Comm Endpoint:** Fixed MQTT handler thread safety using `call_soon_threadsafe()`
- **Blocking I/O Fixes:** Wrapped blocking operations (scandir, open) with `async_add_executor_job()` for proper async handling
- **Binary Sensor:** Fixed binary sensor error logs and StopIteration issues with proper async generator handling
- **System Config:** Improved configuration management with race condition fixes

### Deployment & Configuration

- **Deployment Helpers:** Improved deployment scripts with `HA_SIM_CONFIG` environment variable support for easier simulator setup
- **MQTT Isolation Documentation:** Enhanced documentation explaining topic namespace separation between production (`RAMSES/GATEWAY`) and simulator (`RAMSES/GATEWAY_SIM`)
- **Configuration Safety:** Added prominent warning that simulator should only run on dedicated containers/systems as it modifies Ramses RF settings

### WebSocket Commands

- **Autonomous Speed Control:** New WebSocket command to adjust autonomous emission speed multiplier
- **Profile Device Activation:** New WebSocket command to activate profile devices
- **Zone Membership:** Improved active device info with zone membership display

### Scenario Engine

- **Autonomous Emissions:** Refactored autonomous emission task using `time.monotonic` and speed multiplier for better timing control
- **Device Activity Checks:** Added methods to check device activity status
- **Code Quality:** Removed duplicate method definitions and added type annotations
- **Scenario Persistence:** Auto answer scenario persistence, fixed scenarios continuing while disabled/stopped
- **Service Integration:** Added `device_simulator_run_scenario` and `device_simulator_stop_scenario` services with proper HA integration
- **Fresh Start:** Improved fresh start profile to remove RF devices, cached messages, and reload RF
- **Response Engine:** Complete 2411 response engine with parameter synthesis and delayed sending

### Profile Management

- **Profile Loading:** Load and persist Ramses RF profiles with remove option
- **Profile Options:** Added schema-preload, RF-cache reset, wipe HA storage, and ramses.db removal options
- **Profile Cleaning:** Extra cleaning of devices when changing profiles
- **Auto Reload RF:** Option to automatically reload RF on new profile loads
- **Heat Profiles:** Fixed heat profiles with bound REM support and detection message responses
- **Gateway Topic Persistence:** Gateway topic now persisted and restored, integrated with simulator enable/disable flow
- **HGI Presence:** Fixed HGI presence packet on heat-only profiles
- **Event Subscription:** Fixed event subscription crash and RQ to inactive heating devices timeouts
- **Flooding Control:** Limited message flooding with schema removal from profiles, global speed setting

### Device Database

- **New Database:** Complete device database overhaul with YAML-based configuration
- **Audit Tools:** New device database audit tools for validation
- **Response Templates:** Added 30C9/000C/2349 payload synthesizers for detection message responses
- **Device Type Detection:** Improved device type detection with fingerprint-based lookup
- **Message Logs:** Added message logs to devices for debugging

### Cards & UI

- **Device Simulator Card (Phase 8):** Complete UI card implementation with device tabs, scenario controls, and message log
- **Real-time Updates:** WebSocket subscription for real-time device activation/changed events with live message support
- **Live Subscription:** Fixed card's live subscription to use `hass.connection.subscribeMessage` for proper HA integration
- **Autonomous Emissions Display:** Card now treats autonomous_emissions as active whenever emitters are running
- **Scenario Controls:** Start/Stop buttons on card with scenario_type and params display, proper service integration
- **Device Tab Enhancements:**
  - Known-list badges for device status
  - Zone support and display
  - Live messages with W-RP for 2411 message detection
  - Timeout scale fixes
- **Card Pill:** Fixed to stay on running state, improved stop button functionality
- **Base Card Dependency:** Made sim card depend on basecard for shared functionality
- **Card Loading:** Fixed card not loading issues and translation errors
- **Message Log:** Added user-select CSS to make message log table text selectable for copy/paste operations

---

## Testing & Quality

### Test Infrastructure

- **Logging Configuration:** Added timestamp configuration to pytest console output for better debugging
- **Import Error Handling:** Fixed `ModuleNotFoundError` for ramses_cc import in profile_loader.py with graceful fallback
- **Test Fixes:**
  - Fixed `_reload_ramses_cc` test calls to include new `profile_devices` argument
  - Fixed `test_async_apply_profile_skip_rf_hydrate` to use config_store instead of environment variables
  - Fixed `test_respond_to_rq_send_error` by adding active device to scenario engine
  - Fixed E501 line length errors across multiple test files

### Code Quality

- **Linting:** Fixed Ruff E501 line length errors in multiple files
- **Type Checking:** Fixed MyPy unreachable code and type annotation issues
- **Import Organization:** Fixed E402 errors by moving imports above module docstrings

### Dependency Management

---

## Bug Fixes

### Device Simulator

- **Parser Handling:** Verified that list payloads for fan codes 12A0 and 31DA are correctly handled by existing code
- **Response Engine:** Fixed long log message strings to comply with line length limits
- **Message Log:** Removed unused type: ignore comments for cleaner code

### Framework

- **Message Stream:** Fixed E501 line too long errors, mypy unreachable code warnings, and dict entry type errors
- **Card Loading:** Made message log table text selectable for copy/paste operations

---

## Documentation

### Device Simulator Wiki

- **Deployment Section:** Complete rewrite with `HA_SIM_CONFIG` environment variable instructions
- **MQTT Configuration:** Clarified topic namespace separation and automatic adaptation
- **Known Issues:** Added section documenting:
  - RF restart required to find bound REM on clean systems
  - RQ messages not logged correctly to packet log
  - RQ/RP message order issues due to retries
- **Scenario Registry:** Added "Rotate Log Files" scenario stub for testing log rotation scenarios

---

## Documentation

- **Device Simulator Wiki:** Updated with deployment instructions, MQTT configuration details, and known issues
- **Release Notes:** This file

---

## Full Changelog

See the [full commit history](https://github.com/wimpie70/ramses_extras/compare/0.19.0...0.19.3) for detailed changes.

---

## Contributors

Special thanks to all contributors who helped with testing, bug reports, and code contributions for this release.

---

## Support

For issues, questions, or feature requests:

- GitHub Issues: https://github.com/wimpie70/ramses_extras/issues
- Documentation: https://github.com/wimpie70/ramses_extras/wiki
