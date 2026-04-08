# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Scenario engine for Device Simulator.

Orchestrates simulated device behaviour via the comm endpoint.
Each active device gets:
  - A periodic emitter task (autonomous I messages)
  - A response handler (RQ→RP via comm endpoint)
  - Optional conversation playback

Scenarios wire these together with timing, exclusions, and profile loading.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from datetime import UTC

from .comm_endpoint import SimulatorCommEndpoint
from .const import (
    LOGGER,
    SCENARIO_STATE_COMPLETED,
    SCENARIO_STATE_ERROR,
    SCENARIO_STATE_IDLE,
    SCENARIO_STATE_RUNNING,
    VERB_I,
    VERB_RP,
    VERB_RQ,
)
from .device_db import AutonomousEntry, ConversationFrame, DeviceDatabase, ResponseEntry

_PACKET_RE = re.compile(
    r"^[\d\-T:.]+\s+---\s+(\S+)\s+\S+\s+(\S+)\s+(\S+)\s+\S+\s+([0-9A-F]{4})\s+\d+\s+(\S+)",
    re.IGNORECASE,
)


@dataclass
class ActiveDevice:
    """A device instance active in a scenario.

    :param device_id: Real RAMSES device ID (e.g. '20:123456').
    :param slug: Device type slug (e.g. 'FAN').
    :param variant_id: Hardware variant id.
    :param excluded_codes: Codes suppressed for this device.
    :param suppress_autonomous: If True, no autonomous messages are emitted.
    :param suppress_responses: If True, no RQ responses are sent.
    :param enabled: If False, device is completely silent.
    """

    device_id: str
    slug: str
    variant_id: str | None = None
    excluded_codes: list[str] = field(default_factory=list)
    suppress_autonomous: bool = False
    suppress_responses: bool = False
    enabled: bool = True


