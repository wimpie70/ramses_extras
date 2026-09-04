"""Recipe R101: Orcon CO2 binding and ventilation demand (PR 1187)."""

from __future__ import annotations

from ..base import Recipe, RecipeContext
from ..helpers import docker_exec_python


class R101OrconCo2BindingVentilationDemand(Recipe):
    id = "R101"
    seq = 1010
    title = "Orcon CO2 binding and ventilation demand (PR 1187)"
    tags = ("1298", "1FC9", "31E0", "binding", "co2", "orcon")

    async def run(self, ctx: RecipeContext) -> None:
        """Verify indexed binding offers and Orcon demand dispatch."""
        ctx.log_section("Recipe 101: Orcon CO2 binding and ventilation demand")

        result = docker_exec_python(
            """
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from ramses_rf.address import Address
from ramses_rf.commands.builders import build_dto
from ramses_rf.commands.core import Command
from ramses_rf.devices import HvacCarbonDioxideSensor
from ramses_rf.devices.dev_base import Fakeable
from ramses_rf.enums import Action
from ramses_rf.models import DeviceTraits
from ramses_rf.state import MessageStore
from ramses_tx import Priority
from ramses_tx.const import Code, Verb


class GatewayStub:
    def __init__(self):
        self.config = SimpleNamespace(disable_discovery=True, known_list={})
        self.device_by_id = {}
        self.devices = []
        self._engine = MagicMock()
        self.dispatcher = MagicMock()
        self.dispatcher.send = AsyncMock(return_value=None)
        self.message_store = MessageStore(maintain=False)

    @property
    def device_registry(self):
        return self

    def _add_device(self, dev):
        self.device_by_id[dev.id] = dev
        self.devices.append(dev)


async def run_tests():
    results = {}

    offer = build_dto(
        Command(
            src=Address("29:150156"),
            dst=Address("29:150156"),
            action=Action.PUT_BIND,
            data={
                "verb": Verb.I_,
                "codes": [
                    ("00", Code._31E0),
                    ("01", Code._31E0),
                    ("00", Code._1298),
                ],
                "oem_code": "67",
            },
        )
    )
    results["offer_payload"] = offer.payload

    legacy_offer = build_dto(
        Command(
            src=Address("29:150156"),
            dst=Address("29:150156"),
            action=Action.PUT_BIND,
            data={
                "verb": Verb.I_,
                "codes": [Code._31E0, Code._1298, Code._2E10],
            },
        )
    )
    results["legacy_offer_payload"] = legacy_offer.payload

    gateway = GatewayStub()
    sensor = HvacCarbonDioxideSensor(
        gateway,
        Address("29:150156"),
        traits=DeviceTraits(scheme="orcon", faked=True),
    )

    with patch.object(
        Fakeable,
        "_initiate_binding_process",
        new_callable=AsyncMock,
    ) as initiate:
        await sensor.initiate_binding_process()
        codes = initiate.await_args.args[0]
        results["binding_codes"] = [
            [str(index), str(code)] for index, code in codes
        ]

        default_sensor = HvacCarbonDioxideSensor(
            gateway,
            Address("29:150157"),
        )
        await default_sensor.initiate_binding_process()
        default_codes = initiate.await_args.args[0]
        results["default_binding_codes"] = [
            str(code) for code in default_codes
        ]

    await sensor.set_ventilation_demand("32:155617", 0.5)
    dispatched = gateway.dispatcher.send.await_args
    intent = dispatched.args[0]
    demand = build_dto(intent)
    results["demand_action"] = str(intent.action)
    results["demand_dst"] = str(intent.dst)
    results["demand_priority_high"] = (
        dispatched.kwargs["priority"] == Priority.HIGH
    )
    results["demand_verb"] = str(demand.verb)
    results["demand_code"] = str(demand.code)
    results["demand_payload"] = demand.payload

    print(json.dumps(results))


asyncio.run(run_tests())
"""
        )

        ctx.check(
            "PR 1187 Orcon APIs are importable",
            "error" not in result,
            f"result={result}",
        )
        if "error" in result:
            return

        expected_offer = "0031E0764A8C0131E0764A8C001298764A8C6710E0764A8C001FC9764A8C"
        ctx.check(
            "Binding offer preserves duplicate 31E0 domain indices",
            result.get("offer_payload") == expected_offer,
            f"payload={result.get('offer_payload')}",
        )
        ctx.check(
            "Orcon CO2 sensor selects indexed 31E0 and 1298 bindings",
            result.get("binding_codes")
            == [["00", "31E0"], ["01", "31E0"], ["00", "1298"]],
            f"codes={result.get('binding_codes')}",
        )
        expected_legacy_offer = "0031E0764A8C001298764A8C002E10764A8C001FC9764A8C"
        ctx.check(
            "Legacy binding offers retain the default 00 index",
            result.get("legacy_offer_payload") == expected_legacy_offer,
            f"payload={result.get('legacy_offer_payload')}",
        )
        ctx.check(
            "Default CO2 binding codes remain unchanged",
            result.get("default_binding_codes") == ["31E0", "1298", "2E10"],
            f"codes={result.get('default_binding_codes')}",
        )
        ctx.check(
            "set_ventilation_demand dispatches to the requested fan",
            result.get("demand_action") == "put_ventilation_demand"
            and result.get("demand_dst") == "32:155617"
            and result.get("demand_priority_high") is True,
            f"result={result}",
        )
        ctx.check(
            "50% Orcon demand encodes first-domain 31E0 payload 0000640001000000",
            result.get("demand_verb") == " I"
            and result.get("demand_code") == "31E0"
            and result.get("demand_payload") == "0000640001000000",
            f"result={result}",
        )
