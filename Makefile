# Makefile for Ramses Extras integration installation

# Home Assistant configuration directory (adjust if needed)
HA_CONFIG_DIR ?= /home/willem/docker_files/hass/config

# Simulator HA configuration directory
HA_SIM_CONFIG ?= /home/willem/docker_files/ha-sim/config

# Docker container name (adjust if needed)
HA_CONTAINER ?= homeassistant

# Source directory
SOURCE_DIR ?= .

# Known targets - catch typos like "make install ha-sim" (should be "make install-sim")
KNOWN_TARGETS := help install install-sim install-deps restart-ha clean status check-ha \
	dev-install full-setup env env-test env-full lint type-check type-check-clean \
	format fix-imports qa ruff-version ruff-install local-ci test-python test-frontend \
	test-all build-device-db source

UNKNOWN_TARGETS := $(filter-out $(KNOWN_TARGETS),$(MAKECMDGOALS))
ifneq ($(UNKNOWN_TARGETS),)
$(error Unknown target(s): $(UNKNOWN_TARGETS). Did you mean: install-sim, restart-ha? Run 'make help' for available targets)
endif

.PHONY: help install install-sim install-deps restart-ha clean status check-ha dev-install full-setup env env-test env-full lint type-check type-check-clean format fix-imports qa

help:
	@echo "Available targets:"
	@echo "  install      - Install the ramses_extras integration to HA config"
	@echo "  install-sim  - Install integration to simulator HA (ha-sim on port 8124)"
	@echo "  install-deps - Install Python dependencies (if any)"
	@echo "  restart-ha   - Restart Home Assistant container"
	@echo "  clean        - Remove integration from HA config"
	@echo "  status       - Check HA container status"
	@echo "  check-ha     - Check if HA is running and accessible"
	@echo ""
	@echo "Development targets:"
	@echo "  env          - Set up Python virtual environment with dependencies"
	@echo "  env-test     - Set up environment and run tests"
	@echo "  env-full     - Set up environment and run full QA suite (mypy, black, isort, flake8, pytest)"
	@echo "  source       - Activate the virtual environment"
	@echo "  lint         - Run all code quality checks (mypy, black, isort, flake8)"
	@echo "  type-check   - Run mypy type checking only"
	@echo "  type-check-clean - Run mypy without package conflicts (uninstall/reinstall)"
	@echo "  format       - Format code with black and isort"
	@echo "  fix-imports  - Fix import sorting with isort"
	@echo "  qa           - Run full QA suite (same as env-full)"
	@echo "  dev-install  - Install dependencies and integration"
	@echo "  full-setup   - Full setup with HA restart"
	@echo ""
	@echo "Testing targets:"
	@echo "  local-ci     - Run full local CI pipeline (Python + JS tests)"
	@echo "  test-python  - Run Python tests only"
	@echo "  test-frontend- Run JavaScript tests only"
	@echo "  test-all     - Run all tests (Python + JavaScript)"

install:
	@echo "Installing ramses_extras integration to $(HA_CONFIG_DIR)..."
	@if [ ! -d "$(HA_CONFIG_DIR)" ]; then \
		echo "Error: HA config directory $(HA_CONFIG_DIR) not found!"; \
		exit 1; \
	fi
	@# Sync integration files (rsync --delete removes stale files safely)
	@sudo rsync -av --delete \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		$(SOURCE_DIR)/custom_components/ramses_extras/ \
		$(HA_CONFIG_DIR)/custom_components/ramses_extras/
	@echo "Integration installed successfully"
	@echo "Don't forget to restart Home Assistant to load the new integration"

install-sim:
	@echo "Installing ramses_extras integration to simulator HA..."
	@if [ ! -d "$(HA_SIM_CONFIG)" ]; then \
		echo "Error: Simulator HA config directory not found!"; \
		echo "Run: mkdir -p $(HA_SIM_CONFIG)"; \
		exit 1; \
	fi
	@mkdir -p $(HA_SIM_CONFIG)/custom_components/ramses_extras
	@# Sync integration files (rsync --delete removes stale files safely)
	@sudo rsync -av --delete \
		--exclude='.git' \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='.pytest_cache' \
		--exclude='tests' \
		--exclude='docs' \
		--exclude='scripts' \
		--exclude='wiki' \
		--exclude='makefile' \
		--exclude='.windsurf' \
		--exclude='.github' \
		custom_components/ramses_extras/ \
		$(HA_SIM_CONFIG)/custom_components/ramses_extras/
	@# Verify deployment has __init__.py
	@if [ ! -f "$(HA_SIM_CONFIG)/custom_components/ramses_extras/__init__.py" ]; then \
		echo "ERROR: Deployment failed - __init__.py missing!"; \
		exit 1; \
	fi
	@# Clear Python cache inside container to ensure fresh code is loaded
	@docker exec ha-sim sh -c "find /config/custom_components/ramses_extras -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; echo 'Cache cleared'" || true
	@echo "Integration installed to ha-sim successfully"
	@echo "Don't forget to restart ha-sim to load the integration"

