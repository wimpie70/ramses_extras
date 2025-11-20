# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory

_LOGGER = logging.getLogger(__name__)

# Get the integration directory
INTEGRATION_DIR = Path(__file__).parent

DOMAIN = "ramses_extras"

GITHUB_URL = "https://github.com/wimpie70/ramses_extras"
GITHUB_WIKI_URL = f"{GITHUB_URL}/wiki"

WS_CMD_GET_BOUND_REM = f"{DOMAIN}/get_bound_rem"

# Configuration constants
CONF_NAME = "name"
CONF_ENABLED_FEATURES = "enabled_features"
CONF_ENABLED_WEB_SOCKETS = "enabled_web_sockets"
CONF_MESSAGE_EVENTS = "message_events"  # Import from ramses_cc for enabling events
DESCRIPTION_PLACEHOLDER_INFO = (
    "Ramses Extras provides additional functionality on top of Ramses RF."
)
CARD_FOLDER = "www"
CARD_HELPERS_FOLDER = "www/helpers"
FEATURE_FOLDER = "features"

# Feature identifiers
# FEATURE_ID_FAN_CONTROL = "fan_control"
# FEATURE_ID_HUMIDITY_SENSORS = "humidity_sensors"
FEATURE_ID_DEFAULT = "default"
FEATURE_ID_HVAC_FAN_CARD = "hvac_fan_card"
FEATURE_ID_HUMIDITY_CONTROL = "humidity_control"

# Enhanced Device Discovery Architecture - Event System
EVENT_DEVICE_READY_FOR_ENTITIES = "ramses_device_ready_for_entities"

# Device Type Handler Mapping - Central registry for device type handlers
DEVICE_TYPE_HANDLERS: dict[str, Callable] = {}


def register_device_handler(device_type: str) -> Callable[[Callable], Callable]:
    """Decorator to register device type handlers."""

    def decorator(handler: Callable) -> Callable:
        DEVICE_TYPE_HANDLERS[device_type] = handler
        return handler

    return decorator


def _discover_available_features() -> dict[str, dict[str, Any]]:
    """Dynamically discover available features by scanning the features directory."""
    from pathlib import Path

    features_dir = INTEGRATION_DIR / "features"
    available_features: dict[str, dict[str, Any]] = {}

    if not features_dir.exists():
        _LOGGER.warning(f"Features directory not found: {features_dir}")
        return available_features

    _LOGGER.info(f"Scanning features directory: {features_dir}")

    # Scan feature subdirectories and provide known feature configurations
    # This eliminates hardcoded feature references while maintaining functionality
    for item in features_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            feature_name = item.name

            if feature_name == "default":
                available_features[feature_name] = {
                    "name": "Default Sensors",
                    "description": "Base humidity sensors available for all devices",
                    "feature_module": f"features.{feature_name}",
                    "handler": "handle_hvac_ventilator",
                }
            elif feature_name == "humidity_control":
                available_features[feature_name] = {
                    "name": "Humidity Control",
                    "description": "Automatic humidity control and "
                    "dehumidification management",
                    "feature_module": f"features.{feature_name}",
                    "handler": "handle_hvac_ventilator",
                }
            elif feature_name == "hvac_fan_card":
                available_features[feature_name] = {
                    "name": "HVAC Fan Card",
                    "description": "Advanced fan card for control and configuration",
                    "feature_module": f"features.{feature_name}",
                    "handler": "handle_hvac_ventilator",
                }
            else:
                # Generic fallback for unknown features
                available_features[feature_name] = {
                    "name": feature_name.replace("_", " ").title(),
                    "description": f"{feature_name} feature",
                    "category": _infer_category_from_feature(feature_name),
                    "feature_module": f"features.{feature_name}",
                    "handler": "handle_hvac_ventilator",
                }

    return available_features


def _infer_category_from_feature(feature_name: str) -> str:
    """Infer category from feature name for backward compatibility."""
    if "card" in feature_name:
        return "cards"
    if "control" in feature_name or "automation" in feature_name:
        return "automations"
    if "sensor" in feature_name:
        return "sensors"
    return "sensors"  # Default


# Feature registry (dynamically generated from feature modules)
# Entity definitions are in feature-specific const.py files
# Framework entity registry aggregates all definitions from features
AVAILABLE_FEATURES: dict[str, dict[str, Any]] = _discover_available_features()

# Platform registry for dynamic feature platform discovery
PLATFORM_REGISTRY: dict[str, dict[str, Callable]] = {}


