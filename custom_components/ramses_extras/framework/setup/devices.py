from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from ...const import DOMAIN, EVENT_DEVICES_UPDATED

_LOGGER = logging.getLogger(__name__)

_setup_in_progress = False


async def setup_entity_registry_device_refresh(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    discover_and_store_devices_fn: Any,
) -> None:
    device_refresh_task: asyncio.Task[None] | None = None
    device_refresh_lock: asyncio.Lock = hass.data[DOMAIN].setdefault(
        "_devices_refresh_lock",
        asyncio.Lock(),
    )

    async def _refresh_devices_after_delay() -> None:
        try:
            await asyncio.sleep(5)
            async with device_refresh_lock:
                await discover_and_store_devices_fn(hass)
            async_dispatcher_send(hass, EVENT_DEVICES_UPDATED)
        except asyncio.CancelledError:
            return

    def _schedule_device_refresh() -> None:
        nonlocal device_refresh_task
        if device_refresh_task is not None and not device_refresh_task.done():
            return
        device_refresh_task = hass.async_create_task(_refresh_devices_after_delay())

    @callback  # type: ignore[untyped-decorator]
    def _cancel_device_refresh_task() -> None:
        nonlocal device_refresh_task
        if device_refresh_task is not None and not device_refresh_task.done():
            device_refresh_task.cancel()

    @callback  # type: ignore[untyped-decorator]
    def _on_entity_registry_updated(
        event: Event[er.EventEntityRegistryUpdatedData],
    ) -> None:
        data = event.data
        if data.get("action") != "create":
            return
        entity_id = data.get("entity_id")
        if not isinstance(entity_id, str):
            return

        entity_reg = er.async_get(hass)
        entry = entity_reg.async_get(entity_id)
        if entry is None or getattr(entry, "platform", None) != "ramses_cc":
            return

        _schedule_device_refresh()

    entry.async_on_unload(_cancel_device_refresh_task)

    entry.async_on_unload(
        hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            _on_entity_registry_updated,
        )
    )


async def discover_and_store_devices(hass: HomeAssistant) -> None:
    devices = await discover_ramses_devices(hass)

    data = hass.data.setdefault(DOMAIN, {})
    data["devices"] = devices
    data["device_discovery_complete"] = True

    device_ids = [getattr(device, "id", str(device)) for device in devices]
    _LOGGER.info(
        "Stored %d devices for platform access: %s",
        len(devices),
        device_ids,
    )


async def async_setup_platforms(hass: HomeAssistant) -> None:
    global _setup_in_progress

    if _setup_in_progress:
        _LOGGER.debug("Platform setup already in progress, skipping")
        return

    _setup_in_progress = True

    try:
        _LOGGER.info("Platform setup: integrating with device discovery...")

        ramses_cc_loaded = "ramses_cc" in hass.config.components
        _LOGGER.info("Ramses CC loaded: %s", ramses_cc_loaded)

        if ramses_cc_loaded:
            _LOGGER.debug("Ramses CC is loaded, verifying device discovery...")

            device_data = hass.data.setdefault(DOMAIN, {})
            if "devices" in device_data and "device_discovery_complete" in device_data:
                _LOGGER.debug(
                    "Device discovery already completed, using cached results"
                )
                devices = device_data["devices"]
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                _LOGGER.debug("Using cached device IDs: %s", device_ids)
            else:
                devices = await discover_ramses_devices(hass)
                device_ids = [getattr(device, "id", str(device)) for device in devices]
                device_data["devices"] = devices
                device_data["device_discovery_complete"] = True
                _LOGGER.debug("Fresh discovery device IDs: %s", device_ids)

            if devices:
                _LOGGER.info(
                    "Platform setup: Found %d Ramses devices: %s",
                    len(devices),
                    device_ids,
                )
            else:
                _LOGGER.info("Platform setup: No Ramses devices found via any method")

            return

        _LOGGER.info("Ramses CC not loaded yet, will retry in 60 seconds.")

        if "ramses_cc" not in hass.config.components:

            async def delayed_retry(*_: Any) -> None:
                global _setup_in_progress
                _setup_in_progress = False
                await async_setup_platforms(hass)

            async_call_later(hass, 60.0, delayed_retry)

    except Exception as e:
        _LOGGER.error("Error in platform setup: %s", e)
    finally:
        _setup_in_progress = False