install-deps:
	@echo "Checking for Python dependencies..."
	@if [ -f "$(SOURCE_DIR)/requirements.txt" ]; then \
		echo "Installing Python requirements..."; \
		pip install -r $(SOURCE_DIR)/requirements.txt; \
	else \
		echo "No requirements.txt found, skipping dependency installation"; \
	fi

restart-ha:
	@echo "Restarting Home Assistant container..."
	@docker restart $(HA_CONTAINER)
	@echo "✅ Home Assistant restarted"

clean:
	@echo "Removing ramses_extras integration from $(HA_CONFIG_DIR)..."
	@rm -rf $(HA_CONFIG_DIR)/custom_components/ramses_extras
	@echo "✅ Integration removed"

status:
	@echo "Checking Home Assistant container status..."
	@docker ps --filter name=$(HA_CONTAINER) --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

check-ha:
	@echo "Checking if Home Assistant is accessible..."
	@curl -s http://localhost:8123/api/ | head -5 || echo "❌ HA not accessible on localhost:8123"
	@echo "Checking HA logs for recent entries..."
	@docker logs --tail 5 $(HA_CONTAINER) 2>/dev/null || echo "❌ Cannot access HA logs"

# Development helpers
dev-install: install-deps install
	@echo "Development installation complete"

full-setup: install-deps install restart-ha
	@echo "Full setup complete - integration installed and HA restarted"

# Virtual environment setup
env:
	@echo "Setting up development environment..."
	@if [ ! -d "~/venvs/extras" ]; then \
		echo "Creating virtual environment..."; \
		python3.14 -m venv ~/venvs/extras; \
	fi
	@echo "Activating virtual environment and installing dependencies..."
	@bash -c "source ~/venvs/extras/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt && \
		pip install -e ."
	@echo "✅ Development environment setup complete!"
	@echo "🔧 To use: source ~/venvs/extras/bin/activate"

source:
	@bash -c "source ~/venvs/extras/bin/activate"

# Development environment with testing
env-test: env
	@echo "Running tests in development environment..."
	@bash -c "source ~/venvs/extras/bin/activate && pytest tests/"
	@echo "✅ Tests completed"

# Development tools
lint: env
	@echo "Running code quality checks..."
	@bash -c "source ~/venvs/extras/bin/activate && \
		mypy custom_components/ tests/ && \
		ruff check . && \
		ruff format --check ."

local-ci: env
	@echo "Running local CI pipeline..."
	@./scripts/local-ci.sh

# Device Simulator build targets
build-device-db: env
	@echo "Building device database from ramses_rf regression packets..."
	@bash -c "source ~/venvs/extras/bin/activate && python custom_components/ramses_extras/features/device_simulator/scripts/build_device_db.py"
	@echo "✅ Device database build complete"

test-frontend: env
	@echo "Running frontend tests..."
	@bash -c "source ~/venvs/extras/bin/activate && npm test --prefix config"

test-python: env
	@echo "Running Python tests..."
	@bash -c "source ~/venvs/extras/bin/activate && pytest tests/ -v"

test-all: test-python test-frontend
	@echo "Running all tests..."

type-check: env
	@echo "Running type checking..."
	@bash -c "source ~/venvs/extras/bin/activate && mypy custom_components/ tests/"

type-check-clean: env
	@echo "Running type checking (without package conflicts)..."
	@./scripts/mypy_clean.sh

format: env
	@echo "Formatting code..."
	@bash -c "source ~/venvs/extras/bin/activate && ruff format . && ruff check . --fix"

fix-imports: env
	@echo "Fixing imports and formatting..."
	@bash -c "source ~/venvs/extras/bin/activate && ruff check . --fix && ruff format ."

ruff-version:
	@echo "Ruff version check..."
	@bash -c "source ~/venvs/extras/bin/activate && ruff --version"

ruff-install:
	@echo "Installing/updating ruff to 0.14.4..."
	@bash -c "source ~/venvs/extras/bin/activate && pip install --upgrade 'ruff==0.14.4'"
	@echo "✅ Ruff updated to 0.14.4"

qa: env
	@echo "Running full QA suite..."
	@bash -c "source ~/venvs/extras/bin/activate && \
		mypy custom_components/ tests/ && \
		ruff check . && \
		ruff format --check . && \
		pytest tests/"
