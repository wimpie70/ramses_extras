"""Integration to provide additional entities and automations for Ramses RF/Hive
systems."""

from __future__ import annotations

import asyncio
import importlib
import logging
import shutil
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    DOMAIN,
    PLATFORM_REGISTRY,
    register_feature_platform,
)
from .framework.helpers.paths import DEPLOYMENT_PATHS

_LOGGER = logging.getLogger(__name__)

INTEGRATION_DIR = Path(__file__).parent
_setup_in_progress = False


async def _import_module_in_executor(module_path: str) -> Any:
    """Import module in executor to avoid blocking event loop."""
    import asyncio

    def _do_import() -> Any:
        return importlib.import_module(module_path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_import)


async def _handle_startup_event(
    event: Event, hass: HomeAssistant, config: ConfigType
) -> None:
    """Handle Home Assistant startup event."""
    # This will only be called if the user has Ramses Extras configured
    # from a YAML file. If configured via UI, async_setup_entry will handle it.
    _LOGGER.info("🏠  Starting Ramses Extras from YAML configuration")

    await async_setup_yaml_config(hass, config)


# Component will be loaded when hass starts up.
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Ramses Extras integration from YAML configuration."""

    # Use module-level function with explicit parameters to avoid closure issues
    # and thread-safe execution using run_coroutine_threadsafe
    def _startup_callback(event: Event) -> None:
        """Thread-safe callback for startup event."""
        import asyncio

        # Use run_coroutine_threadsafe for thread safety
        asyncio.run_coroutine_threadsafe(
            _handle_startup_event(event, hass, config), hass.loop
        )

    hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, _startup_callback)

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

    # Load default feature's WebSocket commands and other feature components
    _LOGGER.info("🔧 Loading default feature...")
    from .features.default.const import load_feature

    load_feature()

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
            try:
                # Import all platform modules for this feature
                platforms_dir = (
                    INTEGRATION_DIR / "features" / feature_name / "platforms"
                )
                if platforms_dir.exists():
                    for platform_file in platforms_dir.glob("*.py"):
                        if platform_file.name != "__init__.py":
                            module_path = f"custom_components.ramses_extras.features.{feature_name}.platforms.{platform_file.stem}"  # noqa: E501

                            # Import in executor to avoid blocking event loop
                            await _import_module_in_executor(module_path)
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
        f"✅ EntityRegistry loaded: {sensor_count} sensor, {switch_count} switch, "
        f"{number_count} number, {boolean_count} binary sensor"
    )

    _LOGGER.info("WebSocket functionality moved to feature-centric architecture")

    # Register custom card resources via feature-centric approach
    await _register_feature_card_resources(hass, enabled_features_dict, entry)

    # Register services before setting up platforms
    _LOGGER.info("🔧 Registering services early...")
    await _register_services(hass)

    # Register WebSocket commands for features
    _LOGGER.info("🔌 Setting up WebSocket integration...")
    await _setup_websocket_integration(hass)

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

    # STEP: Post-creation validation with EntityManager
    _LOGGER.info("🔍 Running EntityManager post-creation validation...")
    await _validate_startup_entities(hass, entry)

    # Explicitly create and start feature instances for
    #  enabled features (including default)
    features = hass.data[DOMAIN].setdefault("features", {})
    enabled_feature_names = list(entry.data.get("enabled_features", {}).keys())
    # Always include default
    if "default" not in enabled_feature_names:
        enabled_feature_names.append("default")
    import importlib

    for feature_name in enabled_feature_names:
        if feature_name in features:
            continue  # Already created
        try:
            feature_module_name = (
                f"custom_components.ramses_extras.features.{feature_name}"
            )
            feature_module = importlib.import_module(feature_module_name)
            # Create feature instance if create function exists
            create_func_name = f"create_{feature_name.replace('-', '_')}_feature"
            if hasattr(feature_module, create_func_name):
                create_feature_func = getattr(feature_module, create_func_name)
                # Handle both sync and async create functions
                import asyncio

                if asyncio.iscoroutinefunction(create_feature_func):
                    feature_instance = await create_feature_func(hass, entry)
                else:
                    feature_instance = create_feature_func(hass, entry)
                features[feature_name] = feature_instance
                _LOGGER.info(f"✅ Created feature instance: {feature_name}")
        except Exception as e:
            _LOGGER.warning(
                f"⚠️ Failed to create feature instance '{feature_name}': {e}"
            )
    return True


async def _register_services(hass: HomeAssistant) -> None:
    """Register custom services."""
    _LOGGER.info("Service registration delegated to feature managers")


async def _setup_websocket_integration(hass: HomeAssistant) -> None:
    """Set up WebSocket integration for Ramses Extras.

    Args:
        hass: Home Assistant instance
    """
    try:
        from .websocket_integration import async_setup_websocket_integration

        success = await async_setup_websocket_integration(hass)
        if success:
            _LOGGER.info("✅ WebSocket integration setup complete")
        else:
            _LOGGER.warning("⚠️ WebSocket integration setup failed")

    except Exception as error:
        _LOGGER.error(f"❌ Error setting up WebSocket integration: {error}")
        # Don't fail the entire integration if WebSocket setup fails


async def _register_feature_card_resources(
    hass: HomeAssistant, enabled_features: dict[str, bool], entry: ConfigEntry
) -> None:
    """Register custom card resources using feature-centric approach.

    This function delegates card registration to individual feature managers,
    following the feature-centric architecture pattern where each feature
    handles its own business logic.
    """
    try:
        _LOGGER.info("🔧 Starting feature-centric card resource registration")
        _LOGGER.info(f"📋 Enabled features: {enabled_features}")
        _LOGGER.info(f"📋 Available features: {list(AVAILABLE_FEATURES.keys())}")

        # Initialize card resources storage
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault("card_resources", {})

        # Create feature instances and delegate card registration
        feature_card_registrations: dict[str, dict[str, Any]] = {}

        # Import card-capable features dynamically
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            _LOGGER.info(f"🔍 Processing feature: {feature_key}")

            # Skip default feature (it's not a card feature)
            if feature_key == "default":
                _LOGGER.info("⏭️ Skipping default feature")
                continue

            # Only process features that are enabled
            is_enabled = enabled_features.get(feature_key, False)
            _LOGGER.info(f"🔧 Feature {feature_key} enabled: {is_enabled}")
            if not is_enabled:
                _LOGGER.debug(
                    f"Feature {feature_key} not enabled, skipping card registration"
                )
                continue

            # Check if feature has card configurations
            try:
                # Try to import the feature's const module and check for card configs
                const_module = __import__(
                    f"custom_components.ramses_extras.features.{feature_key}.const",
                    fromlist=["load_feature"],
                )
                has_card_configs = hasattr(
                    const_module, "HVAC_FAN_CARD_CONFIGS"
                ) or hasattr(
                    const_module,
                    f"{feature_key.upper().replace('-', '_')}_CARD_CONFIGS",
                )
                _LOGGER.info(
                    f"🔍 Feature {feature_key} has card configs: {has_card_configs}"
                )
            except (ImportError, AttributeError):
                has_card_configs = False
                _LOGGER.debug(f"🔍 Feature {feature_key} has no card configs")

            if not has_card_configs:
                _LOGGER.debug(
                    f"⏭️ Feature {feature_key} has no card configurations, skipping"
                )
                continue

            try:
                _LOGGER.info(f"📦 Importing feature module: {feature_key}")
                # Import the feature module
                feature_module_name = (
                    f"custom_components.ramses_extras.features.{feature_key}"
                )
                feature_module = __import__(
                    feature_module_name, fromlist=["load_feature"]
                )

                # Check if feature has card management capability
                create_func_name = f"create_{feature_key.replace('-', '_')}_feature"
                _LOGGER.info(f"🔍 Looking for create function: {create_func_name}")
                _LOGGER.info(
                    f"🔍 Has create function: "
                    f"{hasattr(feature_module, create_func_name)}"
                )

                if hasattr(
                    feature_module,
                    create_func_name,
                ):
                    # Create feature instance for card management
                    create_feature_func = getattr(
                        feature_module,
                        create_func_name,
                    )

                    # Create feature instance
                    _LOGGER.info("🎯 Creating feature instance...")
                    # Handle both sync and async create functions
                    import asyncio

                    if asyncio.iscoroutinefunction(create_feature_func):
                        # For async functions, skip automation
                        #  setup for card registration
                        feature_instance = await create_feature_func(
                            hass, entry, skip_automation_setup=True
                        )
                    else:
                        feature_instance = create_feature_func(hass, entry)

                    _LOGGER.info(f"📦 Feature instance created: {feature_instance}")

                    # Get card manager if available
                    card_manager = feature_instance.get("card_manager")
                    _LOGGER.info(f"🎯 Card manager: {card_manager}")

                    if card_manager:
                        _LOGGER.info("📝 Registering cards via card manager...")
                        # Delegate card registration to the feature
                        registered_cards = await card_manager.async_register_cards()
                        _LOGGER.info(f"📋 Registered cards result: {registered_cards}")

                        if registered_cards:
                            feature_card_registrations[feature_key] = registered_cards
                            _LOGGER.info(
                                f"✅ Feature {feature_key} registered "
                                f"{len(registered_cards)} cards"
                            )
                        else:
                            _LOGGER.debug(
                                f"⚠️ Feature {feature_key} has no cards to register"
                            )
                    else:
                        _LOGGER.debug(
                            f"⚠️ No card manager found for feature {feature_key}"
                        )

            except ImportError as e:
                _LOGGER.error(f"❌ Could not import feature {feature_key}: {e}")
            except Exception as e:
                _LOGGER.error(
                    f"❌ Error processing feature {feature_key} for cards: {e}"
                )
                import traceback

                _LOGGER.error(f"Full traceback: {traceback.format_exc()}")

        # Consolidate all card registrations
        _LOGGER.info("🔗 Consolidating card registrations...")
        all_registered_cards = {}
        for feature_key, feature_cards in feature_card_registrations.items():
            all_registered_cards.update(feature_cards)

        _LOGGER.info(f"📊 Final consolidated cards: {all_registered_cards}")

        # Store consolidated registrations
        hass.data[DOMAIN]["card_resources"] = all_registered_cards

        # Register cards with Home Assistant's Lovelace system
        await _register_lovelace_cards(hass, all_registered_cards)

        registered_cards = list(all_registered_cards.keys())
        _LOGGER.info(
            f"✅ Feature-centric card registration complete. "
            f"Total cards registered: {len(all_registered_cards)} from "
            f"{len(feature_card_registrations)} features. "
            f"Cards: {registered_cards}"
        )

    except Exception as e:
        _LOGGER.error(f"❌ Failed to register feature card resources: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _copy_helper_files(hass: HomeAssistant) -> None:
    """Copy helper files to Home Assistant's www directory for card functionality."""
    try:
        _LOGGER.info("📦 Starting helper files copy process...")

        # Source and destination paths
        source_helpers_dir = INTEGRATION_DIR / "framework" / "www"
        destination_helpers_dir = DEPLOYMENT_PATHS.get_destination_helpers_path(
            hass.config.config_dir
        )

        _LOGGER.info(f"📁 Source helpers directory: {source_helpers_dir}")
        _LOGGER.info(f"📁 Destination helpers directory: {destination_helpers_dir}")
        _LOGGER.info(f"📂 Source directory exists: {source_helpers_dir.exists()}")

        if not source_helpers_dir.exists():
            _LOGGER.warning(f"⚠️ Helper files directory not found: {source_helpers_dir}")
            return

        # Create destination directory if it doesn't exist
        destination_helpers_dir.mkdir(parents=True, exist_ok=True)
        _LOGGER.info(f"📁 Created directory: {destination_helpers_dir}")

        # Copy all helper files
        await asyncio.to_thread(
            shutil.copytree,
            source_helpers_dir,
            destination_helpers_dir,
            dirs_exist_ok=True,
        )
        _LOGGER.info("✅ Helper files copied successfully")

    except Exception as e:
        _LOGGER.error(f"❌ Failed to copy helper files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _register_lovelace_cards(
    hass: HomeAssistant, registered_cards: dict[str, dict[str, Any]]
) -> None:
    """Register cards with Home Assistant's Lovelace UI system."""
    try:
        _LOGGER.info("🔧 Starting Lovelace card registration process...")
        _LOGGER.info(f"📋 Input registered_cards: {registered_cards}")

        if not registered_cards:
            _LOGGER.warning("⚠️ No cards to register - registered_cards is empty!")
            return

        # Copy helper files when any card is enabled
        _LOGGER.info("📦 Copying helper files for card functionality...")
        await _copy_helper_files(hass)

        for card_id, card_info in registered_cards.items():
            try:
                _LOGGER.info(f"🔄 Processing card: {card_id}")
                _LOGGER.info(f"📄 Card info: {card_info}")

                # For Home Assistant custom cards, ensure the JavaScript files
                # are copied to the Home Assistant's www directory so they can be
                # accessed via /local/ URLs

                # Get the source directory path from the integration
                # The js_path now points to the main card file,
                # but we need the directory
                integration_js_path = INTEGRATION_DIR / card_info["js_path"]
                integration_card_dir = integration_js_path.parent
                _LOGGER.info(f"🔍 Source integration file path: {integration_js_path}")
                _LOGGER.info(f"📁 Source integration directory: {integration_card_dir}")
                _LOGGER.info(
                    f"📂 Source directory exists: {integration_card_dir.exists()}"
                )

                # Use proper deployment paths from paths.py
                # Extract feature name from card info
                feature_name = card_info.get("feature", "unknown")

                # Get the correct destination path using DEPLOYMENT_PATHS
                homeassistant_card_dir = DEPLOYMENT_PATHS.get_destination_features_path(
                    hass.config.config_dir, feature_name
                )

                _LOGGER.info(f"🎯 Target HA directory: {homeassistant_card_dir}")
                _LOGGER.info(f"📁 Source directory: {integration_card_dir}")

                if integration_card_dir.exists():
                    # Create the destination directory if it doesn't exist
                    homeassistant_card_dir.mkdir(parents=True, exist_ok=True)
                    _LOGGER.info(f"📁 Created directory: {homeassistant_card_dir}")

                    # Copy all files from the card directory
                    # to Home Assistant's www directory
                    await asyncio.to_thread(
                        shutil.copytree,
                        integration_card_dir,
                        homeassistant_card_dir,
                        dirs_exist_ok=True,
                    )
                    _LOGGER.info("✅ Directory copied successfully")

                    # Construct the correct URL for the card
                    # Based on new deployment structure:
                    # /local/ramses_extras/features/{feature_name}/
                    clean_js_path = card_info["js_path"].split("/")[
                        -1
                    ]  # Just the filename
                    card_url = (
                        f"/local/ramses_extras/features/{feature_name}/{clean_js_path}"
                    )

                    _LOGGER.info(
                        f"🎴 Card ready for Lovelace: {card_id} -> {card_info['name']} "
                        f"(available at {card_url})"
                    )
                else:
                    _LOGGER.error(
                        f"❌ Card directory not found: {integration_card_dir}"
                    )
                    continue

            except Exception as e:
                _LOGGER.error(f"❌ Failed to setup card {card_id}: {e}")
                import traceback

                _LOGGER.error(f"Full traceback: {traceback.format_exc()}")
                continue

        _LOGGER.info("✅ Custom card files setup complete")

        # Register cards with Home Assistant's Lovelace resources storage
        await _register_lovelace_resources_storage(hass, registered_cards)

    except Exception as e:
        _LOGGER.error(f"❌ Failed to setup custom card files: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _register_lovelace_resources_storage(
    hass: HomeAssistant, registered_cards: dict[str, dict[str, Any]]
) -> None:
    """Register cards in Home Assistant's Lovelace resources storage.

    This ensures that custom cards are discoverable and can be used in dashboards.
    """
    try:
        _LOGGER.info("🔧 Starting Lovelace resources storage registration...")

        if not registered_cards:
            _LOGGER.warning("⚠️ No cards to register in lovelace_resources storage!")
            return

        # Import Store for proper Home Assistant storage access
        from homeassistant.helpers.storage import Store

        # Get the resources storage using the proper Store API
        store = Store(hass, 1, "lovelace_resources")
        data = await store.async_load() or {"items": []}

        _LOGGER.info(
            f"📋 Current resources storage loaded: {len(data.get('items', []))} items"
        )

        # Get existing resources and fix any missing 'id' fields
        existing_resources = data.get("items", [])
        fixed_resources: list[dict[str, Any]] = []
        fixed_any_resources = False
        for resource in existing_resources:
            # Fix missing 'id' field by using the URL as a unique identifier
            if "id" not in resource:
                resource_id = (
                    resource.get("url", "").replace("/", "_").replace("-", "_")
                )
                if not resource_id:
                    resource_id = f"resource_{len(fixed_resources)}"
                resource["id"] = resource_id
                fixed_any_resources = True
                _LOGGER.warning(
                    f"🔧 Fixed missing 'id' field for resource: "
                    f"{resource.get('url', 'unknown')}"
                )
            fixed_resources.append(resource)

        existing_resources = fixed_resources
        existing_card_urls = {
            resource["url"]
            for resource in existing_resources
            if resource.get("type") == "module"
        }

        _LOGGER.info(f"📄 Existing card URLs: {existing_card_urls}")

        # Clean up old hvac-fan-card entries before adding new ones
        # This removes duplicate/old paths from previous deployments
        cleaned_resources = []
        removed_old_entries = []
        for resource in existing_resources:
            url = resource.get("url", "")
            # Remove old hvac-fan-card entries (not in the new features/ structure)
            if "hvac" in url.lower() and "/ramses_extras/features/" not in url:
                removed_old_entries.append(url)
                _LOGGER.info(f"🗑️  Removing old hvac-fan-card entry: {url}")
            else:
                cleaned_resources.append(resource)

        if removed_old_entries:
            _LOGGER.info(
                f"✅ Cleaned up {len(removed_old_entries)} old hvac-fan-card entries"
            )
            existing_resources = cleaned_resources
            existing_card_urls = {
                resource["url"]
                for resource in existing_resources
                if resource.get("type") == "module"
            }

        # Add new cards to resources
        resources_to_add = []
        for card_id, card_info in registered_cards.items():
            try:
                # Construct the URL for the card using the correct deployment path
                feature_name = card_info.get("feature", "unknown")
                js_filename = card_info["js_path"].split("/")[-1]  # Just the filename
                card_url = f"/local/ramses_extras/features/{feature_name}/{js_filename}"

                # Check if this card is already registered
                if card_url in existing_card_urls:
                    _LOGGER.info(f"⏭️ Card {card_id} already registered at {card_url}")
                    continue

                # Create resource entry with required id field
                resource_entry = {
                    "id": card_id,
                    "url": card_url,
                    "type": "module",
                }

                resources_to_add.append(resource_entry)
                _LOGGER.info(f"📝 Added resource entry for {card_id}: {card_url}")

            except Exception as e:
                _LOGGER.error(f"❌ Failed to create resource entry for {card_id}: {e}")
                continue

        # Update the storage if we have new resources,
        #  fixed existing ones, or removed old ones
        if resources_to_add or fixed_any_resources or removed_old_entries:
            updated_resources = existing_resources + resources_to_add
            data["items"] = updated_resources

            # Save the updated storage using the Store API
            await store.async_save(data)

            if resources_to_add:
                _LOGGER.info(
                    f"✅ Registered {len(resources_to_add)} new card resources"
                )
                _LOGGER.info(f"📋 Updated resources count: {len(updated_resources)}")

                # Notify user about successful registration
                try:
                    await hass.services.async_create(
                        "persistent_notification",
                        "create",
                        {
                            "message": (
                                "The Ramses Extras fan card has been registered "
                                "as a Lovelace resource.<br>"
                                "You can now add it to any dashboard."
                            ),
                            "title": "Ramses Extras",
                            "notification_id": "ramses_extras_lovelace_resource",
                        },
                    )
                except Exception as e:
                    _LOGGER.debug(f"Could not create persistent notification: {e}")
            if fixed_any_resources:
                _LOGGER.info("🔧 Fixed existing resources with missing 'id' fields")
            if removed_old_entries:
                _LOGGER.info(
                    f"🗑️  Removed {len(removed_old_entries)} old hvac-fan-card entries"
                )
        else:
            _LOGGER.info("ℹ️ No new resources to add and no fixes needed")

    except Exception as e:
        _LOGGER.error(f"❌ Failed to register lovelace resources storage: {e}")
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


