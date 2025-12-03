"""Feature Config Flow Base Class - Generic patterns for feature-specific
device selection flows."""

import logging
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from ..device_selection import DeviceSelectionManager
from ..entity_lazy_creation import LazyEntityCreationManager

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class FeatureConfigFlowBase(config_entries.ConfigFlow):
    """Base class for feature-specific config flows with device selection.

    Features can inherit from this class to provide device-specific configuration
    without duplicating common logic. This enables the lazy entity creation pattern
    where devices are selected explicitly before entities are created.

    Supports both standalone config flows and menu-based navigation patterns.
    """

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize feature config flow.

        Args:
            config_entry: Optional config entry for existing configurations
        """
        self._config_entry = config_entry
        self._hass: HomeAssistant | None = None
        self._feature_id: str = ""
        self._feature_config: dict[str, Any] = {}
        self._device_selection_manager: DeviceSelectionManager | None = None
        self._lazy_entity_manager: LazyEntityCreationManager | None = None
        self._discovered_devices: list[dict] = []
        self._pending_device_selection: list[str] = []

    async def async_init_feature(
        self, hass: HomeAssistant, feature_id: str, feature_config: dict[str, Any]
    ) -> None:
        """Initialize feature-specific context.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            feature_config: Feature configuration from AVAILABLE_FEATURES
        """
        self._hass = hass
        self._feature_id = feature_id
        self._feature_config = feature_config

        # Initialize managers
        from ..device_selection import create_device_selection_manager

        self._device_selection_manager = await create_device_selection_manager(
            hass, feature_id
        )

        if "lazy_entity_manager" not in hass.data:
            from ..entity_lazy_creation import create_lazy_entity_manager

            hass.data["lazy_entity_manager"] = await create_lazy_entity_manager(hass)

        self._lazy_entity_manager = hass.data["lazy_entity_manager"]

        _LOGGER.info(f"🔧 Initialized feature config flow for: {feature_id}")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step - device selection."""
        if not self._hass:
            return self.async_abort(reason="invalid_context")

        # If we have user input, validate and proceed
        if user_input is not None:
            return await self._handle_device_selection(user_input)

        # Discover compatible devices
        device_types = self._feature_config.get(
            "supported_device_types", ["HvacVentilator"]
        )
        if self._device_selection_manager is None:
            _LOGGER.error("❌ Device selection manager not initialized")
            return self.async_abort(reason="device_manager_not_initialized")

        self._discovered_devices = (
            await self._device_selection_manager.discover_compatible_devices(
                device_types
            )
        )

        if not self._discovered_devices:
            return await self.async_step_no_devices()

        # Load current device selection if available
        if self._config_entry:
            current_selection = self._config_entry.options.get("selected_devices", [])
            self._pending_device_selection = current_selection
        else:
            self._pending_device_selection = []

        # Build device selection schema
        schema = await self._build_device_selection_schema()

        # Build feature description
        feature_name = self._feature_config.get("name", self._feature_id)
        feature_desc = self._feature_config.get(
            "description", "No description available"
        )

        info_text = f"**{feature_name}**\n\n{feature_desc}\n\n"
        info_text += f"Select devices for {feature_name} entities:\n"

        for device in self._discovered_devices:
            device_info = (
                f"• {device['name']} ({device['device_id']}) - {device['device_type']}"
            )
            if device.get("zone"):
                device_info += f" (Zone: {device['zone']})"
            info_text += f"\n{device_info}"

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    async def _handle_device_selection(
        self, user_input: dict[str, Any]
    ) -> config_entries.FlowResult:
        """Handle device selection from user input.

        Args:
            user_input: User input containing selected devices

        Returns:
            Flow result - either continue to confirm or complete
        """
        selected_devices = user_input.get("selected_devices", [])

        if not selected_devices:
            # No devices selected - show warning but allow proceeding
            return await self.async_step_no_devices_selected()

        # Validate device selection
        if self._device_selection_manager is None:
            _LOGGER.error("❌ Device selection manager not initialized")
            return self.async_abort(reason="device_manager_not_initialized")

        validation_result = (
            await self._device_selection_manager.validate_device_selection(
                selected_devices,
                self._feature_config.get("supported_device_types", ["HvacVentilator"]),
            )
        )

        if not validation_result["valid"]:
            errors = validation_result["errors"]
            error_text = "\n".join(f"• {error}" for error in errors)

            return self.async_show_form(
                step_id="user",
                data_schema=await self._build_device_selection_schema(),
                errors={"base": "invalid_device_selection"},
                description_placeholders={"error": f"Invalid selection:\n{error_text}"},
            )

        # Store selection and proceed to confirmation
        self._pending_device_selection = selected_devices

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle confirmation step."""
        if user_input is not None:
            if user_input.get("confirm", False):
                return await self._save_device_configuration()
            return await self.async_step_user()

        # Build confirmation text
        selected_devices_info = []
        for device_id in self._pending_device_selection:
            device = next(
                (d for d in self._discovered_devices if d["device_id"] == device_id),
                None,
            )
            if device:
                selected_devices_info.append(
                    f"• {device['name']} ({device['device_type']})"
                )

        device_list = (
            "\n".join(selected_devices_info)
            if selected_devices_info
            else "• No devices selected"
        )

        confirmation_text = (
            f"**Device Selection Summary**\n\n"
            f"Selected devices for "
            f"{self._feature_config.get('name', self._feature_id)}:\n"
            f"{device_list}\n\n"
            f"Entities will be created for the selected devices only.\n\n"
            f"Proceed with this configuration?"
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

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle case where no compatible devices are found."""
        if user_input is not None:
            return self.async_abort(reason="no_compatible_devices")

        device_types = self._feature_config.get(
            "supported_device_types", ["HvacVentilator"]
        )

        info_text = (
            f"**No Compatible Devices Found**\n\n"
            f"No devices of types {', '.join(device_types)} were found.\n"
            f"This feature requires compatible devices to function.\n\n"
            f"Make sure your Ramses system has the required devices configured."
        )

        return self.async_show_form(
            step_id="no_devices",
            data_schema=vol.Schema({}),
            description_placeholders={"info": info_text},
        )

    async def async_step_no_devices_selected(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle case where user selected no devices."""
        if user_input is not None:
            if user_input.get("proceed_anyway", False):
                return await self._save_device_configuration()
            return await self.async_step_user()

        info_text = (
            "**No Devices Selected**\n\n"
            "You haven't selected any devices for this feature.\n"
            "Entities will only be created for devices you explicitly select.\n\n"
            "Do you want to proceed without device selection?"
        )

        schema = vol.Schema(
            {
                vol.Required("proceed_anyway", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="no_devices_selected",
            data_schema=schema,
            description_placeholders={"info": info_text},
        )

    async def _save_device_configuration(self) -> config_entries.FlowResult:
        """Save device configuration and create entities.

        Returns:
            Flow result with updated options
        """
        if not self._hass:
            return self.async_abort(reason="invalid_context")

        feature_name = self._feature_config.get("name", self._feature_id)

        _LOGGER.info(
            f"💾 Saving device configuration for {feature_name}: "
            f"{self._pending_device_selection}"
        )

        # Create or update options
        options = {"selected_devices": self._pending_device_selection}

        # For new configurations, return the options
        if not self._config_entry:
            return self.async_create_entry(title="", data=options)

        # For existing configurations, update options
        return self.async_create_entry(title="", data=options)

    async def _build_device_selection_schema(self) -> vol.Schema:
        """Build the device selection schema for the UI.

        Returns:
            Voluptuous schema for device selection
        """
        # Import voluptuous for schema creation
        from voluptuous import vol

        # Create device selection options
        device_options = {}
        for device in self._discovered_devices:
            display_name = (
                f"{device['name']} ({device['device_id']}) - {device['device_type']}"
            )
            if device.get("zone"):
                display_name += f" (Zone: {device['zone']})"
            device_options[device["device_id"]] = display_name

        # Build multi-select schema
        schema = vol.Schema(
            {
                vol.Optional(
                    "selected_devices", default=self._pending_device_selection
                ): vol.All(
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=device_id, label=label)
                                for device_id, label in device_options.items()
                            ],
                            multiple=True,
                        )
                    )
                )
            }
        )

        return schema  # noqa: RET504

    @classmethod
    async def create_feature_config_flow(
        cls,
        hass: HomeAssistant,
        feature_id: str,
        feature_config: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> "FeatureConfigFlowBase":
        """Create and initialize a feature config flow instance.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            feature_config: Feature configuration
            config_entry: Optional existing config entry

        Returns:
            Initialized feature config flow instance
        """
        flow = cls(config_entry)
        await flow.async_init_feature(hass, feature_id, feature_config)
        return flow

    async def get_current_device_selection(self) -> list[str]:
        """Get current device selection for this feature.

        Returns:
            List of currently selected device IDs
        """
        if not self._config_entry:
            return []

        return cast(list[str], self._config_entry.options.get("selected_devices", []))

    async def create_entities_for_selection(
        self, config_entry: ConfigEntry
    ) -> dict[str, list]:
        """Create entities for the current device selection.

        Args:
            config_entry: The main integration config entry

        Returns:
            Dictionary mapping device_id -> list of created entities
        """
        if not self._lazy_entity_manager:
            _LOGGER.warning("⚠️ Lazy entity manager not available")
            return {}

        selected_devices = self._pending_device_selection
        if not selected_devices:
            _LOGGER.info(
                f"No devices selected for {self._feature_id}, skipping entity creation"
            )
            return {}

        _LOGGER.info(
            f"🎯 Creating entities for {self._feature_id} on devices: "
            f"{selected_devices}"
        )

        # Create entities using the lazy entity manager
        created_entities = (
            await self._lazy_entity_manager.create_entities_for_selection(
                self._feature_id, selected_devices, config_entry
            )
        )

        return created_entities  # noqa: RET504

    @classmethod
    async def create_menu_integration_flow(
        cls,
        hass: HomeAssistant,
        feature_id: str,
        feature_config: dict[str, Any],
        config_entry: ConfigEntry,
        menu_handler: Any,
    ) -> config_entries.FlowResult:
        """Create a feature config flow integrated with main menu navigation.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            feature_config: Feature configuration
            config_entry: Main integration config entry
            menu_handler: Main menu handler to return to

        Returns:
            Flow result for menu-based navigation
        """
        flow = cls(config_entry)
        await flow.async_init_feature(hass, feature_id, feature_config)

        # Set the menu handler for navigation
        flow._menu_handler = menu_handler

        # Start the user step for device selection
        return await flow.async_step_user()

    async def return_to_menu(self) -> config_entries.FlowResult:
        """Return to the main configuration menu.

        Returns:
            Flow result for main menu navigation
        """
        if hasattr(self, "_menu_handler") and self._menu_handler:
            return await self._menu_handler()
        # Fallback to abort if no menu handler available
        return self.async_abort(reason="menu_navigation_unavailable")
