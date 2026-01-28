# Ramses Extras

[![CI](https://github.com/wimpie70/ramses_extras/actions/workflows/check-lint.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/check-lint.yml)
[![Quality](https://github.com/wimpie70/ramses_extras/actions/workflows/check-type.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/check-type.yml)
[![Tests](https://github.com/wimpie70/ramses_extras/actions/workflows/tests.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/tests.yml)
[![Integration](https://github.com/wimpie70/ramses_extras/actions/workflows/hassfest.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/hassfest.yml)
[![HACS](https://github.com/wimpie70/ramses_extras/actions/workflows/hacs-validate.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/hacs-validate.yml)
[![CodeQL](https://github.com/wimpie70/ramses_extras/workflows/CodeQL/badge.svg)](https://github.com/wimpie70/ramses_extras/security/code-scanning)
[![codecov](https://codecov.io/gh/wimpie70/ramses_extras/graph/badge.svg?token=3O1T9U8H49)](https://codecov.io/gh/wimpie70/ramses_extras)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![Home Assistant >=2026.1.0](https://img.shields.io/badge/home%20assistant-%3E%3D2026.1.0-green.svg)](https://home-assistant.io)

**Ramses Extras** is a Home Assistant integration that extends the Ramses RF ([ramses_cc](https://github.com/ramses-rf/ramses_cc)) integration with additional features, entities, automation, and UI components. Built on a modular framework for easy extension and maintenance.

## 🎯 **What is Ramses Extras?**

Ramses Extras provides additional features, entities, automation, and UI components for the Ramses RF (ramses_cc) integration.

`note: This is a work in progress, contributions are welcome ([CONTRIBUTING.md](CONTRIBUTING.md)).`

- **Modular Features**: Easy to enable/disable features based on user needs
- **Automatic Cleanup**: Features manage their own entities, cards, and services
- **Custom Cards**: JavaScript cards available as custom card types in dashboards
- **Framework Foundation**: Reusable components for easy feature development

Ramses Extras registers Lovelace cards via a single, versioned bootstrap resource:

- **Lovelace resource URL**: `/local/ramses_extras/v{version}/helpers/main.js`
- **Purpose**: loads card/editor modules on-demand using dynamic imports

Frontend cards and editors are **theme-adaptive** and use Home Assistant theme variables (e.g., `--primary-text-color`, `--ha-card-background`, `--divider-color`) instead of hardcoded colors.

## ✨ **Current Features**

note: the following are tested with an Orcon WTW

- **Hello World** - template feature, example to develop new features
- **HVAC Fan Card** – advanced Lovelace card for FAN monitoring and control
- **Humidity Control** – advanced humidity-based automation and entities
- **Sensor Control** – central sensor mapping for Humidity Control + HVAC Fan Card
- **Ramses Debugger** – advanced debugging tools for Ramses RF protocol analysis
- **Default feature** - Common/reusable websockets, entities, etc to be used by other features

### **✅ HVAC Fan Card**

**Advanced Lovelace card for ventilation system control:**

- **Visual Airflow Diagrams**: Real-time system status visualization
- **Control Interface**: Fan speed, timer, and bypass controls
- **Parameter Editing**: Configuration of system parameters
- **Status Display**: Temperature, humidity, efficiency, and CO₂ monitoring
- **Template System**: Modular JavaScript templates for dynamic content
- **Responsive Design**: Works across different device sizes

![HVAC Fan Card Screenshot 1](docs/hvac_fan_card_1.png)
![HVAC Fan Card Screenshot 2](docs/hvac_fan_card_2.png)

The card uses `ramses_extras/get_entity_mappings` to resolve entities and
Sensor Control's resolver metadata to populate a **Sensor Sources** panel. When
absolute humidity is configured via Sensor Control, the card marks the indoor
and outdoor absolute humidity metrics as **derived** and shows them alongside
temperature, humidity, and CO₂ sources.

### **✅ Humidity Control**

**Intelligent humidity-based ventilation automation:**

- **Smart Decision Logic**: Analyzes indoor vs outdoor absolute humidity to optimize ventilation
- **Dynamic Fan Control**: Automatically adjusts fan speeds based on moisture conditions
- **Comprehensive Entities**:
  - Absolute humidity sensors (indoor/outdoor)
  - Humidity thresholds (min/max configuration)
  - Dehumidification switches and status indicators
  - Offset adjustments for fine-tuning
- **Bilingual Support**: English and Dutch translations
- **Full Test Coverage**: Comprehensive test suite with validation

### **✅ Sensor Control**

**Central sensor source management and override system:**

- **Flexible Source Selection**: Configure external entities for any sensor metric
- **Supported Metrics**: Indoor/outdoor temperature, humidity, CO₂, and absolute humidity
- **Fail-Closed Behavior**: Invalid external entities safely disable rather than fallback
- **Source Types**: Internal (default), external entities, derived (absolute humidity), or disabled
- **Visual Indicators**: HVAC fan card shows sensor source status with color-coded indicators
- **WebSocket Integration**: Real-time sensor mapping updates via `ramses_extras/get_entity_mappings`
- **Automation Integration**: Humidity control automatically uses effective sensor mappings
- **Per-Device Configuration**: Different sensor sources for each FAN/CO2 device

For **absolute humidity**, Sensor Control does not expose a direct entity itself.
Instead it drives the default feature's resolver-aware sensors:

- `sensor.indoor_absolute_humidity_{device_id}`
- `sensor.outdoor_absolute_humidity_{device_id}`

These sensors are calculated as follows:

- If `abs_humidity_inputs` are configured for a device/side, the sensor derives
  absolute humidity either from:
  - an external temperature + relative humidity pair, or
  - a direct external absolute humidity sensor.
- If no `abs_humidity_inputs` are configured, they fall back to the internal
  ramses_cc temperature/humidity values.

This makes the default absolute humidity sensors the **single source of truth**
for:

- the Humidity Control automation logic, and
- the HVAC Fan Card graphs and status.

Sensor Control itself does not create new sensors. Instead, it rewires _which_
entities other features use for each metric:

- Humidity Control reads indoor/outdoor temperature and humidity via
  `SensorControlResolver`, so changing mappings in the Sensor Control UI
  immediately affects the automation inputs.
- The HVAC Fan Card resolves entities through the same resolver and shows the
  effective source (internal vs external vs derived vs disabled) using
  color-coded indicators.

The Sensor Control configuration flow provides:

- A **global overview** page that summarizes only non-internal mappings per
  device, including absolute humidity inputs, so you can quickly see which
  metrics are overridden.
- A **per-device group menu** that shows the current non-internal mappings for
  the selected device before you dive into a specific group (indoor, outdoor,
  CO₂, absolute humidity).
- A **Finish** option in the per-device menu that saves all changes as you go
  and returns to the main Ramses Extras options menu.

CO₂ support today focuses on using a dedicated CO₂ device as an external input
for a FAN. The CO₂ device has a preview-only configuration screen; the real
mappings are configured on the FAN device under the **CO₂** group.

This is especially useful when you have multiple FANs with different hardware
capabilities:

- One FAN may have a full set of built-in sensors.
- Another FAN may be missing one or more sensors, or its internal sensors may
  not represent the rooms you actually care about.

With Sensor Control you can still give **both** FANs the same
features/automations and UI:

- The first FAN uses its internal sensors.
- The second FAN can point individual metrics to external HA sensors located in
  better positions (or on other devices).

### **✅ Ramses Debugger**

This feature works best with a dedicated dashboard page.

**Advanced debugging tools for Ramses RF protocol analysis:**

- **Traffic Analyzer**: Real-time monitoring and analysis of Ramses RF message traffic
- **Log Explorer**: Search and analyze Home Assistant and packet logs with advanced filtering
- **Packet Log Explorer**: Deep dive into packet-level communication details
- **Cross-Filtering**: Navigate between traffic data and log entries seamlessly
- **Message Viewer**: Unified view of messages from multiple sources with filtering and sorting

![Traffic Analyzer](docs/TrafficAnalyser.png)
![HA Log Explorer](docs/HALogExplorer.png)
![Packet Log Explorer](docs/PacketLogExplorer.png)

The debugger provides comprehensive tools for troubleshooting Ramses RF communication:

- Real-time traffic monitoring with device pair filtering
- Advanced log search with context extraction and traceback highlighting
- Packet-level analysis with parsed payload display
- Cross-referencing between traffic events and log entries

### **🏛️ Framework Foundation**

**Reusable architecture for easy feature development:**

- **Feature-Centric Architecture**: Each feature is self-contained and modular
- **Base Classes**: Common functionality for entities, automation, and services
- **Template Systems**: Multiple template approaches (JavaScript, Python, Entity, Translation)
- **Validation Framework**: Type safety and consistency checking
- **Entity Registry**: Centralized entity management and naming

## 📋 **Quick Start**

### **Installation**

#### **HACS (Recommended)**

1. Add this repository to HACS as a custom repository
2. Search for "Ramses Extras" and install
3. Restart Home Assistant
4. Configure through **Settings → Devices & Services → Ramses Extras**

#### **Manual Installation**

1. Copy the `custom_components/ramses_extras` directory to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant
3. Configure through **Settings → Devices & Services**

### **Configuration**

#### **Ramses RF - bound REM**

When using FAN related features, make sure Ramses RF has the 'bound' trait defined for your FAN.
example:

```
"37:168270":
  class: REM
"32:153289":
  bound: "37:168270"
  class: FAN
```

#### **Ramses Extras**

1. Go to **Settings → Devices & Services**
2. Click **"Add Integration"**
3. Search for **"Ramses Extras"**
4. Select which features to enable:
   - ✅ **Humidity Control** (works together with the hvac Fan Card)
   - ✅ **Sensor Control** (shared sensor mapping for Humidity Control + HVAC Fan Card)
   - ✅ **Ramses Debugger** (advanced debugging tools for protocol analysis)
   - 🟡 **HVAC Fan Card**

### **Basic Usage**

After enabling a feature Ramses Extras will automatically create the associated tools, depending on the device type.

- **New Entities**: Sensors, switches, numbers, input boolean, ... eg: `sensor.indoor_absolute_humidity_{device_id}`
- **New Automations**: For now, only hardcoded python scripts are supported. (more control than the yaml automations)
- **New Cards**: javascript cards, available as a card type when edititing a dashboard
- **New Services**: extra service calls, to send commands
- **New Websocket**: For use by javascript to get info from Ramses Extras (or Ramses RF) like `get_bound_rem`

## 🏗️ **Architecture**

Ramses Extras uses a **feature-centric architecture** built on a **framework foundation**. For detailed architecture information, see the [Wiki](https://github.com/wimpie70/ramses_extras/wiki).

## 🔧 **Requirements**

- **Home Assistant**: >=2026.1.0 or later
- **Ramses RF** (ramses_cc): v0.52.1 (pre-release) or later: https://github.com/ramses-rf/ramses_cc
- **Python**: 3.13

## 🤝 **Contributing**

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and the [Wiki](https://github.com/wimpie70/ramses_extras/wiki) for detailed development patterns.

### **Quick Start**

- 📖 Read the [Wiki Architecture Guide](https://github.com/wimpie70/ramses_extras/wiki)
- 🛠️ Write your code
- 🧪 Write tests for new features

## 📜 **License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- **Ramses RF Community**: For the RF library
- **Home Assistant**: For the fantastic automation platform
- **Contributors**: Everyone who has contributed to this project

## 🆘 **Support & Issues**

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/wimpie70/ramses_extras/issues)
- 💬 **Feature Requests**: [GitHub Discussions](https://github.com/wimpie70/ramses_extras/discussions)
- 📚 **Troubleshooting**: See [Wiki Troubleshooting Guide](https://github.com/wimpie70/ramses_extras/wiki)

---
