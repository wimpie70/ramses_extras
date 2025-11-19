"""Integration to provide additional entities and automations for Ramses RF/Hive
systems."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_FOLDER,
    DOMAIN,
    PLATFORM_REGISTRY,
    register_feature_platform,
)

_LOGGER = logging.getLogger(__name__)

INTEGRATION_DIR = Path(__file__).parent
_setup_in_progress = False


# Component will be loaded when hass starts up.
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Ramses Extras integration from YAML configuration."""

    # Listen for when Home Assistant starts up
    async def _async_startup(hass: HomeAssistant) -> None:
        # This will only be called if the user has Ramses Extras configured
        # from a YAML file. If configured via UI, async_setup_entry will handle it.
        _LOGGER.info("🏠  Starting Ramses Extras from YAML configuration")
        hass.async_create_task(async_setup_yaml_config(hass, config))

    # Listen for when Home Assistant starts
    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _async_startup)

    return True


async def async_setup_yaml_config(hass: HomeAssistant, config: ConfigType) -> None:
    """Set up Ramses Extras from YAML config if present."""

    yaml_config = config.get(DOMAIN, {})
    if not yaml_config:
        return

    try:
        _LOGGER.info("🔧 Setting up Ramses Extras from YAML configuration...")

        # Create a config entry from YAML for the integrations to use
        entry_data = {
            "yaml": True,
            "enabled_features": yaml_config.get("enabled_features", {}),
        }

        # Note: This will trigger the normal setup flow
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "yaml"},
                data=entry_data,
            )
        )

    except Exception:
        _LOGGER.exception("Failed to set up Ramses Extras from YAML")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entry for Ramses Extras."""
    _LOGGER.info("🚀 STARTING Ramses Extras integration setup...")

    # Setup from UI (config entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["config_entry"] = entry  # Store for async_setup_platforms access
    hass.data[DOMAIN]["enabled_features"] = entry.data.get("enabled_features", {})
    hass.data[DOMAIN]["PLATFORM_REGISTRY"] = (
        PLATFORM_REGISTRY  # Make registry available to platforms
    )

    _LOGGER.info(f"📋 Enabled features: {entry.data.get('enabled_features', {})}")

    # Load entity definitions from default feature and all enabled features
    _LOGGER.info("📊 Loading entity definitions from features...")
    from .extras_registry import extras_registry

    # Always load default feature definitions
    _LOGGER.info("🔧 Loading default entity definitions...")
    from .features.default.const import (
        DEFAULT_BOOLEAN_CONFIGS,
        DEFAULT_DEVICE_ENTITY_MAPPING,
        DEFAULT_NUMBER_CONFIGS,
        DEFAULT_SENSOR_CONFIGS,
        DEFAULT_SWITCH_CONFIGS,
    )

    extras_registry.register_sensor_configs(DEFAULT_SENSOR_CONFIGS)
    extras_registry.register_switch_configs(DEFAULT_SWITCH_CONFIGS)
    extras_registry.register_number_configs(DEFAULT_NUMBER_CONFIGS)
    extras_registry.register_boolean_configs(DEFAULT_BOOLEAN_CONFIGS)
    extras_registry.register_device_mappings(DEFAULT_DEVICE_ENTITY_MAPPING)
    extras_registry.register_feature("default")

    # Load enabled feature definitions
    enabled_features_dict = entry.data.get("enabled_features", {})
    enabled_feature_names = [
        name for name, enabled in enabled_features_dict.items() if enabled
    ]

    _LOGGER.info(
        f"🔧 Loading definitions from {len(enabled_feature_names)} "
        f"enabled features: {enabled_feature_names}"
    )

    # Load each enabled feature dynamically
    for feature_name in enabled_feature_names:
        try:
            # Import the feature's const module
            module_name = (
                f"custom_components.ramses_extras.features.{feature_name}.const"
            )
            feature_module = __import__(module_name, fromlist=["load_feature"])

            # Call the feature's load function
            if hasattr(feature_module, "load_feature"):
                feature_module.load_feature()
                _LOGGER.info(f"✅ Loaded {feature_name} feature definitions")
            else:
                _LOGGER.warning(
                    f"⚠️  Feature '{feature_name}' has no load_feature function"
                )

            # Import platform modules to trigger registration
            import importlib

            try:
                # Import all platform modules for this feature
                platforms_dir = (
                    INTEGRATION_DIR / "features" / feature_name / "platforms"
                )
                if platforms_dir.exists():
                    for platform_file in platforms_dir.glob("*.py"):
                        if platform_file.name != "__init__.py":
                            module_path = f"custom_components.ramses_extras.features.{feature_name}.platforms.{platform_file.stem}"  # noqa: E501
                            importlib.import_module(module_path)
            except ImportError:
                pass

        except ImportError as e:
            _LOGGER.warning(f"⚠️  Failed to load feature '{feature_name}': {e}")

    # Log loaded definitions for verification
    sensor_count = len(extras_registry.get_all_sensor_configs())
    switch_count = len(extras_registry.get_all_switch_configs())
    number_count = len(extras_registry.get_all_number_configs())
    boolean_count = len(extras_registry.get_all_boolean_configs())
    _LOGGER.info(
        f"✅ EntityRegistry loaded: {sensor_count} sensors, {switch_count} switches, "
        f"{number_count} numbers, {boolean_count} binary sensors"
    )

    _LOGGER.info("WebSocket functionality moved to feature-centric architecture")

    # Register services before setting up platforms
    _LOGGER.info("🔧 Registering services early...")
    await _register_services(hass)

    # CRITICAL: Discover devices BEFORE setting up platforms
    # This ensures platforms have device data when they initialize
    _LOGGER.info("🔍 Discovering devices before platform setup...")
    await _discover_and_store_devices(hass)

    # Forward the setup to the sensor, switch, etc. platforms
    _LOGGER.info("🔧 Registering supported platforms...")
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.NUMBER],
    )

    # Continue with additional platform setup if needed
    _LOGGER.info("🔍 Starting async_setup_platforms...")
    await async_setup_platforms(hass)

    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register custom services."""
    _LOGGER.info("Service registration delegated to feature managers")


