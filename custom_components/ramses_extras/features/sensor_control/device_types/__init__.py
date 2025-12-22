from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import voluptuous as vol
from homeassistant.helpers import selector

from . import co2, fan


@runtime_checkable
class SensorControlDeviceHandler(Protocol):
    def get_group_options(self, device_id: str) -> list[selector.SelectOptionDict]: ...

    def handle_group_submission(
        self,
        group_stage: str,
        user_input: dict[str, Any],
        device_sources: dict[str, dict[str, Any]],
        device_abs_inputs: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]: ...

    def build_group_schema(
        self,
        group_stage: str,
        device_sources: dict[str, dict[str, Any]],
        device_abs_inputs: dict[str, dict[str, Any]],
        kind_options: list[selector.SelectOptionDict],
        kind_options_with_none: list[selector.SelectOptionDict],
        sensor_selector: selector.EntitySelector,
    ) -> tuple[vol.Schema, str]: ...


DEVICE_TYPE_HANDLERS: dict[str, SensorControlDeviceHandler] = {
    "FAN": fan,
    "CO2": co2,
}
