# Ramses Extras

[![CI](https://github.com/wimpie70/ramses_extras/actions/workflows/ci.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/ci.yml)
[![Quality](https://github.com/wimpie70/ramses_extras/actions/workflows/quality.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/quality.yml)
[![Tests](https://github.com/wimpie70/ramses_extras/actions/workflows/test.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/test.yml)
[![Integration](https://github.com/wimpie70/ramses_extras/actions/workflows/integration.yml/badge.svg)](https://github.com/wimpie70/ramses_extras/actions/workflows/integration.yml)
[![codecov](https://codecov.io/gh/wimpie70/ramses_extras/branch/main/graph/badge.svg)](https://codecov.io/gh/wimpie70/ramses_extras)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![Home Assistant 2025.10.4](https://img.shields.io/badge/home%20assistant-2025.10.4-green.svg)](https://home-assistant.io)

**Ramses Extras** is a Home Assistant integration that extends the Ramses RF ([ramses_cc](https://github.com/ramses-rf/ramses_cc)) integration with additional features, entities, automation, and UI components. Built on a modular framework for easy extension and maintenance.

## 🎯 **What is Ramses Extras?**

Ramses Extras provides additional features, entities, automation, and UI components for the Ramses RF (ramses_cc) integration.

`note: This is a work in progress, contributions are welcome ([CONTRIBUTING.md](CONTRIBUTING.md)).`

- **Modular Features**: Easy to enable/disable features based on user needs
- **Automatic Cleanup**: Features manage their own entities, cards, and services
- **Custom Cards**: JavaScript cards available as custom card types in dashboards
- **Framework Foundation**: Reusable components for easy feature development

## ✨ **Current Features**

note: the following are tested with an Orcon WTW FAN

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

### **✅ HVAC Fan Card**

**Advanced Lovelace card for ventilation system control:**

- **Visual Airflow Diagrams**: Real-time system status visualization
- **Control Interface**: Fan speed, timer, and bypass controls
- **Parameter Editing**: Configuration of system parameters
- **Status Display**: Temperature, humidity, efficiency, and CO₂ monitoring
- **Template System**: Modular JavaScript templates for dynamic content
- **Responsive Design**: Works across different device sizes

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

1. Go to **Settings → Devices & Services**
2. Click **"Add Integration"**
3. Search for **"Ramses Extras"**
4. Select which features to enable:
   - ✅ **Humidity Control** (works together with the hvac Fan Card)
   - 🟡 **HVAC Fan Card**

### **Basic Usage**

After enabling a feature Ramses Extras will automatically create the associated tools, depending on the device type.

- **New Entities**: Sensors, switches, numbers, input boolean, ... eg: `sensor.indoor_absolute_humidity_{device_id}`
- **New Automations**: For now, only hardcoded python scripts are supported. (more control than the yaml automations)
- **New Cards**: javascript cards, available as a card type when edititing a dashboard
- **New Services**: extra service calls, to send commands
- **New Websocket**: For use by javascript to get info from Ramses Extras (or Ramses RF) like `get_bound_rem`

## 🏗️ **Architecture**

Ramses Extras uses a **feature-centric architecture** built on a **framework foundation**. For detailed architecture information, see the [Wiki Architecture Guide](https://github.com/wimpie70/ramses_extras/wiki).

## 🔧 **Requirements**

- **Home Assistant**: 2025.10.4 or later
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
