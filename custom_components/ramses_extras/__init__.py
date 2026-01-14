"""Integration to provide additional entities and automations for Ramses RF/Hive
systems."""

from __future__ import annotations

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .framework.setup.entry import (
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from .framework.setup.yaml import async_setup, async_setup_yaml_config

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
