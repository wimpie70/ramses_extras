from __future__ import annotations

import asyncio
import logging
from asyncio import Task
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

LOGGER: logging.Logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.core import HomeAssistant

    from ..device_db import DeviceDatabase
    from ..scenario_engine import ActiveDevice, ScenarioEngine


@dataclass(slots=True)
class ScenarioResult:
    """Outcome of a scenario run."""

    scenario_id: str
    success: bool
    messages_sent: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScenarioDefinition:
    """Describes a scenario that can be loaded dynamically."""

    scenario_id: str
    label: str
    toggleable: bool
    can_run_with: list[str]
    description: str
    run: Callable[[ScenarioContext, dict[str, Any]], Awaitable[ScenarioResult]]


@dataclass(slots=True)
class ScenarioContext:
    """Shared helpers exposed to scenario modules.

    The context wraps the ScenarioEngine so scenarios can silence/resume devices
    without importing the engine module directly (avoids circular imports).
    """

    hass: HomeAssistant
    engine: ScenarioEngine

    @property
    def logger(self) -> logging.Logger:
        """Return the simulator logger for convenience."""
        return LOGGER

    def get_active_device(self, device_id: str) -> ActiveDevice | None:
        """Return the ActiveDevice descriptor if it exists."""
        return self.engine._active_devices.get(device_id)

    def active_devices_by_slug(self, slug: str) -> list[ActiveDevice]:
        """Return active devices filtered by slug."""

        slug = slug.upper()
        return [
            device
            for device in self.engine._active_devices.values()
            if device.slug == slug
        ]

    @property
    def device_db(self) -> DeviceDatabase:
        """Expose the loaded device database to scenarios."""

        return self.engine._db

    def active_device_ids(self) -> list[str]:
        """Return IDs of currently active devices."""
        return list(self.engine._active_devices.keys())

    async def silence_device(self, device_id: str) -> None:
        """Stop autonomous emissions for a device."""
        await self.engine.async_silence_device(device_id)

    async def resume_device(self, device_id: str) -> None:
        """Resume autonomous emissions for a device if it exists."""
        device = self.engine._active_devices.get(device_id)
        if device:
            device.suppress_autonomous = False
            await self.engine.async_activate_device(device)

    def schedule_background_task(self, coro: Awaitable[Any], *, name: str) -> Task[Any]:
        """Schedule a background task via Home Assistant."""
        return cast(Task[Any], self.hass.async_create_background_task(coro, name=name))

    async def cancel_existing(self, scenario_id: str) -> None:
        """Cancel a running scenario via the engine helper."""
        await self.engine.async_cancel_scenario(scenario_id)

    def register_task(self, scenario_id: str, task: Task[Any]) -> None:
        """Store a background task under the scenario id."""
        self.engine._scenario_tasks[scenario_id] = task

    def set_running_metadata(self, scenario_id: str, metadata: dict[str, Any]) -> None:
        """Persist metadata about a running scenario."""
        self.engine._running_scenarios[scenario_id] = metadata

    def clear_running(self, scenario_id: str) -> None:
        """Remove stored task + metadata for a scenario id."""
        self.engine._scenario_tasks.pop(scenario_id, None)
        self.engine._running_scenarios.pop(scenario_id, None)

    def build_packet(
        self, src: str, dst: str, verb: str, code: str, payload: str
    ) -> str:
        """Proxy to the engine packet builder for convenience."""

        return self.engine._build_packet(src, dst, verb, code, payload)

    async def send_packet(self, packet: str) -> None:
        """Send a packet via the simulator endpoint."""

        await self.engine._endpoint.send_packet(packet)

    def new_active_device(self, **kwargs: Any) -> ActiveDevice:
        """Construct an ActiveDevice without importing the engine directly."""

        from ..scenario_engine import ActiveDevice  # Lazy import, avoids circular deps

        return ActiveDevice(**kwargs)
