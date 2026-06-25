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
from homeassistant.helpers import entity_registry as er

from ...const import DOMAIN
from ...framework.helpers.config.model import get_sensor_control_device_section
from ...framework.helpers.entity.entity_id_fallbacks import iter_ramses_cc_entity_ids
from .const import INTERNAL_SENSOR_MAPPINGS, SUPPORTED_METRICS

_LOGGER = logging.getLogger(__name__)


class SensorControlResolver:
    """Resolver for sensor control feature.

    Applies sensor source overrides and returns effective entity mappings
    with fail-closed behavior for invalid overrides.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the sensor control resolver.

        :param hass: Home Assistant instance
        """
        self.hass = hass
        self._logger = _LOGGER

    async def resolve_entity_mappings(
        self, device_id: str, device_type: str
    ) -> dict[str, Any]:
        """Resolve entity mappings for a device applying sensor control overrides.

        :param device_id: Device ID (e.g., "01:145:08")
        :param device_type: Device type (e.g., "FAN", "CO2")
        :return: Dictionary containing:
            - mappings: Effective entity IDs for each metric
            - sources: Source metadata for each metric
            - raw_internal: Raw internal mappings (optional)
            - abs_humidity_inputs: Absolute humidity input mappings
            - area_sensors: Validated area sensor summaries
        """
        # Get sensor control configuration
        sensor_control_config = self._get_sensor_control_config(device_id)
        device_section = get_sensor_control_device_section(
            sensor_control_config or {},
            device_id,
        )

        # Get base internal mappings for this device type
        internal_mappings = self._get_internal_mappings(device_id, device_type)

        # Initialize result structure
        result: dict[str, Any] = {
            "mappings": {},
            "sources": {},
            "raw_internal": internal_mappings,
            "abs_humidity_inputs": {},
            "area_sensors": [],
        }

        # Get device-specific overrides if available
        device_overrides = device_section.get("sources", {})
        if not isinstance(device_overrides, dict):
            device_overrides = {}

        # Get absolute humidity input mappings
        abs_humidity_inputs = device_section.get("abs_humidity_inputs", {})
        if not isinstance(abs_humidity_inputs, dict):
            abs_humidity_inputs = {}

        result["abs_humidity_inputs"] = abs_humidity_inputs

        area_sensors = device_section.get("area_sensors", [])
        if not isinstance(area_sensors, list):
            area_sensors = []

        result["area_sensors"] = self._resolve_area_sensors(area_sensors)

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

        # Add indoor humidity spike detection settings if available
        indoor_humidity_override = device_overrides.get("indoor_humidity", {})
        if indoor_humidity_override:
            result["sources"]["indoor_humidity"]["spike_enabled"] = bool(
                indoor_humidity_override.get("spike_enabled", False)
            )
            result["sources"]["indoor_humidity"]["spike_rise_percent"] = float(
                indoor_humidity_override.get("spike_rise_percent", 10.0)
            )
            result["sources"]["indoor_humidity"]["spike_window_minutes"] = int(
                indoor_humidity_override.get("spike_window_minutes", 5)
            )

        return result

    def _resolve_area_sensors(self, area_sensors: Any) -> list[dict[str, Any]]:
        if not isinstance(area_sensors, list):
            return []

        resolved: list[dict[str, Any]] = []
        for item in area_sensors:
            if not isinstance(item, dict):
                continue

            area_id = str(item.get("area_id") or "").strip()
            temperature_entity = str(item.get("temperature_entity") or "").strip()
            humidity_entity = str(item.get("humidity_entity") or "").strip()
            co2_entity = str(item.get("co2_entity") or "").strip()
            co2_threshold_entity = str(item.get("co2_threshold_entity") or "").strip()
            comfort_temperature_entity = str(
                item.get("comfort_temperature_entity") or ""
            ).strip()
            zone_id = str(item.get("zone_id") or "").strip()
            area_enabled = bool(item.get("enabled", True))
            area_co2_enabled = bool(item.get("area_co2_enabled", False))

            temp_valid = bool(temperature_entity) and self._entity_exists(
                temperature_entity
            )
            humidity_valid = bool(humidity_entity) and self._entity_exists(
                humidity_entity
            )
            co2_valid = (not area_co2_enabled) or (
                not co2_entity or self._entity_exists(co2_entity)
            )
            humidity_valid = (not area_enabled) or (temp_valid and humidity_valid)
            valid = bool(area_id) and humidity_valid and co2_valid

            resolved_item: dict[str, Any] = {
                "area_id": area_id,
                "enabled": area_enabled,
                "temperature_entity": temperature_entity or None,
                "humidity_entity": humidity_entity or None,
                "area_co2_enabled": area_co2_enabled,
                "co2_entity": co2_entity or None,
                "co2_threshold_entity": co2_threshold_entity or None,
                "co2_threshold": item.get("co2_threshold"),
                "comfort_temperature_entity": comfort_temperature_entity or None,
                "spike_rise_percent": item.get("spike_rise_percent"),
                "spike_window_minutes": item.get("spike_window_minutes"),
                "check_interval_minutes": item.get("check_interval_minutes"),
                "trigger_on_high_humidity": bool(
                    item.get("trigger_on_high_humidity", False)
                ),
                "valid": valid,
            }
            if zone_id:
                resolved_item["zone_id"] = zone_id

            resolved.append(resolved_item)

        return resolved

    def _get_sensor_control_config(
        self,
        device_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get sensor control configuration from config entry options.

        :param device_id: Device ID (canonical or legacy format)
        :return: Sensor control configuration dictionary or None if not configured
        """
        try:
            entries: list[Any] = []
            domain_data = self.hass.data.get(DOMAIN, {})

            config_entry = domain_data.get("config_entry")
            if config_entry is not None:
                entries.append(config_entry)

            config_entries = getattr(self.hass, "config_entries", None)
            async_entries = getattr(config_entries, "async_entries", None)
            if callable(async_entries):
                entries.extend(async_entries(DOMAIN))

            # Strip device type suffix (e.g., " (HVC)") before normalizing
            clean_device_id = device_id
            if device_id and " (" in device_id:
                clean_device_id = device_id.split(" (")[0]

            normalized_keys: set[str] = set()
            if clean_device_id:
                normalized_keys = {
                    str(clean_device_id),
                    str(clean_device_id).replace(":", "_"),
                    str(clean_device_id).replace("_", ":"),
                }

            fallback_config: dict[str, Any] | None = None
            seen_entries: set[int] = set()

            for entry in entries:
                if entry is None:
                    continue

                entry_marker = id(entry)
                if entry_marker in seen_entries:
                    continue
                seen_entries.add(entry_marker)

                options = getattr(entry, "options", {}) or {}
                data = getattr(entry, "data", {}) or {}
                sensor_control = self._extract_sensor_control_section(
                    options
                ) or self._extract_sensor_control_section(data)
                if not isinstance(sensor_control, dict):
                    continue

                if fallback_config is None:
                    fallback_config = sensor_control

                if not normalized_keys:
                    return sensor_control

                for config_key in (
                    "sources",
                    "abs_humidity_inputs",
                    "area_sensors",
                    "devices",
                ):
                    section = sensor_control.get(config_key) or {}
                    if not isinstance(section, dict):
                        continue
                    if any(key in section for key in normalized_keys):
                        return sensor_control

            return fallback_config
        except Exception as err:
            self._logger.error("Failed to get sensor_control config: %s", err)
            return None

    def _extract_sensor_control_section(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        # Prefer the canonical section (ramses_extras.features.sensor_control)
        # over the legacy top-level sensor_control key. The canonical section
        # is the one that config flows write to; the legacy key is kept for
        # backward compatibility but may be stale.
        root_section = payload.get("ramses_extras")
        if isinstance(root_section, dict):
            features = root_section.get("features")
            if isinstance(features, dict):
                sensor_control = features.get("sensor_control")
                if isinstance(sensor_control, dict):
                    return sensor_control

        # Fall back to legacy top-level key
        sensor_control = payload.get("sensor_control")
        return sensor_control if isinstance(sensor_control, dict) else None

    def _get_internal_mappings(
        self, device_id: str, device_type: str
    ) -> dict[str, str | None]:
        """Get the internal (default) sensor mappings for a device.

        :param device_id: Device ID
        :param device_type: Device type (FAN, CO2)
        :return: Dictionary mapping metric to internal entity ID
        """
        internal_mappings = INTERNAL_SENSOR_MAPPINGS.get(device_type, {})
        device_id_underscore = device_id.replace(":", "_").lower()
        registry = er.async_get(self.hass)

        metric_keys = {
            "indoor_temperature": "indoor_temperature",
            "indoor_humidity": "indoor_humidity",
            "co2": "co2_level",
            "outdoor_temperature": "outdoor_temperature",
            "outdoor_humidity": "outdoor_humidity",
        }

        result: dict[str, str | None] = {}
        for metric, key in metric_keys.items():
            if metric not in internal_mappings:
                result[metric] = None
                continue

            candidates = iter_ramses_cc_entity_ids(
                "sensor",
                key,
                device_id_underscore=device_id_underscore,
            )
            resolved = next(
                (
                    candidate
                    for candidate in candidates
                    if registry.async_get(candidate) is not None
                    or self.hass.states.get(candidate) is not None
                ),
                None,
            )
            result[metric] = resolved or (candidates[0] if candidates else None)

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

        :param metric: Metric name
        :param internal_entity_id: Internal entity ID for the metric
        :param override_kind: Override kind (internal, external_entity, derived, none)
        :param override_entity_id: Override entity ID (for external_entity)
        :return: Tuple of (effective_entity_id, source_metadata)
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

        :param entity_id: Entity ID to check
        :return: True if entity exists, False otherwise
        """
        if not entity_id:
            return False
        try:
            return self.hass.states.get(entity_id) is not None
        except Exception:
            return False

    def get_supported_metrics(self) -> list[str]:
        """Get list of supported metrics.

        :return: List of supported metric names
        """
        return list(SUPPORTED_METRICS)

    def get_supported_device_types(self) -> list[str]:
        """Get list of supported device types.

        :return: List of supported device type names
        """
        return list(INTERNAL_SENSOR_MAPPINGS.keys())
