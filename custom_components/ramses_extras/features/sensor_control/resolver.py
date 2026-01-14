"""Resolver for Sensor Control feature.

This module provides the sensor source resolution logic for the sensor_control
feature.

The resolver is a pure *mapping* component:

- It does not create entities.
- It reads overrides from the integration's config entry options.
- It returns a deterministic mapping of metrics to entity IDs plus source
  metadata.

## Inputs

- **Internal baseline**: per-device-type entity templates from
  `INTERNAL_SENSOR_MAPPINGS`.
- **User overrides**: stored under the `sensor_control` options tree, per
  device key (a `device_id` with `:` replaced by `_`).

## Precedence rules (per metric)

For regular metrics (temperature, humidity, CO2, etc):

1. Start from the internal baseline entity ID (may be `None`).
2. Apply the override for the metric:
   - `kind = "internal"`:
     - Use the internal baseline entity ID.
   - `kind in {"external", "external_entity"}`:
     - Use the override `entity_id` only if it exists in HA.
     - If it does not exist, **fail closed**: return `None` and mark the source
       as invalid.
   - `kind = "none"`:
     - Explicitly disable the metric: return `None`.
   - Any other kind:
     - **Fail closed**: return `None` and mark the source as invalid.

For absolute humidity metrics (`indoor_abs_humidity`, `outdoor_abs_humidity`):

- These are driven by `abs_humidity_inputs` rather than direct per-metric
  overrides.
- If `abs_humidity_inputs` contains any configuration for the metric, the
  resolver exposes it as `kind = "derived"` (with `entity_id = None`) so
  consumers (e.g. cards) can display it as derived.
- Otherwise it is exposed as `kind = "internal"`.
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from ...const import DOMAIN
from .const import INTERNAL_SENSOR_MAPPINGS, SUPPORTED_METRICS

_LOGGER = logging.getLogger(__name__)


class SensorControlResolver:
    """Resolver for sensor control feature.

    Applies sensor source overrides and returns effective entity mappings
    with fail-closed behavior for invalid overrides.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the sensor control resolver.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._logger = _LOGGER

    async def resolve_entity_mappings(
        self, device_id: str, device_type: str
    ) -> dict[str, Any]:
        """Resolve entity mappings for a device applying sensor control overrides.

        Args:
            device_id: Device ID (e.g., "01:145:08")
            device_type: Device type (e.g., "FAN", "CO2")

        Returns:
            Dictionary containing:
            - mappings: Effective entity IDs for each metric
            - sources: Source metadata for each metric
            - raw_internal: Raw internal mappings (optional)
            - abs_humidity_inputs: Absolute humidity input mappings
        """
        device_key = device_id.replace(":", "_")

        # Get sensor control configuration
        sensor_control_config = self._get_sensor_control_config()

        # Get base internal mappings for this device type
        internal_mappings = self._get_internal_mappings(device_id, device_type)

        # Initialize result structure
        result: dict[str, Any] = {
            "mappings": {},
            "sources": {},
            "raw_internal": internal_mappings,
            "abs_humidity_inputs": {},
        }

        # Get device-specific overrides if available
        device_overrides = {}
        if sensor_control_config and "sources" in sensor_control_config:
            device_overrides = sensor_control_config["sources"].get(device_key, {})

        # Get absolute humidity input mappings
        abs_humidity_inputs = {}
        if sensor_control_config and "abs_humidity_inputs" in sensor_control_config:
            abs_humidity_inputs = sensor_control_config["abs_humidity_inputs"].get(
                device_key, {}
            )

        result["abs_humidity_inputs"] = abs_humidity_inputs

        # Resolve each metric
        for metric in SUPPORTED_METRICS:
            # Absolute humidity metrics are driven by abs_humidity_inputs rather
            # than direct sensor_control overrides. If a device has explicit
            # abs_humidity_inputs configured for a metric, expose it as a
            # non-internal (derived) source so frontends like the HVAC fan card
            # can show it in the Sensor Sources panel.
            if metric in ("indoor_abs_humidity", "outdoor_abs_humidity"):
                metric_cfg = abs_humidity_inputs.get(metric) or {}
                if metric_cfg:
                    result["mappings"][metric] = None
                    result["sources"][metric] = {
                        "kind": "derived",
                        "entity_id": None,
                        "valid": True,
                    }
                else:
                    result["mappings"][metric] = None
                    result["sources"][metric] = {
                        "kind": "internal",
                        "entity_id": None,
                        "valid": True,
                    }
                continue

            # Get internal mapping for this metric
            internal_entity_id = internal_mappings.get(metric)

            # Get override for this metric
            override = device_overrides.get(metric, {})
            override_kind = override.get("kind", "internal")
            override_entity_id = override.get("entity_id")

            # Apply fail-closed logic
            effective_entity_id, effective_source = self._apply_override(
                metric=metric,
                internal_entity_id=internal_entity_id,
                override_kind=override_kind,
                override_entity_id=override_entity_id,
            )

            result["mappings"][metric] = effective_entity_id
            result["sources"][metric] = effective_source

        self._logger.debug(
            "Resolved sensor mappings for %s (%s): %s",
            device_id,
            device_type,
            result["mappings"],
        )

        return result

    def _get_sensor_control_config(self) -> dict[str, Any] | None:
        """Get sensor control configuration from config entry options.

        Returns:
            Sensor control configuration dictionary or None if not configured
        """
        try:
            config_entry = self.hass.data.get(DOMAIN, {}).get("config_entry")
            if not config_entry:
                return None

            return config_entry.options.get("sensor_control") or None
        except Exception as err:
            self._logger.error("Failed to get sensor_control config: %s", err)
            return None

    def _get_internal_mappings(
        self, device_id: str, device_type: str
    ) -> dict[str, str | None]:
        """Get the internal (default) sensor mappings for a device.

        Args:
            device_id: Device ID
            device_type: Device type (FAN, CO2)

        Returns:
            Dictionary mapping metric to internal entity ID
        """
        internal_mappings = INTERNAL_SENSOR_MAPPINGS.get(device_type, {})
        # INTERNAL_SENSOR_MAPPINGS.get() always returns a dict, so no need for
        # isinstance check

        from custom_components.ramses_extras.framework.helpers.entity.core import (
            parse_entity_mapping_templates_for_device,
        )

        templates: dict[str, str] = {
            metric: template
            for metric, template in internal_mappings.items()
            if isinstance(metric, str) and isinstance(template, str)
        }
        parsed = parse_entity_mapping_templates_for_device(templates, device_id)

        result: dict[str, str | None] = {
            metric: parsed.get(metric)
            for metric, template in internal_mappings.items()
            if isinstance(metric, str) and template
        }

        for metric, template in internal_mappings.items():
            if isinstance(metric, str) and not template:
                result[metric] = None

        # Ensure all supported metrics are present
        for metric in SUPPORTED_METRICS:
            if metric not in result:
                result[metric] = None

        return result

    def _apply_override(
        self,
        metric: str,
        internal_entity_id: str | None,
        override_kind: str,
        override_entity_id: str | None,
    ) -> tuple[str | None, dict[str, Any]]:
        """Apply sensor source override with fail-closed behavior.

        Args:
            metric: Metric name
            internal_entity_id: Internal entity ID for the metric
            override_kind: Override kind (internal, external_entity, derived, none)
            override_entity_id: Override entity ID (for external_entity)

        Returns:
            Tuple of (effective_entity_id, source_metadata)
        """
        source_metadata = {
            "kind": override_kind,
            "entity_id": override_entity_id,
            "valid": True,
        }

        # Handle derived sensors (absolute humidity)
        if metric.endswith("_abs_humidity"):
            if override_kind == "derived":
                # Derived sensors don't have entity IDs
                return None, source_metadata
            # Invalid kind for derived sensors
            source_metadata["valid"] = False
            return None, source_metadata

        # Handle internal kind
        if override_kind == "internal":
            return (
                internal_entity_id,
                {**source_metadata, "entity_id": internal_entity_id},
            )

        # Handle external entity kind
        # Accept both the canonical value "external_entity" and
        # the shorthand "external" used by the config flow.
        if override_kind in ("external_entity", "external"):
            if override_entity_id and self._entity_exists(override_entity_id):
                return override_entity_id, source_metadata
            # Fail-closed: invalid external entity
            source_metadata["valid"] = False
            return None, source_metadata

        # Handle none kind (explicitly disable)
        if override_kind == "none":
            return None, source_metadata

        # Unknown kind - fail closed
        source_metadata["valid"] = False
        return None, source_metadata

    def _entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists in Home Assistant.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity exists, False otherwise
        """
        if not entity_id:
            return False
        try:
            return self.hass.states.get(entity_id) is not None
        except Exception:
            return False

    def get_supported_metrics(self) -> list[str]:
        """Get list of supported metrics.

        Returns:
            List of supported metric names
        """
        return SUPPORTED_METRICS.copy()

    def get_supported_device_types(self) -> list[str]:
        """Get list of supported device types.

        Returns:
            List of supported device type names
        """
        return list(INTERNAL_SENSOR_MAPPINGS.keys())
