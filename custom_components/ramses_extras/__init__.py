"""Ramses Extras - Advanced Home Assistant integration for Ramses RF systems.

This integration extends the base ramses_cc integration with additional entities,
automations, Lovelace cards, and enhanced functionality for Ramses RF systems.

Key Features:
- Feature-centric architecture with modular functionality
- Advanced automations for humidity, temperature, and system control
- Custom Lovelace cards for enhanced UI
- Device-specific brand customizations
- WebSocket integration for real-time updates
- Primary config flow setup with optional YAML-to-config-flow bridge

Architecture:
The integration uses a feature-centric framework where functionality is organized
into independent features that can be enabled/disabled per device. Each feature
provides its own entities, automations, and UI components.

Setup Process:
1. async_setup: Optional YAML-to-config-flow bridge (secondary method)
2. async_setup_entry: Primary config flow setup (main entry point)
3. Framework initialization: Sets up devices, platforms, and features
4. Feature loading: Dynamically loads enabled features
5. Card deployment: Sets up Lovelace cards and frontend resources
6. Service registration: Registers integration services

Integration Lifecycle:
- Setup: Discovers devices, loads features, sets up platforms
- Runtime: Manages automations, handles updates, provides services
- Unload: Cleans up resources, removes entities, stops automations
- Remove: Complete cleanup of all integration data

Configuration Priority:
Once a config flow entry is created and modified via the UI, config flow settings
take precedence over initial YAML configuration. YAML is only used to create the
initial config entry; subsequent changes through config flow become the source
of truth.

"""

from __future__ import annotations

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .framework.setup.entry import (
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from .framework.setup.yaml import async_setup, async_setup_yaml_config

"""Configuration schema for Ramses Extras integration.

Defines that this integration requires config flow configuration as the primary
setup method. YAML configuration is supported only as a bridge to create
config flow entries.

:return: Home Assistant configuration schema
:rtype: homeassistant.helpers.config_validation.ConfigSchema
"""
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
