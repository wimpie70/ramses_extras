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

Ramses Extras provides a collection of (front-end) utilities for the Ramses RF (ramses_cc) integration.

`note: This is a work in progress, contributions are welcome ([CONTRIBUTING.md](CONTRIBUTING.md)).`

- Easy to disable/enable features to the users needs
- Features will create (or clean-up) their own entities, cards, webhooks, servicecalls or other logic
- when editing dashboards, the provided cards will be available as their own type
- The framework provides a lot of the overhead needed when creating a new feature. Helpers, Entity creation (by definition),
-

## ✨ **Current Features**

note: the following are tested with an Orcon WTW FAN

### **✅ Humidity Control (Partially Implemented)**

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

**How it works:**

1. **Monitors** absolute humidity levels inside and outside
2. **Calculates** optimal ventilation strategy using temperature differentials
3. **Controls** fan speeds to either bring in drier air or prevent moisture ingress
4. **Provides** real-time status and manual override capabilities

### **✅ HVAC Fan Card (Partially Implemented)**

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

## 🏗️ **Architecture Overview**

Ramses Extras uses a **feature-centric architecture** built on a **framework foundation**:

```
custom_components/ramses_extras/
├── 🏛️ framework/           # Reusable foundation layer
├── 🎯 features/            # Feature implementations
├── 🌐 platforms/           # Home Assistant integration
├── 🎨 www/                 # Frontend assets and cards
└── 🌍 translations/        # Localization files
```

**Key Benefits:**

- **Modularity**: Each feature is self-contained
- **Extensibility**: Easy to add new features
- **Maintainability**: Clear separation of concerns
- **Testability**: Components can be tested independently

For detailed architecture information, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 📚 **Documentation**

- 📖 **[Architecture Guide](docs/ARCHITECTURE.md)**: Complete system architecture and design decisions
- 🛠️ **[Development Guide](README_DEV.md)**: Setup, contribution guidelines, and development workflow
- 🎯 **[Entity Naming Improvements](docs/entity_naming_improvements.md)**: Technical solution documentation
- 🌐 **[JavaScript Integration](docs/JS_MESSAGE_LISTENER.md)**: Frontend implementation guide

## 🔧 **Requirements**

- **Home Assistant**: 2025.10.4 or later
- **Ramses RF** (ramses_cc): v0.52.1 (pre-release) or later: https://github.com/ramses-rf/ramses_cc
- **Python**: 3.13

## 🧪 **Development & Testing**

### **Development Setup**

```bash
# Clone the repository
git clone https://github.com/wimpie70/ramses_extras.git
cd ramses_extras

# Create the virtual environment
python3.13 -m venv venvs/extras

# Activate virtual environment
source ~/venvs/extras/bin/activate

# Install development dependencies
pip install -r requirements_dev.txt

# Install pre-commit hooks
pre-commit install
```

### **Running Tests**

```bash
# All Python tests
pytest -v

# Specific test file
pytest tests/managers/test_humidity_automation.py -v

# With coverage
pytest --cov=custom_components/ramses_extras

# Quality checks
make local-ci
```

### **Code Quality**

The code is all tested with the following tools:

#### **Python Quality Tools**

- **Ruff**: Fast linting and formatting (replaces Black + Flake8 + more)
- **MyPy**: Static type checking for Python code
- **Pytest**: Unit and integration testing with async support
- **Pre-commit**: Automated quality checks before commits

#### **Frontend Quality Tools**

- **ESLint**: JavaScript code quality and style enforcement
- **Prettier**: Code formatting for consistent style
- **Jest**: JavaScript unit and integration testing
- **JSDOM**: DOM simulation for component testing

All tools are configured to work together following industry best practices. See [`tests/frontend/README.md`](tests/frontend/README.md) for frontend testing details.

### **Architecture Development**

The project follows specific patterns for adding new features:

1. **Create Feature Structure**: Follow established patterns in `features/`
2. **Implement Components**: Automation, services, entities, platforms, websockets
3. **Add Templates**: Frontend templates for UI components
4. **Write Tests**: Comprehensive test coverage
5. **Update Documentation**: Keep architecture docs current

For detailed development guidelines, see [`docs/ARCHITECTURE.md#adding-new-features`](docs/ARCHITECTURE.md#adding-new-features).

## 🤝 **Contributing**

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### **Getting Started**

- 📖 Read the [Architecture Guide](docs/ARCHITECTURE.md)
- 🛠️ Follow the [Development Guide](README_DEV.md)
- 🧪 Write tests for new features
- 📝 Update documentation

### **Contribution Areas**

- 🧠 **New Automation Features**: Smart control algorithms
- 🎨 **UI/UX Improvements**: Better Lovelace cards
- 🧪 **Test Coverage**: More comprehensive testing
- 📚 **Documentation**: Guides and examples
- 🐛 **Bug Fixes**: Issue resolution
- ⭐ **Feature Requests**: New functionality ideas

## 📜 **License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- **Ramses RF Community**: For the excellent RF library
- **Ramses CC**: For the Home Assistant integration foundation
- **Home Assistant**: For the fantastic automation platform
- **Contributors**: Everyone who has contributed to this project

## 🆘 **Support & Issues**

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/wimpie70/ramses_extras/issues)
- 💬 **Feature Requests**: [GitHub Discussions](https://github.com/wimpie70/ramses_extras/discussions)
- 📚 **Documentation Issues**: Report via GitHub Issues

---
