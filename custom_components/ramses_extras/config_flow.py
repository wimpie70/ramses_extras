import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
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
from .framework.helpers.entity.manager import EntityManager
from .framework.helpers.platform import (
    calculate_required_entities,
    get_enabled_features,
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
    www_community_path = Path(hass.config.path("www", "community"))

    # Handle all card features dynamically
    for feature_key, feature_config in AVAILABLE_FEATURES.items():
        # Skip default feature from card management (it's not a card feature)
        if feature_key == "default":
            continue

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


class RamsesExtrasOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ramses Extras."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._pending_data: dict[str, list[str]] | None = None
        self._entity_manager: EntityManager | None = (
            None  # Will be initialized when needed
        )
        self._feature_changes_detected = False
        self._entities_to_remove: list[str] = []
        self._entities_to_create: list[str] = []

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
            # Get current features and determine feature changes
            current_features = self._config_entry.data.get("enabled_features", {})
            selected_features = user_input.get("features", [])

            # Convert selected features to enabled features dict
            enabled_features = {}
            for feature_key in AVAILABLE_FEATURES.keys():
                # Default feature is always enabled, regardless of user selection
                if feature_key == "default":
                    enabled_features[feature_key] = True
                else:
                    enabled_features[feature_key] = feature_key in selected_features

            # Check for any feature changes using EntityManager
            feature_changes = []
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                currently_enabled = current_features.get(feature_key, False)
                will_be_enabled = enabled_features[feature_key]

                if currently_enabled != will_be_enabled:
                    change_type = "enabling" if will_be_enabled else "disabling"
                    feature_changes.append((feature_key, change_type))

            # If there are any feature changes, build entity catalog
            #  and show confirmation
            if feature_changes:
                # Initialize EntityManager once and build catalog with target features
                self._entity_manager = EntityManager(self.hass)
                await self._entity_manager.build_entity_catalog(
                    AVAILABLE_FEATURES, current_features, enabled_features
                )

                # Store entity changes for confirmation
                self._entities_to_remove = self._entity_manager.get_entities_to_remove()
                self._entities_to_create = self._entity_manager.get_entities_to_create()
                self._feature_changes_detected = True
                self._pending_data = user_input

                _LOGGER.info(
                    f"EntityManager created for feature changes: {feature_changes}"
                )

                # Show confirmation with entity changes
                return await self.async_step_confirm()

            # No feature changes detected, save config
            return await self._save_config(user_input)

        # Get current enabled features for default values
        current_features = self._config_entry.data.get("enabled_features", {})

        # Ensure all features are present in the config (for backward compatibility)
        if len(current_features) != len(AVAILABLE_FEATURES):
            # Initialize missing features with their default values
            for feature_key, feature_config in AVAILABLE_FEATURES.items():
                if feature_key not in current_features:
                    # Default feature is always enabled
                    if feature_key == "default":
                        current_features[feature_key] = True
                    else:
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
        # Exclude "default" feature since it's not user-configurable in the selector
        current_selected = [
            k for k, v in current_features.items() if v and k != "default"
        ]

        # Build options for multi-select
        feature_options = []
        for feature_key, feature_config in AVAILABLE_FEATURES.items():
            # Skip default feature from user configuration (it's always enabled)
            if feature_key == "default":
                continue

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
            # Skip default feature from user display (it's always enabled)
            if feature_key == "default":
                continue

            name = str(feature_config.get("name", feature_key))
            category = str(feature_config.get("category", ""))
            description = str(feature_config.get("description", ""))

            detail_parts = [f"**{name}** ({category})"]
            if description:
                detail_parts.append(description)

            # Get feature details from the feature module
            feature_details = _get_feature_details_from_module(feature_key)

            if feature_details:
                # Add supported device types
                supported_devices = feature_details.get("supported_device_types", [])
                if isinstance(supported_devices, list) and supported_devices:
                    detail_parts.append(
                        f"Device Types: {', '.join(str(d) for d in supported_devices)}"
                    )

                # Add entity requirements
                required_entities = feature_details.get("required_entities", {})
                if isinstance(required_entities, dict):
                    required_sensor = required_entities.get("sensor", [])
                    required_switch = required_entities.get("switch", [])
                    required_booleans = required_entities.get("booleans", [])

                    if isinstance(required_sensor, list) and required_sensor:
                        detail_parts.append(
                            f"• sensor: {', '.join(str(s) for s in required_sensor)}"
                        )
                    if isinstance(required_switch, list) and required_switch:
                        detail_parts.append(
                            f"• switch: {', '.join(str(s) for s in required_switch)}"
                        )
                    if isinstance(required_booleans, list) and required_booleans:
                        detail_parts.append(
                            f"• Booleans: {', '.join(str(b) for b in required_booleans)}"  # noqa: E501
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
        """Handle confirmation step for feature changes using EntityManager."""
        if user_input is not None:
            if user_input.get("confirm", False):
                return await self._save_config(
                    self._pending_data if self._pending_data else {}
                )
            return await self.async_step_features()

        # Use EntityManager to build clean confirmation message
        if self._entity_manager is None:
            # Fallback to old behavior if EntityManager not initialized
            return await self.async_step_features()

        # Get entity changes from EntityManager
        entities_to_remove = self._entities_to_remove
        entities_to_create = self._entities_to_create

        # Get feature summary
        entity_summary = self._entity_manager.get_entity_summary()

        # Build clean confirmation text
        confirmation_parts = []

        # Entities to be removed
        if entities_to_remove:
            confirmation_parts.append(
                f"**Entities to be removed ({len(entities_to_remove)}):**\n"
                f"• {', '.join(entities_to_remove[:5])}"
                f"{'...' if len(entities_to_remove) > 5 else ''}"
            )

        # Entities to be created
        if entities_to_create:
            confirmation_parts.append(
                f"**Entities to be created ({len(entities_to_create)}):**\n"
                f"• {', '.join(entities_to_create[:5])}"
                f"{'...' if len(entities_to_create) > 5 else ''}"
            )

        # Entity summary
        summary_parts = [
            f"Total possible entities: {entity_summary['total_entities']}",
            f"Existing and enabled: {entity_summary['existing_enabled']}",
            f"Existing but will be removed: {entity_summary['existing_disabled']}",
            f"Will be created: {entity_summary['non_existing_enabled']}",
        ]
        confirmation_parts.append(
            "**Entity Summary:**\n• " + "\n• ".join(summary_parts)
        )

        if not confirmation_parts:
            confirmation_parts.append("No entity changes detected.")

        confirmation_text = "\n\n".join(confirmation_parts)

        # Add general warnings for card changes
        if any("card" in entity for entity in entities_to_remove + entities_to_create):
            confirmation_text += "\n\n**Important for card changes:**"
            confirmation_text += "\n• After saving, restart Home Assistant"
            confirmation_text += "\n• Clear browser cache to see changes"

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
        """Save the configuration and apply entity changes using EntityManager."""
        enabled_features = {}
        selected_features = user_input.get("features", [])

        for feature_key in AVAILABLE_FEATURES.keys():
            # Default feature is always enabled, regardless of user selection
            if feature_key == "default":
                enabled_features[feature_key] = True
            else:
                enabled_features[feature_key] = feature_key in selected_features

        _LOGGER.info(
            f"Config flow - Current features: "
            f"{self._config_entry.data.get('enabled_features', {})}"
        )
        _LOGGER.info(f"Config flow - New features: {enabled_features}")

        # Apply entity changes using EntityManager if available
        if self._entity_manager and self._feature_changes_detected:
            try:
                _LOGGER.info(
                    f"Applying entity changes using EntityManager: "
                    f"remove={len(self._entities_to_remove)}, "
                    f"create={len(self._entities_to_create)}"
                )
                await self._entity_manager.apply_entity_changes()
            except Exception as e:
                _LOGGER.warning(
                    f"EntityManager changes failed, continuing with config update: {e}"
                )
        else:
            # No EntityManager available, should not happen in normal flow
            _LOGGER.warning("EntityManager not available, skipping entity changes")

        # Update the config entry data
        new_data = self._config_entry.data.copy()
        new_data["enabled_features"] = enabled_features

        self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)

        # Install/remove cards based on new feature settings
        await _manage_cards_config_flow(self.hass, enabled_features)

        # Reload the integration to apply entity changes
        # This triggers platform setup which creates/removes entities
        _LOGGER.info("Config flow - Reloading integration to apply entity changes")
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)

        return self.async_create_entry(title="", data={})

    async def _apply_targeted_changes(self) -> None:
        """Apply targeted changes using EntityManager."""
        if self._entity_manager:
            await self._entity_manager.apply_entity_changes()
        else:
            # EntityManager is required for entity changes - should not reach here
            _LOGGER.error("EntityManager not available for targeted changes")
