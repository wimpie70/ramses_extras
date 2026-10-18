# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Constants for the Floorplan Helper feature.

This feature produces a managed bundle for the community `ha-floorplan`
card (https://github.com/ExperienceLovelace/ha-floorplan): a generated
elements SVG, a shared stylesheet, and rules YAML that map RAMSES
entities onto SVG elements. The entity/element/icon mapping is stored
in the integration's config entry options so edits happen inside
ramses_extras and the bundle is regenerated — floorplan YAML is never
hand-maintained.

The feature is global — it reads ramses_cc/ramses_extras entities and
creates no entities of its own besides optional derived binary sensors.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from typing import Any

DOMAIN = "floorplan_helper"

# Feature identification
FEATURE_ID = "floorplan_helper"

FEATURE_NAME = "Floorplan Helper"
FEATURE_DESCRIPTION = (
    "Generate a managed ha-floorplan bundle (icons, CSS, rules YAML) "
    "from the discovered RAMSES system"
)

# ---------------------------------------------------------------------------
# Deployed/generated paths (relative to <config>/www/ramses_extras/floorplan)
# ---------------------------------------------------------------------------

# Shipped static assets live under the feature www dir and are deployed by
# the standard card pipeline to /local/ramses_extras/features/floorplan_helper/
FLOORPLAN_STATIC_BASE = "/local/ramses_extras/features/floorplan_helper"
FLOORPLAN_GENERATED_BASE = "/local/ramses_extras/floorplan/generated"
FLOORPLAN_GENERATED_DIR_NAME = "floorplan/generated"

GENERATED_ELEMENTS_SVG = "ramses-elements.svg"
GENERATED_CARD_YAML = "ramses-floorplan-card.yaml"
STYLESHEET_FILENAME = "ramses-floorplan.css"

# Markers wrapping generated rules inside the card YAML.  Users keep their
# own rules outside these markers; only the marked block is regenerated.
RULES_BEGIN_MARKER = "# >>> ramses_extras managed rules >>>"
RULES_END_MARKER = "# <<< ramses_extras managed rules <<<"

# ---------------------------------------------------------------------------
# Options section keys (stored under options.ramses_extras.features.floorplan_helper)
# ---------------------------------------------------------------------------

OPTION_SVG_MODE = "svg_mode"
OPTION_CUSTOM_SVG_PATH = "custom_svg_path"
OPTION_ICON_OVERRIDES = "icon_overrides"
OPTION_ELEMENT_BINDINGS = "element_bindings"
OPTION_AREA_OVERRIDES = "area_overrides"
OPTION_EXTRA_RULES = "extra_rules"
OPTION_LAST_SNAPSHOT = "last_snapshot"

SVG_MODE_GENERATED = "generated"
SVG_MODE_CUSTOM = "custom"

DEFAULT_FLOORPLAN_OPTIONS: dict[str, Any] = {
    OPTION_SVG_MODE: SVG_MODE_GENERATED,
    OPTION_CUSTOM_SVG_PATH: "",
    OPTION_ICON_OVERRIDES: {},
    OPTION_ELEMENT_BINDINGS: {},
    OPTION_AREA_OVERRIDES: {},
    OPTION_EXTRA_RULES: [],
}

# ---------------------------------------------------------------------------
# Icons — shipped in www/floorplan_helper/icons/<name>.svg
# ---------------------------------------------------------------------------

# Canonical icon keys shipped with the feature. Values are the SVG filenames
# (without extension) under www/floorplan_helper/icons/.
FLOORPLAN_ICONS: tuple[str, ...] = (
    "fan",
    "radiator",
    "valve",
    "water-boiler",
    "thermostat",
    "thermometer",
    "remote",
    "gateway",
    "fire",
    "window-open",
    "battery",
    "co2",
    "gauge",
    "pipe-valve",
    "help",
)

# Default icon per ramses device class (device._SLUG). Per-entity and
# per-class overrides in options take precedence.
FLOORPLAN_DEVICE_ICON_MAP: dict[str, str] = {
    "FAN": "fan",
    "HVAC": "fan",
    "TRV": "radiator",
    "CTL": "thermostat",
    "OTB": "water-boiler",
    "DHW": "water-boiler",
    "REM": "remote",
    "RND": "remote",
    "HGI": "gateway",
    "BDR": "pipe-valve",
    "UFC": "pipe-valve",
    "CO2": "co2",
    "THM": "thermometer",
    "SEN": "thermometer",
    "SWI": "remote",
}

DEFAULT_ICON = "help"

# Entity-role classification used by the generator to decide which entities
# get rules on an element. Ordered — first match wins for "primary".
ENTITY_ROLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "status": ("_status",),
    "heat_demand": ("heat_demand",),
    "window_open": ("window_open",),
    "battery": ("battery",),
    "fan_rate": ("fan_rate", "fan_speed", "fan_mode"),
    "co2": ("co2_level", "co2_control"),
    "temperature": ("temperature", "indoor_temp", "outdoor_temp", "_temp"),
    "humidity": ("humidity",),
    "setpoint": ("setpoint",),
}

