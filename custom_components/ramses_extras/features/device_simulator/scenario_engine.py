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
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


from ...framework.helpers.ramses_message_stream import get_ramses_message_stream
from .comm_endpoint import SimulatorCommEndpoint
from .const import (
    LOGGER,
    SCENARIO_AUTO_ANSWER,
    SCENARIO_DEVICE_UNAVAILABILITY,
    SCENARIO_HVAC_DEVICE_LOSS,
    SCENARIO_MANUAL_DEVICE_INJECTION,
    SCENARIO_PROFILE_EMISSIONS,
    SCENARIO_REGISTRY,
    SCENARIO_STATE_IDLE,
    VERB_I,
    VERB_RP,
    VERB_RQ,
    VERB_W,
)
from .device_db import AutonomousEntry, DeviceDatabase, ResponseEntry
from .message_log import DeviceMessageLog, PacketDirection
from .response_templates import build_dynamic_response
from .scenarios import discover_scenarios
from .scenarios.base import ScenarioContext, ScenarioDefinition, ScenarioResult
from .system_config import SIM_DEVICE_ID, SystemConfigProfile

MESSAGE_EVENT = "ramses_extras_simulator_messages"

_PACKET_RE = re.compile(
    # Match RAMSES frame format: [RSSI] VERB SEQ SRC DST BROADCAST CODE LEN PAYLOAD
    # Example: 000 RP --- 32:153289 37:168270 --:------ 2411 023 0000010020002DCAAF00...
    # Or:  W --- 37:170000 32:150000 --:------ 2411 023 000075009200000438...
    r"^(?:\d{3}|---)?\s*"  # Optional RSSI (3 digits) or '---'
    r"([ RQWI]{1,2})\s+"  # Verb (space-padded for 1-char, 2-char verbs as-is)
    r"(?:\d{3}|---)?\s+"  # Optional SEQ (some frames omit it)
    r"([0-9:]{9})\s+"  # SRC
    r"([0-9:]{9}|--:------)\s+"  # DST
    r"(?:[0-9:]{9}|--:------)\s+"  # BROADCAST (non-capturing)
    r"([0-9A-F]{4})\s+(?:\d{3})?\s*([0-9A-F]+)$",  # CODE, optional LEN, PAYLOAD
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
    :param bound_device_id: Device ID this device is bound to (e.g. FAN -> REM).
    """

    device_id: str
    slug: str
    variant_id: str | None = None
    excluded_codes: list[str] = field(default_factory=list)
    suppress_autonomous: bool = False
    suppress_responses: bool = False
    enabled: bool = True
    bound_device_id: str | None = None
    origin: str = "scenario"


class ScenarioEngine:
    """Orchestrates device simulation scenarios via the comm endpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        endpoint: SimulatorCommEndpoint,
        db: DeviceDatabase,
        *,
        scenario_definitions: dict[str, ScenarioDefinition] | None = None,
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
        # Per-scenario pause gates. Event is *set* → running; *cleared* → paused.
        self._scenario_pause_events: dict[str, asyncio.Event] = {}
        self._state: str = SCENARIO_STATE_IDLE
        self._messages_sent = 0
        self._messages_received = 0
        self._message_log: list[str] = []
        self._response_index: dict[tuple[str, str], int] = {}
        self._scenario_definitions = scenario_definitions or discover_scenarios()
        self._profile_device_ids: set[str] = set()
        self._manual_device_ids: set[str] = set()
        self._primed_fans: set[str] = set()
        self._autonomous_speed: float = 1.0
        self._recent_frames: dict[tuple[PacketDirection, str], float] = {}
        # Global RQ→RP auto-answer toggle (default on).
        # When False the engine receives RQs but never replies — simulates a
        # device that is powered off or unreachable (e.g. broken ESP).
        self._auto_answer_enabled: bool = True
        self.message_log: DeviceMessageLog = DeviceMessageLog()

        endpoint.add_inbound_handler(self._handle_inbound_frame)

    @property
    def device_db(self) -> DeviceDatabase:
        """Expose the device database to external consumers."""
        return self._db

    async def async_setup(self) -> None:
        """Connect the endpoint and load the device DB."""
        self._db.load_all()
        await self._endpoint.async_connect()
        LOGGER.info("ScenarioEngine ready. DB: %s", self._db.stats())

    def _log_and_emit(
        self, direction: PacketDirection, frame: str, timestamp: float | None = None
    ) -> None:
        now = time.monotonic()
        key = (direction, frame)
        last_seen = self._recent_frames.get(key)
        if last_seen is not None and now - last_seen < 0.25:
            return
        self._recent_frames[key] = now
        cutoff = now - 2.0
        self._recent_frames = {
            recent_key: recent_ts
            for recent_key, recent_ts in self._recent_frames.items()
            if recent_ts >= cutoff
        }
        entry = self.message_log.log(direction, frame, timestamp)
        if not entry:
            return
        self.hass.bus.async_fire(
            MESSAGE_EVENT,
            {"messages": [self.message_log.to_dict(entry)]},
        )

    def log_processed_frame(self, frame: str, timestamp: float | None = None) -> None:
        self._log_and_emit("outbound", frame, timestamp)

    def is_scenario_running(self, scenario_id: str) -> bool:
        """Return True if the scenario id is currently marked as running."""

        return scenario_id in self._running_scenarios

    def set_running_metadata(self, scenario_id: str, metadata: dict[str, Any]) -> None:
        """Store metadata describing a running scenario."""

        self._running_scenarios[scenario_id] = metadata

    def clear_running_metadata(self, scenario_id: str) -> None:
        """Clear metadata for a scenario id if present."""

        self._running_scenarios.pop(scenario_id, None)

    async def async_teardown(self) -> None:
        """Stop all emitters and disconnect."""
        await self.async_stop_all()
        await self._endpoint.async_disconnect()

    async def async_emit_startup_burst(self) -> None:
        """Emit an immediate I-frame burst for all active devices.

        Called after HA restarts so ramses_cc can re-discover active devices
        from I frames rather than waiting for RQ→timeout cycles.
        """
        for device in list(self._active_devices.values()):
            if device.suppress_autonomous or not device.enabled:
                continue
            entries = self._db.get_periodic(device.slug, device.variant_id)
            if not entries:
                continue
            payload_idx: dict[str, int] = {e.code: 0 for e in entries}
            LOGGER.debug(
                "Startup burst (restart) for %s (%d codes)",
                device.device_id,
                len(entries),
            )
            await self._emit_burst(device, entries, payload_idx)

    @staticmethod
    def _coerce_code_list(value: Any) -> list[str]:
        """Normalize excluded code inputs to a list of uppercase strings."""

        if not value:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped.upper()] if stripped else []
        if isinstance(value, (list, tuple, set)):
            return [str(code).strip().upper() for code in value if str(code).strip()]
        return []

    def _build_profile_device_entry(
        self,
        profile: SystemConfigProfile,
        device_id: str,
        entry: Any,
    ) -> ActiveDevice | None:
        """Return an ActiveDevice for a single known_list entry."""

        if not isinstance(entry, dict):
            return None

        slug = (entry.get("class") or "FAN").upper()
        if slug == "HGI":
            return None

        overrides = profile.device_configs.get(device_id, {})
        variant_id = (
            overrides.get("variant_id")
            or overrides.get("variant")
            or entry.get("variant_id")
            or entry.get("variant")
        )
        excluded_codes = overrides.get("excluded_codes")
        if excluded_codes is None:
            excluded_codes = entry.get("excluded_codes")
        suppress_autonomous = overrides.get(
            "suppress_autonomous", entry.get("suppress_autonomous", False)
        )
        suppress_responses = overrides.get(
            "suppress_responses", entry.get("suppress_responses", False)
        )
        enabled = overrides.get("enabled", entry.get("enabled", True))
        bound_device_id = overrides.get("bound") or entry.get("bound")

        return ActiveDevice(
            device_id=device_id,
            slug=slug,
            variant_id=variant_id,
            excluded_codes=self._coerce_code_list(excluded_codes),
            suppress_autonomous=bool(suppress_autonomous),
            suppress_responses=bool(suppress_responses),
            enabled=bool(enabled),
            bound_device_id=bound_device_id,
            origin="profile",
        )

    def build_profile_devices(self, profile: SystemConfigProfile) -> list[ActiveDevice]:
        """Construct ActiveDevice instances for every profile known_list entry."""

        known_list = profile.device_configs.get("_known_list") or {}
        devices: list[ActiveDevice] = []
        for device_id, entry in known_list.items():
            device = self._build_profile_device_entry(profile, device_id, entry)
            if device:
                devices.append(device)
        return devices

    def build_profile_device(
        self, profile: SystemConfigProfile, device_id: str
    ) -> ActiveDevice | None:
        """Construct a single ActiveDevice from the profile known_list."""

        known_list = profile.device_configs.get("_known_list") or {}
        entry = known_list.get(device_id)
        if not entry:
            return None
        return self._build_profile_device_entry(profile, device_id, entry)

    async def async_stop_profile_devices(self) -> None:
        """Stop and remove devices that were started via the profile scenario."""

        for device_id in list(self._profile_device_ids):
            await self.async_silence_device(device_id)
            device = self._active_devices.get(device_id)
            if device and device.origin == "profile":
                self._active_devices.pop(device_id, None)
        self._profile_device_ids.clear()

    async def async_stop_manual_devices(self, device_id: str | None = None) -> None:
        """Stop and remove devices that were injected manually."""

        targets = (
            [device_id] if device_id is not None else list(self._manual_device_ids)
        )
        for target_id in targets:
            if target_id not in self._manual_device_ids:
                continue
            await self.async_silence_device(target_id)
            self._active_devices.pop(target_id, None)
            self._manual_device_ids.discard(target_id)

    def get_device_source(self, device_id: str) -> str | None:
        """Return the origin/source tag for a device if it exists."""

        device = self._active_devices.get(device_id)
        return device.origin if device else None

    def is_profile_device(self, device_id: str) -> bool:
        """Return True if the device was started via the profile scenario."""

        return device_id in self._profile_device_ids

    def is_device_active(self, device_id: str) -> bool:
        """Return True if a device_id currently has an active descriptor."""

        return device_id in self._active_devices

    def is_manual_device(self, device_id: str) -> bool:
        """Return True if the device was injected manually."""

        return device_id in self._manual_device_ids

    def has_manual_devices(self) -> bool:
        """Return True if any manual injection devices are active."""

        return bool(self._manual_device_ids)

    def get_autonomous_speed(self) -> float:
        """Return the global autonomous emission speed multiplier."""

        return self._autonomous_speed

    def set_autonomous_speed(self, speed: float) -> None:
        """Set the global autonomous emission speed multiplier (clamped)."""

        try:
            value = float(speed)
        except (TypeError, ValueError):
            value = 1.0
        self._autonomous_speed = max(0.01, min(value, 100.0))

    async def async_activate_device(
        self,
        device: ActiveDevice,
        *,
        start_emitter: bool | None = None,
        emit_startup_burst: bool | None = None,
    ) -> None:
        """Activate a device: optionally start its periodic emitter.

        :param device: ActiveDevice descriptor.
        :param start_emitter: Force whether the background emitter task runs.
            Defaults to ``not device.suppress_autonomous`` so existing callers
            keep their behaviour.
        :param emit_startup_burst: When True, emit a discovery burst even if the
            emitter is not started. Defaults to ``not start_emitter`` so silent
            registrations still announce themselves once.
        """

        if start_emitter is None:
            start_emitter = not device.suppress_autonomous
        if emit_startup_burst is None:
            emit_startup_burst = not start_emitter

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
        if device.origin == "profile":
            self._profile_device_ids.add(device.device_id)
            self._manual_device_ids.discard(device.device_id)
        elif device.origin == "manual":
            self._manual_device_ids.add(device.device_id)
            self._profile_device_ids.discard(device.device_id)
        else:
            self._profile_device_ids.discard(device.device_id)
            self._manual_device_ids.discard(device.device_id)

        # Fire event to notify UI that devices have changed
        self.hass.bus.async_fire(
            "ramses_extras_simulator_devices_changed",
            {
                "device_id": device.device_id,
                "action": "activated",
                "count": len(self._active_devices),
                "source": device.origin,
            },
        )

        periodic: list[AutonomousEntry] = []
        needs_periodic = (start_emitter and not device.suppress_autonomous) or (
            emit_startup_burst and not device.suppress_autonomous
        )
        if needs_periodic:
            periodic = self._db.get_periodic(device.slug, device.variant_id)

        if (
            emit_startup_burst
            and periodic
            and self._auto_answer_enabled
            and not device.suppress_responses
        ):
            payload_idx = {entry.code: 0 for entry in periodic}
            LOGGER.debug(
                "Startup burst for %s (%d codes)", device.device_id, len(periodic)
            )
            asyncio.create_task(self._emit_burst(device, periodic, payload_idx))

        if start_emitter and not device.suppress_autonomous:
            LOGGER.debug("Starting emitter task for %s", device.device_id)
            self._emitter_tasks[device.device_id] = asyncio.create_task(
                self._periodic_emitter(device, periodic)
            )

        if device.slug == "FAN":
            await self._prime_fan_params(device)

    async def async_silence_device(self, device_id: str) -> None:
        """Stop a device's autonomous emission (simulate going offline).

        :param device_id: Device to silence.
        """
        device = self._active_devices.get(device_id)
        task = self._emitter_tasks.pop(device_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if device_id in self._active_devices:
            self._active_devices[device_id].suppress_autonomous = True
            # Fire event to notify UI that devices have changed
            self.hass.bus.async_fire(
                "ramses_extras_simulator_devices_changed",
                {
                    "device_id": device_id,
                    "action": "silenced",
                    "count": len(self._active_devices),
                    "source": device.origin if device else None,
                },
            )
        self._profile_device_ids.discard(device_id)
        self._manual_device_ids.discard(device_id)
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
        device_count = len(self._active_devices)
        self._active_devices.clear()
        self._profile_device_ids.clear()
        self._manual_device_ids.clear()
        self._state = SCENARIO_STATE_IDLE
        # Fire event to notify UI that all devices have been stopped
        if device_count > 0:
            self.hass.bus.async_fire(
                "ramses_extras_simulator_devices_changed",
                {"action": "stopped_all", "count": 0},
            )
        # Drain any packets that were already queued but not yet published so
        # they don't get sent after the user pressed Stop.
        send_queue = getattr(self._endpoint, "_send_queue", None)
        if send_queue is not None:
            drained = 0
            while not send_queue.empty():
                try:
                    send_queue.get_nowait()
                    drained += 1
                except Exception:  # noqa: BLE001
                    break
            if drained:
                LOGGER.debug("Drained %d queued packets on stop", drained)
        LOGGER.debug("ScenarioEngine stopped all devices")

    async def async_play_conversation(
        self,
        ref: str,
        device_map: dict[str, str],
        scheme: str | None = None,
        speed: float | None = None,
        pause_event: asyncio.Event | None = None,
        inter_message_delay: float | None = None,
    ) -> ScenarioResult:
        """Play back a conversation block by ref.

        :param ref: Conversation ref (e.g. 'fan+co2/dcv_reaction').
        :param device_map: Slug → device_id mapping (e.g. {'FAN': '20:123456'}).
        :param scheme: Optional scheme filter.
        :param speed: Playback speed multiplier. ``None`` means follow the
            engine's global ``autonomous_speed`` so the Devices tab speed
            control affects playback live.
        :param pause_event: Optional asyncio.Event. When provided, playback
            awaits this event before each frame (``set()`` = running,
            ``clear()`` = paused). Cancellation of the surrounding task stops
            playback immediately.
        :param inter_message_delay: Optional fixed gap (seconds) between every
            frame, overriding the conversation's recorded timing.
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
            # Honour pause gate before computing delay
            if pause_event is not None and not pause_event.is_set():
                await pause_event.wait()

            # Effective speed: explicit > global autonomous
            eff_speed = speed if speed is not None else self._autonomous_speed
            eff_speed = max(0.01, float(eff_speed))

            if inter_message_delay is not None:
                delay = max(0.0, float(inter_message_delay))
            else:
                delay = (frame.t - prev_t) / eff_speed
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
                self._log_and_emit("outbound", packet)
            except Exception as err:
                errors.append(str(err))

        return ScenarioResult(
            scenario_id=ref,
            success=not errors,
            messages_sent=messages_sent,
            duration_seconds=asyncio.get_event_loop().time() - start,
            errors=errors,
        )

    async def _emit_burst(
        self,
        device: ActiveDevice,
        entries: list[AutonomousEntry],
        payload_idx: dict[str, int],
        inter_packet_delay: float = 0.05,
    ) -> None:
        """Emit one round of all periodic I frames for a device immediately.

        Used at startup so ramses_cc can discover/characterise devices from I
        frames rather than waiting for slow RQ→timeout cycles.

        :param device: ActiveDevice.
        :param entries: Autonomous entries to emit.
        :param payload_idx: Mutable payload rotation index (updated in-place).
        :param inter_packet_delay: Seconds between packets (avoid MQTT flooding).
        """
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
                device.device_id, "--:------", VERB_I, entry.code, payload
            )
            try:
                await self._endpoint.send_packet(packet)
                self._messages_sent += 1
                self._message_log.append(
                    f"[{asyncio.get_event_loop().time():.3f}] {packet[:60]}..."
                )
                if len(self._message_log) > 1000:
                    self._message_log = self._message_log[-500:]
                self._log_and_emit("outbound", packet)
                if inter_packet_delay > 0:
                    await asyncio.sleep(inter_packet_delay)
            except Exception as err:
                LOGGER.warning(
                    "Burst send error for %s/%s: %s",
                    device.device_id,
                    entry.code,
                    err,
                )

    async def _periodic_emitter(
        self,
        device: ActiveDevice,
        entries: list[AutonomousEntry],
        speed_override: float | None = None,
    ) -> None:
        """Background task: emit periodic I messages for a device.

        Starts with an immediate burst so ramses_cc can discover the device
        quickly, then falls into the normal periodic interval loop.

        :param device: ActiveDevice.
        :param entries: Autonomous entries to emit.
        :param speed_override: Optional per-task speed multiplier.
        """
        if not entries:
            return

        payload_idx: dict[str, int] = {e.code: 0 for e in entries}
        next_due: dict[str, float] = {e.code: time.monotonic() for e in entries}
        interval_cache: dict[str, float] = {
            e.code: max(float(e.interval_seconds or 1.0), 0.5) for e in entries
        }

        # Immediate startup burst — lets ramses_cc discover the device from I
        # frames rather than waiting for RQ→timeout cycles (can take 20s each).
        # Skip when auto-answer is off — no point announcing a "silent" device.
        if self._auto_answer_enabled:
            LOGGER.debug(
                "Startup burst for %s (%d codes)", device.device_id, len(entries)
            )
            await self._emit_burst(device, entries, payload_idx)

        while True:
            now = time.monotonic()
            for entry in entries:
                if device.suppress_autonomous or not device.enabled:
                    break
                if not self._auto_answer_enabled:
                    break
                if entry.code in device.excluded_codes:
                    continue
                if not entry.payloads:
                    continue

                due = next_due.get(entry.code, now)
                if now < due:
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
                    self._message_log.append(
                        f"[{asyncio.get_event_loop().time():.3f}] {packet[:60]}..."
                    )
                    if len(self._message_log) > 1000:
                        self._message_log = self._message_log[-500:]
                    self._log_and_emit("outbound", packet)
                except Exception as err:
                    LOGGER.warning(
                        "Emitter send error for %s/%s: %s",
                        device.device_id,
                        entry.code,
                        err,
                    )

                current_speed = max(
                    speed_override
                    if speed_override is not None
                    else self._autonomous_speed,
                    0.01,
                )
                interval = interval_cache.get(entry.code, 60.0) / current_speed
                next_due[entry.code] = time.monotonic() + interval

            soonest_due = min(next_due.values(), default=time.monotonic() + 5.0)
            delay = max(soonest_due - time.monotonic(), 0.5)
            await asyncio.sleep(min(delay, 5.0))

    async def _handle_inbound_frame(self, frame: str) -> None:
        """Handle a frame received from ramses_rf (outbound /tx) or from device
        (inbound /rx).

        Parses the verb and code, routes RQ to response engine, echoes W frames.

        :param frame: Raw RAMSES packet string.
        """
        LOGGER.debug("Simulator inbound frame: %s", frame)
        match = _PACKET_RE.match(frame.strip())
        if not match:
            LOGGER.debug("Simulator: frame doesn't match regex: %s", frame)
            return

        self._messages_received += 1
        self._log_and_emit("inbound", frame)
        verb, src, dst, code, payload = match.groups()
        self._inject_inbound_to_stream(verb, src, dst, code, payload, frame)
        verb_raw = verb
        verb = verb.upper().strip()  # Strip leading space from 1-char verbs like ' I'
        LOGGER.debug(
            "Simulator parsed: verb_raw='%s', verb='%s', src=%s, dst=%s, code=%s",
            verb_raw,
            verb,
            src,
            dst,
            code,
        )
        LOGGER.debug(
            "VERB_W='%s', comparison: verb == VERB_W = %s", VERB_W, verb == VERB_W
        )

        # Echo W frames to satisfy ramses_tx WantEcho state
        if verb == VERB_W:
            LOGGER.debug(
                "Simulator received W frame: %s -> %s, code=%s", src, dst, code
            )
            await self._echo_write(src, dst, code, payload)
            return

        if verb != VERB_RQ:
            LOGGER.debug("Simulator: ignoring non-RQ, non-W frame: verb=%s", verb)
            return

        if not self._auto_answer_enabled:
            LOGGER.debug("Auto-answer disabled, dropping RQ %s from %s", code, src)
            return

        await self._respond_to_rq(src, dst, code, payload)

    def _inject_inbound_to_stream(
        self, verb: str, src: str, dst: str, code: str, payload: str, frame: str
    ) -> None:
        """Push RQ/W frames the simulator received into the shared message stream.

        The ramses_rf add_msg_handler only fires for inbound RP/I frames;
        outbound RQ/W commands never appear there for MQTT transports.
        Injecting them here makes the Packet Log Explorer see the full exchange.
        """
        verb_upper = verb.upper().strip()
        if verb_upper not in {"RQ", "W"}:
            return
        try:
            stream = get_ramses_message_stream(self.hass)
            stream.inject(
                {
                    "verb": verb_upper,
                    "src": src,
                    "dst": dst,
                    "code": code,
                    "payload": payload,
                    "frame": frame,
                    "dtm": datetime.now(tz=UTC).isoformat(timespec="microseconds"),
                }
            )
        except Exception:
            pass

    async def _echo_write(self, src: str, dst: str, code: str, payload: str) -> None:
        """Echo a W frame back so the FSM WantEcho state is satisfied.

        The ramses_tx FSM waits for its outbound W frame to appear on the bus
        as confirmation. Without this echo the FSM times out after 20 s.

        If this is a FAN with a bound REM that hasn't been discovered yet,
        emit a minimal packet for the REM so it gets discovered immediately.

        :param src: Original sender (HGI / REM).
        :param dst: Target simulated device.
        :param code: RAMSES code.
        :param payload: Hex payload.
        """
        device = self._active_devices.get(dst)
        LOGGER.debug("Echo W: looking up device %s -> %s", dst, device)
        if not device:
            LOGGER.warning("Echo W: device %s not active", dst)
            return
        if not device.enabled:
            LOGGER.debug("Echo W: device %s disabled", dst)
            return
        if device.suppress_responses:
            LOGGER.debug("Echo W: device %s suppresses responses", dst)
            return

        # If this is a FAN with a bound REM that isn't active yet, wake up the REM
        if device.slug == "FAN" and hasattr(device, "bound_device_id"):
            bound_id = getattr(device, "bound_device_id", None)
            if bound_id and bound_id not in self._active_devices:
                # Emit a minimal I frame for the bound REM so it gets discovered
                rem_packet = self._build_packet(
                    bound_id, "--:------", VERB_I, "0000", ""
                )
                try:
                    await self._endpoint.send_packet(rem_packet)
                    LOGGER.debug("Emitted wake-up packet for bound REM %s", bound_id)
                except Exception as err:  # noqa: BLE001
                    LOGGER.warning("Failed to emit wake-up for %s: %s", bound_id, err)

        packet = self._build_packet(src, dst, VERB_W, code, payload)
        try:
            await self._endpoint.send_packet(packet)
            LOGGER.debug("Echoed W frame %s/%s for %s", code, dst, src)
        except Exception as err:  # noqa: BLE001
            LOGGER.warning("Failed to echo W for %s/%s: %s", dst, code, err)

    async def _respond_to_rq(
        self,
        src: str,
        dst: str,
        code: str,
        rq_payload: str,
    ) -> None:
        """Look up and send an RP for an inbound RQ.

        Only responds for explicitly activated devices (in _active_devices).

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
            # Device not in active list — do not respond.
            # Responding for non-activated devices would cause traffic even
            # after the user stops all emissions.
            LOGGER.debug("RQ for inactive device %s/%s, not responding", dst, code)
            return

        if code in excluded_codes:
            LOGGER.debug("Dropping RQ %s for %s (excluded)", code, dst)
            return

        resp: ResponseEntry | None = self._db.find_response(slug, code, variant_id)
        payload: str | None = None
        delay_ms = 0
        if resp and resp.payloads:
            key = (slug, code)
            idx = self._response_index.get(key, 0) % len(resp.payloads)
            payload = resp.payloads[idx]
            self._response_index[key] = idx + 1
            delay_ms = resp.delay_ms
        else:
            payload = build_dynamic_response(slug, code, rq_payload)

        if not payload:
            LOGGER.debug("No response entry for %s/%s", slug, code)
            return

        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

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
            self._log_and_emit("outbound", packet)
            LOGGER.debug("Responded %s RP/%s → %s", dst, code, src)
        except Exception as err:
            LOGGER.warning("Failed to send RP for %s/%s: %s", dst, code, err)

    async def _prime_fan_params(self, device: ActiveDevice) -> None:
        """Send an initial 2411 detection RQ so FAN params are available early."""

        if device.device_id in self._primed_fans:
            return

        self._primed_fans.add(device.device_id)

        if not self._auto_answer_enabled:
            LOGGER.debug(
                "Skipping FAN prime for %s: auto-answer disabled", device.device_id
            )
            return

        if not self._endpoint.is_connected:
            LOGGER.debug(
                "Skipping FAN prime for %s: endpoint not connected", device.device_id
            )
            return

        rem_id = device.bound_device_id or SIM_DEVICE_ID.get("REM")
        if not rem_id:
            LOGGER.debug("Skipping FAN prime for %s: no REM id", device.device_id)
            return

        payload = "00003E"  # Param 0x3E matches the real detection RQ
        packet = self._build_packet(rem_id, device.device_id, VERB_RQ, "2411", payload)

        try:
            await self._endpoint.send_packet(packet)
            self._messages_sent += 1
            self._message_log.append(
                f"[{asyncio.get_event_loop().time():.3f}] {packet[:60]}..."
            )
            if len(self._message_log) > 1000:
                self._message_log = self._message_log[-500:]
            self._log_and_emit("outbound", packet)
            LOGGER.debug(
                "Primed FAN %s with 2411/3E request from %s", device.device_id, rem_id
            )
            await self._respond_to_rq(rem_id, device.device_id, "2411", payload)
        except Exception as err:  # noqa: BLE001
            LOGGER.warning("Failed to prime FAN %s: %s", device.device_id, err)

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
    def auto_answer_enabled(self) -> bool:
        """Return True when the engine will reply to RQ frames."""
        return self._auto_answer_enabled

    @property
    def messages_sent(self) -> int:
        """Return total messages sent since startup."""
        return self._messages_sent

    @property
    def messages_received(self) -> int:
        """Return total inbound frames seen since startup."""
        return self._messages_received

    @property
    def active_device_ids(self) -> list[str]:
        """Return list of currently active device IDs."""
        return list(self._active_devices.keys())

    def set_auto_answer(self, enabled: bool) -> None:
        """Enable or disable global RQ→RP auto-answering.

        When disabled the engine never responds to RQ frames, simulating a
        device that is powered off or the ESP transport being unavailable.
        Individual device suppress_responses flags are still respected when
        auto-answer is enabled.

        :param enabled: True to respond to RQs, False to drop all responses.
        """
        self._auto_answer_enabled = enabled
        LOGGER.info(
            "Auto-answer %s", "enabled" if enabled else "disabled (no RQ replies)"
        )

    def get_running_scenario_ids(self) -> list[str]:
        """Return IDs of explicitly started timed/toggleable scenarios."""

        return list(self._running_scenarios.keys())

    def get_running_metadata(self) -> dict[str, dict[str, Any]]:
        """Return a copy of running scenario metadata."""

        return dict(self._running_scenarios)

    @property
    def autonomous_emissions_active(self) -> bool:
        """Return True if any device emitter task is currently running."""
        return bool(self._emitter_tasks)

    def has_scenario_definition(self, scenario_id: str) -> bool:
        """Return True if a dynamic scenario definition exists."""

        return scenario_id in self._scenario_definitions

    async def async_run_registered_scenario(
        self, scenario_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a dynamically registered scenario."""

        return await self._run_registered_scenario(scenario_id, params)

    async def _run_registered_scenario(
        self, scenario_id: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        definition = self._scenario_definitions.get(scenario_id)
        if not definition:
            return {
                "success": False,
                "error": f"Scenario '{scenario_id}' is not available",
            }

        context = ScenarioContext(self.hass, self)
        result = await definition.run(context, params)

        if result.success:
            response: dict[str, Any] = {"success": True}
            response.update(result.details)
            if "message" not in response and result.details.get("message"):
                response["message"] = result.details["message"]
            return response

        error_msg = result.errors[0] if result.errors else "Scenario failed"
        return {
            "success": False,
            "error": error_msg,
            "details": result.details,
        }

    def _all_active_scenario_ids(self) -> list[str]:
        """Return all currently active scenario IDs for conflict checking.

        Unlike get_running_scenario_ids this includes the pseudo-scenarios
        auto_answer and autonomous_emissions so conflict logic sees them.
        """
        ids = list(self._running_scenarios.keys())
        if self._auto_answer_enabled:
            ids.append(SCENARIO_AUTO_ANSWER)
        if self._manual_device_ids and SCENARIO_MANUAL_DEVICE_INJECTION not in ids:
            ids.append(SCENARIO_MANUAL_DEVICE_INJECTION)
        return ids

    def check_scenario_conflicts(self, new_scenario_id: str) -> list[str]:
        """Return running scenario IDs that conflict with new_scenario_id.

        A conflict exists when a running scenario does not list new_scenario_id
        in its can_run_with, and new_scenario_id does not list the running
        scenario in its own can_run_with (and neither side has "*").

        :param new_scenario_id: Scenario about to be started.
        :return: List of conflicting running scenario IDs (empty = no conflicts).
        """
        new_meta = SCENARIO_REGISTRY.get(new_scenario_id, {})
        new_compat = new_meta.get("can_run_with", [])
        if "*" in new_compat:
            return []

        conflicts: list[str] = []
        for running_id in self._all_active_scenario_ids():
            if running_id == new_scenario_id:
                continue
            running_meta = SCENARIO_REGISTRY.get(running_id, {})
            running_compat = running_meta.get("can_run_with", [])
            # Compatible if either side lists the other OR either side has "*"
            if (
                "*" in running_compat
                or new_scenario_id in running_compat
                or running_id in new_compat
            ):
                continue
            conflicts.append(running_id)
        return conflicts

    async def async_cancel_scenario(self, scenario_id: str) -> None:
        """Cancel a running timed scenario task.

        :param scenario_id: The scenario type id to cancel.
        """
        task = self._scenario_tasks.pop(scenario_id, None)
        # Ensure a paused scenario wakes up so cancellation propagates.
        ev = self._scenario_pause_events.pop(scenario_id, None)
        if ev is not None and not ev.is_set():
            ev.set()
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.clear_running_metadata(scenario_id)
        LOGGER.info("Scenario '%s' cancelled", scenario_id)

    def get_pause_event(self, scenario_id: str) -> asyncio.Event:
        """Return (creating if needed) the pause gate for ``scenario_id``.

        The event starts in the *set* state (running). Pass this into scenario
        ``run`` implementations (typically via ``ScenarioContext``) so they can
        block on it each iteration.
        """
        ev = self._scenario_pause_events.get(scenario_id)
        if ev is None:
            ev = asyncio.Event()
            ev.set()
            self._scenario_pause_events[scenario_id] = ev
        return ev

    def pause_scenario(self, scenario_id: str) -> bool:
        """Pause a running scenario that cooperates with its pause event.

        :return: True if a pause gate existed and was cleared, False otherwise.
        """
        ev = self._scenario_pause_events.get(scenario_id)
        if ev is None:
            return False
        ev.clear()
        meta = self._running_scenarios.get(scenario_id)
        if meta is not None:
            meta["paused"] = True
        LOGGER.info("Scenario '%s' paused", scenario_id)
        return True

    def resume_scenario(self, scenario_id: str) -> bool:
        """Resume a previously paused scenario.

        :return: True if a pause gate existed and was set, False otherwise.
        """
        ev = self._scenario_pause_events.get(scenario_id)
        if ev is None:
            return False
        ev.set()
        meta = self._running_scenarios.get(scenario_id)
        if meta is not None:
            meta["paused"] = False
        LOGGER.info("Scenario '%s' resumed", scenario_id)
        return True

    def is_scenario_paused(self, scenario_id: str) -> bool:
        """Return True if the scenario's pause gate is currently cleared."""
        ev = self._scenario_pause_events.get(scenario_id)
        return ev is not None and not ev.is_set()

    async def async_run_unavailability_test(
        self,
        device_id: str | None = None,
        silence_after: float = 30.0,
        resume_after: float = 60.0,
    ) -> dict[str, Any]:
        params = {
            "device_id": device_id,
            "silence_after": silence_after,
            "resume_after": resume_after,
        }
        return await self._run_registered_scenario(
            SCENARIO_DEVICE_UNAVAILABILITY, params
        )

    async def async_run_hvac_device_loss(
        self,
        device_id: str,
        loss_after: float = 30.0,
        restore_after: float | None = None,
    ) -> dict[str, Any]:
        params = {
            "device_id": device_id,
            "loss_after": loss_after,
            "restore_after": restore_after,
        }
        return await self._run_registered_scenario(SCENARIO_HVAC_DEVICE_LOSS, params)
