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
# Which rooms a device serves (e.g. rooms a WTW ventilates).  Selecting
# the device's marker in studio highlights these rooms; double-click
# opens the device card.  Maps ramses device id → {"areas": [area_id],
# "color": "#hex"}.
OPTION_DEVICE_ZONES = "device_zones"
# Optional dashboard/view path for a zoned device's double-tap — when set,
# the rule navigates there instead of firing the ll-custom popup event
# (which needs the ramses-floorplan-actions card on the same view).
OPTION_DEVICE_VIEW_URL = "device_view_url"
OPTION_TOOLBAR_ENABLED = "toolbar_enabled"
OPTION_EDITOR_URL = "editor_url"
OPTION_PLANNER_URL = "planner_url"

SVG_MODE_GENERATED = "generated"
SVG_MODE_CUSTOM = "custom"

# External helper tools (client-side only — no HA auth/API). Point these at
# vendored copies under /local/... or an iframe panel path to keep the
# round-trip inside HA. Internal paths (leading '/') emit a `navigate`
# tap_action; anything else emits `url` (new tab).
DEFAULT_EDITOR_URL = "https://qaddodi.github.io/ha-floorplan-editor/"
DEFAULT_PLANNER_URL = "https://sleien.github.io/HA-floorplanner-gui/"

# Element ids of the in-SVG toolbar glyphs. Users paste the toolbar <g>
# snippet into custom SVGs; generated SVGs include it automatically.
TOOLBAR_ELEMENT_EXPORT = "floorplan.export"
TOOLBAR_ELEMENT_IMPORT = "floorplan.import"
TOOLBAR_ELEMENT_UPLOAD = "floorplan.upload"
TOOLBAR_ELEMENT_EDITOR = "floorplan.editor"
TOOLBAR_ELEMENT_PLANNER = "floorplan.planner"

# Dir under <config>/www/ramses_extras/ where user SVGs are uploaded.
FLOORPLAN_UPLOAD_DIR_NAME = "floorplan"

DEFAULT_FLOORPLAN_OPTIONS: dict[str, Any] = {
    OPTION_SVG_MODE: SVG_MODE_GENERATED,
    OPTION_CUSTOM_SVG_PATH: "",
    OPTION_ICON_OVERRIDES: {},
    OPTION_ELEMENT_BINDINGS: {},
    OPTION_AREA_OVERRIDES: {},
    OPTION_EXTRA_RULES: [],
    OPTION_DEVICE_ZONES: {},
    OPTION_DEVICE_VIEW_URL: "",
    OPTION_TOOLBAR_ENABLED: True,
    OPTION_EDITOR_URL: DEFAULT_EDITOR_URL,
    OPTION_PLANNER_URL: DEFAULT_PLANNER_URL,
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
    "DIS": "thermostat",
    "HGI": "gateway",
    "BDR": "pipe-valve",
    "UFC": "pipe-valve",
    "CO2": "co2",
    "THM": "thermometer",
    "SEN": "thermometer",
    "SWI": "remote",
}

DEFAULT_ICON = "help"

# Our icon keys → mdi names for floorplan-studio markers (studio's icon
# style renders mdi names; our keys mostly match 1:1).
FLOORPLAN_ICON_MDI: dict[str, str] = {
    "fan": "fan",
    "radiator": "radiator",
    "valve": "valve",
    "water-boiler": "water-boiler",
    "thermostat": "thermostat",
    "thermometer": "thermometer",
    "remote": "remote",
    "gateway": "router-wireless",
    "fire": "fire",
    "window-open": "window-open-variant",
    "battery": "battery",
    "co2": "molecule-co2",
    "gauge": "gauge",
    "pipe-valve": "pipe-valve",
    "help": "help-circle",
}

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
    "get_config": "ramses_extras/floorplan_helper/get_config",
    "get_topology": "ramses_extras/floorplan_helper/get_topology",
    "list_icons": "ramses_extras/floorplan_helper/list_icons",
}

# Entities this feature creates outside the per-device config schema —
# declared so the startup entity janitor doesn't remove them as "extra":
# the global export button and the registry-derived heat-demand sensors.
FLOORPLAN_STANDALONE_ENTITIES: dict[str, list[str]] = {
    "button": ["floorplan_helper*"],
    "binary_sensor": ["*_heat_demand"],
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
    "standalone_entities": FLOORPLAN_STANDALONE_ENTITIES,
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
    "DEFAULT_EDITOR_URL",
    "DEFAULT_FLOORPLAN_OPTIONS",
    "DEFAULT_ICON",
    "DEFAULT_PLANNER_URL",
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
    "FLOORPLAN_ICON_MDI",
    "FLOORPLAN_NUMBER_CONFIGS",
    "FLOORPLAN_SENSOR_CONFIGS",
    "FLOORPLAN_STANDALONE_ENTITIES",
    "FLOORPLAN_STATIC_BASE",
    "FLOORPLAN_SWITCH_CONFIGS",
    "FLOORPLAN_UPLOAD_DIR_NAME",
    "FLOORPLAN_WEBSOCKET_COMMANDS",
    "GENERATED_CARD_YAML",
    "GENERATED_ELEMENTS_SVG",
    "OPTION_AREA_OVERRIDES",
    "OPTION_CUSTOM_SVG_PATH",
    "OPTION_DEVICE_VIEW_URL",
    "OPTION_DEVICE_ZONES",
    "OPTION_EDITOR_URL",
    "OPTION_ELEMENT_BINDINGS",
    "OPTION_EXTRA_RULES",
    "OPTION_ICON_OVERRIDES",
    "OPTION_LAST_SNAPSHOT",
    "OPTION_PLANNER_URL",
    "OPTION_SVG_MODE",
    "OPTION_TOOLBAR_ENABLED",
    "RULES_BEGIN_MARKER",
    "RULES_END_MARKER",
    "STYLESHEET_FILENAME",
    "SVG_MODE_CUSTOM",
    "SVG_MODE_GENERATED",
    "TOOLBAR_ELEMENT_EDITOR",
    "TOOLBAR_ELEMENT_EXPORT",
    "TOOLBAR_ELEMENT_IMPORT",
    "TOOLBAR_ELEMENT_PLANNER",
    "TOOLBAR_ELEMENT_UPLOAD",
    "load_feature",
]