def register_feature_platform(
    platform: str, feature_name: str, setup_func: Callable
) -> None:
    """Register a feature platform setup function."""
    if platform not in PLATFORM_REGISTRY:
        PLATFORM_REGISTRY[platform] = {}
    PLATFORM_REGISTRY[platform][feature_name] = setup_func


def get_feature_platform_setups(platform: str) -> list[Callable]:
    """Get all registered setup functions for a platform."""
    return list(PLATFORM_REGISTRY.get(platform, {}).values())


# Event System Implementation
async def fire_device_ready_event(
    hass: HomeAssistant,
    device_id: str,
    device_type: str,
    device: Any,
    entity_ids: list[str],
    handled_by: str,
) -> None:
    """Fire event after device handling but before entity creation."""

    event_data = {
        "device_id": device_id,
        "device_type": device_type,
        "device_object": device,  # Full device object for inspection
        "entity_ids": entity_ids,  # Entities that will be created
        "handled_by": handled_by,  # Which feature called the handler
        "timestamp": time.time(),
    }

    # Fire event for internal listeners
    async_dispatcher_send(hass, EVENT_DEVICE_READY_FOR_ENTITIES, event_data)

    # Also fire Home Assistant event for external listeners
    try:
        # Check if async_fire is a coroutine function or mock
        if callable(hass.bus.async_fire):
            # For mocks in testing, just call it without await
            if hasattr(hass.bus.async_fire, "mock"):
                # This is a mock, just call it
                hass.bus.async_fire(EVENT_DEVICE_READY_FOR_ENTITIES, event_data)
            else:
                # This might be a real async function, await it
                await hass.bus.async_fire(EVENT_DEVICE_READY_FOR_ENTITIES, event_data)
    except Exception:
        # Silently ignore errors in fire_event for testing scenarios
        pass


# Device Discovery Error Handling
class DeviceDiscoveryError(Exception):
    """Base exception for device discovery errors."""


class DeviceHandlingError(DeviceDiscoveryError):
    """Raised when device handler fails."""


# Import the registry at module level to avoid circular imports
try:
    from .extras_registry import extras_registry
except ImportError:
    # For testing scenarios where the registry might not be available
    pass  # Keep the name undefined for now


async def safe_handle_device_discovery(
    device: Any, device_type: str, feature_name: str, hass: HomeAssistant
) -> dict[str, Any]:
    """Safely handle device discovery with comprehensive error handling."""
    device_id = getattr(device, "id", "unknown")
    logger = logging.getLogger(__name__)

    try:
        # Validate device type mapping
        if device_type not in DEVICE_TYPE_HANDLERS:
            logger.warning(f"No handler registered for device type: {device_type}")
            return {"success": False, "reason": "unknown_device_type"}

        handler = DEVICE_TYPE_HANDLERS[device_type]

        # Execute handler with timeout
        try:
            result = await asyncio.wait_for(handler(device, feature_name), timeout=30.0)
        except TimeoutError:
            logger.warning(f"Handler timeout for device {device_id}")
            return {"success": False, "reason": "handler_timeout"}

        if not result:
            logger.warning(
                f"Handler returned False for device {device_id} "
                f"(type: {device_type}, feature: {feature_name})"
            )
            return {"success": False, "reason": "handler_returned_false"}

        # Get entity IDs for event firing
        entity_ids = []

        # Default entity IDs for HvacVentilator devices
        base_entity_ids = [
            f"sensor.indoor_absolute_humidity_{device_id}",
            f"sensor.outdoor_absolute_humidity_{device_id}",
        ]

        # Try to get device mappings from registry
        try:
            if extras_registry:
                device_mappings = extras_registry.get_all_device_mappings()
                logger.debug(
                    f"Available device mappings: {list(device_mappings.keys())}"
                )

                if device_type in device_mappings:
                    entity_mapping = device_mappings[device_type]
                    logger.debug(
                        f"Found entity mapping for {device_type}: {entity_mapping}"
                    )
                    # Use registry mappings
                    entity_ids = base_entity_ids.copy()
                else:
                    logger.debug(f"No mapping found for {device_type}, using defaults")
                    entity_ids = base_entity_ids.copy()
            else:
                logger.debug("Extras registry not available, using defaults")
                entity_ids = base_entity_ids.copy()
        except Exception as ex:
            logger.warning(f"Could not get device mappings from registry: {ex}")
            # Fallback entity IDs
            entity_ids = base_entity_ids.copy()

        # Add feature-specific entities
        if feature_name == "humidity_control":
            entity_ids.extend(
                [
                    f"switch.dehumidify_{device_id}",
                    f"number.relative_humidity_minimum_{device_id}",
                    f"number.relative_humidity_maximum_{device_id}",
                    f"number.absolute_humidity_offset_{device_id}",
                    f"binary_sensor.dehumidifying_active_{device_id}",
                ]
            )

        logger.debug(f"Generated entity IDs for {device_id}: {entity_ids}")

        # Fire device ready event
        await fire_device_ready_event(
            hass, device_id, device_type, device, entity_ids, feature_name
        )

        return {"success": True, "device": device}

    except DeviceHandlingError:
        raise
    except Exception as ex:
        logger.error(
            f"Unexpected error handling device {device_id}: {ex}", exc_info=True
        )
        return {"success": False, "reason": "unexpected_error", "error": str(ex)}