async def discover_ramses_devices(hass: HomeAssistant) -> list[Any]:
    ramses_cc_entries = hass.config_entries.async_entries("ramses_cc")
    if not ramses_cc_entries:
        _LOGGER.warning("No ramses_cc entries found")
        return await _discover_devices_from_entity_registry(hass)

    entry = ramses_cc_entries[0]

    try:
        broker: Any | None = None
        if "ramses_cc" in hass.data and entry.entry_id in hass.data["ramses_cc"]:
            broker_data = hass.data["ramses_cc"][entry.entry_id]
            if (
                hasattr(broker_data, "__class__")
                and "Broker" in broker_data.__class__.__name__
            ):
                broker = broker_data
            elif isinstance(broker_data, dict) and "broker" in broker_data:
                broker = broker_data["broker"]
            elif not isinstance(broker_data, dict) and hasattr(broker_data, "broker"):
                broker = broker_data.broker
            else:
                broker = broker_data
            _LOGGER.debug("Found broker via hass.data method: %s", broker)

        if broker is None and hasattr(entry, "broker"):
            broker = entry.broker
            _LOGGER.debug("Found broker via entry method: %s", broker)

        if broker is None:
            for integration in hass.data.get("integrations", {}).values():
                if hasattr(integration, "broker") and integration.broker:
                    broker = integration.broker
                    _LOGGER.debug("Found broker via integration registry: %s", broker)
                    break

        if broker is None:
            try:
                from ramses_cc.gateway import Gateway  # noqa: F401

                gateway_entries = [
                    e for e in ramses_cc_entries if hasattr(e, "gateway")
                ]
                if gateway_entries:
                    broker = gateway_entries[0].gateway
                    _LOGGER.debug("Found broker via direct gateway access: %s", broker)
            except ImportError:
                _LOGGER.debug("ramses_cc module not available for direct access")

        if broker is None:
            _LOGGER.warning("Could not find ramses_cc broker via any method")
            return await _discover_devices_from_entity_registry(hass)

        devices = getattr(broker, "_devices", None)
        if devices is None:
            devices = getattr(broker, "devices", None)

        if not devices:
            _LOGGER.debug("No devices found in broker, using entity registry fallback")
            return await _discover_devices_from_entity_registry(hass)

        if isinstance(devices, dict):
            devices_list = list(devices.values())
        elif isinstance(devices, (list, set, tuple)):
            devices_list = list(devices)
        else:
            devices_list = [devices]

        device_ids = [getattr(device, "id", str(device)) for device in devices_list]
        _LOGGER.info(
            "Found %d devices from broker for config flows: %s",
            len(devices_list),
            device_ids,
        )

        return devices_list

    except Exception as e:
        _LOGGER.error("Error accessing ramses_cc broker: %s", e)
        import traceback

        _LOGGER.debug("Full traceback: %s", traceback.format_exc())
        return await _discover_devices_from_entity_registry(hass)


async def _discover_devices_from_entity_registry(hass: HomeAssistant) -> list[str]:
    try:
        entity_registry = er.async_get(hass)
        device_ids: list[str] = []

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
                if (
                    isinstance(device_id, str)
                    and device_id
                    and device_id not in device_ids
                ):
                    device_ids.append(device_id)

        _LOGGER.info(
            "Found %d devices via entity registry fallback: %s",
            len(device_ids),
            device_ids,
        )
        return device_ids

    except Exception as e:
        _LOGGER.error("Error discovering devices from entity registry: %s", e)
        return []


async def cleanup_orphaned_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_registry: Any | None = None,
    entity_registry: Any | None = None,
) -> None:
    device_registry = cast(Any, device_registry or dr.async_get(hass))
    entity_registry = cast(Any, entity_registry or er.async_get(hass))

    if device_registry is None:
        _LOGGER.warning("Device registry unavailable, skipping cleanup")
        return

    if entity_registry is None:
        _LOGGER.warning("Entity registry unavailable, skipping cleanup")
        return

    ramses_devices = []
    for device_entry in device_registry.devices.values():
        if any(identifier[0] == DOMAIN for identifier in device_entry.identifiers):
            ramses_devices.append(device_entry)

    orphaned_devices = []
    for device_entry in ramses_devices:
        entities_obj = getattr(entity_registry, "entities", None)

        if entities_obj is None:
            continue

        has_entities = False
        if hasattr(entities_obj, "get"):
            try:
                device_entities = entities_obj.get(device_entry.id, [])
                if isinstance(device_entities, list):
                    has_entities = bool(device_entities)
            except Exception:
                has_entities = False

        if not has_entities and hasattr(entities_obj, "values"):
            try:
                values = list(entities_obj.values())
                if values and all(isinstance(v, list) for v in values):
                    has_entities = bool(entities_obj.get(device_entry.id, []))
                else:
                    has_entities = any(
                        getattr(entity_entry, "device_id", None) == device_entry.id
                        for entity_entry in values
                    )
            except Exception:
                has_entities = False

        if not has_entities:
            device_id = list(device_entry.identifiers)[0][1]
            orphaned_devices.append((device_id, device_entry))
            _LOGGER.info("Found orphaned device: %s (no entities)", device_id)

    if not orphaned_devices:
        _LOGGER.debug("No orphaned devices found")
        return

    _LOGGER.info("Removing %d orphaned devices", len(orphaned_devices))

    entry_id = getattr(entry, "entry_id", None)
    if not isinstance(entry_id, str):
        entry_id = getattr(entry, "id", None)
    if not isinstance(entry_id, str):
        entry_id = None

    for device_id, device_entry in orphaned_devices:
        if entry_id and entry_id not in device_entry.config_entries:
            continue

        try:
            await device_registry.async_remove_device(device_entry.id)
            _LOGGER.info("Removed orphaned device: %s", device_id)
        except Exception as e:
            _LOGGER.warning(f"Failed to remove device {device_id}: {e}")
