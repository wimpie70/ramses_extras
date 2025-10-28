# Ramses Extras

[![CI](https://github.com/willem/ramses_extras/actions/workflows/ci.yml/badge.svg)](https://github.com/willem/ramses_extras/actions/workflows/ci.yml)
[![Quality](https://github.com/willem/ramses_extras/actions/workflows/quality.yml/badge.svg)](https://github.com/willem/ramses_extras/actions/workflows/quality.yml)
[![Tests](https://github.com/willem/ramses_extras/actions/workflows/test.yml/badge.svg)](https://github.com/willem/ramses_extras/actions/workflows/test.yml)
[![Integration](https://github.com/willem/ramses_extras/actions/workflows/integration.yml/badge.svg)](https://github.com/willem/ramses_extras/actions/workflows/integration.yml)
[![codecov](https://codecov.io/gh/willem/ramses_extras/branch/main/graph/badge.svg)](https://codecov.io/gh/willem/ramses_extras)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![Home Assistant 2025.10.4](https://img.shields.io/badge/home%20assistant-2025.10.4-green.svg)](https://home-assistant.io)

Extra features and enhancements for the Ramses CC Home Assistant integration.

## Features (WIP)

- hvac_fan_card
- currently testing...

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Search for "Ramses Extras" and install
3. Restart Home Assistant
4. Configure through Settings → Devices & Services → Ramses Extras

### Manual Installation

1. Copy the `custom_components/ramses_extras` directory to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant
3. Configure through Settings → Devices & Services

## Configuration

After installation, configure the integration through the Home Assistant UI:

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Ramses Extras"
4. Select which features to enable

## Requirements

- Home Assistant 2025.10.4 or later
- Ramses CC integration v0.52.1 (pre-release) or later: https://github.com/zxdavb/ramses_cc
- Ramses RF library v0.52.2 or later: https://github.com/ramses-rf/ramses_rf
- Python 3.13

## Development

For development setup and contribution guidelines, see [README_DEV.md](README_DEV.md).

### Code Quality

This project uses comprehensive testing and quality tools:

#### Python Testing
- **Ruff**: Linting and formatting (replaces Black + Flake8)
- **MyPy**: Static type checking
- **Pytest**: Unit and integration testing
- **Pre-commit**: Automated quality checks

#### Frontend Testing
- **ESLint**: JavaScript code quality and style
- **Stylelint**: CSS validation and best practices
- **Jest**: JavaScript unit and integration testing
- **JSDOM**: DOM simulation for testing

All tools are configured to work together and follow best practices. See [tests/frontend/README.md](tests/frontend/README.md) for frontend testing details.

## Running Tests

```bash
# Python tests
pytest tests/

# Frontend tests
npm test

# All quality checks
pre-commit run --all-files
```
