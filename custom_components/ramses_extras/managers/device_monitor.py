"""Simple device monitor that only listens to ramses_cc for new devices."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DeviceMonitor:
    """Simple monitor that only adds new devices discovered by ramses_cc."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize device monitor."""
        self.hass = hass
        self._known_devices: set[str] = set()
        self._ramses_cc_available = False

    async def start_monitoring(self) -> None:
        """Start monitoring by getting initial device list from hass.data."""
        _LOGGER.info("Starting simple device monitor")

        # Check if ramses_cc is available
        ramses_domain = "ramses_cc"
        if ramses_domain not in self.hass.data:
            _LOGGER.warning("ramses_cc not loaded, device monitoring disabled")
            return

        self._ramses_cc_available = True

        # Get device list from hass.data (populated by device discovery)
        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        self._known_devices = set(devices)
        _LOGGER.info(f"Initial device list from hass.data: {devices}")

        # Set up listeners for ongoing monitoring
        self._setup_ramses_cc_listeners()
        self._setup_device_registry_listener()

        # Send initial device discovery signal if we have devices
        if devices:
            async_dispatcher_send(self.hass, f"{DOMAIN}_devices_discovered", devices)

    def _setup_ramses_cc_listeners(self) -> None:
        """Set up listeners for ramses_cc device events."""
        ramses_domain = "ramses_cc"

        # Listen to all platform-specific new device signals from ramses_cc
        platforms = ["sensor", "number", "switch", "binary_sensor", "climate"]

        for platform in platforms:
            signal = f"{ramses_domain}_new_devices_{platform}"

            async_dispatcher_connect(
                self.hass, signal, self._handle_ramses_cc_device_event
            )

    def _setup_device_registry_listener(self) -> None:
        """Set up listener for device registry changes via event bus."""
        # Listen for device registry events on the event bus
        self.hass.bus.async_listen(
            "device_registry_updated", self._handle_device_registry_event
        )
        _LOGGER.debug("Listening to device registry events")

    def _handle_device_registry_event(self, event: Any) -> None:
        """Handle device registry events (removals)."""
        try:
            # Check if this is a removal event
            if event.data.get("action") == "remove":
                device_id = event.data.get("device_id")

                if device_id and device_id in self._known_devices:
                    _LOGGER.info(f"Device manually removed from HA: {device_id}")
                    self._known_devices.remove(device_id)

                    # Notify platform reloader about removed device
                    async_dispatcher_send(
                        self.hass, f"{DOMAIN}_devices_removed", [device_id]
                    )

        except Exception as e:
            _LOGGER.debug(f"Error handling device registry event: {e}")

    async def _handle_ramses_cc_device_event(self, devices: list[Any]) -> None:
        """Handle new devices discovered by ramses_cc."""
        if not devices:
            return

        # Extract device IDs from the device objects
        new_device_ids = []
        for device in devices:
            # Handle both device objects and device IDs
            if hasattr(device, "id"):
                device_id = device.id
            else:
                device_id = str(device)

            # Check if this is a device type we support
            if await self._is_supported_device(device_id):
                new_device_ids.append(device_id)

        if new_device_ids:
            new_devices_set = set(new_device_ids)
            added_devices = new_devices_set - self._known_devices

            if added_devices:
                _LOGGER.info(f"New devices detected via ramses_cc: {added_devices}")
                self._known_devices.update(added_devices)

                # Notify platform reloader about new devices
                async_dispatcher_send(
                    self.hass, f"{DOMAIN}_devices_added", list(added_devices)
                )

    async def _is_supported_device(self, device_id: str) -> bool:
        """Check if a device is supported by ramses_extras."""
        try:
            # Use our existing helper to check if device is supported
            from ..helpers.device import find_ramses_device, get_device_type

            device = find_ramses_device(self.hass, device_id)
            if device:
                device_type = get_device_type(device)
                return device_type in ["HvacVentilator"]  # Add more types as needed

            return False

        except Exception as e:
            _LOGGER.debug(f"Error checking device support for {device_id}: {e}")
            return False

    async def stop_monitoring(self) -> None:
        """Stop monitoring (no cleanup needed for event listeners)."""
        _LOGGER.info("Stopping device monitor")
        self._ramses_cc_available = False