@dataclass
class ScenarioResult:
    """Result of a scenario run.

    :param scenario_id: Identifier.
    :param success: Completed without error.
    :param messages_sent: Total frames sent.
    :param duration_seconds: Wall-clock duration.
    :param errors: Error messages.
    """

    scenario_id: str
    success: bool
    messages_sent: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class ScenarioEngine:
    """Orchestrates device simulation scenarios via the comm endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        endpoint: SimulatorCommEndpoint,
        db: DeviceDatabase,
    ) -> None:
        """Initialize the scenario engine.

        :param hass: Home Assistant instance.
        :param endpoint: Communication endpoint (MQTT or serial).
        :param db: Device database.
        """
        self.hass = hass
        self._endpoint = endpoint
        self._db = db

        self._active_devices: dict[str, ActiveDevice] = {}
        self._emitter_tasks: dict[str, asyncio.Task] = {}
        self._running_scenarios: dict[str, dict[str, Any]] = {}
        self._state = SCENARIO_STATE_IDLE
        self._messages_sent = 0
        self._message_log: list[str] = []

        endpoint.set_inbound_handler(self._handle_inbound_frame)

    async def async_setup(self) -> None:
        """Connect the endpoint and load the device DB."""
        self._db.load_all()
        await self._endpoint.async_connect()
        LOGGER.info("ScenarioEngine ready. DB: %s", self._db.stats())

    async def async_teardown(self) -> None:
        """Stop all emitters and disconnect."""
        await self.async_stop_all()
        await self._endpoint.async_disconnect()

    async def async_activate_device(self, device: ActiveDevice) -> None:
        """Activate a device: start its periodic emitter.

        :param device: ActiveDevice descriptor.
        """
        if not device.enabled:
            return

        self._active_devices[device.device_id] = device

        if not device.suppress_autonomous:
            periodic = self._db.get_periodic(device.slug, device.variant_id)
            task = self.hass.async_create_background_task(
                self._periodic_emitter(device, periodic),
                name=f"device_simulator_emitter_{device.device_id}",
            )
            self._emitter_tasks[device.device_id] = task
            LOGGER.debug("Started emitter for %s (%s)", device.device_id, device.slug)

    async def async_silence_device(self, device_id: str) -> None:
        """Stop a device's autonomous emission (simulate going offline).

        :param device_id: Device to silence.
        """
        task = self._emitter_tasks.pop(device_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if device_id in self._active_devices:
            self._active_devices[device_id].suppress_autonomous = True
        LOGGER.info("Device %s silenced", device_id)

    async def async_stop_all(self) -> None:
        """Stop all active emitters and clear state."""
        for task in list(self._emitter_tasks.values()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._emitter_tasks.clear()
        self._active_devices.clear()
        self._state = SCENARIO_STATE_IDLE
        LOGGER.debug("ScenarioEngine stopped all devices")

    async def async_play_conversation(
        self,
        ref: str,
        device_map: dict[str, str],
        scheme: str | None = None,
        speed: float = 1.0,
    ) -> ScenarioResult:
        """Play back a conversation block by ref.

        :param ref: Conversation ref (e.g. 'fan+co2/dcv_reaction').
        :param device_map: Slug → device_id mapping (e.g. {'FAN': '20:123456'}).
        :param scheme: Optional scheme filter.
        :param speed: Playback speed multiplier.
        """
        conv = self._db.get_conversation(ref, scheme)
        if not conv:
            return ScenarioResult(
                scenario_id=ref,
                success=False,
                errors=[f"Conversation '{ref}' not found in DB"],
            )

        messages_sent = 0
        errors: list[str] = []
        start = asyncio.get_event_loop().time()

        prev_t = 0.0
        for frame in conv.frames:
            delay = (frame.t - prev_t) / speed
            if delay > 0:
                await asyncio.sleep(delay)
            prev_t = frame.t

            src_id = device_map.get(frame.src, frame.src)
            dst_id = (
                device_map.get(frame.dst, frame.dst)
                if frame.dst != "ALL"
                else "--:------"
            )

            device = self._active_devices.get(src_id)
            if device and not device.enabled:
                continue
            if device and frame.code in device.excluded_codes:
                continue

            packet = self._build_packet(
                src_id, dst_id, frame.verb, frame.code, frame.payload
            )
            try:
                await self._endpoint.send_packet(packet)
                messages_sent += 1
            except Exception as err:
                errors.append(str(err))

        return ScenarioResult(
            scenario_id=ref,
            success=not errors,
            messages_sent=messages_sent,
            duration_seconds=asyncio.get_event_loop().time() - start,
            errors=errors,
        )

    async def _periodic_emitter(
        self,
        device: ActiveDevice,
        entries: list[AutonomousEntry],
        speed: float = 1.0,
    ) -> None:
        """Background task: emit periodic I messages for a device.

        :param device: ActiveDevice.
        :param entries: Autonomous entries to emit.
        :param speed: Speed multiplier.
        """
        if not entries:
            return

        payload_idx: dict[str, int] = {e.code: 0 for e in entries}

        while True:
            for entry in entries:
                if device.suppress_autonomous or not device.enabled:
                    break
                if entry.code in device.excluded_codes:
                    continue
                if not entry.payloads:
                    continue

                idx = payload_idx[entry.code]
                payload = entry.payloads[idx % len(entry.payloads)]
                payload_idx[entry.code] = idx + 1

                packet = self._build_packet(
                    device.device_id,
                    "--:------",
                    VERB_I,
                    entry.code,
                    payload,
                )
                try:
                    await self._endpoint.send_packet(packet)
                    self._messages_sent += 1
                except Exception as err:
                    LOGGER.warning(
                        "Emitter send error for %s/%s: %s",
                        device.device_id,
                        entry.code,
                        err,
                    )

            # Sleep for the shortest interval among all entries (next wake-up)
            min_interval = min((e.interval_seconds for e in entries), default=60.0)
            await asyncio.sleep(min_interval / speed)

    async def _handle_inbound_frame(self, frame: str) -> None:
        """Handle a frame received from ramses_rf (outbound /tx).

        Parses the verb and code, routes RQ to response engine.

        :param frame: Raw RAMSES packet string.
        """
        match = _PACKET_RE.match(frame.strip())
        if not match:
            return

        verb, src, dst, code, payload = match.groups()
        verb = verb.upper()

        if verb != VERB_RQ:
            return

        await self._respond_to_rq(src, dst, code)

    async def _respond_to_rq(self, src: str, dst: str, code: str) -> None:
        """Look up and send an RP for an inbound RQ.

        :param src: Requesting device ID.
        :param dst: Target device ID (the simulated device being queried).
        :param code: RAMSES code.
        """
        device = self._active_devices.get(dst)
        if not device:
            return
        if not device.enabled or device.suppress_responses:
            return
        if code in device.excluded_codes:
            LOGGER.debug("Dropping RQ %s for %s (excluded)", code, dst)
            return

        resp: ResponseEntry | None = self._db.find_response(
            device.slug, code, device.variant_id
        )
        if not resp or not resp.payloads:
            LOGGER.debug("No response entry for %s/%s", device.slug, code)
            return

        payload = resp.payloads[0]
        if resp.delay_ms > 0:
            await asyncio.sleep(resp.delay_ms / 1000.0)

        packet = self._build_packet(dst, src, VERB_RP, code, payload)
        try:
            await self._endpoint.send_packet(packet)
            self._messages_sent += 1
            LOGGER.debug("Responded %s RP/%s → %s", dst, code, src)
        except Exception as err:
            LOGGER.warning("Failed to send RP for %s/%s: %s", dst, code, err)

    @staticmethod
    def _build_packet(src: str, dst: str, verb: str, code: str, payload: str) -> str:
        """Build a minimal RAMSES packet string.

        Format: TIMESTAMP ---  VERB SRC DST --- CODE LEN PAYLOAD

        :param src: Source device ID.
        :param dst: Destination device ID.
        :param verb: Message verb.
        :param code: RAMSES code.
        :param payload: Hex payload.
        """
        from datetime import datetime, timezone

        ts = datetime.now(UTC).isoformat(timespec="microseconds")
        length = len(payload) // 2
        return f"{ts} ---  {verb} --- {src} {dst} --- {code} {length:03d} {payload}"

    @property
    def state(self) -> str:
        """Return current engine state."""
        return self._state

    @property
    def messages_sent(self) -> int:
        """Return total messages sent since startup."""
        return self._messages_sent

    @property
    def active_device_ids(self) -> list[str]:
        """Return list of currently active device IDs."""
        return list(self._active_devices.keys())
