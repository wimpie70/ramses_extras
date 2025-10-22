# Ramses Extras Development Environment

This directory contains the development environment for the Ramses Extras Home Assistant custom component.

## Setup

1. **Create and activate virtual environment:**
   ```bash
   cd ~/venvs
   python3.13 -m venv extras
   source extras/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   cd /home/willem/dev/ramses_extras
   ./activate_dev.sh
   ```

3. **Or install manually:**
   ```bash
   source ~/venvs/extras/bin/activate
   pip install -r requirements.txt
   pip install -e .
   ```

## Development Tools

### Testing
```bash
pytest                    # Run all tests
pytest tests/helpers/    # Run helper tests only
pytest -v                # Verbose output
pytest --cov             # Coverage report
```

### Code Quality
```bash
mypy .                   # Type checking
black .                  # Code formatting
isort .                  # Import sorting
flake8 .                 # Linting
pre-commit run --all     # Run all pre-commit hooks
```

### Pre-commit Hooks
Install pre-commit hooks to automatically run code quality checks:
```bash
pre-commit install
```

## Project Structure

```
ramses_extras/
├── custom_components/
│   └── ramses_extras/
│       ├── __init__.py          # Integration setup
│       ├── config_flow.py       # Configuration flow
│       ├── const.py             # Constants and configs
│       ├── helpers/
│       │   └── platform.py      # Common helper functions
│       └── platforms/           # Platform modules (future)
│           ├── sensor.py
│           ├── switch.py
│           └── binary_sensor.py
├── tests/
│   ├── helpers/
│   │   └── test_platform.py     # Helper function tests
│   └── platforms/               # Platform tests (future)
├── requirements.txt             # Python dependencies
├── pyproject.toml              # Project configuration
├── setup.py                    # Package setup
├── pytest.ini                 # Pytest configuration
└── .pre-commit-config.yaml     # Pre-commit hooks
```

## Configuration Files

- **`pyproject.toml`**: Project metadata and tool configurations
- **`requirements.txt`**: Python dependencies for installation
- **`setup.py`**: Package setup for development installation
- **`pytest.ini`**: Pytest configuration and markers
- **`.pre-commit-config.yaml`**: Pre-commit hook configurations

## Virtual Environment

The virtual environment is located at `~/venvs/extras/` and includes:
- Python 3.13
- Home Assistant 2025.10.1 (matches your Docker setup)
- Type hints and development tools (compatible with HA 2025.10.1)
- typing-extensions>=4.15.0

## Running Tests

Tests are organized by component:
- `tests/helpers/` - Tests for helper functions
- `tests/platforms/` - Tests for platform modules (future)

## Makefile Commands

The project includes a comprehensive Makefile for easy development workflow:

### **🚀 Quick Setup:**
```bash
make env          # Set up virtual environment with all dependencies
make env-test     # Set up environment and run tests
make env-full     # Set up environment and run full QA suite
```

### **📦 Integration Management:**
```bash
make install      # Install integration to HA config
make clean        # Remove integration from HA config
make restart-ha   # Restart Home Assistant container
make status       # Check HA container status
```

### **🧪 Development Workflow:**
```bash
make help         # Show all available targets
make dev-install  # Install dependencies and integration
make full-setup   # Complete setup with HA restart
```

### **🔍 Testing & Quality:**
```bash
make check-ha     # Verify HA is running and accessible
make env-test     # Run tests in development environment
make env-full     # Run full QA (mypy, black, isort, flake8, pytest)
make lint         # Run all code quality checks (includes mypy)
make type-check   # Run mypy type checking only
make type-check-clean - Run mypy without package conflicts (uninstall/reinstall)
make format       # Format code with black and isort
make fix-imports  # Fix import sorting with isort
make qa           # Run full QA suite
```

**Note:** Mypy is configured like ramses_cc to only check source files (`custom_components` and `tests`), avoiding conflicts with the installed package.

The project uses multiple tools for code quality:
- **Black**: Code formatting
- **isort**: Import sorting
- **Flake8**: Linting and style checking
- **MyPy**: Static type checking
- **Pre-commit**: Automated quality checks

All tools are configured to work together and follow Python best practices.
