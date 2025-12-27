"""Default feature sensor platform.

This module provides the sensor platform implementation for the default feature,
creating base humidity sensors for all devices with automatic calculation logic.

The sensors support both direct humidity readings and calculated absolute humidity
values based on temperature and relative humidity measurements.
"""

import logging
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.base_classes.base_entity import (
    ExtrasBaseEntity,
)
from custom_components.ramses_extras.framework.helpers.device.core import (
    extract_device_id_as_string,
)
from custom_components.ramses_extras.framework.helpers.entity.core import EntityHelpers

# Import entity patterns for absolute humidity sensors
from ..const import ENTITY_PATTERNS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up default feature sensor platform.

    This function is called by Home Assistant when the sensor platform
    is initialized. It creates sensor entities for all devices that have
    the default feature enabled.

    :param hass: Home Assistant instance
    :type hass: HomeAssistant
    :param config_entry: Configuration entry containing device settings
    :type config_entry: ConfigEntry
    :param async_add_entities: Callback to add entities to Home Assistant
    :type async_add_entities: AddEntitiesCallback

    .. note::
        This function respects the device_feature_matrix to only create
        sensors for devices that have the default feature enabled.
    """
    _LOGGER.debug("Setting up default feature sensor")

    # Get devices from Home Assistant data
    devices = hass.data.get("ramses_extras", {}).get("devices", [])
    _LOGGER.debug(
        f"Default feature sensor platform: found {len(devices)} devices: {devices}"
    )

    # Get entity manager to check device_feature_matrix
    entity_manager = hass.data.get("ramses_extras", {}).get("entity_manager")
    if entity_manager is None:
        # Create a temporary entity manager for device enablement checking
        # This ensures we respect the device_feature_matrix even during startup
        from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
            SimpleEntityManager,
        )

        entity_manager = SimpleEntityManager(hass)

        # Restore matrix state from config entry if available
        matrix_state = config_entry.data.get("device_feature_matrix", {})
        if matrix_state:
            entity_manager.restore_device_feature_matrix_state(matrix_state)
            _LOGGER.debug(f"Restored matrix state with {len(matrix_state)} devices")

    sensor: list[SensorEntity] = []
    for device_id in devices:
        # Check if device is enabled for the default feature
        device_id_str = extract_device_id_as_string(device_id)
        if not entity_manager.device_feature_matrix.is_device_enabled_for_feature(
            device_id_str, "default"
        ):
            _LOGGER.debug(
                f"Skipping disabled device for default feature: {device_id_str}"
            )
            continue

        # Create default sensor for this device
        device_sensor = await create_default_sensor(hass, device_id, config_entry)
        sensor.extend(device_sensor)
        _LOGGER.debug(
            f"Created {len(device_sensor)} default sensor for device {device_id}"
        )

    _LOGGER.debug(f"Total default sensor created: {len(sensor)}")
    async_add_entities(sensor, True)


async def create_default_sensor(
    hass: HomeAssistant, device_id: str, config_entry: ConfigEntry | None = None
) -> list[SensorEntity]:
    """Create default sensor for a device.

    This function creates humidity sensors for a specific device based on
    the DEFAULT_SENSOR_CONFIGS configuration. Currently supports FAN
    devices with absolute humidity calculation capabilities.

    :param hass: Home Assistant instance
    :type hass: HomeAssistant
    :param device_id: Device identifier for which to create sensors
    :type device_id: str
    :param config_entry: Optional configuration entry for additional settings
    :type config_entry: ConfigEntry | None

    :return: List of created sensor entities
    :rtype: list[SensorEntity]

    .. note::
        For absolute humidity sensors, calculation logic is created immediately,
        but listeners for underlying temperature/humidity entities are set up
        when the entity is added to Home Assistant.
    """
    # Import default sensor configurations
    from ..const import DEFAULT_SENSOR_CONFIGS

    # Ensure device_id is a string (convert from device object if needed)
    device_id_str = extract_device_id_as_string(device_id)

    sensor_list: list[SensorEntity] = []

    # Create sensor for each configured sensor type
    for sensor_type, config in DEFAULT_SENSOR_CONFIGS.items():
        if config.get("supported_device_types") and "FAN" in config.get(
            "supported_device_types", []
        ):
            # Create sensor with calculation logic (always create, listeners
            #  will be set up when entities exist)
            sensor_entity = DefaultHumiditySensor(
                hass, device_id_str, sensor_type, config
            )
            sensor_list.append(sensor_entity)
            _LOGGER.debug(
                f"Created default {sensor_type} sensor with calculation logic "
                f"for device {device_id_str}"
            )

    return sensor_list


async def _check_underlying_entities_exist(
    hass: HomeAssistant, device_id: str, sensor_type: str
) -> bool:
    """Check if the underlying ramses_cc entities exist for a humidity sensor.

    This function verifies that the required temperature and humidity entities
    exist in the entity registry before attempting to create listeners for
    absolute humidity calculation.

    :param hass: Home Assistant instance
    :type hass: HomeAssistant
    :param device_id: Device identifier
    :type device_id: str
    :param sensor_type: Type of humidity sensor
     ("indoor_absolute_humidity" or "outdoor_absolute_humidity")
    :type sensor_type: str

    :return: True if underlying entities exist, False otherwise
    :rtype: bool

    .. note::
        Non-absolute humidity sensors don't require underlying entities and
        will always return True.
    """
    from homeassistant.helpers import entity_registry

    if sensor_type not in ENTITY_PATTERNS:
        return True  # Non-absolute humidity sensors don't need underlying entities

    temp_type, humidity_type = ENTITY_PATTERNS[sensor_type]
    device_id_underscore = device_id.replace(":", "_")

    # ramses_cc entities use CC format (device_id prefix): {device_id}_{identifier}
    temp_entity = EntityHelpers.generate_entity_name_from_template(
        "sensor", "{device_id}_" + temp_type, device_id=device_id_underscore
    )
    humidity_entity = EntityHelpers.generate_entity_name_from_template(
        "sensor", "{device_id}_" + humidity_type, device_id=device_id_underscore
    )

    # Check entity registry instead of states,
    #  as states may not be available during setup
    registry = entity_registry.async_get(hass)
    temp_entity_entry = registry.async_get(temp_entity)
    humidity_entity_entry = registry.async_get(humidity_entity)

    exists = temp_entity_entry is not None and humidity_entity_entry is not None
    if not exists:
        _LOGGER.debug(
            f"Underlying entities not found for {sensor_type}: {temp_entity}="
            f"{temp_entity_entry is not None}, {humidity_entity}="
            f"{humidity_entity_entry is not None}"
        )

    return exists


class DefaultHumiditySensor(SensorEntity, ExtrasBaseEntity):
    """Default humidity sensor for the default feature.

    This sensor creates base absolute humidity sensors for all devices with
    automatic calculation logic. It supports both direct humidity readings
    and calculated absolute humidity values based on temperature and
    relative humidity measurements.

    The sensor automatically sets up listeners for underlying temperature
    and humidity entities when they become available, enabling real-time
    calculation of absolute humidity values.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize default humidity sensor.

        :param hass: Home Assistant instance
        :type hass: HomeAssistant
        :param device_id: Device identifier for this sensor
        :type device_id: str
        :param sensor_type: Type of humidity sensor (e.g., "indoor_absolute_humidity")
        :type sensor_type: str
        :param config: Sensor configuration dictionary
         containing unit, device_class, etc.
        :type config: dict[str, Any]

        .. note::
            The sensor is created with calculation logic immediately, but listeners
            for underlying temperature/humidity entities are set up asynchronously
            when the entity is added to Home Assistant.
        """
        # Initialize base entity
        ExtrasBaseEntity.__init__(self, hass, device_id, sensor_type, config)

        # Ensure device_id is a string (convert from device object if needed)
        device_id_str = extract_device_id_as_string(device_id)

        # Set sensor-specific attributes
        self._sensor_type = sensor_type
        self._attr_native_unit_of_measurement = config.get("unit", "g/m³")
        self._attr_device_class = config.get("device_class")
        self._attr_icon = config.get("icon")

        # Set unique_id and name
        device_id_underscore = device_id_str.replace(":", "_")
        self._attr_unique_id = f"{sensor_type}_{device_id_underscore}"

        name_template = config.get(
            "name_template", f"{sensor_type} {device_id_underscore}"
        )
        self._attr_name = name_template.format(device_id=device_id_underscore)

        # Track if we have listeners set up (only for absolute humidity sensors)
        self._listeners_set_up = False

    @property
    def name(self) -> str:
        """Return the name of the entity.

        :return: Formatted sensor name with device ID
        :rtype: str
        """
        device_id_str = extract_device_id_as_string(self._device_id)
        device_id_underscore = device_id_str.replace(":", "_")
        return self._attr_name or f"{self._sensor_type} {device_id_underscore}"

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass.

        This method sets up the necessary listeners for absolute humidity
        calculation and triggers an initial calculation after setup is complete.

        For absolute humidity sensors (indoor/outdoor), it sets up listeners
        for the underlying temperature and humidity entities and performs
        an initial calculation.
        """
        await super().async_added_to_hass()
        # Set up listeners for underlying temperature and humidity sensor
        # for absolute humidity sensors
        if self._sensor_type in [
            "indoor_absolute_humidity",
            "outdoor_absolute_humidity",
        ]:
            await self._setup_listeners()
            # Trigger initial calculation after setting up listeners
            await self._recalculate_and_update()

    async def _setup_listeners(self) -> None:
        """Set up listeners for temperature and humidity sensor changes.

        This method creates state change listeners for the underlying temperature
        and humidity entities required for absolute humidity calculation.

        For absolute humidity sensors, it listens to:
        - Temperature sensor (e.g., device_indoor_temp)
        - Humidity sensor (e.g., device_indoor_humidity)

        The listeners trigger automatic recalculation when either underlying
        entity changes state.

        .. note::
            This method is idempotent - calling it multiple times will not
            create duplicate listeners.
        """
        if self._listeners_set_up:
            return

        if self._sensor_type not in ENTITY_PATTERNS:
            return

        temp_type, humidity_type = ENTITY_PATTERNS[self._sensor_type]

        # ramses_cc entities use CC format (device_id prefix): {device_id}_{identifier}
        device_id_str = extract_device_id_as_string(self._device_id)
        device_id_underscore = device_id_str.replace(":", "_")

        # Generate entity IDs using CC format for ramses_cc entities
        temp_entity = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_" + temp_type, device_id=device_id_underscore
        )
        humidity_entity = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_" + humidity_type, device_id=device_id_underscore
        )

        # Track state changes on both temperature and humidity sensor
        async def state_changed_listener(*args: Any) -> None:
            """Handle state changes on temperature or humidity sensor.

            This callback is triggered when either the temperature or humidity
            entity changes state. It recalculates the absolute humidity value
            and updates the sensor state.
            """
            await self._recalculate_and_update()

        # Listen for state changes on both sensor
        async_track_state_change(
            self.hass, [temp_entity, humidity_entity], state_changed_listener
        )

        self._listeners_set_up = True
        _LOGGER.debug(
            "Set up state change listeners for %s: %s, %s",
            self._attr_name,
            temp_entity,
            humidity_entity,
        )

    async def _recalculate_and_update(self) -> None:
        """Recalculate absolute humidity and update sensor state.

        For absolute humidity sensors, this first attempts to use the
        sensor_control configuration (abs_humidity_inputs + resolver
        mappings). If that is not available or fails, it falls back to
        the original CC-based temp/RH entities.
        """
        try:
            result: float | None = None

            if self._sensor_type in [
                "indoor_absolute_humidity",
                "outdoor_absolute_humidity",
            ]:
                result = await self._async_compute_abs_from_sensor_control()

            if result is None:
                temp, rh = self._get_temp_and_humidity()
                result = self._calculate_abs_humidity(temp, rh)

            if result is not None:
                _LOGGER.debug(
                    "Recalculated absolute humidity for %s: %.2f g/m³",
                    self._attr_name,
                    result,
                )
                self._attr_native_value = result
                self.async_write_ha_state()
        except Exception as e:
            _LOGGER.debug("Error recalculating humidity for %s: %s", self._attr_name, e)

    def _get_temp_and_humidity(self) -> tuple[float | None, float | None]:
        """Get temperature and humidity data from ramses_cc entities.

        This method retrieves the current temperature and relative humidity
        values from the underlying ramses_cc entities required for absolute
        humidity calculation.

        :return: tuple: (temperature, humidity) in Celsius and percentage
                  respectively, or (None, None) if sensors are missing/failed
        :rtype: tuple[float | None, float | None]

        .. note::
            The method validates that humidity values are within the valid
            range (0-100%) and handles unavailable/unknown states gracefully.
        """
        if self._sensor_type not in ENTITY_PATTERNS:
            _LOGGER.error(
                "Unknown sensor type for humidity calculation: %s", self._sensor_type
            )
            return None, None

        temp_type, humidity_type = ENTITY_PATTERNS[self._sensor_type]

        # ramses_cc entities use CC format (device_id prefix): {device_id}_{identifier}
        device_id_str = extract_device_id_as_string(self._device_id)
        device_id_underscore = device_id_str.replace(":", "_")

        # Generate entity IDs using CC format for ramses_cc entities
        temp_entity = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_" + temp_type, device_id=device_id_underscore
        )
        humidity_entity = EntityHelpers.generate_entity_name_from_template(
            "sensor", "{device_id}_" + humidity_type, device_id=device_id_underscore
        )

        try:
            # Get temperature from ramses_cc sensor
            temp_state = self.hass.states.get(temp_entity)
            if temp_state is None or temp_state.state in (
                "unavailable",
                "unknown",
                "uninitialized",
            ):
                _LOGGER.debug(
                    "Missing temperature entity %s for %s - "
                    "absolute humidity cannot be calculated",
                    temp_entity,
                    self._attr_name,
                )
                return None, None

            temp = float(temp_state.state)

            # Get humidity from ramses_cc sensor
            humidity_state = self.hass.states.get(humidity_entity)
            if humidity_state is None or humidity_state.state in (
                "unavailable",
                "unknown",
                "uninitialized",
            ):
                _LOGGER.debug(
                    "Missing humidity entity %s for %s - "
                    "absolute humidity cannot be calculated",
                    humidity_entity,
                    self._attr_name,
                )
                return None, None

            humidity = float(humidity_state.state)

            # Validate humidity range
            if not (0 <= humidity <= 100):
                _LOGGER.error(
                    "Invalid humidity value %.1f%% for %s (must be 0-100%%)",
                    humidity,
                    self._attr_name,
                )
                return None, None

            return temp, humidity

        except (ValueError, AttributeError) as e:
            _LOGGER.debug("Error parsing temp/humidity for %s: %s", self._attr_name, e)
            return None, None

    async def _async_compute_abs_from_sensor_control(self) -> float | None:
        """Compute absolute humidity using sensor_control configuration.

        This uses SensorControlResolver's abs_humidity_inputs and mappings
        to determine which temperature and humidity entities (or direct
        absolute humidity entity) should be used for this sensor.
        """
        try:
            if not self._is_sensor_control_enabled():
                return None

            # Import resolver lazily to avoid circular imports
            from custom_components.ramses_extras.features.sensor_control.resolver import (  # noqa: E501
                SensorControlResolver,
            )

            device_id_str = extract_device_id_as_string(self._device_id)
            device_type = self._get_device_type(device_id_str)
            if not device_type:
                return None

            resolver = SensorControlResolver(self.hass)
            result = await resolver.resolve_entity_mappings(device_id_str, device_type)

            abs_inputs = cast(dict[str, Any], result.get("abs_humidity_inputs") or {})
            mappings = cast(dict[str, str | None], result.get("mappings") or {})

            side = (
                "indoor"
                if self._sensor_type == "indoor_absolute_humidity"
                else "outdoor"
            )
            metric = f"{side}_abs_humidity"
            metric_cfg = cast(dict[str, Any], abs_inputs.get(metric) or {})

            if not metric_cfg:
                # No special config for this side - let fallback handle it
                return None

            temp_cfg = cast(dict[str, Any], metric_cfg.get("temperature") or {})
            hum_cfg = cast(dict[str, Any], metric_cfg.get("humidity") or {})

            temp_kind = str(temp_cfg.get("kind") or "internal")
            hum_kind = str(hum_cfg.get("kind") or "internal")

            # Direct absolute humidity entity
            if temp_kind == "external_abs":
                abs_entity_id = cast(str | None, temp_cfg.get("entity_id"))
                if not abs_entity_id:
                    return None

                # Avoid recursion if user accidentally selects this sensor itself
                if abs_entity_id == self.entity_id:
                    return None

                state = self.hass.states.get(abs_entity_id)
                if not state or state.state in [
                    "unavailable",
                    "unknown",
                    "uninitialized",
                ]:
                    return None

                try:
                    return float(state.state)
                except ValueError:
                    return None

            # If humidity is disabled and not in external_abs mode, skip
            if hum_kind == "none":
                return None

            # Derived mode: temperature + RH
            temp_metric = f"{side}_temperature"
            if temp_kind == "internal":
                temp_entity_id = mappings.get(temp_metric)
            elif temp_kind == "external_temp":
                temp_entity_id = cast(str | None, temp_cfg.get("entity_id"))
            else:
                return None

            if not temp_entity_id:
                return None

            temp_state = self.hass.states.get(temp_entity_id)
            if not temp_state or temp_state.state in [
                "unavailable",
                "unknown",
                "uninitialized",
            ]:
                return None

            try:
                temp_value = float(temp_state.state)
            except ValueError:
                return None

            hum_metric = f"{side}_humidity"
            if hum_kind == "internal":
                hum_entity_id = mappings.get(hum_metric)
            elif hum_kind == "external":
                hum_entity_id = cast(str | None, hum_cfg.get("entity_id"))
            else:
                return None

            if not hum_entity_id:
                return None

            hum_state = self.hass.states.get(hum_entity_id)
            if not hum_state or hum_state.state in [
                "unavailable",
                "unknown",
                "uninitialized",
            ]:
                return None

            try:
                hum_value = float(hum_state.state)
            except ValueError:
                return None

            from custom_components.ramses_extras.framework.helpers.entities import (
                calculate_absolute_humidity,
            )

            calc_result = calculate_absolute_humidity(temp_value, hum_value)
            return float(calc_result) if calc_result is not None else None
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug(
                "Error computing absolute humidity from sensor_control for %s: %s",
                self._attr_name,
                err,
            )
            return None

    def _is_sensor_control_enabled(self) -> bool:
        """Check if sensor_control feature is enabled in config_entry.

        This mirrors the check used in the WebSocket helper.
        """
        try:
            config_entry = self.hass.data.get(DOMAIN, {}).get("config_entry")
            if not config_entry:
                return False

            enabled_features = (
                config_entry.data.get("enabled_features")
                or config_entry.options.get("enabled_features")
                or {}
            )

            return bool(enabled_features.get("sensor_control", False))
        except Exception:
            return False

    def _get_device_type(self, device_id: str) -> str | None:
        """Get device type for sensor_control resolution.

        The resolver needs a device type (e.g. "FAN"). We reuse the
        same lookup strategy as the WebSocket helpers.
        """
        try:
            devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
            for device in devices:
                if isinstance(device, dict):
                    if device.get("device_id") == device_id:
                        return cast(str | None, device.get("type"))
                elif hasattr(device, "device_id"):
                    if extract_device_id_as_string(device.device_id) == device_id:
                        return cast(str | None, getattr(device, "type", None))
                elif hasattr(device, "id"):
                    if extract_device_id_as_string(device.id) == device_id:
                        return cast(str | None, getattr(device, "type", None))
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Failed to get device type for %s: %s", device_id, err)

        return None

    def _calculate_abs_humidity(
        self, temp: float | None, rh: float | None
    ) -> float | None:
        """Calculate absolute humidity using proper formula.

        This method uses the Magnus formula to calculate absolute humidity
        (water vapor density) from temperature and relative humidity.

        The Magnus formula provides accurate results across typical
        indoor temperature ranges and is the standard method for
        converting relative humidity to absolute humidity.

        :param temp: Temperature in Celsius
        :type temp: float | None
        :param rh: Relative humidity as percentage (0-100)
        :type rh: float | None

        :return: Absolute humidity in g/m³, or None if calculation fails
        :rtype: float | None

        .. note::
            The calculation requires both temperature and humidity values.
            If either is None, the calculation cannot be performed.
        """
        if temp is None or rh is None:
            return None

        # Import humidity calculation helper
        from custom_components.ramses_extras.framework.helpers.entities import (
            calculate_absolute_humidity,
        )

        result = calculate_absolute_humidity(temp, rh)
        return float(result) if result is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.

        :return: Dictionary containing additional sensor attributes
         including sensor_type
        :rtype: dict[str, Any]
        """
        base_attrs = super().extra_state_attributes or {}
        return {**base_attrs, "sensor_type": self._sensor_type}


# Register this platform with the global registry
from custom_components.ramses_extras.const import (  # noqa: E402
    register_feature_platform,  # noqa: E402
)

register_feature_platform("sensor", "default", async_setup_entry)

__all__ = [
    "DefaultHumiditySensor",
    "async_setup_entry",
    "create_default_sensor",
]
