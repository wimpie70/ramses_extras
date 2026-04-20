# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Response Engine for Device Simulator.

Parses incoming RQ frames, looks up RP responses from Device Database,
and sends responses with configured delays.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Final

from .const import LOGGER
from .device_db import DeviceDatabase, ResponseEntry
from .response_templates import build_dynamic_response
from .system_config import ConfigProfileStore

if TYPE_CHECKING:
    from .comm_endpoint import MqttEndpoint
    from .scenario_engine import ScenarioEngine


SUPPORTED_WRITE_CODES: Final[set[str]] = {"2411"}


class ResponseEngine:
    """Handles incoming RQ frames and sends RP responses.

    :param device_db: Device database for response lookups
    :param endpoint: MQTT endpoint for sending responses
    """

    # RAMSES frame format:  RQ --- 37:168270 32:153289 --:------ 2411 003 000001
    #                        V RSSI  SRC        DST        BROADCAST  CODE LEN PAYLOAD
    FRAME_PATTERN = re.compile(
        r"^(?P<verb>[IRW]|RQ|RP)\s+"
        r"(?P<rssi>\d{3}|---)\s+"
        r"(?P<src>[0-9A-Fa-f]{2}:[0-9A-Fa-f]{6})\s+"
        r"(?P<dst>[0-9A-Fa-f]{2}:[0-9A-Fa-f]{6}|--:------)\s+"
        r"(?P<broadcast>[0-9A-Fa-f]{2}:[0-9A-Fa-f]{6}|--:------)\s+"
        r"(?P<code>[0-9A-Fa-f]{4})\s+"
        r"(?P<len>\d{3})\s*"
        r"(?P<payload>[0-9A-Fa-f]*)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        device_db: DeviceDatabase,
        endpoint: MqttEndpoint,
        *,
        config_store: ConfigProfileStore | None = None,
    ) -> None:
        """Initialize the response engine.

        :param device_db: Device database instance
        :param endpoint: MQTT endpoint for sending responses
        """
        self._db = device_db
        self._endpoint = endpoint
        self._pending_tasks: set[asyncio.Task] = set()
        self._config_store = config_store
        self._engine: ScenarioEngine | None = None

    def set_engine(self, engine: ScenarioEngine | None) -> None:
        """Provide the ScenarioEngine so we can skip duplicate replies."""

        self._engine = engine

    async def handle_inbound_frame(self, frame: str) -> None:
        """Handle an incoming frame from ramses_rf.

        Parses the frame, looks up appropriate response, and sends it
        with the configured delay.

        :param frame: Raw RAMSES frame string
        """
        try:
            LOGGER.debug("ResponseEngine: processing frame: %s", frame[:60])
            if not self._endpoint.is_connected:
                LOGGER.debug("ResponseEngine: endpoint not connected, dropping")
                return

            parsed = self._parse_frame(frame)
            if not parsed:
                LOGGER.debug("ResponseEngine: failed to parse frame: %s", frame[:80])
                return

            verb = parsed.get("verb", "").upper()
            code = parsed.get("code", "").upper()

            LOGGER.debug(
                "ResponseEngine: frame parsed, verb=%s, code=%s",
                verb,
                code,
            )

            if verb == "W" and code not in SUPPORTED_WRITE_CODES:
                LOGGER.debug("ResponseEngine: ignoring unsupported W frame %s", code)
                return

            # Only process RQ frames plus selected W frames
            if verb not in {"RQ", "W"}:
                LOGGER.debug("ResponseEngine: ignoring %s frame", verb)
                return

            LOGGER.debug(
                "ResponseEngine: processing RQ from %s to %s code %s",
                parsed["src"],
                parsed["dst"],
                parsed["code"],
            )

            dst = parsed["dst"]
            if dst == "--:------" or not dst:
                LOGGER.debug("ResponseEngine: dropping RQ - broadcast destination")
                return

            if verb == "RQ" and self._engine and self._engine.is_device_active(dst):
                LOGGER.debug(
                    "ResponseEngine: %s handled by ScenarioEngine; "
                    "skipping legacy reply",
                    dst,
                )
                return

            device_type = self._get_device_type(dst)
            LOGGER.debug(
                "ResponseEngine: device_type lookup for %s = %s", dst, device_type
            )
            if not device_type:
                LOGGER.debug(
                    "ResponseEngine: dropping RQ - unknown device type for %s", dst
                )
                return

            LOGGER.debug("ResponseEngine: device %s is type %s", dst, device_type)

            response = None
            if device_type:
                response = self._db.find_response(device_type, code)
                LOGGER.debug(
                    "ResponseEngine: DB lookup for %s/%s = %s",
                    device_type,
                    parsed["code"],
                    response,
                )

            payload: str | None = None
            delay_ms = 0
            if verb == "W":
                payload = self._build_write_ack_payload(parsed, response)

            if not payload and response and response.payloads:
                payload = response.payloads[0]
                delay_ms = response.delay_ms
            elif not payload:
                payload = build_dynamic_response(device_type, code, parsed["payload"])

            if not payload:
                LOGGER.debug(
                    "ResponseEngine: no response defined for %s/%s",
                    device_type,
                    parsed["code"],
                )
                return

            LOGGER.debug(
                "ResponseEngine: sending %s/%s response", device_type, parsed["code"]
            )
            await self._send_response(
                parsed,
                ResponseEntry(
                    code=parsed["code"],
                    delay_ms=delay_ms,
                    payloads=[payload],
                ),
            )

        except Exception as e:
            LOGGER.error("ResponseEngine: EXCEPTION: %s", e, exc_info=True)
            raise

    def _parse_frame(self, frame: str) -> dict | None:
        """Parse a RAMSES frame string.

        :param frame: Raw frame string
        :return: Parsed components or None if invalid
        """
        match = self.FRAME_PATTERN.match(frame.strip())
        if not match:
            return None

        return {
            "verb": match.group("verb"),
            "rssi": match.group("rssi"),
            "src": match.group("src").upper(),
            "dst": match.group("dst").upper(),
            "code": match.group("code").upper(),
            "len": int(match.group("len")),
            "payload": match.group("payload"),
        }

    def _lookup_profile_device_type(self, device_id: str) -> str | None:
        if not self._config_store:
            return None
        profile_name = self._config_store.get_active_profile()
        if not profile_name:
            return None
        profile = self._config_store.get_profile(profile_name)
        if not profile:
            return None
        known_list = profile.device_configs.get("_known_list", {})
        entry = known_list.get(device_id)
        if isinstance(entry, dict):
            device_class = entry.get("class")
            if device_class:
                return str(device_class).upper()
        return None

    def _get_device_type(self, device_id: str) -> str | None:
        """Determine device type from device ID.

        For now, this is a simple mapping based on the first 2 chars.
        In production, this should look up the known_list or use
        the device's actual type from ramses_cc.

        :param device_id: Device address like "37:168270"
        :return: Device type slug like "FAN", "REM", etc.
        """
        # Mapping from type code to device type slug
        # NOTE: These should match ramses_cc known_list device types
        device_class = self._lookup_profile_device_type(device_id)
        if device_class:
            return device_class

        type_map = {
            "32": "FAN",  # Fan (Orcon ventilation units)
            "37": "DIS",  # Display (37:168270)
            "34": "CO2",  # CO2 sensor
            "29": "REM",  # Remote
            "31": "DIS",  # Display
            "30": "RFS",  # RFS sensor
            "22": "CTL",  # Controller
            "01": "CTL",  # Legacy controller prefix
            "04": "TRV",  # TRV
            "07": "DHW",  # DHW sensor
            "10": "OTB",  # OpenTherm bridge
            "13": "BDR",  # BDR relay
        }

        type_code = device_id.split(":")[0]
        return type_map.get(type_code)

    def _build_write_ack_payload(
        self, parsed: dict[str, str], response: ResponseEntry | None
    ) -> str | None:
        """Return an RP payload for supported W frames."""

        code = (parsed.get("code") or "").upper()
        if code not in SUPPORTED_WRITE_CODES:
            return None

        request_payload = (parsed.get("payload") or "").strip()
        if not request_payload:
            return None

        payload = request_payload.upper()

        if code == "2411" and response and response.payloads:
            template = response.payloads[0]
            if template and len(template) > len(payload):
                payload = payload.ljust(len(template), "0")

        return payload if payload else None

    async def _send_response(self, parsed: dict, response: ResponseEntry) -> None:
        """Send a response frame after the configured delay.

        :param parsed: Parsed incoming frame
        :param response: Response definition from device database
        """
        if not response.payloads:
            LOGGER.debug("ResponseEngine: no payloads for response")
            return

        # For 2411 (fan parameters), find matching payload from database
        # RQ payload: 000001 (parameter ID), RP payload includes param ID + value
        if parsed["code"] == "2411" and parsed["payload"]:
            raw_param = parsed["payload"][:6]
            param_id_rq = raw_param.upper()
            param_hex = param_id_rq[4:6].upper()  # Extract "01" from "000001"

            # Find matching payload from database (payloads start with param ID)
            payload = None
            for p in response.payloads:
                if p.upper().startswith(param_id_rq):
                    payload = p
                    break

            if not payload:
                # Fallback: use first available payload and replace param ID
                base_payload = response.payloads[0]
                payload = f"{param_id_rq}{base_payload[6:]}"
                LOGGER.debug("ResponseEngine: adapting payload for param %s", param_hex)

            LOGGER.debug(
                "ResponseEngine: 2411 response for param %s: %s...",
                param_hex,
                payload[:30],
            )
        else:
            # Use first available payload
            payload = response.payloads[0]
            LOGGER.debug("ResponseEngine: using payload from DB: %s...", payload[:20])

        # Build response frame (swap src/dst, change verb to RP)
        # Note: In real implementation, we'd need the simulator's device ID
        # For now, we use the destination as source (echo back)
        rsp_frame = self._build_response_frame(parsed, payload)

        # Send immediately (no delay needed for simulation)
        LOGGER.debug(
            "ResponseEngine: sending %s response for %s/%s",
            rsp_frame[:30],
            parsed["src"],
            parsed["code"],
        )

        task = asyncio.create_task(
            self._send_immediate(rsp_frame),
            name=f"response_{parsed['src']}_{parsed['code']}",
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    def _build_response_frame(self, parsed: dict, payload: str) -> str:
        """Build a response frame from incoming frame and payload.

        :param parsed: Parsed incoming frame
        :param payload: Response payload
        :return: Formatted response frame
        """
        # Swap source and destination
        src = parsed["dst"] if parsed["dst"] != "--:------" else "18:001234"
        dst = parsed["src"]

        # Calculate payload length (in bytes, not hex chars)
        payload_len = len(payload) // 2 if payload else 0

        # Build frame: RSSI VERB --- src dst broadcast code len payload
        # RSSI is 000 (simulated good signal strength)
        return (
            f"000 RP --- {src} {dst} --:------ {parsed['code']} "
            f"{payload_len:03d} {payload}"
        )

    async def _send_immediate(self, frame: str) -> None:
        """Send a frame immediately.

        :param frame: Frame to send
        """
        if self._endpoint.is_connected:
            await self._endpoint.send_packet(frame)
            if self._engine:
                self._engine._log_and_emit("outbound", frame, origin="auto_answer")
            LOGGER.debug("ResponseEngine: sent response: %s", frame[:70])
        else:
            LOGGER.warning("ResponseEngine: endpoint disconnected, dropped response")

    async def shutdown(self) -> None:
        """Shutdown the response engine and cancel pending tasks."""
        LOGGER.debug(
            "ResponseEngine: shutting down, cancelling %d tasks",
            len(self._pending_tasks),
        )
        for task in self._pending_tasks:
            task.cancel()
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()
