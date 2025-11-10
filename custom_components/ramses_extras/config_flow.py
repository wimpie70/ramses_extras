import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import selector

from .const import (
    AVAILABLE_FEATURES,
    CARD_FOLDER,
    CONF_ENABLED_FEATURES,
    CONF_NAME,
    DEVICE_ENTITY_MAPPING,
    DOMAIN,
    GITHUB_WIKI_URL,
    INTEGRATION_DIR,
)
from .framework.helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def _manage_cards_config_flow(
    hass: "HomeAssistant", enabled_features: dict[str, bool]
) -> None:
    """Install or remove custom cards based on enabled features (for config flow)."""
    www_community_path = Path(hass.config.path("www", "community"))

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        if feature_config.get("category") == "cards":
            # Use the same path resolution as the rest of the code
            card_source_path = (
                INTEGRATION_DIR / CARD_FOLDER / str(feature_config.get("location", ""))
            )
            card_dest_path = www_community_path / feature_key

            if enabled_features.get(feature_key, False):
                if card_source_path.exists():
                    # For automatic registration, we don't need to copy files anymore
                    # The card is registered as a static resource in async_setup_entry
                    _LOGGER.info(f"Card {feature_key} is automatically registered")
                else:
                    _LOGGER.warning(
                        f"Cannot register {feature_key}: {card_source_path} not found"
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


@config_entries.HANDLERS.register(DOMAIN)
class RamsesExtrasConfigFlow(config_entries.ConfigFlow):
    async def async_step_user(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        # Check if we already have an entry for this domain
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            return self.async_abort(reason="single_instance_allowed")

        # No user input needed for single-instance integration
        # Just create the config entry directly
        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = False  # Start with all disabled

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


class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ramses Extras."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_data: dict[str, list[str]] | None = None
        self._cards_deselected: list[str] = []
        self._automations_deselected: list[str] = []
        self._sensors_deselected: list[str] = []
        self._other_deselected: list[str] = []
        self._cards_selected: list[str] = []
        self._automations_selected: list[str] = []
        self._sensors_selected: list[str] = []
        self._other_selected: list[str] = []
        self._newly_enabled_features: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle options initialization - redirect to features step."""
        return await self.async_step_features()

    async def async_step_features(
        self, user_input: dict[str, list[str]] | None = None
    ) -> config_entries.FlowResult:
        """Handle the feature selection step for options."""
        if user_input is not None:
            # Check if any currently enabled features would be disabled
            current_features = self._config_entry.data.get("enabled_features", {})
            selected_features = user_input.get("features", [])

            # Convert selected features to enabled features dict
            enabled_features = {}
            for feature_key in AVAILABLE_FEATURES.keys():
                enabled_features[feature_key] = feature_key in selected_features

            # Check for deselected features
            deselected_features = []
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                currently_enabled = current_features.get(feature_key, False)
                will_be_enabled = enabled_features[feature_key]

                if currently_enabled and not will_be_enabled:
                    deselected_features.append(feature_key)

            if deselected_features:
                # Check what types of features are being deselected
                cards_deselected = [
                    f
                    for f in deselected_features
                    if str(AVAILABLE_FEATURES[f].get("category")) == "cards"
                ]
                sensors_deselected = [
                    f
                    for f in deselected_features
                    if str(AVAILABLE_FEATURES[f].get("category")) == "sensors"
                ]
                automations_deselected = [
                    f
                    for f in deselected_features
                    if str(AVAILABLE_FEATURES[f].get("category")) == "automations"
                ]
                other_deselected = [
                    f
                    for f in deselected_features
                    if str(AVAILABLE_FEATURES[f].get("category"))
                    not in ["cards", "automations", "sensors"]
                ]

                # Check what types of features are being selected
                cards_selected = [
                    f
                    for f in user_input.get("features", [])
                    if str(AVAILABLE_FEATURES[f].get("category")) == "cards"
                ]
                automations_selected = [
                    f
                    for f in user_input.get("features", [])
                    if str(AVAILABLE_FEATURES[f].get("category")) == "automations"
                ]
                sensors_selected = [
                    f
                    for f in user_input.get("features", [])
                    if str(AVAILABLE_FEATURES[f].get("category")) == "sensors"
                ]
                other_selected = [
                    f
                    for f in user_input.get("features", [])
                    if str(AVAILABLE_FEATURES[f].get("category"))
                    not in ["cards", "automations", "sensors"]
                ]

                # Show confirmation if any features are being deselected
                self._pending_data = user_input
                self._cards_deselected = cards_deselected
                self._sensors_deselected = sensors_deselected
                self._automations_deselected = automations_deselected
                self._other_deselected = other_deselected
                self._cards_selected = cards_selected
                self._automations_selected = automations_selected
                self._sensors_selected = sensors_selected
                self._other_selected = other_selected
                return await self.async_step_confirm()

            # No features deselected, check if any features are newly enabled
            newly_enabled_features = []
            for feature_key in user_input.get("features", []):
                if feature_key not in [k for k, v in current_features.items() if v]:
                    newly_enabled_features.append(feature_key)

            if newly_enabled_features:
                # Show confirmation for new feature enabling
                self._pending_data = user_input
                self._newly_enabled_features = newly_enabled_features
                return await self.async_step_confirm()

            return await self._save_config(user_input)

        # Get current enabled features for default values
        current_features = self._config_entry.data.get("enabled_features", {})

        # Ensure all features are present in the config (for backward compatibility)
        if len(current_features) != len(AVAILABLE_FEATURES):
            # Initialize missing features with their default values
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                if feature_key not in current_features:
                    current_features[feature_key] = feature_config.get(
                        "default_enabled", False
                    )

            # Update the config entry with the complete feature set
            new_data = self._config_entry.data.copy()
            new_data["enabled_features"] = current_features
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )

        # Get current selected features for the selector default
        current_selected = [k for k, v in current_features.items() if v]

        # Build options for multi-select
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            feature_name = str(feature_config.get("name", feature_key))
            description = str(feature_config.get("description", ""))
            if description:
                short_desc = (
                    description[:60] + "..." if len(description) > 60 else description
                )
                label = f"{feature_name} - {short_desc}"
            else:
                label = feature_name

            feature_options.append(
                selector.SelectOptionDict(value=feature_key, label=label)
            )

        # Build detailed summary for description area
        feature_summaries = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            name = str(feature_config.get("name", feature_key))
            category = str(feature_config.get("category", ""))
            description = str(feature_config.get("description", ""))

            detail_parts = [f"**{name}** ({category})"]
            if description:
                detail_parts.append(description)

            # Add supported device types
            supported_devices = feature_config.get("supported_device_types", [])
            if isinstance(supported_devices, list) and supported_devices:
                detail_parts.append(
                    f"Device Types: {', '.join(str(d) for d in supported_devices)}"
                )

            # Add entity requirements
            required_entities = feature_config.get("required_entities", {})
            if isinstance(required_entities, dict):
                required_sensors = required_entities.get("sensors", [])
                required_switches = required_entities.get("switches", [])
                required_booleans = required_entities.get("booleans", [])

                if isinstance(required_sensors, list) and required_sensors:
                    detail_parts.append(
                        f"• Sensors: {', '.join(str(s) for s in required_sensors)}"
                    )
                if isinstance(required_switches, list) and required_switches:
                    detail_parts.append(
                        f"• Switches: {', '.join(str(s) for s in required_switches)}"
                    )
                if isinstance(required_booleans, list) and required_booleans:
                    detail_parts.append(
                        f"• Booleans: {', '.join(str(b) for b in required_booleans)}"
                    )

            feature_summaries.append("• " + "\n  ".join(detail_parts))

        features_info = "\n\n".join(feature_summaries)

        # Build the info text
        info_text = "Configure which Ramses Extras features are enabled."
        info_text += "\n📖 For detailed documentation, visit: " + GITHUB_WIKI_URL
        info_text += f"\n\n**Available Features:**\n{features_info}"

        schema = vol.Schema(
            {
                vol.Optional(
                    "features", default=current_selected
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=feature_options,
                        multiple=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="features",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    async def async_step_confirm(
        self, user_input: dict[str, bool] | None = None
    ) -> config_entries.FlowResult:
        """Handle confirmation step for feature deselection."""
        if user_input is not None:
            if user_input.get("confirm", False):
                return await self._save_config(
                    self._pending_data if self._pending_data else {}
                )
            return await self.async_step_features()

        # Build confirmation message
        current_features: dict[str, bool] = self._config_entry.data.get(
            "enabled_features", {}
        )
        selected_features: list[str] = (
            self._pending_data.get("features", []) if self._pending_data else []
        )

        enabled_features = {}
        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = feature_key in selected_features

        # Build details about what will be removed
        removal_details = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            currently_enabled = current_features.get(feature_key, False)
            will_be_enabled = enabled_features[feature_key]

            if currently_enabled and not will_be_enabled:
                feature_name = str(feature_config.get("name", feature_key))
                detail_parts = [f"  • {feature_name}\n"]

                required_entities = feature_config.get("required_entities", {})
                if isinstance(required_entities, dict):
                    required_sensors = required_entities.get("sensors", [])
                    required_switches = required_entities.get("switches", [])

                    if isinstance(required_sensors, list) and required_sensors:
                        detail_parts.append(
                            f"  - {len(required_sensors)} sensor entities\n"
                        )
                    if isinstance(required_switches, list) and required_switches:
                        detail_parts.append(
                            f"  - {len(required_switches)} switch entities\n"
                        )

                if "card" in feature_key:
                    detail_parts.append("  - Dashboard card")
                if "automation" in feature_key:
                    detail_parts.append("  - Related automations")

                removal_details.append(" ".join(detail_parts))

        # Add warnings for different feature types
        warnings = []

        if self._cards_deselected:
            card_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._cards_deselected
            ]
            warnings.append(f"⚠️ **Cards being disabled:** {', '.join(card_names)}")
            warnings.append("🔄 **Required:** Clear browser cache after restart")

        if self._automations_deselected:
            automation_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._automations_deselected
            ]
            warnings.append(
                f"⚠️ **Automations being disabled:** {', '.join(automation_names)}"
            )

        if self._other_deselected:
            other_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._other_deselected
            ]
            warnings.append(f"⚠️ **Features being disabled:** {', '.join(other_names)}")

        if self._cards_selected:
            card_names = [
                str(AVAILABLE_FEATURES[f].get("name", f)) for f in self._cards_selected
            ]
            warnings.append(f"✅ **Cards being enabled:** {', '.join(card_names)}")
            warnings.append("🔄 **Required:** Clear browser cache after restart")

        if self._automations_selected:
            automation_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._automations_selected
            ]
            warnings.append(
                f"✅ **Automations being enabled:** {', '.join(automation_names)}"
            )

        if self._other_selected:
            other_names = [
                str(AVAILABLE_FEATURES[f].get("name", f)) for f in self._other_selected
            ]
            warnings.append(f"✅ **Features being enabled:** {', '.join(other_names)}")

        if self._newly_enabled_features:
            feature_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._newly_enabled_features
            ]
            warnings.append(
                f"✅ **New features being enabled:** {', '.join(feature_names)}"
            )

        # Build confirmation text
        confirmation_parts = []

        # Features being disabled
        disabled_parts = []
        if self._cards_deselected:
            cards_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._cards_deselected
            ]
            disabled_parts.append(f"**Cards:** {', '.join(cards_names)}")
        if self._automations_deselected:
            automation_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._automations_deselected
            ]
            disabled_parts.append(f"**Automations:** {', '.join(automation_names)}")
        if self._sensors_deselected:
            sensor_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._sensors_deselected
            ]
            disabled_parts.append(f"**Sensors:** {', '.join(sensor_names)}")
        if self._other_deselected:
            other_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._other_deselected
            ]
            disabled_parts.append(f"**Features:** {', '.join(other_names)}")

        if disabled_parts:
            disabled_text = "\n• ".join(["  • " + part for part in disabled_parts])
            confirmation_parts.append(
                f"**Features being disabled:**\n• {disabled_text}"
            )

        # Features being enabled
        enabled_parts = []
        if self._cards_selected:
            cards_names = [
                str(AVAILABLE_FEATURES[f].get("name", f)) for f in self._cards_selected
            ]
            enabled_parts.append(f"**Cards:** {', '.join(cards_names)}")
        if self._automations_selected:
            automation_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._automations_selected
            ]
            enabled_parts.append(f"**Automations:** {', '.join(automation_names)}")
        if self._sensors_selected:
            sensor_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._sensors_selected
            ]
            enabled_parts.append(f"**Sensors:** {', '.join(sensor_names)}")
        if self._other_selected:
            other_names = [
                str(AVAILABLE_FEATURES[f].get("name", f)) for f in self._other_selected
            ]
            enabled_parts.append(f"**Features:** {', '.join(other_names)}")
        if self._newly_enabled_features:
            new_names = [
                str(AVAILABLE_FEATURES[f].get("name", f))
                for f in self._newly_enabled_features
            ]
            enabled_parts.append(f"**New:** {', '.join(new_names)}")

        if enabled_parts:
            enabled_text = "\n• ".join(["  • " + part for part in enabled_parts])
            confirmation_parts.append(f"**Features being enabled:**\n• {enabled_text}")

        if not confirmation_parts:
            confirmation_parts.append("No feature changes detected.")

        confirmation_text = "\n\n".join(confirmation_parts)

        # Add instructions
        if self._cards_deselected or self._cards_selected:
            confirmation_text += "\n\n**Important:** After saving changes, you must:"
            confirmation_text += (
                "\n1. **Restart Home Assistant** (Settings → System → Restart)"
            )
            confirmation_text += (
                "\n2. **Clear browser cache** (Ctrl+Shift+R or clear site data)"
            )
            confirmation_text += "\n3. **Refresh dashboards** to see card changes"

        if warnings:
            confirmation_text += "\n\n" + "\n".join(warnings)

        confirmation_text += (
            "\n\nThis action cannot be undone. Are you sure you want to proceed?"
        )

        schema = vol.Schema(
            {
                vol.Required("confirm", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={"info": confirmation_text},
        )

    async def _save_config(
        self, user_input: dict[str, list[str]]
    ) -> config_entries.FlowResult:
        """Save the configuration and reload the integration."""
        enabled_features = {}
        selected_features = user_input.get("features", [])

        for feature_key in AVAILABLE_FEATURES.keys():
            enabled_features[feature_key] = feature_key in selected_features

        # Check what features were disabled and clean them up
        current_features = self._config_entry.data.get("enabled_features", {})
        disabled_automations = []
        disabled_cards = []
        disabled_sensors = []

        _LOGGER.info(f"Config flow - Current features: {current_features}")
        _LOGGER.info(f"Config flow - New features: {enabled_features}")

        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            currently_enabled = current_features.get(feature_key, False)
            will_be_enabled = enabled_features[feature_key]

            _LOGGER.info(
                f"Config flow - Feature {feature_key}: currently {currently_enabled}, "
                f"will be {will_be_enabled}, category {feature_config.get('category')}"
            )

            # If automation feature was disabled, clean it up
            if (
                currently_enabled
                and not will_be_enabled
                and feature_config.get("category") == "automations"
            ):
                disabled_automations.append(feature_key)
                _LOGGER.info(
                    f"Config flow - Detected disabled automation feature: {feature_key}"
                )

            # If card feature was disabled, clean it up
            if (
                currently_enabled
                and not will_be_enabled
                and feature_config.get("category") == "cards"
            ):
                disabled_cards.append(feature_key)
                _LOGGER.info(
                    f"Config flow - Detected disabled card feature: {feature_key}"
                )

            # If sensor feature was disabled, clean it up
            if (
                currently_enabled
                and not will_be_enabled
                and feature_config.get("category") == "sensors"
            ):
                disabled_sensors.append(feature_key)
                _LOGGER.info(
                    f"Config flow - Detected disabled sensor feature: {feature_key}"
                )

        _LOGGER.info(
            f"Config flow - Features to cleanup: automations={disabled_automations}, "
            f"cards={disabled_cards}, sensors={disabled_sensors}"
        )

        # Clean up disabled features before updating config
        if disabled_automations or disabled_cards or disabled_sensors:
            try:
                _LOGGER.info(
                    f"Cleaning up disabled features: "
                    f"automations={disabled_automations}, "
                    f"cards={disabled_cards}, sensors={disabled_sensors}"
                )
                await self._cleanup_disabled_features(
                    disabled_automations, disabled_cards, disabled_sensors
                )
            except Exception as e:
                _LOGGER.warning(f"Cleanup failed, continuing with config update: {e}")

        # Update the config entry data
        new_data = self._config_entry.data.copy()
        new_data["enabled_features"] = enabled_features

        self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)

        # Install/remove cards based on new feature settings
        await _manage_cards_config_flow(self.hass, enabled_features)

        # Reload the integration to apply changes
        try:
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
        except Exception as e:
            _LOGGER.warning(f"Integration reload failed, but config updated: {e}")

        return self.async_create_entry(title="", data={})

    async def _cleanup_disabled_features(
        self,
        disabled_automations: list[str],
        disabled_cards: list[str],
        disabled_sensors: list[str],
    ) -> None:
        """Clean up entities and resources for disabled features."""
        try:
            # Clean up automation features
            if disabled_automations:
                await self._cleanup_disabled_automations(disabled_automations)

            # Clean up card features (file removal)
            if disabled_cards:
                await self._cleanup_disabled_cards(disabled_cards)

            # Clean up sensor features (entity cleanup)
            if disabled_sensors:
                await self._cleanup_disabled_sensors(disabled_sensors)

        except Exception as e:
            _LOGGER.error(f"Cleanup - Failed to cleanup disabled features: {e}")

    async def _cleanup_disabled_cards(self, disabled_cards: list[str]) -> None:
        """Clean up files for disabled card features."""
        try:
            www_community_path = Path(self.hass.config.path("www", "community"))

            for feature_key in disabled_cards:
                if feature_key in AVAILABLE_FEATURES:
                    feature_config = AVAILABLE_FEATURES[feature_key]
                    card_location = feature_config.get("location", "")
                    if card_location:
                        card_dest_path = www_community_path / feature_key
                        await _remove_card_config_flow(self.hass, card_dest_path)
                        _LOGGER.info(f"Cleanup - Removed card files for {feature_key}")

        except Exception as e:
            _LOGGER.error(f"Cleanup - Failed to cleanup disabled cards: {e}")

    async def _cleanup_disabled_sensors(self, disabled_sensors: list[str]) -> None:
        """Clean up entities for disabled sensor features."""
        try:
            # Get current devices and enabled features
            devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
            config_entry = None
            if DOMAIN in self.hass.data and "entry_id" in self.hass.data[DOMAIN]:
                entry_id = self.hass.data[DOMAIN]["entry_id"]
                config_entry = self.hass.config_entries.async_get_entry(entry_id)

            if config_entry and devices:
                # Calculate which sensor entities are still required
                calculate_required_entities(
                    "sensor",
                    get_enabled_features(self.hass, config_entry),
                    devices,
                    self.hass,
                )

                # Remove orphaned sensor entities
                from .framework.helpers.entity.core import EntityHelpers

                removed_count = EntityHelpers.cleanup_orphaned_entities(
                    self.hass,
                    devices,
                )
                _LOGGER.info(
                    f"Cleanup - Removed {removed_count} orphaned sensor entities"
                )

        except Exception as e:
            _LOGGER.error(f"Cleanup - Failed to cleanup disabled sensors: {e}")

    async def _cleanup_disabled_automations(
        self, disabled_automations: list[str]
    ) -> None:
        """Clean up automations for disabled features."""
        try:
            from pathlib import Path

            import yaml

            automation_path = Path(self.hass.config.path("automations.yaml"))

            _LOGGER.info(
                f"Cleanup - Starting cleanup for features: {disabled_automations}"
            )
            _LOGGER.info(f"Cleanup - Automation path: {automation_path}")

            if not automation_path.exists():
                _LOGGER.info("Cleanup - Automation file does not exist")
                return

            # Read file content asynchronously
            def read_automations_file() -> str:
                with open(automation_path, encoding="utf-8") as f:
                    return f.read()

            content_str = await self.hass.async_add_executor_job(read_automations_file)
            content = yaml.safe_load(content_str)

            _LOGGER.info(f"Cleanup - File content type: {type(content)}")
            _LOGGER.info(
                "Cleanup - File content keys: %s",
                content.keys() if isinstance(content, dict) else "N/A (list format)",
            )

            if not content:
                _LOGGER.info("Cleanup - No automation content found")
                return

            # Handle both formats: with or without automation wrapper
            if isinstance(content, list):
                automations_to_filter = content
                _LOGGER.info(
                    f"Cleanup - Found {len(automations_to_filter)} automations "
                    f"in list format"
                )
            elif isinstance(content, dict) and "automation" in content:
                automations_to_filter = content["automation"]
                _LOGGER.info(
                    f"Cleanup - Found {len(automations_to_filter)} automations "
                    f"in dict format"
                )
            else:
                _LOGGER.info("Cleanup - No valid automation format found")
                return

            # Log automation IDs before filtering
            automation_ids = [auto.get("id", "") for auto in automations_to_filter]
            _LOGGER.info(f"Cleanup - Automation IDs found: {automation_ids}")

            # Remove automations for disabled features
            filtered_automations = []
            removed_count = 0

            for auto in automations_to_filter:
                automation_id = auto.get("id", "")
                should_remove = False

                # Check if this automation belongs to any disabled feature
                for feature_key in disabled_automations:
                    # Map feature keys to automation patterns
                    feature_patterns = {
                        "humidity_control": ["dehumidifier"],
                    }

                    patterns = feature_patterns.get(feature_key, [feature_key])
                    for pattern in patterns:
                        if pattern in automation_id:
                            should_remove = True
                            _LOGGER.info(
                                f"Cleanup - Will remove automation {automation_id} "
                                f"(matches pattern '{pattern}' "
                                f"for feature '{feature_key}')"
                            )
                            break

                    if should_remove:
                        break

                if not should_remove:
                    filtered_automations.append(auto)

            # Update file if any automations were removed
            if len(filtered_automations) != len(automations_to_filter):
                removed_count = len(automations_to_filter) - len(filtered_automations)

                def write_automations_file() -> None:
                    if isinstance(content, list):
                        with open(automation_path, "w", encoding="utf-8") as f:
                            yaml.dump(
                                filtered_automations,
                                f,
                                default_flow_style=False,
                                sort_keys=False,
                            )
                    else:
                        content["automation"] = filtered_automations
                        with open(automation_path, "w", encoding="utf-8") as f:
                            yaml.dump(
                                content, f, default_flow_style=False, sort_keys=False
                            )

                await self.hass.async_add_executor_job(write_automations_file)

                _LOGGER.info(
                    f"Cleanup - Successfully removed {removed_count} automations "
                    f"for disabled features: {disabled_automations}"
                )
            else:
                _LOGGER.info(
                    "Cleanup - No automations removed for features: "
                    f"{disabled_automations}"
                )

        except Exception as e:
            _LOGGER.error(f"Cleanup - Failed to cleanup disabled automations: {e}")
