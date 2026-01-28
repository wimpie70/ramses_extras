# Ramses Extras - Quick Reference

**Ramses Extras** extends the Ramses RF (ramses_cc) integration with additional features, entities, automation, and UI components.

## 🚀 Quick Start

### Installation
1. **HACS**: Add as custom repository, search "Ramses Extras", install, restart HA
2. **Manual**: Copy to `custom_components/ramses_extras`, restart HA

### Configuration
1. Settings → Devices & Services → Add Integration → "Ramses Extras"
2. Select features:
   - ✅ **Humidity Control**: Smart ventilation automation
   - 🟡 **HVAC Fan Card**: Advanced control interface

## 🎯 Features

### Humidity Control
- Intelligent humidity-based ventilation automation
- Dynamic fan speed control
- Absolute humidity sensors and switches
- Manual override capabilities

### HVAC Fan Card
- Real-time system visualization
- Fan speed, timer, and bypass controls
- Temperature and humidity monitoring
- Parameter configuration interface

## 📚 Full Documentation

- **[Architecture Guide](Home)**: Complete system architecture
- **[Troubleshooting Guide](Home#debugging-and-troubleshooting-guide)**: Common issues and solutions

## 🆘 Support

- **Bugs**: [GitHub Issues](https://github.com/wimpie70/ramses_extras/issues)
- **Features**: [GitHub Discussions](https://github.com/wimpie70/ramses_extras/discussions)

## 📋 Requirements

- Home Assistant >=2026.1.0
- Ramses RF (ramses_cc) v0.52.1+
- Python 3.13
