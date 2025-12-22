from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector


def get_group_options(device_id: str) -> list[selector.SelectOptionDict]:
    """Return group options for CO2 devices.

    For now CO2 devices are not fully supported by sensor control. We expose a
    minimal menu so the flow structure is ready for future expansion.
    """
    return [
        selector.SelectOptionDict(value="co2", label="CO2 (preview only)"),
        selector.SelectOptionDict(value="done", label="Finish editing device"),
    ]


def handle_group_submission(
    group_stage: str,
    user_input: dict[str, Any],
    device_sources: dict[str, dict[str, Any]],
    device_abs_inputs: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Handle submission for CO2 devices.

    Currently CO2 sensor control is not implemented, so this is a no-op that
    simply returns the existing mappings. This keeps the flow stable while
    signaling that CO2 support is planned.
    """
    return device_sources, device_abs_inputs


def build_group_schema(
    group_stage: str,
    device_sources: dict[str, dict[str, Any]],
    device_abs_inputs: dict[str, dict[str, Any]],
    kind_options: list[selector.SelectOptionDict],
    kind_options_with_none: list[selector.SelectOptionDict],
    sensor_selector: selector.EntitySelector,
) -> tuple[vol.Schema, str]:
    """Return a minimal schema and info text for CO2 devices.

    We intentionally do not expose any configurable fields yet; the schema is
    empty and the description explains that this is future work.
    """
    if group_stage != "co2":
        # We only expect the "co2" group for this handler. Any other group
        # should be treated as unsupported.
        raise ValueError(f"Unsupported group_stage for CO2 handler: {group_stage}")

    schema = vol.Schema({})
    info_suffix = (
        "CO2 devices are detected, but sensor control for CO2 is not yet "
        "implemented. This section is prepared as a preview for future use."
    )
    return schema, info_suffix