async def _validate_startup_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Validate startup entity creation and fix discrepancies using EntityManager.

    This function runs after all platforms have been set up to ensure that
    the actual entities match the expected configuration. It uses EntityManager
    to detect and fix any discrepancies.

    Args:
        hass: Home Assistant instance
        entry: Configuration entry
    """
    try:
        from .framework.helpers.entity.manager import EntityManager

        # Create EntityManager for validation
        entity_manager = EntityManager(hass)

        # Import AVAILABLE_FEATURES for validation
        from .const import AVAILABLE_FEATURES

        # Build catalog of what SHOULD exist vs what DOES exist
        await entity_manager.build_entity_catalog(
            AVAILABLE_FEATURES, entry.data.get("enabled_features", {})
        )

        # Update targets to establish what the final state should be
        # This ensures default features (which are always enabled) are properly marked
        target_features = entry.data.get("enabled_features", {}).copy()

        # Ensure default feature is always enabled in targets
        # The default feature provides base entities that should always be created
        target_features["default"] = True

        entity_manager.update_feature_targets(target_features)

        # Get any discrepancies
        entities_to_remove = entity_manager.get_entities_to_remove()
        entities_to_create = entity_manager.get_entities_to_create()

        if entities_to_remove or entities_to_create:
            _LOGGER.warning(
                f"Startup validation found discrepancies: "
                f"remove {len(entities_to_remove)}, create {len(entities_to_create)}"
            )
            if entities_to_remove:
                _LOGGER.warning(f"Entities to remove: {entities_to_remove}")
            if entities_to_create:
                _LOGGER.warning(f"Entities to create: {entities_to_create}")

            # Apply cleanup/creation as needed
            await entity_manager.apply_entity_changes()
        else:
            _LOGGER.info(
                "✅ Startup validation: all entities match expected configuration"
            )

    except Exception as e:
        _LOGGER.error(f"EntityManager startup validation failed: {e}")
        # Don't fail startup if validation fails - log error and continue
        import traceback

        _LOGGER.debug(f"Full traceback: {traceback.format_exc()}")


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
