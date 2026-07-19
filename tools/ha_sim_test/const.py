"""Shared constants for ha_sim_test recipes and infrastructure."""

from __future__ import annotations

# HA sim instance
HA_URL = "http://localhost:8124"
HA_USER = "admin"
HA_PASS = "admin123"

# Sim device IDs (from system_config.py)
HGI = "18:001234"
CTL = "01:150000"
TRV = "04:150003"  # zone 03 actuator
DHW = "07:150000"
FAN = "32:150000"
CO2 = "37:120000"
REM = "37:170000"
