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
   ./scripts/activate_dev.sh
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
ruff check .             # Linting (replaces flake8)
ruff format .            # Code formatting (replaces black)
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
├── config/                     # Configuration files
│   ├── mypy.ini               # MyPy type checking
│   ├── package.json           # Node.js dependencies
│   ├── .eslintrc.json         # ESLint configuration
│   └── .pre-commit-config.yaml # Pre-commit hooks
└── pytest.ini                 # Pytest configuration
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
- Home Assistant 2025.10.4 (matches your Docker setup)
- Ramses RF library v0.52.2
- Ramses CC integration v0.52.1 (pre-release)
- Type hints and development tools (compatible with HA 2025.10.4)

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
make env-full     # Run full QA (mypy, ruff, pytest)
make lint         # Run all code quality checks (includes mypy)
make type-check   # Run mypy type checking only
make type-check-clean - Run mypy without package conflicts (uninstall/reinstall)
make format       # Format code with ruff
make fix-imports  # Fix formatting and linting with ruff
make qa           # Run full QA suite
```

**Note:** Mypy is configured like ramses_cc to only check source files (`custom_components` and `tests`), avoiding conflicts with the installed package.

The project uses multiple tools for code quality:

- **Ruff**: Linting and code formatting (replaces Black + Flake8 + isort)
- **MyPy**: Static type checking
- **Pre-commit**: Automated quality checks

## CI/CD and Contribution Guidelines

### Continuous Integration

This project uses GitHub Actions for automated testing and quality checks:

#### **🚀 Workflows:**

- **`ci.yml`**: Main CI pipeline (tests, coverage, ruff, mypy)
- **`test.yml`**: Multi-Python version testing with Home Assistant integration
- **`quality.yml`**: Code quality checks (pre-commit, ruff, mypy)
- **`integration.yml`**: Home Assistant integration validation
- **`dependency-review.yml`**: Security vulnerability scanning
- **`pr-validation.yml`**: Pull request validation and automated testing

#### **📋 Branch Protection Rules**

To maintain code quality, the following rules are enforced:

- ✅ **Pull requests required** for merging to main/develop branches
- ✅ **Status checks must pass** before merging
- ✅ **Code review required** from maintainers
- ✅ **Branch up-to-date** requirement

### Contributing

1. **Fork the repository** and create a feature branch
2. **Make your changes** following the coding standards
3. **Run tests locally**:
   ```bash
   make env-test  # Set up environment and run tests
   make qa        # Run full quality assurance suite
   ```
4. **Create a pull request** with a descriptive title and description
5. **Ensure CI passes** - all status checks must be green
6. **Request review** from maintainers

#### **Pull Request Requirements:**

- 📝 **Descriptive title** using conventional commits format
- 📖 **Detailed description** of changes and rationale
- ✅ **Tests included** for new functionality
- ✅ **Documentation updated** if needed
- ✅ **CI/CD passes** all quality checks

#### **Conventional Commit Format:**

```
type(scope)!: description

Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert
Examples:
- feat: add humidity sensor support
- fix: resolve mypy type errors
- docs: update installation guide
- test: add integration tests
```

### Automated Testing

#### **🧪 Test Coverage:**

- **Unit tests** for all helper functions and components
- **Integration tests** with Home Assistant container
- **Type checking** with mypy (strict mode)
- **Code formatting** with black and isort
- **Linting** with flake8

#### **🔒 Security:**

- **Dependabot** automatically updates dependencies
- **Dependency review** scans for vulnerabilities
- **Safety checks** in CI pipeline

### Quality Gates

All pull requests must pass these quality gates:

1. ✅ **Unit tests** (pytest)
2. ✅ **Type checking** (mypy)
3. ✅ **Code formatting** (ruff format)
4. ✅ **Linting** (ruff check)
5. ✅ **Pre-commit hooks** (all)
6. ✅ **Security scan** (dependency review)
7. ✅ **Integration tests** (Home Assistant compatibility)

### Development Workflow

```bash
# 1. Create feature branch
git checkout -b feature/new-sensor

# 2. Make changes and run tests locally
make env-test    # Environment + tests
make qa          # Full QA suite

# 3. Commit with conventional format
git commit -m "feat: add new sensor support"

# 4. Push and create PR
git push origin feature/new-sensor

# 5. Monitor CI results in GitHub
# 6. Address any failing checks
# 7. Request review from maintainers
```

**Note:** The CI system will automatically run all tests and quality checks. Only PRs with passing checks can be merged.
