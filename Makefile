# Makefile for Ramses Extras integration installation

# Home Assistant configuration directory (adjust if needed)
HA_CONFIG_DIR ?= /home/willem/docker_files/hass/config

# Docker container name (adjust if needed)
HA_CONTAINER ?= homeassistant

# Source directory
SOURCE_DIR ?= .

.PHONY: help install install-deps restart-ha clean status check-ha

help:
	@echo "Available targets:"
	@echo "  install      - Install the ramses_extras integration to HA config"
	@echo "  install-deps - Install Python dependencies (if any)"
	@echo "  restart-ha   - Restart Home Assistant container"
	@echo "  clean        - Remove integration from HA config"
	@echo "  status       - Check HA container status"
	@echo "  check-ha     - Check if HA is running and accessible"

install:
	@echo "Installing ramses_extras integration to $(HA_CONFIG_DIR)..."
	@if [ ! -d "$(HA_CONFIG_DIR)" ]; then \
		echo "Error: HA config directory $(HA_CONFIG_DIR) not found!"; \
		exit 1; \
	fi
	@cp -r $(SOURCE_DIR)/custom_components $(HA_CONFIG_DIR)/
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
