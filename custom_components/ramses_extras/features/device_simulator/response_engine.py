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
from typing import TYPE_CHECKING

from .const import LOGGER

if TYPE_CHECKING:
    from .comm_endpoint import MqttEndpoint
    from .device_db import DeviceDatabase, ResponseEntry


class ResponseEngine:
    """Handles incoming RQ frames and sends RP responses.

    :param device_db: Device database for response lookups
    :param endpoint: MQTT endpoint for sending responses
    """

    # RAMSES frame format:  I 001 37:168270 37:126776 31DA 001 21...
    #                        V RSSI  SRC        DST        CODE LEN PAYLOAD
    FRAME_PATTERN = re.compile(
        r"^(?P<verb>[IRW]|RQ|RP)\s+"
        r"(?P<rssi>\d{3})\s+"
        r"(?P<src>[0-9A-Fa-f]{2}:[0-9A-Fa-f]{6})\s+"
        r"(?P<dst>[0-9A-Fa-f]{2}:[0-9A-Fa-f]{6}|--:------)\s+"
        r"(?P<code>[0-9A-Fa-f]{4})\s+"
        r"(?P<len>\d{3})\s*"
        r"(?P<payload>[0-9A-Fa-f]*)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        device_db: DeviceDatabase,
        endpoint: MqttEndpoint,
    ) -> None:
        """Initialize the response engine.

        :param device_db: Device database instance
        :param endpoint: MQTT endpoint for sending responses
        """
        self._db = device_db
        self._endpoint = endpoint
        self._pending_tasks: set[asyncio.Task] = set()

    async def handle_inbound_frame(self, frame: str) -> None:
        """Handle an incoming frame from ramses_rf.

        Parses the frame, looks up appropriate response, and sends it
        with the configured delay.

        :param frame: Raw RAMSES frame string
        """
        if not self._endpoint.is_connected:
            LOGGER.debug("ResponseEngine: endpoint not connected, dropping frame")
            return

        parsed = self._parse_frame(frame)
        if not parsed:
            LOGGER.debug("ResponseEngine: failed to parse frame: %s", frame[:80])
            return

        # Only process RQ (request) frames - not I or W
        if parsed["verb"] != "RQ":
            LOGGER.debug(
                "ResponseEngine: ignoring %s frame from %s",
                parsed["verb"],
                parsed["src"],
            )
            return

        # Determine device type from source address
        device_type = self._get_device_type(parsed["src"])
        if not device_type:
            LOGGER.debug("ResponseEngine: unknown device type for %s", parsed["src"])
            return

        # Look up response in device database
        response = self._db.find_response(device_type, parsed["code"])
        if not response:
            LOGGER.debug(
                "ResponseEngine: no response for %s/%s", device_type, parsed["code"]
            )
            return

        # Schedule response with delay
        await self._send_response(parsed, response)

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

    def _get_device_type(self, device_id: str) -> str | None:
        """Determine device type from device ID.

        For now, this is a simple mapping based on the first 2 chars.
        In production, this should look up the known_list or use
        the device's actual type from ramses_cc.

        :param device_id: Device address like "37:168270"
        :return: Device type slug like "FAN", "REM", etc.
        """
        # Mapping from type code to device type slug
        type_map = {
            "37": "FAN",  # Fan
            "34": "CO2",  # CO2 sensor
            "32": "HUM",  # Humidity sensor
            "29": "REM",  # Remote
            "31": "DIS",  # Display
            "30": "RFS",  # RFS sensor
            "22": "CTL",  # Controller
            "01": "DHW",  # DHW sensor
            "04": "TRV",  # TRV
            "07": "OTB",  # OTB
            "13": "BDR",  # BDR relay
        }

        type_code = device_id.split(":")[0]
        return type_map.get(type_code)

    async def _send_response(self, parsed: dict, response: ResponseEntry) -> None:
        """Send a response frame after the configured delay.

        :param parsed: Parsed incoming frame
        :param response: Response definition from device database
        """
        if not response.payloads:
            LOGGER.debug("ResponseEngine: no payloads for response")
            return

        # Use first available payload
        payload = response.payloads[0]

        # Build response frame (swap src/dst, change verb to RP)
        # Note: In real implementation, we'd need the simulator's device ID
        # For now, we use the destination as source (echo back)
        rsp_frame = self._build_response_frame(parsed, payload)

        # Apply delay
        delay_ms = response.delay_ms
        LOGGER.debug(
            "ResponseEngine: scheduling %s response in %dms for %s/%s",
            rsp_frame[:30],
            delay_ms,
            parsed["src"],
            parsed["code"],
        )

        # Create delayed task
        task = asyncio.create_task(
            self._delayed_send(delay_ms / 1000, rsp_frame),
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

        # Build frame: R 000 src dst code len payload
        # Using "R" for response (RP)
        return f"R 000 {src} {dst} {parsed['code']} {payload_len:03d} {payload}"

    async def _delayed_send(self, delay_seconds: float, frame: str) -> None:
        """Send a frame after a delay.

        :param delay_seconds: Delay in seconds
        :param frame: Frame to send
        """
        await asyncio.sleep(delay_seconds)
        if self._endpoint.is_connected:
            await self._endpoint.send_packet(frame)
            LOGGER.debug("ResponseEngine: sent response: %s", frame[:60])
        else:
            LOGGER.debug("ResponseEngine: endpoint disconnected, dropped response")

    async def shutdown(self) -> None:
        """Shutdown the response engine and cancel pending tasks."""
        LOGGER.info(
            "ResponseEngine: shutting down, cancelling %d tasks",
            len(self._pending_tasks),
        )
        for task in self._pending_tasks:
            task.cancel()
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()
