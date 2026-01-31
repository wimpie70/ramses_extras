import asyncio
import inspect
import json
import logging
import shutil
import traceback
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    HANDLERS,
    ConfigEntry,
    ConfigFlow,
    FlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    CONF_ENABLED_FEATURES,
    CONF_NAME,
    DOMAIN,
    GITHUB_WIKI_URL,
    INTEGRATION_DIR,
)
from .features.sensor_control.const import SUPPORTED_METRICS
from .framework.helpers.config_flow import ConfigFlowHelper
from .framework.helpers.device.filter import DeviceFilter
from .framework.helpers.entity.simple_entity_manager import (
    SimpleEntityManager,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _get_feature_details_from_module(feature_key: str) -> dict[str, Any]:
    """Get feature details from AVAILABLE_FEATURES.

    Args:
        feature_key: Feature identifier

    Returns:
        Dictionary with feature details or empty dict if not found
    """
    feature_config = AVAILABLE_FEATURES.get(feature_key, {})
    if not feature_config:
        return {}

    # Extract supported device types from feature configuration
    supported_device_types = feature_config.get("supported_device_types", [])
    if not supported_device_types:
        # Default to HvacVentilator for most features
        supported_device_types = ["HvacVentilator"]

    # For now, return minimal details since entity loading is handled elsewhere
    return {
        "supported_device_types": supported_device_types,
        "required_entities": {},  # Will be populated by entity manager
    }


async def _manage_cards_config_flow(
    hass: "HomeAssistant", enabled_features: dict[str, bool]
) -> None:
    """Install or remove custom cards based on enabled features (for config flow)."""
    # Use the new /local/ramses_extras path structure instead of www/community
    www_local_path = Path(hass.config.path("local")) / "ramses_extras"

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        # Skip default feature from card management (it's not a card feature)
        if feature_key == "default":
            continue

        # Get card info from the registry
        from .extras_registry import extras_registry

        card_info = extras_registry.get_card_config(feature_key) or {}

        # Use the location from the card_info or feature key
        card_source_path = (
            INTEGRATION_DIR / CARD_FOLDER / card_info.get("location", feature_key)
        )
        card_dest_path = www_local_path / "features" / feature_key

        if enabled_features.get(feature_key, False):
            if card_source_path.exists():
                # For automatic registration, we don't need to copy files anymore
                # The card is registered as a static resource in async_setup_entry
                _LOGGER.info(f"Card {feature_key} is automatically registered")
            else:
                # Only warn if this feature actually has a card_config
                # Some features don't have frontend cards
                # (e.g., sensor_control, humidity_control)
                if card_info:
                    _LOGGER.warning(
                        f"Cannot register {feature_key}: {card_source_path} not found"
                    )
                else:
                    _LOGGER.debug(
                        f"Feature {feature_key} has no card configuration, skipping"
                    )
        else:
            # Remove card from community folder if it exists
            await _remove_card_config_flow(hass, card_dest_path)


async def _install_card_config_flow(
    hass: "HomeAssistant", source_path: Path, dest_path: Path
) -> None:
    """Install a custom card by copying files (for config flow)."""
    try:
        if source_path.exists():
            # Create destination directory if it doesn't exist
            dest_path.mkdir(parents=True, exist_ok=True)

            # Copy all files from source to destination using executor
            await hass.async_add_executor_job(
                _copy_card_files_config_flow, source_path, dest_path
            )

            _LOGGER.info(f"Successfully installed card to {dest_path}")
        else:
            _LOGGER.warning(f"Card source path does not exist: {source_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to install card: {e}")


def _copy_card_files_config_flow(source_path: Path, dest_path: Path) -> None:
    """Copy card files from source to destination (runs in executor)."""
    for file_path in source_path.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(source_path)
            dest_file_path = dest_path / relative_path

            # Create subdirectories if needed
            dest_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(file_path, dest_file_path)


async def _remove_card_config_flow(hass: "HomeAssistant", card_path: Path) -> None:
    """Remove a custom card (for config flow)."""
    try:
        if card_path.exists():
            await hass.async_add_executor_job(shutil.rmtree, card_path)
            _LOGGER.info(f"Successfully removed card from {card_path}")
        else:
            _LOGGER.debug(f"Card path does not exist, nothing to remove: {card_path}")
    except Exception as e:
        _LOGGER.error(f"Failed to remove card: {e}")


@HANDLERS.register(DOMAIN)
class RamsesExtrasConfigFlow(ConfigFlow):
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Check if we already have an entry for this domain
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            return self.async_abort(reason="single_instance_allowed")

        # No user input needed for single-instance integration
        # Just create the config entry directly
        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            # Default feature is always enabled, others start disabled
            if feature_key == "default":
                enabled_features[feature_key] = True
            else:
                enabled_features[feature_key] = (
                    False  # Start with all optional features disabled
                )

        return self.async_create_entry(
            title="Ramses Extras",
            data={
                CONF_NAME: "Ramses Extras",
                CONF_ENABLED_FEATURES: enabled_features,
            },
        )

    @classmethod
    def async_get_options_flow(
        cls, config_entry: ConfigEntry
    ) -> "RamsesExtrasOptionsFlowHandler":
        """Return options flow handler for existing config entries."""
        return RamsesExtrasOptionsFlowHandler(config_entry)


class RamsesExtrasOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Ramses Extras."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_data: dict[str, Any] | None = None
        self._entity_manager: SimpleEntityManager | None = (
            None  # Will be initialized when needed
        )
        self._config_flow_helper: ConfigFlowHelper | None = None
        self._feature_changes_detected = False
        # Do not uncomment the next lines !!!! change the testfile if needed.
        # We must not set these or the confirm step will fail
        # self._matrix_entities_to_remove: list[str] = []
        # self._matrix_entities_to_create: list[str] = []
        self._selected_feature: str | None = None
        self._all_devices: list[Any] | None = None
        self._features_for_device_config: list[str] | None = None

    def _refresh_config_entry(self, hass: HomeAssistant) -> None:
        entry_id = getattr(self._config_entry, "entry_id", None)
        config_entries = getattr(hass, "config_entries", None)
        if not entry_id or config_entries is None:
            return

        latest = config_entries.async_get_entry(entry_id)
        if latest is not None and latest is not self._config_entry:
            self._config_entry = latest
        if self._config_flow_helper is not None:
            self._config_flow_helper.config_entry = self._config_entry

    async def async_step_init(
        self, user_input: dict[str, list[str]] | None = None
    ) -> FlowResult:
        """Handle options initialization - redirect to main menu."""
        return await self.async_step_main_menu()

    async def async_step_main_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the main configuration menu with ramses_cc style
        link/button navigation."""

        self._refresh_config_entry(self.hass)

        # Build main menu options with ramses_cc style (links/buttons, not dropdowns)
        # Menu options must be a list of step IDs; labels are provided via translations
        menu_options: list[str] = []

        # Add static menu options; step IDs must match async_step_* method names
        static_menu_items = {
            "features": "Enable/Disable Features",
            "advanced_settings": "Advanced Settings",
        }

        for static_item, static_label in static_menu_items.items():
            menu_options.append(static_item)
            # _LOGGER.info(f"DEBUG: Added static menu item: {static_item}
            #  -> {static_label}")

        # Add dynamic feature options for features with config flows
        # Only list features that are actually enabled in the config entry
        dynamic_features_found = []
        current_features = (self._config_entry.data or {}).get("enabled_features", {})
        for feature_id, feature_config in AVAILABLE_FEATURES.items():
            # Don't Skip default feature from menu (we may have settings for it)
            # if feature_id == "default":
            #     _LOGGER.info("DEBUG: Skipping default feature from menu")
            #     continue

            if feature_id == "ramses_debugger":
                if current_features.get(feature_id):
                    step_id = f"feature_{feature_id}"
                    menu_options.append(step_id)
                    dynamic_features_found.append(feature_id)
                continue

            # Only add features that have device configuration (has_device_config: True)
            if feature_config.get("has_device_config", False):
                # Skip features that are not enabled
                if not current_features.get(feature_id):
                    # _LOGGER.info(
                    #     "DEBUG: Feature %s is not enabled, skipping", feature_id
                    # )
                    continue

                # Use feature-specific step IDs that map to
                # async_step_feature_* handlers
                step_id = f"feature_{feature_id}"
                menu_options.append(step_id)
                dynamic_features_found.append(feature_id)
                # _LOGGER.info(
                #     f"DEBUG: Added dynamic menu item: {step_id} -> "
                #     f"{feature_config.get('name', feature_id)}"
                # )
            else:
                _LOGGER.debug(
                    f"Feature {feature_id} does not have "
                    f"has_device_config=True, skipping"
                )

        _LOGGER.debug(f"Dynamic features found: {dynamic_features_found}")

        # Get current configuration summary
        enabled_count = sum(
            1
            for enabled in current_features.values()
            if enabled and not isinstance(enabled, str)
        )

        info_text = "🎛️ **Ramses Extras Configuration**\n\n"
        info_text += f"Currently have {enabled_count} features enabled.\n"
        info_text += "Choose what you want to configure:"

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Current language: %s", self.hass.config.language)
            _LOGGER.debug("Translation domain: %s", DOMAIN)

        return self.async_show_menu(
            step_id="main_menu",
            menu_options=menu_options,
            description_placeholders={"info": info_text},
        )

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle enable/disable features step."""
        self._refresh_config_entry(self.hass)
        # Get current enabled features
        current_features = (self._config_entry.data or {}).get("enabled_features", {})
        enabled_features = {k: v for k, v in current_features.items() if k != "default"}

        # Get config flow helper
        helper = self._get_config_flow_helper()

        if user_input is not None:
            # User submitted feature selection - stage changes for confirmation
            selected_features = user_input.get("features", [])

            # Build new enabled_features mapping including default
            staged_enabled_features: dict[str, bool] = {"default": True}
            for feature_id in AVAILABLE_FEATURES.keys():
                if feature_id == "default":
                    continue  # Skip default feature in selector
                staged_enabled_features[feature_id] = feature_id in selected_features

            if self._pending_data is None:
                self._pending_data = {}

            assert self._pending_data is not None
            self._pending_data["enabled_features_old"] = current_features
            self._pending_data["enabled_features_new"] = staged_enabled_features
            self._feature_changes_detected = staged_enabled_features != current_features

            return await self.async_step_confirm()

        # Build feature selection schema
        schema = helper.get_feature_selection_schema(enabled_features)

        # Build info text
        info_text = helper.build_feature_info_text()

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    async def async_step_sensor_control_overview(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show a read-only overview of sensor_control mappings.

        This summarizes per-device mappings for each supported metric, so users
        can quickly see which entities are in use without diving into
        per-device sensor_control submenus.
        """

        # Ensure we have the latest options snapshot
        self._refresh_config_entry(self.hass)

        options = dict(self._config_entry.options)
        sensor_control_options = options.get("sensor_control") or {}
        sources: dict[str, dict[str, dict[str, Any]]] = sensor_control_options.get(
            "sources", {}
        )
        abs_inputs: dict[str, dict[str, Any]] = sensor_control_options.get(
            "abs_humidity_inputs", {}
        )

        device_keys = set(sources.keys()) | set(abs_inputs.keys())

        if not device_keys:
            info_text = (
                "📡 **Sensor Control Overview**\n\n"
                "No sensor control mappings have been configured yet.\n\n"
                "Use the Sensor Control feature menu to assign sensors per device."
            )
            return self.async_show_form(
                step_id="sensor_control_overview",
                description_placeholders={"info": info_text},
                data_schema=vol.Schema({}),
            )

        # Build per-device summary, showing only non-internal mappings and
        # including abs_humidity_inputs for the abs humidity metrics.
        lines: list[str] = ["📡 **Sensor Control Overview**\n"]

        # Sort device keys for stable display
        for device_key in sorted(device_keys):
            device_sources = sources.get(device_key) or {}
            device_abs_inputs = abs_inputs.get(device_key) or {}
            # Convert back to colon-separated device id for readability
            device_id = device_key.replace("_", ":")

            device_lines: list[str] = []

            # Show metrics in a fixed order using SUPPORTED_METRICS
            for metric in SUPPORTED_METRICS:
                if metric in ("indoor_abs_humidity", "outdoor_abs_humidity"):
                    metric_cfg = device_abs_inputs.get(metric) or {}
                    temp_cfg = metric_cfg.get("temperature") or {}
                    hum_cfg = metric_cfg.get("humidity") or {}
                    temp_kind = str(temp_cfg.get("kind") or "internal")
                    hum_kind = str(hum_cfg.get("kind") or "internal")

                    abs_parts: list[str] = []
                    if temp_kind == "external_abs":
                        ent = temp_cfg.get("entity_id")
                        if ent:
                            abs_parts.append(f"external abs → {ent}")
                        else:
                            abs_parts.append("external abs (no entity)")
                    else:
                        if temp_kind in ("external", "external_temp"):
                            ent = temp_cfg.get("entity_id")
                            if ent:
                                abs_parts.append(f"temp: external → {ent}")
                        if hum_kind == "external":
                            ent = hum_cfg.get("entity_id")
                            if ent:
                                abs_parts.append(f"humidity: external → {ent}")
                        if hum_kind == "none":
                            abs_parts.append("humidity: none")

                    if not abs_parts:
                        continue

                    summary = "; ".join(abs_parts)
                    device_lines.append(f"- {metric}: {summary}")
                else:
                    override = device_sources.get(metric) or {}
                    kind = str(override.get("kind") or "internal")
                    entity_id = override.get("entity_id")

                    if kind == "internal":
                        continue
                    if kind in ("external", "external_entity"):
                        if entity_id:
                            summary = f"external → {entity_id}"
                        else:
                            summary = "external (no entity)"
                    elif kind == "derived":
                        summary = "derived"
                    elif kind == "none":
                        summary = "disabled"
                    else:
                        summary = f"{kind}"

                    device_lines.append(f"- {metric}: {summary}")

            if not device_lines:
                continue

            lines.append(f"\n**Device {device_id}** ({device_key}):")
            lines.extend(device_lines)

        info_text = "\n".join(lines)

        return self.async_show_form(
            step_id="sensor_control_overview",
            description_placeholders={"info": info_text},
            data_schema=vol.Schema({}),
        )

    async def async_step_advanced_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle advanced settings step."""
        self._refresh_config_entry(self.hass)

        if user_input is not None:
            new_options = dict(self._config_entry.options)

            frontend_log_level = user_input.get("frontend_log_level")
            if isinstance(frontend_log_level, str) and frontend_log_level:
                new_options["frontend_log_level"] = frontend_log_level
            else:
                new_options["frontend_log_level"] = "info"

            # Keep legacy boolean for compatibility with older configs/tests.
            new_options["debug_mode"] = new_options["frontend_log_level"] == "debug"

            log_level = user_input.get("log_level")
            if isinstance(log_level, str) and log_level:
                new_options["log_level"] = log_level
            else:
                new_options["log_level"] = "info"

            self.hass.config_entries.async_update_entry(
                self._config_entry,
                options=new_options,
            )

            return await self.async_step_main_menu()

        current_options = dict(self._config_entry.options)
        frontend_log_default_raw = current_options.get("frontend_log_level")
        if isinstance(frontend_log_default_raw, str) and frontend_log_default_raw:
            frontend_log_default = frontend_log_default_raw
        else:
            # Migrate default from legacy boolean.
            frontend_log_default = (
                "debug" if bool(current_options.get("debug_mode", False)) else "info"
            )
        log_default = str(current_options.get("log_level", "info"))

        # Show advanced settings form
        data_schema = vol.Schema(
            {
                vol.Optional(
                    "frontend_log_level",
                    default=frontend_log_default,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="debug", label="Debug"),
                            selector.SelectOptionDict(value="info", label="Info"),
                            selector.SelectOptionDict(value="warning", label="Warning"),
                            selector.SelectOptionDict(value="error", label="Error"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "log_level",
                    default=log_default,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="debug", label="Debug"),
                            selector.SelectOptionDict(value="info", label="Info"),
                            selector.SelectOptionDict(value="warning", label="Warning"),
                            selector.SelectOptionDict(value="error", label="Error"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=data_schema,
        )

    async def async_step_feature_ramses_debugger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle ramses_debugger feature configuration."""
        self._selected_feature = "ramses_debugger"
        return await self.async_step_feature_config(user_input)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirmation step after feature or device configuration.

        This step summarizes pending changes and applies them once confirmed,
        before returning to the main menu.
        """
        helper = self._get_config_flow_helper()

        current_features = (self._config_entry.data or {}).get("enabled_features", {})
        pending = self._pending_data or {}

        staged_enabled_features = pending.get("enabled_features_new", current_features)

        if user_input is not None:
            # Apply staged feature changes, if any
            if staged_enabled_features != current_features:
                new_data = dict(self._config_entry.data)
                new_data["enabled_features"] = staged_enabled_features

                # Clean up device_feature_matrix to remove disabled features
                device_feature_matrix = new_data.get("device_feature_matrix", {})
                for device_id in device_feature_matrix:
                    device_features = device_feature_matrix[device_id]
                    # Remove features that are now disabled
                    device_feature_matrix[device_id] = {
                        feature_id: enabled
                        for feature_id, enabled in device_features.items()
                        if staged_enabled_features.get(feature_id, False)
                    }
                new_data["device_feature_matrix"] = device_feature_matrix

                new_options = dict(self._config_entry.options)
                options_matrix = new_options.get("device_feature_matrix")
                if isinstance(options_matrix, Mapping):
                    cleaned_matrix: dict[str, dict[str, bool]] = {}
                    for device_id, device_features in options_matrix.items():
                        if not isinstance(device_features, Mapping):
                            continue
                        cleaned_matrix[str(device_id)] = {
                            feature_id: bool(enabled)
                            for feature_id, enabled in device_features.items()
                            if staged_enabled_features.get(feature_id, False)
                        }
                    new_options["device_feature_matrix"] = cleaned_matrix

                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=new_data,
                    options=new_options,
                )

                # Update cards based on new feature set
                await _manage_cards_config_flow(self.hass, staged_enabled_features)

                # Clean up orphaned devices after feature changes
                from .framework.setup.devices import cleanup_orphaned_devices

                await cleanup_orphaned_devices(self.hass, self._config_entry)

            # Reset pending state and return to main menu
            self._pending_data = {}
            self._feature_changes_detected = False

            return await self.async_step_main_menu()

        # Build summary of feature changes
        feature_change_lines: list[str] = []
        if staged_enabled_features != current_features:
            for feature_id, old_value in current_features.items():
                new_value = bool(staged_enabled_features.get(feature_id, False))
                if bool(old_value) != new_value:
                    feature_name = AVAILABLE_FEATURES.get(feature_id, {}).get(
                        "name", feature_id
                    )
                    state = "ENABLED" if new_value else "DISABLED"
                    feature_change_lines.append(
                        f"- {feature_name} ({feature_id}): {state}"
                    )

        # Add high-level feature/device summary from helper
        feature_device_summary = helper.get_feature_device_summary()

        # Add a brief summary of current sensor_control mappings so that
        # sensor-related changes are visible in the confirmation step.
        sensor_control_summary = ""
        try:
            options = dict(self._config_entry.options)
            sensor_control_options = options.get("sensor_control") or {}
            sources: dict[str, dict[str, Any]] = sensor_control_options.get(
                "sources", {}
            )
            if sources:
                device_ids = [key.replace("_", ":") for key in sorted(sources.keys())]
                joined_ids = ", ".join(device_ids)
                sensor_control_summary = (
                    "\nSensor control mappings are configured for devices: "
                    f"{joined_ids}."
                )
        except Exception:
            # Best-effort only; do not break the confirm step if options are
            # unexpectedly shaped.
            sensor_control_summary = ""

        info_text = "✅ **Confirm configuration changes**\n\n"
        if feature_change_lines:
            info_text += "Feature changes:\n" + "\n".join(feature_change_lines) + "\n\n"

        info_text += feature_device_summary

        if sensor_control_summary:
            info_text += sensor_control_summary + "\n"

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info_text},
        )

    """ Generic Step Feature Config
    If a Feature does not have it's own config_flow.py and step implemented,
    then we use this"""

    async def generic_step_feature_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle configuration for a feature using the generic flow."""
        self._refresh_config_entry(self.hass)
        if not hasattr(self, "_selected_feature"):
            # This should not happen if called from the menu
            return self.async_abort(reason="invalid_feature")

        feature_id = self._selected_feature
        if not feature_id:
            return self.async_abort(reason="invalid_feature")
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})

        # Get devices for this feature using the central helpers
        devices = self._get_all_devices()  # noqa: SLF001
        helper = self._get_config_flow_helper()

        _LOGGER.debug("Using generic config flow for %s", feature_id)
        # Restore matrix state to see current device assignments
        matrix_state = self._get_persisted_matrix_state()
        if matrix_state:
            helper.restore_matrix_state(matrix_state)
            _LOGGER.debug("Restored matrix state with %d devices", len(matrix_state))
        else:
            _LOGGER.debug("No matrix state found, starting with empty matrix")

        _LOGGER.debug(f"matrix state: {matrix_state}")
        # Save the matrix state to be used for comparison to the flow
        # Use deepcopy, or helper.set_enabled_devices_for_feature will modify flow
        self._old_matrix_state = deepcopy(matrix_state)

        # Get devices for this feature
        devices = self._get_all_devices()
        filtered_devices = helper.get_devices_for_feature_selection(
            feature_config, devices
        )
        current_enabled = helper.get_enabled_devices_for_feature(feature_id)
        _LOGGER.debug(
            f"Devices: filtered: {filtered_devices} Current enabled: {current_enabled}"
        )

        if user_input is not None:  # POST processing
            _LOGGER.debug("User submitted the form (post)")
            # User submitted the form - process device selections
            selected_device_ids = user_input.get("enabled_devices", [])

            # Store the new device configuration for this feature
            helper.set_enabled_devices_for_feature(feature_id, selected_device_ids)

            # Save the rest of the states to the flow
            temp_matrix_state = helper.get_feature_device_matrix_state()
            if not temp_matrix_state:
                temp_matrix_state = {
                    # device_id: {feature_id: True} for device_id in selected_device_ids
                }
            self._selected_feature = feature_id
            self._temp_matrix_state = temp_matrix_state

            _LOGGER.debug(
                "Staged device selection for feature %s: selected=%s matrix_devices=%s",
                feature_id,
                selected_device_ids,
                sorted(temp_matrix_state.keys()),
            )

            # Log the matrix state for debugging
            _LOGGER.debug(f"self.temp matrix state: {self._temp_matrix_state}")
            _LOGGER.debug(f"self.old_matrix_state: {self._old_matrix_state}")

            # Log entity tracking attributes, check if they exist first
            entities_to_create = getattr(self, "_matrix_entities_to_create", [])
            entities_to_remove = getattr(self, "_matrix_entities_to_remove", [])
            _LOGGER.debug("Entities to create: %d", len(entities_to_create))
            _LOGGER.debug("Entities to remove: %d", len(entities_to_remove))

            # Route through the matrix-based confirm step so changes are summarized
            return await self._show_matrix_based_confirmation()

        # PRE processing (show options)
        _LOGGER.debug("Build device options (pre)")
        # Build device options (value = device_id, label = human readable name)
        device_options = [
            selector.SelectOptionDict(
                value=dev_id,
                label=self._get_device_label(dev),
            )
            for dev in filtered_devices
            if (dev_id := self._extract_device_id(dev))
        ]

        # Create schema for device selection
        # Use LIST mode so the UI renders as a list of checkboxes instead of
        # a dropdown with multi-select chips.
        schema = vol.Schema(
            {
                vol.Required(
                    "enabled_devices", default=current_enabled
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        feature_name = feature_config.get("name", feature_id)
        info_text = f"🎛️ **{feature_name} Configuration**\n\n"
        info_text += f"Select devices to enable {feature_name} for:\n"

        # Reuse the generic "feature_config" step translations from the
        # root translations file; the detailed text comes from info_text.
        return self.async_show_form(
            step_id="feature_config",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    """ Check if the feature has implemented this or use a generic handler
    Routes to one of these:
        - custom_components.ramses_extras.features.{feature_id}.config_flow.
            async_step_{feature_id}_config()
        - self.generic_step_feature_config()
    """

    async def async_step_feature_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle feature configuration step."""
        self._refresh_config_entry(self.hass)
        _LOGGER.debug("async_step_feature_config called")

        if not hasattr(self, "_selected_feature") or not self._selected_feature:
            _LOGGER.warning("No selected feature, redirecting to main menu")
            return await self.async_step_main_menu()

        feature_id = self._selected_feature

        # Check if feature has its own config flow and use it if available
        try:
            feature_config_flow_module = "custom_components.ramses_extras.features."
            feature_config_flow_module += f"{feature_id}.config_flow"

            feature_config_flow = __import__(feature_config_flow_module, fromlist=[""])

            # Look for a function named async_step_{feature_id}_config
            config_function_name = f"async_step_{feature_id}_config"
            if hasattr(feature_config_flow, config_function_name):
                config_function = getattr(feature_config_flow, config_function_name)
                _LOGGER.info(f"📦 Using feature-specific config flow for {feature_id}")
                # Support both async and sync feature-specific config flows.
                if asyncio.iscoroutinefunction(config_function):
                    return await config_function(self, user_input)

                result = config_function(self, user_input)
                if inspect.isawaitable(result):
                    return await result

                return result

            _LOGGER.debug(
                f"Feature {feature_id} has config_flow.py but no "
                f"{config_function_name} function"
            )
        except ImportError:
            _LOGGER.debug(
                f"No feature-specific config flow found for {feature_id}, "
                f"using generic flow"
            )
        except Exception as e:
            _LOGGER.warning(f"Error loading feature config flow for {feature_id}: {e}")

        return await self.generic_step_feature_config(user_input)

    async def async_step_device_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device selection step."""
        self._refresh_config_entry(self.hass)
        if not hasattr(self, "_selected_feature") or not self._selected_feature:
            # Fallback to main menu if no feature is selected
            return await self.async_step_main_menu()

        feature_id = self._selected_feature
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})

        # Get devices for this feature
        devices = self._get_all_devices()
        filtered_devices = (
            self._get_config_flow_helper().get_devices_for_feature_selection(
                feature_config, devices
            )
        )

        # Get current enabled devices for this feature
        current_enabled = (
            self._get_config_flow_helper().get_enabled_devices_for_feature(feature_id)
        )

        # Create device selection options
        device_options = [
            selector.SelectOptionDict(
                value=device_id, label=self._get_device_label(device)
            )
            for device in filtered_devices
            if (device_id := self._extract_device_id(device))
        ]

        option_values = {opt["value"] for opt in device_options}
        current_enabled = [d for d in current_enabled if d in option_values]

        # Create schema for device selection
        schema = vol.Schema(
            {
                vol.Required(
                    "enabled_devices", default=current_enabled
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        feature_name = feature_config.get("name", feature_id)
        info_text = f"🎛️ **{feature_name} Device Selection**\n\n"
        info_text += f"Select devices to enable {feature_name} for:\n"

        return self.async_show_form(
            step_id="device_selection",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    def _store_feature_device_config(
        self, feature_id: str, device_ids: list[str]
    ) -> None:
        """Store feature/device configuration."""
        helper = self._get_config_flow_helper()
        helper.set_enabled_devices_for_feature(feature_id, device_ids)
        # DON'T save matrix state here - we need the old state for entity calculation
        # self._save_matrix_state()

    def _get_all_devices(self) -> list[Any]:
        """Get all available devices."""
        if hasattr(self.hass, "data") and "ramses_extras" in self.hass.data:
            devices = self.hass.data["ramses_extras"].get("devices", [])
            return devices if isinstance(devices, list) else []
        return []

    def _extract_device_id(self, device: Any) -> str | None:
        """Extract device ID from device object."""
        if isinstance(device, str):
            return device

        if hasattr(device, "id"):
            return str(device.id)
        if hasattr(device, "device_id"):
            return str(device.device_id)
        if hasattr(device, "_id"):
            return str(device._id)
        if hasattr(device, "name"):
            return str(device.name)

        return None

    def _get_device_label(self, device: Any) -> str:
        """Get display label for a device."""
        if isinstance(device, str):
            base_label = device
        elif hasattr(device, "name"):
            base_label = str(device.name)
        elif hasattr(device, "device_id"):
            base_label = str(device.device_id)
        elif hasattr(device, "id"):
            base_label = str(device.id)
        else:
            base_label = "Unknown Device"

        # Try to enrich the label with device slugs when available so users
        # can see both the ID and the logical slug (e.g. FAN).
        try:
            slugs = DeviceFilter._get_device_slugs(device)
            if slugs:
                # Remove duplicates and avoid repeating the base label as slug
                unique_slugs = sorted({str(slug) for slug in slugs if str(slug)})
                slugs_label = ", ".join(unique_slugs)
                if slugs_label and slugs_label != base_label:
                    return f"{base_label} [{slugs_label}]"
        except Exception:  # pragma: no cover - defensive, should not happen
            pass

        return base_label

    def _get_config_flow_helper(self) -> ConfigFlowHelper:
        """Get or create config flow helper."""
        if self._config_flow_helper is None:
            self._config_flow_helper = ConfigFlowHelper(self.hass, self._config_entry)
        return self._config_flow_helper

    async def _get_feature_title_from_translations(self, feature_id: str) -> str:
        """Get feature title from feature-specific translations if available.

        Falls back to the feature name from AVAILABLE_FEATURES when no
        feature-specific translation file is present.
        """
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})
        default_title = str(feature_config.get("name", feature_id))

        language = getattr(self.hass.config, "language", "en") or "en"

        base_path = Path(__file__).parent / "features" / feature_id / "translations"
        translations_path = base_path / f"{language}.json"
        if not translations_path.exists():
            translations_path = base_path / "en.json"
            if not translations_path.exists():
                return default_title

        def _load_title(path: Path, fallback: str) -> str:
            try:
                with path.open(encoding="utf-8") as file:
                    data: dict[str, Any] = json.load(file)
                title = (
                    data.get("config", {})
                    .get("step", {})
                    .get(f"feature_{feature_id}", {})
                    .get("title", fallback)
                )
                return str(title) if title else fallback
            except Exception:
                return fallback

        # Handle both real hass objects and mock objects (for testing)
        # Check if hass is a MagicMock (used in tests) by checking the type name
        if (
            hasattr(self.hass, "__class__") and "MagicMock" in str(self.hass.__class__)
        ) or not hasattr(self.hass, "async_add_executor_job"):  # noqa: E501
            # For mock objects in tests, call the function directly
            result = _load_title(translations_path, default_title)
        else:
            result = await self.hass.async_add_executor_job(
                _load_title, translations_path, default_title
            )
        return str(result)

    # Add handler for dynamic feature menu items
    async def async_step_feature_default(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle default configuration via feature-specific helper.

        This method stays as the Home Assistant entrypoint but delegates the
        actual form building to the feature's own config_flow helper so that
        the default feature can serve as an example for other features.
        """
        _LOGGER.debug("async_step_feature_default called")

        # CRITICAL FIX: Set the selected feature before calling the default config flow
        # This ensures that async_step_feature_config can properly route the flow
        self._selected_feature = "default"
        _LOGGER.debug("Set _selected_feature to: %s", self._selected_feature)

        try:
            from .features.default import config_flow as default_config_flow

            _LOGGER.debug("Importing default config flow module")
            result = await default_config_flow.async_step_default_config(
                self, user_input
            )
            _LOGGER.debug("Default config flow completed")
            return result

        except Exception as e:
            _LOGGER.error("Error in async_step_feature_default: %s", e)
            _LOGGER.debug("Full traceback: %s", traceback.format_exc())
            # Fallback to main menu if there's an error
            return await self.async_step_main_menu()

    async def async_step_feature_humidity_control(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle humidity control feature configuration."""
        self._selected_feature = "humidity_control"
        return await self.async_step_feature_config(user_input)

    async def async_step_feature_hvac_fan_card(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle HVAC fan card feature configuration.

        The HVAC fan card does not require per-device configuration. This
        step therefore only shows an informational message and no form
        fields, so the user can see that the card is enabled without
        having to select devices.
        We could have created a config_flow.py file in the features folder.
        """
        feature_id = "hvac_fan_card"
        feature_config = AVAILABLE_FEATURES.get(feature_id, {})
        feature_name = feature_config.get("name", feature_id)

        info_text = "🎴 **" + str(feature_name) + "**\n\n"
        info_text += (
            "This feature only installs and registers the HVAC fan card. "
            "No additional configuration is required."
        )

        # Reuse the generic feature_config step translations by using the
        # existing step_id but with an empty schema.
        return self.async_show_form(
            step_id="feature_config",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info_text},
        )

    async def async_step_feature_hello_world(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle hello world card feature configuration."""
        self._selected_feature = "hello_world"
        return await self.async_step_feature_config(user_input)

    async def async_step_feature_sensor_control(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle sensor control feature configuration."""
        self._selected_feature = "sensor_control"
        return await self.async_step_feature_config(user_input)

    # Matrix State Persistence Methods
    def _get_persisted_matrix_state(self) -> dict[str, dict[str, bool]]:
        self._refresh_config_entry(self.hass)

        options = self._config_entry.options
        if isinstance(options, Mapping):
            opts_matrix = options.get("device_feature_matrix")
            if isinstance(opts_matrix, Mapping):
                return {
                    str(device_id): dict(features)
                    for device_id, features in opts_matrix.items()
                    if isinstance(features, Mapping)
                }

        data = self._config_entry.data
        if isinstance(data, Mapping):
            data_matrix = data.get("device_feature_matrix")
            if isinstance(data_matrix, Mapping):
                return {
                    str(device_id): dict(features)
                    for device_id, features in data_matrix.items()
                    if isinstance(features, Mapping)
                }

        return {}

    def _persist_matrix_state(self, matrix_state: dict[str, dict[str, bool]]) -> None:
        self._refresh_config_entry(self.hass)

        new_options = dict(self._config_entry.options)
        new_options["device_feature_matrix"] = {
            str(device_id): dict(features)
            for device_id, features in matrix_state.items()
        }

        new_data = dict(self._config_entry.data)
        new_data["device_feature_matrix"] = {
            str(device_id): dict(features)
            for device_id, features in matrix_state.items()
        }

        self.hass.config_entries.async_update_entry(
            self._config_entry,
            options=new_options,
            data=new_data,
        )
        self._refresh_config_entry(self.hass)

    def _save_matrix_state(self) -> None:
        """Save current matrix state to config entry options."""
        self._refresh_config_entry(self.hass)
        matrix_state = self._get_config_flow_helper().get_feature_device_matrix_state()
        self._persist_matrix_state(matrix_state)
        _LOGGER.debug("Saved matrix state with %d devices", len(matrix_state))

    def _restore_matrix_state(self) -> None:
        """Restore matrix state from config entry."""
        self._refresh_config_entry(self.hass)
        matrix_state = self._get_persisted_matrix_state()
        if matrix_state:
            self._get_config_flow_helper().restore_matrix_state(matrix_state)
            _LOGGER.debug("Restored matrix state with %d devices", len(matrix_state))

    async def _reload_platforms_for_entity_creation(self) -> None:
        """Reload platforms to create entities after configuration changes.

        This method triggers platform reloads to let Home Assistant's platform system
        create entities properly with the real async_add_entities callback.
        """
        _LOGGER.info("Reloading platforms for entity creation...")

        try:
            # Use platform reload approach - this is the correct way
            # Home Assistant's platform system will call the setup functions
            # with the proper async_add_entities callback
            await self._direct_platform_reload()

            _LOGGER.debug("Platform reload sequence completed")

        except Exception as e:
            _LOGGER.error("Error with platform reload: %s", e)
            # Don't re-raise - platform reload failure shouldn't break config flow

    async def _direct_platform_reload(self) -> None:
        """Fallback method for direct platform reloading."""
        _LOGGER.debug("Using direct platform reload...")

        try:
            # Reload the config entry to trigger platform setup
            # This will cause Home Assistant to call the platform setup functions
            # with the proper async_add_entities callback
            _LOGGER.debug(f"Reloading config entry {self._config_entry.entry_id}...")
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            _LOGGER.debug("Successfully reloaded config entry")

            _LOGGER.debug("Direct platform reload sequence completed")

        except Exception as e:
            _LOGGER.error("Error during direct platform reload: %s", e)
            # Don't re-raise - platform reload failure shouldn't break config flow

    async def _show_matrix_based_confirmation(self) -> FlowResult:
        """Show confirmation with matrix-based entity changes."""
        _LOGGER.debug("_show_matrix_based_confirmation called")
        # Ensure we have the latest entity lists
        if hasattr(self, "_matrix_entities_to_create") and hasattr(
            self, "_matrix_entities_to_remove"
        ):
            entities_to_create = self._matrix_entities_to_create
            entities_to_remove = self._matrix_entities_to_remove
            _LOGGER.debug(
                "Using pre-computed entities - create=%d remove=%d",
                len(entities_to_create),
                len(entities_to_remove),
            )
        else:
            # Fallback: compute entity changes if not already pre-computed
            _LOGGER.debug("Computing entity changes for confirmation")

            # Use SimpleEntityManager for entity management
            entity_manager = SimpleEntityManager(self.hass)

            # Prefer using the temporary matrix state when available so we can
            # show the diff between the current config entry state and the
            # user's new selections.
            temp_matrix_state = getattr(self, "_temp_matrix_state", None)
            # Prefer the per-flow snapshot if present
            old_matrix_state = getattr(self, "_old_matrix_state", None)
            if (old_matrix_state is None) or (old_matrix_state == {}):
                old_matrix_state = self._get_persisted_matrix_state()

            _LOGGER.debug("Temp matrix state devices=%s", len(temp_matrix_state or {}))
            _LOGGER.debug("Old matrix state devices=%s", len(old_matrix_state or {}))

            if temp_matrix_state is not None:
                (
                    entities_to_create,
                    entities_to_remove,
                ) = await entity_manager.calculate_entity_changes(
                    old_matrix_state,
                    temp_matrix_state,
                )
                _LOGGER.debug(
                    "Computed entities from matrix diff - create=%s remove=%s",
                    len(entities_to_create),
                    len(entities_to_remove),
                )
            else:
                # Last-resort: derive required entities from the current matrix only
                matrix_state = old_matrix_state
                if matrix_state:
                    entity_manager.restore_device_feature_matrix_state(matrix_state)

                required_entities = await entity_manager._calculate_required_entities()
                current_entities = await entity_manager._get_current_entities()

                # Entities to create: should exist but don't yet
                entities_to_create = list(
                    set(required_entities) - set(current_entities)
                )

                # Entities to remove: exist but shouldn't
                extra_entities = set(current_entities) - set(required_entities)
                entities_to_remove = [
                    entity
                    for entity in extra_entities
                    if entity_manager._is_managed_entity(entity)
                ]

                _LOGGER.debug(
                    "Computed entities from current state - create=%s remove=%s",
                    len(entities_to_create),
                    len(entities_to_remove),
                )

        info_text = "🔄 **Confirm Device Configuration Changes**\n\n"

        # Add information about what was configured
        if hasattr(self, "_selected_feature") and self._selected_feature:
            feature_config = AVAILABLE_FEATURES.get(self._selected_feature, {})
            feature_name = feature_config.get("name", self._selected_feature)
            info_text += f"You have configured the **{feature_name}** feature.\n\n"

        # Initialize matrix variable to avoid UnboundLocalError
        # Use the shared helper as fallback to ensure matrix is always defined
        matrix = self._get_config_flow_helper().device_feature_matrix

        # Show selected devices - use the TEMPORARY matrix state that was calculated
        # Don't use the shared helper to avoid caching issues
        if hasattr(self, "_selected_feature") and self._selected_feature:
            # Create a temporary helper with the current selections
            #  to get the correct matrix state
            temp_helper = ConfigFlowHelper(self.hass, self._config_entry)

            # Get current enabled devices for this feature from the temporary helper
            current_enabled = (
                self._get_config_flow_helper().get_enabled_devices_for_feature(
                    self._selected_feature
                )
            )
            if current_enabled:
                # Set the current enabled devices in the temp helper
                #  to get correct matrix state
                temp_helper.set_enabled_devices_for_feature(
                    self._selected_feature, current_enabled
                )

                # Get the matrix from the temp helper (clean state)
                matrix = temp_helper.device_feature_matrix
                enabled_devices = matrix.get_enabled_devices_for_feature(
                    self._selected_feature
                )

                if enabled_devices:
                    info_text += f"**Selected devices for {feature_name}:**\n"
                    for device_id in enabled_devices:
                        # Get device label
                        devices = self._get_all_devices()
                        device = next(
                            (
                                d
                                for d in devices
                                if self._extract_device_id(d) == device_id
                            ),
                            None,
                        )
                        if device:
                            device_label = self._get_device_label(device)
                            info_text += f"- {device_label}\n"
                    info_text += "\n"

        # Show entity changes
        if entities_to_create or entities_to_remove:
            info_text += "**Entity changes that will be applied:**\n\n"

            if entities_to_create:
                info_text += f"📝 **Entities to create**: {len(entities_to_create)}\n"
                info_text += f"- {', '.join(entities_to_create[:5])}"
                if len(entities_to_create) > 5:
                    info_text += f" and {len(entities_to_create) - 5} more"
            else:
                info_text += "📝 **Entities to create**: 0"

            if entities_to_remove:
                info_text += (
                    f"\n\n🗑️ **Entities to remove**: {len(entities_to_remove)}\n"
                )
                info_text += f"- {', '.join(entities_to_remove[:5])}"
                if len(entities_to_remove) > 5:
                    info_text += f" and {len(entities_to_remove) - 5} more"
            else:
                info_text += "\n\n🗑️ **Entities to remove**: 0"
        else:
            info_text += "**No entity changes required.**\n"
            info_text += "Your device configuration has been saved successfully.\n\n"
            info_text += "Entities will be created/updated automatically based"
            info_text += " on your device selections.\n"

        # Add matrix state summary
        info_text += "\n📊 **Configuration Summary**: "
        info_text += f"{len(matrix.get_all_enabled_combinations())} "
        info_text += "active device-feature combinations"

        return self.async_show_form(
            step_id="matrix_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info_text},
        )

    async def async_step_matrix_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle matrix-based confirmation."""
        _LOGGER.debug("async_step_matrix_confirm called")

        self._refresh_config_entry(self.hass)
        matrix_state = self._get_persisted_matrix_state()
        _LOGGER.debug("Matrix on entry before confirm: devices=%s", len(matrix_state))

        if user_input is not None:
            # User confirmed the changes - apply them and complete the options flow
            _LOGGER.info("User confirmed matrix changes - applying")

            try:
                # Apply matrix-based entity changes using SimpleEntityManager
                # Use simple entity manager for direct entity management
                entity_manager = SimpleEntityManager(self.hass)

                # CRITICAL FIX: Use the stored temporary matrix state, not the
                #  helper's current state
                # The helper's state may not have the user's new selections
                temp_matrix_state = getattr(self, "_temp_matrix_state", None)
                _LOGGER.debug(
                    "Staged matrix has %s devices",
                    len(temp_matrix_state or {}),
                )

                if temp_matrix_state is not None:
                    # CRITICAL: Use the saved _old_matrix_state to avoid corruption
                    # The config entry may have been modified during the flow,
                    # so we use the originally saved state for accurate comparison
                    old_matrix_state = getattr(self, "_old_matrix_state", None)
                    if old_matrix_state is None:
                        # Fallback to config entry if _old_matrix_state not available
                        old_matrix_state = self._get_persisted_matrix_state()

                    self._persist_matrix_state(temp_matrix_state)
                    _LOGGER.debug(
                        "Persisted new matrix state with %d devices",
                        len(temp_matrix_state),
                    )

                    # Apply the temporary matrix state to entity manager
                    #  (now with latest saved state)
                    entity_manager.restore_device_feature_matrix_state(
                        temp_matrix_state
                    )

                    (
                        entities_to_create,
                        entities_to_remove,
                    ) = await entity_manager.calculate_entity_changes(
                        old_matrix_state,  # Use OLD state (saved or from config entry)
                        temp_matrix_state,  # Use NEW state (from user selection)
                    )

                    # Apply the calculated entity changes directly
                    _LOGGER.info(
                        f"Applying entity changes: {len(entities_to_create)} to "
                        f"create, {len(entities_to_remove)} to remove"
                    )

                    # Also update the helper's state to match the config entry
                    helper = self._get_config_flow_helper()
                    helper.restore_matrix_state(temp_matrix_state)
                    _LOGGER.debug("Updated helper with new matrix state")

                    # Store information about entities to be created for platform setup
                    # IMPORTANT: do not create entity-registry-only entries here.
                    # Entity objects must be created by the normal HA platform setup
                    # flow (async_add_entities). Otherwise entities become
                    #  'unavailable'.

                    # Remove extra entities (before platform reload)
                    for entity_id in entities_to_remove:
                        try:
                            await entity_manager.remove_entity(entity_id)
                            _LOGGER.debug("Removed entity: %s", entity_id)
                        except Exception as e:
                            _LOGGER.warning(
                                "Failed to remove entity %s: %s",
                                entity_id,
                                e,
                            )

                    # Clean up devices that no longer have any features enabled
                    from .framework.setup.devices import cleanup_orphaned_devices

                    await cleanup_orphaned_devices(self.hass, self._config_entry)

                    # Reload the config entry to trigger platform setup for new entities
                    # This must happen AFTER entity creation so platforms
                    #  can register them properly
                    await self.hass.config_entries.async_reload(
                        self._config_entry.entry_id
                    )
                    _LOGGER.debug("Reloaded config entry to trigger platform setup")

                # Clear temporary data
                self._matrix_entities_to_create: list = []
                self._matrix_entities_to_remove: list = []

                # Clear selected feature since we're completing the flow
                self._selected_feature = None

                _LOGGER.info(
                    "Matrix changes applied successfully - options flow complete"
                )

                # For options flows, complete by returning a result that ends the flow.
                # IMPORTANT: Do not wipe existing config_entry.options here; other
                # feature-specific config flows (e.g. sensor_control) persist their
                # settings in config_entry.options. Use the latest options snapshot
                # from the config entry so those settings remain intact.
                result_options = dict(self._config_entry.options)
                temp_matrix_state = getattr(self, "_temp_matrix_state", None)
                if isinstance(temp_matrix_state, Mapping):
                    result_options["device_feature_matrix"] = {
                        str(device_id): dict(features)
                        for device_id, features in temp_matrix_state.items()
                        if isinstance(features, Mapping)
                    }
                    _LOGGER.debug(
                        "Returning options with matrix_devices=%s",
                        len(temp_matrix_state),
                    )
                return self.async_create_entry(
                    title="",
                    data=result_options,
                )

            except Exception as e:
                _LOGGER.error("Error applying matrix changes: %s", e)
                _LOGGER.debug("Full traceback: %s", traceback.format_exc())
                # If there's an error, show the confirmation form again
                #  with error message
                return await self._show_matrix_based_confirmation()

        return await self._show_matrix_based_confirmation()

    async def _cleanup_orphaned_devices(
        self,
        old_matrix: dict[str, dict[str, bool]],
        new_matrix: dict[str, dict[str, bool]],
    ) -> None:
        """Clean up devices that no longer have any entities.

        Simple logic: if a device has no entities, it's orphaned and should be removed.
        """
        _LOGGER.debug("Device cleanup: function called")

        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        device_registry = dr.async_get(self.hass)
        entity_registry = er.async_get(self.hass)

        # Get all devices that belong to ramses_extras
        ramses_devices = []
        for device_entry in device_registry.devices.values():
            if (DOMAIN, device_entry.id) in device_entry.identifiers or any(
                identifier[0] == DOMAIN for identifier in device_entry.identifiers
            ):
                ramses_devices.append(device_entry)

        # Find orphaned devices: devices that have no entities
        orphaned_devices = []
        for device_entry in ramses_devices:
            # Check if this device has any entities
            entities = entity_registry.entities.get(device_entry.id, [])
            if not entities:
                # No entities found - this device is orphaned
                device_id = list(device_entry.identifiers)[0][1]  # Extract device ID
                orphaned_devices.append((device_id, device_entry))
                _LOGGER.debug("Found orphaned device: %s (no entities)", device_id)

        if not orphaned_devices:
            _LOGGER.debug("No orphaned devices found")
            return

        _LOGGER.info("Removing %d orphaned devices", len(orphaned_devices))

        # Remove orphaned devices
        for device_id, device_entry in orphaned_devices:
            try:
                if self._config_entry.entry_id in device_entry.config_entries:
                    device_registry.async_remove_device(device_entry.id)
                    _LOGGER.info("Removed orphaned device: %s", device_id)
                else:
                    _LOGGER.debug(
                        f"Device {device_id} not owned by ramses_extras, skipping"
                    )
            except Exception as e:
                _LOGGER.warning(f"Failed to remove device {device_id}: {e}")