async def _discover_and_store_devices(hass: HomeAssistant) -> None:
    """Discover devices and store them in hass.data for platform access."""
    device_ids = await _discover_ramses_devices(hass)

    # Store devices in a location that platforms can access
    hass.data.setdefault(DOMAIN, {})["devices"] = device_ids
    hass.data.setdefault(DOMAIN, {})["device_discovery_complete"] = True

    _LOGGER.info(
        f"💾 Stored {len(device_ids)} devices for platform access: {device_ids}"
    )


async def async_setup_platforms(hass: HomeAssistant) -> None:
    """Enhanced platform setup with reliable device discovery integration."""
    global _setup_in_progress

    # Prevent multiple simultaneous setup attempts
    if _setup_in_progress:
        _LOGGER.debug("Platform setup already in progress, skipping")
        return

    _setup_in_progress = True

    try:
        _LOGGER.info("🚀 Platform setup: integrating with device discovery...")

        # Check if ramses_cc is loaded and working
        ramses_cc_loaded = "ramses_cc" in hass.config.components
        _LOGGER.info(f"🔍 Ramses CC loaded: {ramses_cc_loaded}")

        if ramses_cc_loaded:
            _LOGGER.info("🔍 Ramses CC is loaded, verifying device discovery...")

            # Check if device discovery was already completed
            device_data = hass.data.setdefault(DOMAIN, {})
            if "devices" in device_data and "device_discovery_complete" in device_data:
                _LOGGER.info(
                    "✅ Device discovery already completed, using cached results"
                )
                device_ids = device_data["devices"]
                _LOGGER.info(f"📋 Using cached device IDs: {device_ids}")
            else:
                # Re-discover devices and update storage
                device_ids = await _discover_ramses_devices(hass)
                device_data["devices"] = device_ids
                device_data["device_discovery_complete"] = True
                _LOGGER.info(f"📋 Fresh discovery device IDs: {device_ids}")

            if device_ids:
                _LOGGER.info(
                    "✅ Platform setup: Found %d Ramses devices: %s",
                    len(device_ids),
                    device_ids,
                )
            else:
                _LOGGER.info("⚠️ Platform setup: No Ramses devices found via any method")

            return
        _LOGGER.info("⚠️  Ramses CC not loaded yet, will retry in 60 seconds.")

        # Schedule a retry in 60 seconds - only if ramses_cc not loaded
        if "ramses_cc" not in hass.config.components:

            async def delayed_retry() -> None:
                global _setup_in_progress
                _setup_in_progress = False
                await async_setup_platforms(hass)

            # Use async_call_later instead of async_add_job
            hass.call_later(60.0, hass.async_create_task(delayed_retry))

    except Exception as e:
        _LOGGER.error(f"Error in platform setup: {e}")
    finally:
        # Reset setup flag
        _setup_in_progress = False