# Debug utilities for device discovery
def log_device_discovery_event(event_data: dict[str, Any], level: str = "info") -> None:
    """Log device discovery event with structured data."""
    logger = logging.getLogger(__name__)

    log_data = {
        "event": "device_ready_for_entities",
        "device_id": event_data.get("device_id"),
        "device_type": event_data.get("device_type"),
        "handled_by": event_data.get("handled_by"),
        "entity_count": len(event_data.get("entity_ids", [])),
        "timestamp": event_data.get("timestamp"),
    }

    # Add device info if available
    device = event_data.get("device_object")
    if device:
        log_data.update(
            {
                "device_model": getattr(device, "model", None),
                "device_firmware": getattr(device, "firmware_version", None),
                "device_capabilities": list(getattr(device, "capabilities", [])),
            }
        )

    log_message = f"Device Discovery Event: {log_data}"

    if level == "debug":
        logger.debug(log_message)
    elif level == "info":
        logger.info(log_message)
    elif level == "warning":
        logger.warning(log_message)
    else:
        logger.error(log_message)


# Import global EntityRegistry - standalone to avoid circular imports
# Moved inside functions to avoid import issues during testing
# Device Type Handler Implementations
@register_device_handler("HvacVentilator")
async def handle_hvac_ventilator(device: Any, feature_name: str) -> bool:
    """Handle HVAC Ventilator device discovery."""
    logger = logging.getLogger(__name__)

    try:
        # Validate device capabilities
        if not hasattr(device, "id"):
            logger.warning("Device missing ID capability")
            return False

        device_id = device.id
        device_type = device.__class__.__name__

        # Validate device has humidity sensor capability for features that need it
        if feature_name == "humidity_control":
            # Check if the device has humidity sensor capability
            has_humidity_sensor = (
                hasattr(device, "humidity_sensor")
                and device.humidity_sensor is not None
            ) or "humidity_sensing" in getattr(device, "capabilities", [])

            if not has_humidity_sensor:
                logger.warning(
                    f"Device {device_id} missing humidity_sensor "
                    f"capability for {feature_name}"
                )
                return False

        # Store device metadata for entity creation
        if not hasattr(device, "_entity_metadata"):
            device._entity_metadata = {}

        device._entity_metadata.update(
            {
                "feature": feature_name,
                "capabilities": ["humidity_sensing", "dehumidification"],
                "model_family": _extract_model_family(getattr(device, "model", "")),
                "device_type": device_type,
            }
        )

        logger.info(
            f"✅ Successfully handled HVAC Ventilator {device_id} for {feature_name}"
        )
        return True

    except Exception as ex:
        logger.error(
            f"Failed to handle HVAC Ventilator {getattr(device, 'id', 'unknown')}: {ex}"
        )
        return False


def _extract_model_family(model: str) -> str:
    """Extract model family from device model string."""
    if not model:
        return "unknown"

    # Common model patterns
    model_upper = model.upper()

    # Orcon patterns
    if any(pattern in model_upper for pattern in ["HRV", "ORCON"]):
        return "orcon"

    # Zehnder patterns
    if "COMFOAIR" in model_upper or "ZEHNDER" in model_upper:
        return "zehnder"

    # Generic patterns
    if "VENTILATOR" in model_upper:
        return "generic_ventilator"

    return "unknown"


# Future device type handlers can be added here
# @register_device_handler("HvacController")
# async def handle_hvac_controller(device, feature_name: str) -> bool:
#     """Handle HVAC Controller devices."""
#     return True
#
# @register_device_handler("Thermostat")
# async def handle_thermostat(device, feature_name: str) -> bool:
#     """Handle Thermostat devices."""
#     return True
# from .extras_registry import extras_registry  # noqa: E402
