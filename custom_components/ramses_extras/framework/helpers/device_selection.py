"""Generic Device Selection Framework - Feature-agnostic patterns for
device discovery and selection."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class DeviceSelectionManager:
    """Manages device selection for features requiring specific device configuration.

    This framework provides generic, reusable patterns for
     device discovery and selection
    that all features can use. Feature-specific logic should be implemented in the
    individual feature folders, not in this framework.
    """

    def __init__(self, hass: HomeAssistant, feature_id: str):
        """Initialize device selection manager.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier for context
        """
        self.hass = hass
        self.feature_id = feature_id
        self._selected_devices: set[str] = set()

    async def discover_compatible_devices(self, device_types: list[str]) -> list[dict]:
        """Discover devices compatible with the specified device types.

        Args:
            device_types: List of device types to search for (e.g., ["HvacVentilator"])

        Returns:
            List of device information dictionaries with format:
            {
                "device_id": str,
                "device_type": str,
                "name": str,
                "manufacturer": str,
                "model": str,
                "compatible": bool
            }
        """
        _LOGGER.info(f"🔍 Discovering compatible devices for {self.feature_id}")
        _LOGGER.info(f"🔍 Looking for device types: {device_types}")

        compatible_devices = []

        try:
            # Try broker-based discovery first
            devices = await self._get_devices_from_broker()

            if devices:
                for device in devices:
                    device_info = await self._get_device_info(device, device_types)
                    if device_info:
                        compatible_devices.append(device_info)
                        _LOGGER.info(
                            f"✅ Found compatible device: {device_info['device_id']}"
                            f" ({device_info['device_type']})"
                        )
            else:
                # Fallback to entity registry discovery
                _LOGGER.info("No devices from broker, trying entity registry fallback")
                compatible_devices.extend(
                    await self._discover_devices_from_entity_registry(device_types)
                )

        except Exception as e:
            _LOGGER.error(f"❌ Error during device discovery: {e}")
            # Try entity registry as last resort
            try:
                _LOGGER.info("Trying entity registry fallback due to broker error")
                compatible_devices.extend(
                    await self._discover_devices_from_entity_registry(device_types)
                )
            except Exception as fallback_error:
                _LOGGER.error(
                    f"❌ Entity registry fallback also failed: {fallback_error}"
                )

        _LOGGER.info(
            f"🔍 Discovery complete: found {len(compatible_devices)} compatible devices"
        )
        return compatible_devices

    async def discover_all_ramses_cc_devices(self) -> list[dict]:
        """Discover ALL ramses_cc devices without filtering by device types.

        This method is used for features like hello_world_card that need to show
        all available ramses_cc devices regardless of their type.

        Returns:
            List of all ramses_cc device information dictionaries
        """
        _LOGGER.info(f"🌍 Discovering ALL ramses_cc devices for {self.feature_id}")

        all_devices = []

        try:
            # Try broker-based discovery first
            devices = await self._get_devices_from_broker()

            if devices:
                for device in devices:
                    device_info = await self._get_device_info_wildcard(device)
                    if device_info:
                        all_devices.append(device_info)
                        _LOGGER.info(
                            f"🌍 Found ramses_cc device: {device_info['device_id']}"
                            f" ({device_info['device_type']})"
                        )
            else:
                # Fallback to entity registry discovery
                _LOGGER.info("No devices from broker, trying entity registry fallback")
                all_devices.extend(
                    await self._discover_all_ramses_cc_devices_from_entity_registry()
                )

        except Exception as e:
            _LOGGER.error(f"❌ Error during wildcard device discovery: {e}")
            # Try entity registry as last resort
            try:
                _LOGGER.info("Trying entity registry fallback due to broker error")
                all_devices.extend(
                    await self._discover_all_ramses_cc_devices_from_entity_registry()
                )
            except Exception as fallback_error:
                _LOGGER.error(
                    f"❌ Entity registry fallback also failed: {fallback_error}"
                )

        _LOGGER.info(
            f"🌍 Wildcard discovery complete: found {len(all_devices)} "
            f"ramses_cc devices"
        )
        return all_devices

    async def _get_devices_from_broker(self) -> list[Any]:
        """Get devices from ramses_cc broker using robust discovery logic.

        Returns:
            List of device objects from the broker
        """
        try:
            # Try multiple methods to get the broker (similar to EntityManager)
            broker = await self._find_broker()

            if broker is None:
                _LOGGER.warning("Could not find ramses_cc broker")
                return []

            # Try multiple ways to get devices from broker
            devices = await self._find_devices_for_broker(broker)
            _LOGGER.debug(f"Found {len(devices)} devices from broker")
            return devices

        except Exception as e:
            _LOGGER.error(f"Error getting devices from broker: {e}")
            return []

    async def _find_broker(self) -> Any:
        """Find ramses_cc broker using multiple discovery methods.

        Returns:
            Broker object or None
        """
        # Method 1: hass.data["ramses_cc"][entry.entry_id] (newest)
        try:
            ramses_cc_entries = self.hass.config_entries.async_entries("ramses_cc")
            if ramses_cc_entries:
                entry = ramses_cc_entries[0]  # Use first ramses_cc entry
                if entry.entry_id in self.hass.data.get("ramses_cc", {}):
                    broker = self.hass.data["ramses_cc"][entry.entry_id]
                    _LOGGER.debug(f"Found broker via Method 1 for {entry.entry_id}")
                    return broker
        except Exception as e:
            _LOGGER.debug(f"Broker Method 1 failed: {e}")

        # Method 2: hass.data["ramses_cc"] directly (older structure)
        try:
            if "ramses_cc" in self.hass.data:
                data = self.hass.data["ramses_cc"]
                if isinstance(data, dict) and len(data) > 0:
                    # Try first entry
                    first_value = list(data.values())[0]
                    if hasattr(first_value, "_devices") or hasattr(
                        first_value, "devices"
                    ):
                        _LOGGER.debug("Found broker via Method 2")
                        return first_value
        except Exception as e:
            _LOGGER.debug(f"Broker Method 2 failed: {e}")

        # Method 3: entry.broker (older versions)
        try:
            ramses_cc_entries = self.hass.config_entries.async_entries("ramses_cc")
            if ramses_cc_entries:
                entry = ramses_cc_entries[0]
                if hasattr(entry, "broker"):
                    _LOGGER.debug(f"Found broker via Method 3 for {entry.entry_id}")
                    return entry.broker
        except Exception as e:
            _LOGGER.debug(f"Broker Method 3 failed: {e}")

        # Method 4: Any entry in hass.data["ramses_cc"] with devices
        try:
            if "ramses_cc" in self.hass.data:
                for key, value in self.hass.data["ramses_cc"].items():
                    if hasattr(value, "_devices") or hasattr(value, "devices"):
                        _LOGGER.debug(f"Found broker via Method 4 ({key})")
                        return value
        except Exception as e:
            _LOGGER.debug(f"Broker Method 4 failed: {e}")

        return None

    async def _find_devices_for_broker(self, broker: Any) -> list[Any]:
        """Find devices for a broker using all possible methods.

        Args:
            broker: Broker object

        Returns:
            List of devices
        """
        # Method 1: broker._devices (newest - private attribute)
        try:
            if hasattr(broker, "_devices"):
                devices = broker._devices
                if devices:
                    _LOGGER.debug("Found devices via broker Method 1")
                    return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 1 failed: {e}")

        # Method 2: broker.devices (older - public attribute)
        try:
            if hasattr(broker, "devices"):
                devices = broker.devices
                if devices:
                    _LOGGER.debug("Found devices via broker Method 2")
                    return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 2 failed: {e}")

        # Method 3: broker.client.devices (alternative structure)
        try:
            if hasattr(broker, "client") and hasattr(broker.client, "devices"):
                devices = broker.client.devices
                if devices:
                    _LOGGER.debug("Found devices via broker Method 3")
                    return self._normalize_devices_list(devices)
        except Exception as e:
            _LOGGER.debug(f"Device Method 3 failed: {e}")

        return []

    def _normalize_devices_list(self, devices: Any) -> list[Any]:
        """Normalize different device storage formats to a list.

        Args:
            devices: Devices in various formats

        Returns:
            List of devices
        """
        try:
            # Dict format: return values
            if isinstance(devices, dict):
                return list(devices.values())
            # List format: return as-is
            if isinstance(devices, list):
                return devices
            # Set format: convert to list
            if isinstance(devices, set):
                return list(devices)
            # Single device: wrap in list
            return [devices]
        except Exception as e:
            _LOGGER.debug(f"Failed to normalize devices: {e}")
            return []

    async def _discover_devices_from_entity_registry(
        self, device_types: list[str]
    ) -> list[dict]:
        """Fallback method to discover devices from entity registry.

        Args:
            device_types: List of device types to search for

        Returns:
            List of device information dictionaries
        """
        try:
            from homeassistant.helpers import entity_registry

            entity_registry_instance = entity_registry.async_get(self.hass)

            discovered_devices: list[dict] = []

            # Look for ramses_cc entities
            for entity in entity_registry_instance.entities.values():
                if (
                    entity.domain
                    in ["fan", "climate", "sensor", "switch", "number", "binary_sensor"]
                    and entity.platform == "ramses_cc"
                    and hasattr(entity, "device_id")
                    and entity.device_id
                ):
                    device_id = entity.device_id

                    # Skip if we already found this device
                    if any(d["device_id"] == device_id for d in discovered_devices):
                        continue

                    # Determine device type from entity domain
                    device_type = self._infer_device_type_from_entity(entity)

                    # Check if this device type is compatible
                    if any(compatible in device_type for compatible in device_types):
                        device_info = {
                            "device_id": device_id,
                            "device_type": device_type,
                            "name": getattr(entity, "name", device_id) or device_id,
                            "manufacturer": "Unknown",
                            "model": "Unknown",
                            "compatible": True,
                            "zone": getattr(entity, "zone", "Unknown"),
                        }
                        discovered_devices.append(device_info)
                        _LOGGER.debug(
                            f"Found device from entity registry: {device_id} "
                            f"({device_type})"
                        )

            _LOGGER.info(
                f"Entity registry fallback found {len(discovered_devices)} devices"
            )
            return discovered_devices

        except Exception as e:
            _LOGGER.error(f"Error in entity registry device discovery: {e}")
            return []

    def _infer_device_type_from_entity(self, entity: Any) -> str:
        """Infer device type from entity information.

        Args:
            entity: Entity object

        Returns:
            Inferred device type
        """
        # For ramses_cc entities, we can infer device type from the entity
        # Most ventilation devices show up as fan entities
        if entity.domain == "fan":
            return "HvacVentilator"
        if entity.domain == "climate":
            return "HvacController"
        # Default fallback
        return "HvacVentilator"

    async def _get_device_info(
        self, device: Any, device_types: list[str]
    ) -> dict[str, Any] | None:
        """Get standardized device information.

        Args:
            device: Device object from ramses_cc
            device_types: List of compatible device types

        Returns:
            Device information dictionary or None if not compatible
        """
        # Use _SLUG attribute for device type identification (ramses_cc pattern)
        # Fallback to device_type if _SLUG is not available
        device_type = None
        if hasattr(device, "_SLUG"):
            # Map ramses_cc SLUG values to device types
            if device._SLUG == "FAN":
                device_type = "HvacVentilator"
            elif device._SLUG == "CO2":
                device_type = "HvacCarbonDioxideSensor"
            elif device._SLUG == "TEMP":
                device_type = "HvacTemperatureSensor"
            elif device._SLUG == "HUM":
                device_type = "HvacHumiditySensor"
            # Add more SLUG mappings as needed
        elif hasattr(device, "device_type"):
            device_type = device.device_type

        # If we couldn't determine device type, skip this device
        if device_type is None:
            return None

        # Check if device type is compatible
        if device_type not in device_types:
            return None

        return {
            "device_id": device.id,
            "device_type": device_type,
            "name": getattr(device, "name", device.id),
            "manufacturer": getattr(device, "manufacturer", "Unknown"),
            "model": getattr(device, "model", "Unknown"),
            "compatible": True,
            "zone": getattr(device, "zone", "Unknown"),
        }

    async def _get_device_info_wildcard(self, device: Any) -> dict[str, Any] | None:
        """Get standardized device information without filtering by device type.

        Args:
            device: Device object from ramses_cc

        Returns:
            Device information dictionary or None if device info cannot be determined
        """
        # Use _SLUG attribute for device type identification (ramses_cc pattern)
        # Fallback to device_type if _SLUG is not available
        device_type = None
        if hasattr(device, "_SLUG"):
            # Map ramses_cc SLUG values to device types
            if device._SLUG == "FAN":
                device_type = "HvacVentilator"
            elif device._SLUG == "CO2":
                device_type = "HvacCarbonDioxideSensor"
            elif device._SLUG == "TEMP":
                device_type = "HvacTemperatureSensor"
            elif device._SLUG == "HUM":
                device_type = "HvacHumiditySensor"
            # Add more SLUG mappings as needed
            else:
                # Default device type for unknown SLUGs
                device_type = "HvacVentilator"
        elif hasattr(device, "device_type"):
            device_type = device.device_type
        else:
            # Default device type if no type information available
            device_type = "HvacVentilator"

        # If we couldn't determine device type, use default
        if device_type is None:
            device_type = "HvacVentilator"

        return {
            "device_id": device.id,
            "device_type": device_type,
            "name": getattr(device, "name", device.id),
            "manufacturer": getattr(device, "manufacturer", "Unknown"),
            "model": getattr(device, "model", "Unknown"),
            "compatible": True,
            "zone": getattr(device, "zone", "Unknown"),
        }

    async def _discover_all_ramses_cc_devices_from_entity_registry(
        self,
    ) -> list[dict]:
        """Fallback method to discover ALL ramses_cc devices from entity registry.

        Returns:
            List of all ramses_cc device information dictionaries
        """
        try:
            from homeassistant.helpers import entity_registry

            entity_registry_instance = entity_registry.async_get(self.hass)

            discovered_devices: list[dict] = []

            # Look for all ramses_cc entities
            for entity in entity_registry_instance.entities.values():
                if (
                    entity.platform == "ramses_cc"
                    and hasattr(entity, "device_id")
                    and entity.device_id
                ):
                    device_id = entity.device_id

                    # Skip if we already found this device
                    if any(d["device_id"] == device_id for d in discovered_devices):
                        continue

                    # Determine device type from entity domain
                    device_type = self._infer_device_type_from_entity(entity)

                    # Create device info for ALL ramses_cc devices
                    device_info = {
                        "device_id": device_id,
                        "device_type": device_type,
                        "name": getattr(entity, "name", device_id) or device_id,
                        "manufacturer": "Unknown",
                        "model": "Unknown",
                        "compatible": True,
                        "zone": getattr(entity, "zone", "Unknown"),
                    }
                    discovered_devices.append(device_info)
                    _LOGGER.debug(
                        f"Found device from entity registry: "
                        f"{device_id} ({device_type})"
                    )

            _LOGGER.info(
                f"Entity registry wildcard discovery found "
                f"{len(discovered_devices)} devices"
            )
            return discovered_devices

        except Exception as e:
            _LOGGER.error(f"Error in entity registry wildcard device discovery: {e}")
            return []

    async def get_device_selection_schema(
        self, discovered_devices: list[dict]
    ) -> vol.Schema:
        """Generate Home Assistant schema for device selection UI.

        Args:
            discovered_devices: List of discovered device information

        Returns:
            Voluptuous schema for device selection form
        """
        _LOGGER.info(
            f"📋 Generating device selection schema for "
            f"{len(discovered_devices)} devices"
        )

        # Create device selection options
        device_options = []
        for device in discovered_devices:
            device_options.append(
                {
                    "value": device["device_id"],
                    "label": f"{device['name']} ({device['device_id']}) - "
                    f"{device['device_type']}",
                }
            )

        # Generate schema using selector.SelectSelector
        #  (this is used in the config_flow)
        from homeassistant.helpers import selector

        schema = vol.Schema(
            {
                vol.Optional(
                    "selected_devices", default=list(self._selected_devices)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )

        return schema  # noqa: RET504

    def set_selected_devices(self, device_ids: list[str]) -> None:
        """Set the currently selected devices.

        Args:
            device_ids: List of device IDs to select
        """
        self._selected_devices = set(device_ids)
        _LOGGER.info(
            f"🎯 Selected devices for {self.feature_id}: {self._selected_devices}"
        )

    def get_selected_devices(self) -> list[str]:
        """Get currently selected devices.

        Returns:
            List of selected device IDs
        """
        return list(self._selected_devices)

    def is_device_selected(self, device_id: str) -> bool:
        """Check if a device is currently selected.

        Args:
            device_id: Device ID to check

        Returns:
            True if device is selected
        """
        return device_id in self._selected_devices

    async def validate_device_selection(
        self, device_ids: list[str], device_types: list[str]
    ) -> dict:
        """Validate selected devices against compatibility requirements.

        Args:
            device_ids: List of device IDs to validate
            device_types: List of required device types

        Returns:
            Validation result dictionary with 'valid' (bool) and 'errors' (list) keys
        """
        result: dict[str, Any] = {"valid": True, "errors": []}

        try:
            if "ramses_cc" not in self.hass.data:
                result["valid"] = False
                result["errors"].append("ramses_cc broker not available")
                return result

            broker = self.hass.data["ramses_cc"]["broker"]

            for device_id in device_ids:
                device = None
                for dev in broker.devices:
                    if dev.id == device_id:
                        device = dev
                        break

                if not device:
                    result["valid"] = False
                    result["errors"].append(f"Device {device_id} not found")
                else:
                    # Use _SLUG attribute for device type identification
                    #  (ramses_cc pattern)
                    # Fallback to device_type if _SLUG is not available
                    device_type = None
                    if hasattr(device, "_SLUG"):
                        # Map ramses_cc SLUG values to device types
                        if device._SLUG == "FAN":
                            device_type = "HvacVentilator"
                        elif device._SLUG == "CO2":
                            device_type = "HvacCarbonDioxideSensor"
                        elif device._SLUG == "TEMP":
                            device_type = "HvacTemperatureSensor"
                        elif device._SLUG == "HUM":
                            device_type = "HvacHumiditySensor"
                        # Add more SLUG mappings as needed
                    elif hasattr(device, "device_type"):
                        device_type = device.device_type

                    # If we couldn't determine device type, skip this device
                    if device_type is None:
                        result["valid"] = False
                        result["errors"].append(
                            f"Device {device_id} has unknown device type"
                        )
                    elif device_type not in device_types:
                        result["valid"] = False
                        result["errors"].append(
                            f"Device {device_id} type {device_type} not compatible "
                            f"with {device_types}"
                        )

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Validation error: {str(e)}")

        return result

    def clear_selection(self) -> None:
        """Clear current device selection."""
        self._selected_devices.clear()
        _LOGGER.info(f"🧹 Cleared device selection for {self.feature_id}")


# Utility functions for framework consumers
async def create_device_selection_manager(
    hass: HomeAssistant, feature_id: str
) -> DeviceSelectionManager:
    """Create a device selection manager instance.

    This is the preferred way to create DeviceSelectionManager instances
    to ensure consistent initialization.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier

    Returns:
        DeviceSelectionManager instance
    """
    return DeviceSelectionManager(hass, feature_id)


# Import cv for schema validation
try:
    import homeassistant.helpers.config_validation as cv
except ImportError:
    cv = None
    _LOGGER.warning("⚠️ Home Assistant config validation not available")