# CSS classes emitted by ramses-floorplan.css that rules reference.
CSS_CLASSES: dict[str, str] = {
    "online": "rx-online",
    "offline": "rx-offline",
    "heat_demand": "rx-heat-demand",
    "window_open": "rx-window-open",
    "fan_spin": "rx-spin",
    "valve_open": "rx-valve-open",
}

# The feature creates no per-device entities of its own besides the derived
# binary sensors declared in platforms/ — and those are registry-driven
# (one binary_sensor per discovered sensor.*_heat_demand), not config-driven.
FLOORPLAN_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}
FLOORPLAN_SWITCH_CONFIGS: dict[str, dict[str, Any]] = {}
FLOORPLAN_NUMBER_CONFIGS: dict[str, dict[str, Any]] = {}
FLOORPLAN_BINARY_SENSOR_CONFIGS: dict[str, dict[str, Any]] = {}

# WebSocket commands
FLOORPLAN_WEBSOCKET_COMMANDS: dict[str, str] = {
    "get_bundle": "ramses_extras/floorplan_helper/get_bundle",
    "get_topology": "ramses_extras/floorplan_helper/get_topology",
    "list_icons": "ramses_extras/floorplan_helper/list_icons",
}

# Global feature — works across all device types.
FLOORPLAN_DEVICE_ENTITY_MAPPING: dict[str, dict[str, list[str]]] = {}

FEATURE_DEFINITION: dict[str, Any] = {
    "feature_id": FEATURE_ID,
    "sensor_configs": FLOORPLAN_SENSOR_CONFIGS,
    "switch_configs": FLOORPLAN_SWITCH_CONFIGS,
    "number_configs": FLOORPLAN_NUMBER_CONFIGS,
    "boolean_configs": FLOORPLAN_BINARY_SENSOR_CONFIGS,
    "device_entity_mapping": FLOORPLAN_DEVICE_ENTITY_MAPPING,
    "websocket_commands": FLOORPLAN_WEBSOCKET_COMMANDS,
    "card_configs": [],
    "required_entities": {},
    "entity_mappings": {},
}


def load_feature() -> None:
    """Load floorplan_helper feature into the registry."""
    from custom_components.ramses_extras.extras_registry import extras_registry

    extras_registry.register_device_mappings(FLOORPLAN_DEVICE_ENTITY_MAPPING)

    extras_registry.register_websocket_commands(
        FEATURE_ID, FLOORPLAN_WEBSOCKET_COMMANDS
    )

    extras_registry.register_feature(FEATURE_ID)


__all__ = [
    "CSS_CLASSES",
    "DEFAULT_FLOORPLAN_OPTIONS",
    "DEFAULT_ICON",
    "DOMAIN",
    "ENTITY_ROLE_PATTERNS",
    "FEATURE_DEFINITION",
    "FEATURE_ID",
    "FLOORPLAN_BINARY_SENSOR_CONFIGS",
    "FLOORPLAN_DEVICE_ENTITY_MAPPING",
    "FLOORPLAN_DEVICE_ICON_MAP",
    "FLOORPLAN_GENERATED_BASE",
    "FLOORPLAN_GENERATED_DIR_NAME",
    "FLOORPLAN_ICONS",
    "FLOORPLAN_NUMBER_CONFIGS",
    "FLOORPLAN_SENSOR_CONFIGS",
    "FLOORPLAN_STATIC_BASE",
    "FLOORPLAN_SWITCH_CONFIGS",
    "FLOORPLAN_WEBSOCKET_COMMANDS",
    "GENERATED_CARD_YAML",
    "GENERATED_ELEMENTS_SVG",
    "OPTION_AREA_OVERRIDES",
    "OPTION_CUSTOM_SVG_PATH",
    "OPTION_ELEMENT_BINDINGS",
    "OPTION_EXTRA_RULES",
    "OPTION_ICON_OVERRIDES",
    "OPTION_LAST_SNAPSHOT",
    "OPTION_SVG_MODE",
    "RULES_BEGIN_MARKER",
    "RULES_END_MARKER",
    "STYLESHEET_FILENAME",
    "SVG_MODE_CUSTOM",
    "SVG_MODE_GENERATED",
    "load_feature",
]