async def _discover_ramses_devices(hass: HomeAssistant) -> list[str]:
    """Discover Ramses devices from ramses_cc integration with improved reliability.

    This function leverages ramses_cc to discover devices by looking for
    ramses_cc entities in the entity registry with multiple fallback methods.
    """

    # Access the broker from the ramses_cc integration
    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No ramses_cc entries found")
        return await _discover_devices_from_entity_registry(hass)

    # Use the first ramses_cc entry
    entry = ramses_cc_entries[0]

    try:
        # Method 1: Try to get broker from hass.data (most reliable)
        broker = None
        if "ramses_cc" in hass.data and entry.entry_id in hass.data["ramses_cc"]:
            broker_data = hass.data["ramses_cc"][entry.entry_id]
            # The broker is stored directly, not nested under a "broker" key
            if (
                hasattr(broker_data, "__class__")
                and "Broker" in broker_data.__class__.__name__
            ):
                broker = broker_data
            elif isinstance(broker_data, dict) and "broker" in broker_data:
                broker = broker_data["broker"]
            elif hasattr(broker_data, "broker"):
                broker = broker_data.broker
            else:
                # Direct assignment if broker is stored directly
                broker = broker_data
            _LOGGER.debug(f"Found broker via hass.data method: {broker}")

        # Method 2: If not found, try getting broker from the entry
        if broker is None and hasattr(entry, "broker"):
            broker = entry.broker
            _LOGGER.debug(f"Found broker via entry method: {broker}")

        # Method 3: Try to access through the integration registry
        if broker is None:
            # Look for ramses_cc integration instance in integration registry
            for integration in hass.data.get("integrations", {}).values():
                if hasattr(integration, "broker") and integration.broker:
                    broker = integration.broker
                    _LOGGER.debug(f"Found broker via integration registry: {broker}")
                    break

        # Method 4: Direct import and access (new fallback)
        if broker is None:
            try:
                from ramses_cc.gateway import Gateway

                # Try to find gateway through Home Assistant's component registry
                gateway_entries = [
                    e for e in ramses_cc_entries if hasattr(e, "gateway")
                ]
                if gateway_entries:
                    broker = gateway_entries[0].gateway
                    _LOGGER.debug(f"Found broker via direct gateway access: {broker}")
            except ImportError:
                _LOGGER.debug("ramses_cc module not available for direct access")

        if broker is None:
            _LOGGER.warning("Could not find ramses_cc broker via any method")
            # Fallback: try to find devices from entity registry
            return await _discover_devices_from_entity_registry(hass)

        # Get devices from the broker with robust access
        # The broker stores devices as _devices (list), not devices (dict)
        devices = getattr(broker, "_devices", None)
        if devices is None:
            # Try alternative attribute names
            devices = getattr(broker, "devices", None)

        if not devices:
            _LOGGER.debug("No devices found in broker, using entity registry fallback")
            return await _discover_devices_from_entity_registry(hass)

        _LOGGER.debug(f"Found {len(devices)} total devices in broker")

        # Filter for different device types based on feature requirements
        discovered_devices = []

        # Fan devices (HvacVentilator) for ventilation features
        fan_devices = [
            device
            for device in devices
            if hasattr(device, "__class__")
            and "HvacVentilator" in device.__class__.__name__
        ]
        discovered_devices.extend(fan_devices)

        # Sensor devices for sensor features
        sensor_devices = [
            device
            for device in devices
            if hasattr(device, "__class__")
            and (
                "HvacController" in device.__class__.__name__
                or "Climate" in device.__class__.__name__
            )
        ]
        discovered_devices.extend(sensor_devices)

        # Get device IDs
        device_ids = [
            getattr(device, "id", str(device)) for device in discovered_devices
        ]
        _LOGGER.info(f"Found {len(discovered_devices)} relevant devices: {device_ids}")

        return device_ids

    except Exception as e:
        _LOGGER.error(f"Error accessing ramses_cc broker: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")
        # Fallback to entity registry discovery
        return await _discover_devices_from_entity_registry(hass)


async def _discover_devices_from_entity_registry(hass: HomeAssistant) -> list[str]:
    """Fallback method to discover devices from entity registry with comprehensive
    device support."""
    try:
        from homeassistant.helpers.entity_registry import async_get

        entity_registry = async_get(hass)
        device_ids = []

        # Look for ramses_cc entities across multiple domains
        relevant_domains = [
            "fan",
            "climate",
            "sensor",
            "switch",
            "number",
            "binary_sensor",
        ]

        for entity in entity_registry.entities.values():
            if (
                entity.domain in relevant_domains
                and entity.platform == "ramses_cc"
                and hasattr(entity, "device_id")
            ):
                device_id = entity.device_id
                if device_id and device_id not in device_ids:
                    device_ids.append(device_id)

        _LOGGER.info(
            f"Found {len(device_ids)} devices via entity registry fallback: "
            f"{device_ids}"
        )
        return device_ids

    except Exception as e:
        _LOGGER.error(f"Error discovering devices from entity registry: {e}")
        return []


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("🚫 Unloading Ramses Extras integration...")

    # Forward the unload to our platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        [
            Platform.SENSOR,
            Platform.SWITCH,
            Platform.BINARY_SENSOR,
            Platform.NUMBER,
        ],
    )

    if unload_ok:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return bool(unload_ok)
