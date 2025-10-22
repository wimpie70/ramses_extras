# Makefile for Ramses Extras integration installation

# Home Assistant configuration directory (adjust if needed)
HA_CONFIG_DIR ?= /home/willem/docker_files/hass/config

# Docker container name (adjust if needed)
HA_CONTAINER ?= homeassistant

# Source directory
SOURCE_DIR ?= .

.PHONY: help install install-deps restart-ha clean status check-ha dev-install full-setup env env-test env-full lint type-check type-check-clean format fix-imports qa

help:
	@echo "Available targets:"
	@echo "  install      - Install the ramses_extras integration to HA config"
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
	@echo "  lint         - Run all code quality checks (mypy, black, isort, flake8)"
	@echo "  type-check   - Run mypy type checking only"
	@echo "  type-check-clean - Run mypy without package conflicts (uninstall/reinstall)"
	@echo "  format       - Format code with black and isort"
	@echo "  fix-imports  - Fix import sorting with isort"
	@echo "  qa           - Run full QA suite (same as env-full)"
	@echo "  dev-install  - Install dependencies and integration"
	@echo "  full-setup   - Full setup with HA restart"

install:
	@echo "Installing ramses_extras integration to $(HA_CONFIG_DIR)..."
	@if [ ! -d "$(HA_CONFIG_DIR)" ]; then \
		echo "Error: HA config directory $(HA_CONFIG_DIR) not found!"; \
		exit 1; \
	fi
	@# Remove existing integration (excluding __pycache__ to avoid permission issues)
	@find $(HA_CONFIG_DIR)/custom_components/ramses_extras -type f -name "*.py" -delete 2>/dev/null || true
	@find $(HA_CONFIG_DIR)/custom_components/ramses_extras -type d -empty -delete 2>/dev/null || true
	@# Copy without __pycache__ directories
	@rsync -av --exclude='__pycache__' $(SOURCE_DIR)/custom_components $(HA_CONFIG_DIR)/
	@echo "✅ Integration installed successfully"
	@echo "💡 Don't forget to restart Home Assistant to load the new integration"

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
		python3.13 -m venv ~/venvs/extras; \
	fi
	@echo "Activating virtual environment and installing dependencies..."
	@source ~/venvs/extras/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt && \
		pip install -e .
	@echo "✅ Development environment setup complete!"
	@echo "🔧 To use: source ~/venvs/extras/bin/activate"

# Development environment with testing
env-test: env
	@echo "Running tests in development environment..."
	@source ~/venvs/extras/bin/activate && pytest tests/
	@echo "✅ Tests completed"

# Development tools
lint: env
	@echo "Running code quality checks..."
	@source ~/venvs/extras/bin/activate && \
		mypy . && \
		black --check . && \
		isort --check-only . && \
		flake8 .

type-check: env
	@echo "Running type checking..."
	@source ~/venvs/extras/bin/activate && mypy .

type-check-clean: env
	@echo "Running type checking (without package conflicts)..."
	@./mypy_clean.sh

format: env
	@echo "Formatting code..."
	@source ~/venvs/extras/bin/activate && black . && isort .

fix-imports: env
	@echo "Fixing import sorting..."
	@source ~/venvs/extras/bin/activate && isort .

qa: env
	@echo "Running full QA suite..."
	@source ~/venvs/extras/bin/activate && \
		mypy . && \
		black --check . && \
		isort --check-only . && \
		flake8 . && \
		pytest tests/
