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
    SCENARIO_DEVICE_UNAVAILABILITY,
    SCENARIO_HVAC_DEVICE_LOSS,
    SCENARIO_STATE_COMPLETED,
    SCENARIO_STATE_ERROR,
    SCENARIO_STATE_IDLE,
    SCENARIO_STATE_RUNNING,
    VERB_I,
    VERB_RP,
    VERB_RQ,
)
from .device_db import AutonomousEntry, ConversationFrame, DeviceDatabase, ResponseEntry

# Device type mapping from device ID prefix (e.g., "37" -> FAN)
# Used to auto-respond to RQs for discovered but not explicitly activated devices
# NOTE: These should match ramses_cc known_list device types
_DEVICE_TYPE_MAP: dict[str, str] = {
    "37": "FAN",  # Fan (Orcon ventilation units)
    "32": "FAN",  # Fan (some models like 32:153289)
    "34": "CO2",  # CO2 sensor
    "29": "REM",  # Remote
    "31": "DIS",  # Display
    "30": "RFS",  # RFS sensor
    "22": "CTL",  # Controller
    "01": "DHW",  # DHW sensor
    "04": "TRV",  # TRV
    "07": "OTB",  # OTB
    "13": "BDR",  # BDR relay
}

_PACKET_RE = re.compile(
    # Match RAMSES frame format: RSSI VERB SEQ SRC DST BROADCAST CODE LEN PAYLOAD
    # Example: 000 RP --- 32:153289 37:168270 --:------ 2411 023 0000010020002DCAAF00...
    r"^(?:\d{3}|---)?\s*"  # Optional RSSI (3 digits or ---)
    r"([ RQWI]{2,3})\s+"  # Verb (space-padded for 1-char, no pad for 2-char)
    r"(?:\d{3}|---)\s+"  # SEQ (non-capturing)
    r"([0-9:]{9})\s+"  # SRC
    r"([0-9:]{9}|--:------)\s+"  # DST
    r"(?:[0-9:]{9}|--:------)\s+"  # BROADCAST (non-capturing)
    r"([0-9A-F]{4})\s+(?:\d{3})\s+([0-9A-F]+)$",  # CODE, LEN (non-capturing), PAYLOAD
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
        self._scenario_tasks: dict[str, asyncio.Task] = {}
        self._state = SCENARIO_STATE_IDLE
        self._messages_sent = 0
        self._message_log: list[str] = []

        endpoint.add_inbound_handler(self._handle_inbound_frame)

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
        # If this device already has an emitter task running, stop it first so that
        # any updated configuration (e.g. excluded codes) takes effect immediately.
        existing_task = self._emitter_tasks.pop(device.device_id, None)
        if existing_task:
            existing_task.cancel()
            try:
                await existing_task
            except asyncio.CancelledError:
                pass

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
                # Log the message
                self._message_log.append(
                    f"[{asyncio.get_event_loop().time():.3f}] {packet[:60]}..."
                )
                # Keep log size bounded
                if len(self._message_log) > 1000:
                    self._message_log = self._message_log[-500:]
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
                    # Log the message
                    self._message_log.append(
                        f"[{asyncio.get_event_loop().time():.3f}] {packet[:60]}..."
                    )
                    # Keep log size bounded
                    if len(self._message_log) > 1000:
                        self._message_log = self._message_log[-500:]
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
        verb = verb.upper().strip()  # Strip leading space from 1-char verbs like ' I'

        if verb != VERB_RQ:
            return

        await self._respond_to_rq(src, dst, code)

    def _get_device_type_from_id(self, device_id: str) -> str | None:
        """Determine device type from device ID prefix.

        :param device_id: Device address like "32:153289"
        :return: Device type slug like "FAN", "HUM", etc.
        """
        type_code = device_id.split(":")[0]
        return _DEVICE_TYPE_MAP.get(type_code)

    async def _respond_to_rq(self, src: str, dst: str, code: str) -> None:
        """Look up and send an RP for an inbound RQ.

        Responds for:
        1. Explicitly activated devices (in _active_devices)
        2. Known device types (from device ID prefix mapping)

        :param src: Requesting device ID.
        :param dst: Target device ID (the simulated device being queried).
        :param code: RAMSES code.
        """
        device = self._active_devices.get(dst)
        slug: str | None = None
        variant_id: str | None = None
        excluded_codes: list[str] = []

        if device:
            # Device is explicitly activated - use its settings
            if not device.enabled or device.suppress_responses:
                return
            if code in device.excluded_codes:
                LOGGER.debug("Dropping RQ %s for %s (excluded)", code, dst)
                return
            slug = device.slug
            variant_id = device.variant_id
            excluded_codes = device.excluded_codes
        else:
            # Device not explicitly activated - try to determine type from ID
            slug = self._get_device_type_from_id(dst)
            if not slug:
                LOGGER.debug("Unknown device type for %s, cannot respond", dst)
                return
            LOGGER.debug(
                "Auto-responding to RQ for discovered device %s (type=%s)", dst, slug
            )

        if code in excluded_codes:
            LOGGER.debug("Dropping RQ %s for %s (excluded)", code, dst)
            return

        resp: ResponseEntry | None = self._db.find_response(slug, code, variant_id)
        if not resp or not resp.payloads:
            LOGGER.debug("No response entry for %s/%s", slug, code)
            return

        payload = resp.payloads[0]
        if resp.delay_ms > 0:
            await asyncio.sleep(resp.delay_ms / 1000.0)

        packet = self._build_packet(dst, src, VERB_RP, code, payload)
        try:
            await self._endpoint.send_packet(packet)
            self._messages_sent += 1
            # Log the message
            self._message_log.append(
                f"[{asyncio.get_event_loop().time():.3f}] {packet[:60]}..."
            )
            # Keep log size bounded
            if len(self._message_log) > 1000:
                self._message_log = self._message_log[-500:]
            LOGGER.debug("Responded %s RP/%s → %s", dst, code, src)
        except Exception as err:
            LOGGER.warning("Failed to send RP for %s/%s: %s", dst, code, err)

    @staticmethod
    def _build_packet(src: str, dst: str, verb: str, code: str, payload: str) -> str:
        """Build a minimal RAMSES packet string for transmission.

        Format: RSSI VERB SEQ SRC DST BROADCAST CODE LEN PAYLOAD
        Example I frame: 082  I --- 32:153289 --:------ 32:153289 1FC9 030 003...
        Example RP frame: 000 RP --- 32:153289 37:168270 --:------ 2411 023 000...

        :param src: Source device ID.
        :param dst: Destination device ID.
        :param verb: Message verb (I, RQ, RP, W).
        :param code: RAMSES code.
        :param payload: Hex payload.
        """
        length = len(payload) // 2
        # Determine RSSI: use 082 for I frames (typical), 000 for responses
        rssi = "082" if verb == "I" else "000"
        # Sequence number is not used in modern systems
        seq = "---"
        # Determine BROADCAST field: for I frames, BROADCAST = SRC;
        # for others, --:------
        broadcast = src if verb == "I" else "--:------"
        # Spacing: 1-char verbs (I, W) have leading space to make them 2 chars
        verb_formatted = f" {verb}" if len(verb) == 1 else verb
        return (
            f"{rssi} {verb_formatted} {seq} {src} {dst} {broadcast} {code} "
            f"{length:03d} {payload}"
        )

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

    # Scenario runner methods (stubs - to be fully implemented)
    async def async_run_device_playback(
        self, log_file: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Playback device messages from packet log."""
        LOGGER.info("Device playback from %s (stub)", log_file)
        return {"success": True, "message": "Playback started", "messages_sent": 0}

    async def async_run_device_suite(
        self, slugs: list[str], duration: int
    ) -> dict[str, Any]:
        """Run a suite of standard device tests."""
        LOGGER.info("Device suite test: %s for %ds (stub)", slugs, duration)
        return {"success": True, "message": "Suite started", "messages_sent": 0}

    async def async_run_discovery_test(self, params: dict[str, Any]) -> dict[str, Any]:
        """Test device discovery by simulating new devices."""
        LOGGER.info("Discovery test (stub)")
        return {"success": True, "message": "Discovery test started"}

    async def async_run_timeout_test(self, delay: float) -> dict[str, Any]:
        """Test timeout handling with slow responses."""
        LOGGER.info("Timeout test with delay %fs (stub)", delay)
        return {"success": True, "message": "Timeout test started"}

    async def async_run_flooding_test(
        self, count: int, interval: float
    ) -> dict[str, Any]:
        """Test flooding/burst message handling."""
        LOGGER.info("Flooding test: %d messages @ %fs (stub)", count, interval)
        return {"success": True, "message": "Flooding test started"}

    async def async_cancel_scenario(self, scenario_id: str) -> None:
        """Cancel a running timed scenario task.

        :param scenario_id: The scenario type id to cancel.
        """
        task = self._scenario_tasks.pop(scenario_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._running_scenarios.pop(scenario_id, None)
        LOGGER.info("Scenario '%s' cancelled", scenario_id)

    async def async_run_unavailability_test(
        self,
        device_id: str | None = None,
        silence_after: float = 30.0,
        resume_after: float = 60.0,
    ) -> dict[str, Any]:
        """Simulate device going offline then coming back.

        :param device_id: Specific device to silence, or None for all active devices.
        :param silence_after: Seconds until device(s) go silent.
        :param resume_after: Seconds after silence_after until device(s) resume.
        """
        targets = [device_id] if device_id else list(self._active_devices.keys())
        if not targets:
            return {"success": False, "error": "No active devices to test"}

        async def _run() -> None:
            LOGGER.info(
                "device_unavailability: silencing %s in %.0fs", targets, silence_after
            )
            await asyncio.sleep(silence_after)
            for did in targets:
                await self.async_silence_device(did)
                LOGGER.info("device_unavailability: silenced %s", did)
            LOGGER.info(
                "device_unavailability: resuming %s in %.0fs", targets, resume_after
            )
            await asyncio.sleep(resume_after)
            for did in targets:
                device = self._active_devices.get(did)
                if device:
                    device.suppress_autonomous = False
                    await self.async_activate_device(device)
                    LOGGER.info("device_unavailability: resumed %s", did)
            self._scenario_tasks.pop(SCENARIO_DEVICE_UNAVAILABILITY, None)
            self._running_scenarios.pop(SCENARIO_DEVICE_UNAVAILABILITY, None)
            LOGGER.info("device_unavailability scenario completed")

        await self.async_cancel_scenario(SCENARIO_DEVICE_UNAVAILABILITY)
        task = self.hass.async_create_background_task(
            _run(), name="device_simulator_unavailability"
        )
        self._scenario_tasks[SCENARIO_DEVICE_UNAVAILABILITY] = task
        self._running_scenarios[SCENARIO_DEVICE_UNAVAILABILITY] = {
            "targets": targets,
            "silence_after": silence_after,
            "resume_after": resume_after,
        }
        return {
            "success": True,
            "message": (
                f"Silencing {targets} in {silence_after:.0f}s,"
                f" resuming after {resume_after:.0f}s"
            ),
            "targets": targets,
        }

    async def async_run_hvac_device_loss(
        self,
        device_id: str,
        loss_after: float = 30.0,
        restore_after: float | None = None,
    ) -> dict[str, Any]:
        """Simulate a specific HVAC device dropping off mid-run.

        :param device_id: Device to silence.
        :param loss_after: Seconds until device goes silent.
        :param restore_after: Optional seconds after loss until device resumes.
                              If None, device stays silent.
        """
        if device_id not in self._active_devices:
            return {
                "success": False,
                "error": f"Device '{device_id}' is not active",
            }

        async def _run() -> None:
            LOGGER.info(
                "hvac_device_loss: silencing %s in %.0fs", device_id, loss_after
            )
            await asyncio.sleep(loss_after)
            await self.async_silence_device(device_id)
            LOGGER.info("hvac_device_loss: %s is now silent", device_id)
            if restore_after is not None:
                await asyncio.sleep(restore_after)
                device = self._active_devices.get(device_id)
                if device:
                    device.suppress_autonomous = False
                    await self.async_activate_device(device)
                    LOGGER.info("hvac_device_loss: %s restored", device_id)
            self._scenario_tasks.pop(SCENARIO_HVAC_DEVICE_LOSS, None)
            self._running_scenarios.pop(SCENARIO_HVAC_DEVICE_LOSS, None)
            LOGGER.info("hvac_device_loss scenario completed")

        await self.async_cancel_scenario(SCENARIO_HVAC_DEVICE_LOSS)
        task = self.hass.async_create_background_task(
            _run(), name="device_simulator_hvac_device_loss"
        )
        self._scenario_tasks[SCENARIO_HVAC_DEVICE_LOSS] = task
        self._running_scenarios[SCENARIO_HVAC_DEVICE_LOSS] = {
            "device_id": device_id,
            "loss_after": loss_after,
            "restore_after": restore_after,
        }
        return {
            "success": True,
            "message": (
                f"Silencing {device_id} in {loss_after:.0f}s"
                + (f", restoring after {restore_after:.0f}s" if restore_after else "")
            ),
            "device_id": device_id,
        }
