"""Recipe R155: Zigbee native APS & ZHA discovery (PR 1326 / 1362).

Conditionally verifies:
- https://github.com/ramses-rf/ramses_rf/pull/1326 (native APS mode
  ``?ack=aps`` on ``ZigbeeTransport``: ZCL command ``0x03`` mode
  selection, ``0x02`` chunked TX/RX with ``zigpy`` serialization,
  duplicate/gap handling, and write-lock recovery).
- https://github.com/ramses-rf/ramses_cc/pull/1362 (ZHA device registry
  lookup via ``dev_reg.devices.values()``, firmware version detection in
  ``zigbee.py``, automatic ``?ack=aps`` selection, ``zigbee_legacy_ack``
  override, and pool IEEE deduplication).

If either PR is not yet installed in ``ha-sim``, its section is skipped
gracefully so the recipe passes both before and after merge.
"""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R155ZigbeeApsAndDiscoveryPr1362(Recipe):
    """Verify Zigbee native APS transport and config flow discovery."""

    id = "R155"
    seq = 1550
    title = "Zigbee native APS & ZHA discovery (PR 1326 / PR 1362)"
    tags = ("zigbee", "transport", "config_flow", "pr_1326", "pr_1362")

    async def run(self, ctx: RecipeContext) -> None:
        """Run conditional Zigbee APS and discovery checks in ha-sim."""
        ctx.log_section(
            "Recipe 155: Zigbee native APS & ZHA discovery (PR 1326 / PR 1362)"
        )

        result = docker_exec_python(
            """
import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from zigpy import types
from zigpy.types import EUI64
from zigpy.zcl import Cluster, foundation

from ramses_tx import exceptions as exc
from ramses_tx.transport.base import TransportConfig
from ramses_tx.transport.zigbee.transport import ZigbeeTransport

results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append({"name": name, "status": status, "detail": detail})


IEEE = "10:bd:a3:ff:fe:a8:19:60"
BASE_URL = f"zigbee://{IEEE}/0xfc00/0x0000/10/0xfc01/0x0000/10"


class NativeRXCluster(Cluster):
    cluster_id = 0xFC00

    class ClientCommandDefs(foundation.BaseCommandDefs):
        recv_chunk = foundation.ZCLCommandDef(
            id=0x02,
            schema={
                "message_id": types.uint32_t,
                "sequence": types.uint8_t,
                "total": types.uint8_t,
                "text": types.CharacterString,
            },
        )


class NativeTXCluster(Cluster):
    cluster_id = 0xFC01

    class ClientCommandDefs(foundation.BaseCommandDefs):
        send_chunk = foundation.ZCLCommandDef(
            id=0x02,
            schema={
                "message_id": types.uint32_t,
                "sequence": types.uint8_t,
                "total": types.uint8_t,
                "text": types.CharacterString,
            },
        )
        native_mode = foundation.ZCLCommandDef(
            id=0x03,
            schema={"enabled": types.Bool},
        )


def make_zha_hass():
    endpoint = MagicMock()
    endpoint.reply = AsyncMock()
    endpoint.device.get_sequence.return_value = 7

    rx_cluster = NativeRXCluster(endpoint, is_server=False)
    tx_cluster = NativeTXCluster(endpoint, is_server=True)
    ep10 = SimpleNamespace(
        out_clusters={0xFC00: rx_cluster},
        in_clusters={0xFC01: tx_cluster},
    )
    zha_device = SimpleNamespace(
        available=True,
        on_network=True,
        is_initialized=True,
        last_seen=time.time(),
        endpoints={10: ep10},
    )
    gateway = SimpleNamespace(
        devices={EUI64.convert(IEEE): zha_device},
        application_controller=None,
    )
    zha_data = SimpleNamespace(
        gateway_proxy=SimpleNamespace(gateway=gateway)
    )
    hass = MagicMock()
    hass.data = {"zha": zha_data}
    hass.loop = asyncio.get_running_loop()
    return hass, endpoint, rx_cluster, tx_cluster, zha_device


async def test_ramses_rf_pr_1326():
    has_aps = callable(getattr(ZigbeeTransport, "_enable_native_mode", None))
    if not has_aps:
        return {"rf_skipped": True}

    hass, endpoint, rx_cluster, tx_cluster, _ = make_zha_hass()
    proto = MagicMock()
    proto.set_regex_rules = MagicMock()

    # 1. URL query parsing: default legacy vs invalid ack mode
    def _close_coro(coro, **_kw):
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
    mock_loop.create_task.side_effect = _close_coro
    t_leg = ZigbeeTransport(
        BASE_URL, proto, config=TransportConfig(), loop=mock_loop
    )
    check("default URL retains legacy mode", not t_leg._aps_ack)

    invalid_raised = False
    try:
        ZigbeeTransport(
            f"{BASE_URL}?ack=invalid",
            proto,
            config=TransportConfig(),
            loop=mock_loop,
        )
    except exc.TransportSourceInvalid:
        invalid_raised = True
    check("invalid ?ack= value raises TransportSourceInvalid", invalid_raised)

    # 2. Startup sends ZCL command 0x03 (enable_native_mode) with APS ACK
    transport = ZigbeeTransport(
        f"{BASE_URL}?ack=aps",
        proto,
        config=TransportConfig(app_context=hass),
        loop=hass.loop,
    )
    await asyncio.sleep(0.1)
    check(
        "APS transport online after startup",
        transport._aps_ack and transport._device_online,
    )
    check(
        "startup sent ZCL command 0x03 once",
        endpoint.reply.await_count == 1,
        f"await_count={endpoint.reply.await_count}",
    )
    if endpoint.reply.await_count == 1:
        kw = endpoint.reply.call_args.kwargs
        hdr, body = foundation.ZCLHeader.deserialize(kw["data"])
        check(
            "command 0x03 serialized with ask_for_ack=True, body=0x01",
            hdr.command_id == 0x03
            and body == b"\\x01"
            and kw.get("ask_for_ack") is True
            and kw.get("expect_reply") is False,
        )

    # 3. Native RX (0x02): chunk reassembly, duplicate suppression, gap drop
    received = []
    transport._frame_read = lambda dtm, frame: received.append(frame)
    raw_pkt = "045  I --- 01:145038 --:------ 01:145038 1F09 003 FF0730"
    schema = NativeRXCluster.ClientCommandDefs.recv_chunk.schema
    endpoint.reply.reset_mock()

    transport.cluster_command(
        1,
        0x02,
        schema(message_id=100, sequence=1, total=2, text=raw_pkt[:30]),
    )
    # Duplicate chunk 1
    transport.cluster_command(
        2,
        0x02,
        schema(message_id=100, sequence=1, total=2, text=raw_pkt[:30]),
    )
    check("incomplete frame not delivered early", len(received) == 0)

    transport.cluster_command(
        3,
        0x02,
        schema(message_id=100, sequence=2, total=2, text=raw_pkt[30:]),
    )
    # Duplicate final chunk for already completed message_id=100
    transport.cluster_command(
        4,
        0x02,
        schema(message_id=100, sequence=2, total=2, text=raw_pkt[30:]),
    )
    check(
        "native RX reassembled frame once with 0 ASCII ACKs",
        received == [raw_pkt] and endpoint.reply.await_count == 0,
        f"received={received} replies={endpoint.reply.await_count}",
    )

    # Gap drops incomplete message 101; message 102 recovers cleanly
    transport.cluster_command(
        5, 0x02, schema(message_id=101, sequence=1, total=3, text="part1")
    )
    transport.cluster_command(
        6, 0x02, schema(message_id=101, sequence=3, total=3, text="part3")
    )
    transport.cluster_command(
        7, 0x02, schema(message_id=102, sequence=1, total=1, text=raw_pkt[:20])
    )
    check(
        "sequence gap dropped message 101 and message 102 recovered",
        len(received) == 2 and received[1] == raw_pkt[:20],
    )

    # 4. Native TX (0x02): 30-byte chunking + ZCL serialization
    endpoint.reply.reset_mock()
    tx_pkt = "RQ --- 18:000730 01:145038 --:------ 1F09 001 00\\r\\n"
    await transport._write_frame(tx_pkt)
    check(
        "48-byte TX frame split into 2 ZCL 0x02 chunks",
        endpoint.reply.await_count == 2,
        f"await_count={endpoint.reply.await_count}",
    )
    if endpoint.reply.await_count == 2:
        tx_schema = NativeTXCluster.ClientCommandDefs.send_chunk.schema
        c0_hdr, c0_body = foundation.ZCLHeader.deserialize(
            endpoint.reply.call_args_list[0].kwargs["data"]
        )
        c1_hdr, c1_body = foundation.ZCLHeader.deserialize(
            endpoint.reply.call_args_list[1].kwargs["data"]
        )
        p0, _ = tx_schema.deserialize(c0_body)
        p1, _ = tx_schema.deserialize(c1_body)
        check(
            "TX chunks share message_id and reconstruct frame",
            c0_hdr.command_id == 0x02
            and c1_hdr.command_id == 0x02
            and p0.message_id == p1.message_id
            and (p0.sequence, p0.total) == (1, 2)
            and (p1.sequence, p1.total) == (2, 2)
            and str(p0.text) + str(p1.text) == tx_pkt.strip(),
        )

    transport.close()
    await asyncio.sleep(0.05)
    return {"rf_skipped": False}


async def test_ramses_cc_pr_1362():
    try:
        from custom_components.ramses_cc.config_flow import (
            CONF_ADDITIONAL_PORTS,
            CONF_ZIGBEE_LEGACY_ACK,
            RamsesConfigFlow,
            RamsesOptionsFlowHandler,
        )
        from custom_components.ramses_cc.const import (
            SZ_PORT_NAME,
            SZ_SERIAL_PORT,
        )
        from custom_components.ramses_cc.zigbee import (
            _native_firmware,
            _native_stack_ready,
            build_zigbee_url,
        )
    except ImportError:
        return {"cc_skipped": True}

    # 1. Firmware version parser boundaries
    check(
        "_native_firmware accepts >= v0.6.0 (hex and semver)",
        _native_firmware("0x00060000")
        and _native_firmware("v0.6.1")
        and not _native_firmware("0x00050500")
        and not _native_firmware("v0.5.5")
        and not _native_firmware("v0.6.0-dirty")
        and not _native_firmware(None),
    )

    hass, _, _, _, _ = make_zha_hass()
    dev_entry = SimpleNamespace(
        id="dev_zha_esp32c6",
        model="Ramses_esp32c6",
        name="RAMSES ESP32-C6 Bridge",
        name_by_user=None,
        identifiers={("zha", IEEE)},
        sw_version="0x00060000",
    )
    fake_reg = MagicMock()
    fake_reg.devices = {"dev_zha_esp32c6": dev_entry}
    fake_reg.async_get.side_effect = lambda d_id: fake_reg.devices.get(d_id)
    fake_reg.async_get_device.side_effect = lambda identifiers=None: (
        dev_entry if identifiers == {("zha", IEEE)} else None
    )

    with (
        patch(
            "custom_components.ramses_cc.zigbee.dr.async_get",
            return_value=fake_reg,
        ),
        patch(
            "custom_components.ramses_cc.config_flow.dr.async_get",
            return_value=fake_reg,
        ),
        patch(
            "custom_components.ramses_cc.zigbee._native_stack_ready",
            return_value=True,
        ),
    ):
        # 2. URL construction (auto APS vs force_legacy vs old firmware)
        check(
            "build_zigbee_url selects ?ack=aps for v0.6.0",
            build_zigbee_url(hass, IEEE) == f"{BASE_URL}?ack=aps",
        )
        check(
            "build_zigbee_url honours force_legacy=True",
            build_zigbee_url(hass, IEEE, force_legacy=True)
            == f"{BASE_URL}?ack=legacy",
        )
        dev_entry.sw_version = "0x00050500"
        check(
            "build_zigbee_url retains bare URL for v0.5.5",
            build_zigbee_url(hass, IEEE) == BASE_URL,
        )
        dev_entry.sw_version = "0x00060000"

        # 3. Primary config flow discovery + legacy override
        flow = RamsesConfigFlow()
        flow.hass = hass
        flow.options = {SZ_SERIAL_PORT: {SZ_PORT_NAME: None}}
        res = await flow.async_step_zigbee_device(None)
        check(
            "async_step_zigbee_device auto-discovers ZHA bridge with ?ack=aps",
            res.get("step_id") == "configure_serial_port"
            and flow.options[SZ_SERIAL_PORT][SZ_PORT_NAME]
            == f"{BASE_URL}?ack=aps"
            and CONF_ZIGBEE_LEGACY_ACK in res["data_schema"].schema,
        )
        with (
            patch.object(
                flow, "_async_validate_port_connection", return_value=None
            ),
            patch.object(flow, "async_step_config", return_value={}),
        ):
            await flow.async_step_configure_serial_port(
                {SZ_SERIAL_PORT: {}, CONF_ZIGBEE_LEGACY_ACK: True}
            )
        check(
            "configure_serial_port saves ?ack=legacy override",
            flow.options[SZ_SERIAL_PORT][SZ_PORT_NAME]
            == f"{BASE_URL}?ack=legacy",
        )

        # 4. Pool Zigbee step updates existing IEEE entry without duplication
        entry = MagicMock()
        entry.options = {
            SZ_SERIAL_PORT: {SZ_PORT_NAME: "mqtt_ha"},
            CONF_ADDITIONAL_PORTS: [BASE_URL],
        }
        opt_flow = RamsesOptionsFlowHandler(entry)
        opt_flow.hass = hass
        with patch.object(
            opt_flow, "_async_save", return_value={"type": "create_entry"}
        ):
            await opt_flow.async_step_manage_pool_zigbee(
                {"device": dev_entry.id, CONF_ZIGBEE_LEGACY_ACK: False}
            )
        check(
            "manage_pool_zigbee replaces existing IEEE URL in-place",
            opt_flow.options[CONF_ADDITIONAL_PORTS] == [f"{BASE_URL}?ack=aps"],
            f"additional={opt_flow.options[CONF_ADDITIONAL_PORTS]}",
        )

    return {"cc_skipped": False}


async def run_all():
    rf_info = await test_ramses_rf_pr_1326()
    cc_info = await test_ramses_cc_pr_1362()
    print(
        json.dumps(
            {
                "rf_skipped": rf_info["rf_skipped"],
                "cc_skipped": cc_info["cc_skipped"],
                "passed": sum(1 for r in results if r["status"] == "PASS"),
                "failed": sum(1 for r in results if r["status"] == "FAIL"),
                "results": results,
            }
        )
    )


asyncio.run(run_all())
""",
            timeout=120,
        )

        if "error" in result:
            ctx.check("Recipe 155 executed", False, f"error: {result['error']}")
            return

        if result.get("rf_skipped"):
            ctx.check(
                "ramses_rf PR 1326 checks (skipped — not yet installed)",
                True,
            )
        if result.get("cc_skipped"):
            ctx.check(
                "ramses_cc PR 1362 checks (skipped — not yet installed)",
                True,
            )

        for chk in result.get("results", []):
            ctx.check(chk["name"], chk["status"] == "PASS", chk["detail"])
