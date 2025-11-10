"""Sensor Management Feature for Ramses Extras framework.

This module provides a sensor management feature implementation using the framework's
base automation class, enabling comprehensive sensor operations including calibration,
validation, data processing, and maintenance scheduling.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Any, Optional, Set

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry

from ....const import AVAILABLE_FEATURES, FEATURE_ID_HUMIDITY_SENSORS
from ....framework.helpers.automation import ExtrasBaseAutomation
from ....framework.helpers.common import RamsesValidator
from ....framework.helpers.device import find_ramses_device, get_device_type
from ....framework.helpers.entity import EntityHelpers
from ....helpers.entity import get_feature_entity_mappings

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorConfig:
    """Configuration for a sensor."""

    name: str
    entity_id: str
    sensor_type: str  # temperature, humidity, pressure, etc.
    calibration_offset: float = 0.0
    calibration_factor: float = 1.0
    valid_range: tuple[float, float] = (0.0, 100.0)
    validation_threshold: float = 5.0  # Max deviation for validation
    update_interval: int = 30  # seconds
    last_calibration: datetime | None = None
    maintenance_due: datetime | None = None
    calibration_history: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if self.calibration_history is None:
            self.calibration_history = []


@dataclass
class SensorReading:
    """Represents a sensor reading with validation."""

    timestamp: datetime
    value: float
    raw_value: float
    calibrated_value: float
    is_valid: bool
    deviation_from_normal: float = 0.0
    calibration_applied: bool = False


class SensorManagementFeature(ExtrasBaseAutomation):
    """Sensor Management feature using the framework.

    This implementation provides comprehensive sensor management including:
    - Sensor calibration and validation
    - Data quality monitoring
    - Maintenance scheduling
    - Anomaly detection
    - Sensor health reporting
    - Calibration history tracking
    """

    def __init__(
        self,
        hass: HomeAssistant,
        feature_id: str = FEATURE_ID_HUMIDITY_SENSORS,
        binary_sensor: Any = None,
        debounce_seconds: int = 45,
    ) -> None:
        """Initialize the sensor management feature.

        Args:
            hass: Home Assistant instance
            feature_id: Feature identifier
            binary_sensor: Optional binary sensor for status
            debounce_seconds: Debounce duration
        """
        super().__init__(hass, feature_id, binary_sensor, debounce_seconds)

        # Sensor management configuration
        self._sensor_config = self._get_sensor_config()

        # Sensor tracking
        self._managed_sensors: dict[str, SensorConfig] = {}
        self._sensor_readings: dict[str, list[SensorReading]] = {}
        self._sensor_stats: dict[str, dict[str, Any]] = {}

        # Calibration and maintenance
        self._calibration_queue: list[str] = []
        self._maintenance_schedule: dict[str, datetime] = {}

        # Health monitoring
        self._sensor_health: dict[str, dict[str, Any]] = {}
        self._anomaly_detector_enabled = True

        # Data processing
        self._data_buffer_size = 1000
        self._processing_interval = 60  # seconds

        _LOGGER.info(
            f"SensorManagementFeature initialized with config: {self._sensor_config}"
        )

    def _get_sensor_config(self) -> dict[str, Any]:
        """Get sensor management configuration.

        Returns:
            Sensor management configuration dictionary
        """
        feature_config = AVAILABLE_FEATURES.get(FEATURE_ID_HUMIDITY_SENSORS, {})
        return {
            "auto_calibration": feature_config.get("auto_calibration", True),
            "calibration_interval": feature_config.get(
                "calibration_interval", 30
            ),  # days
            "maintenance_interval": feature_config.get(
                "maintenance_interval", 90
            ),  # days
            "anomaly_detection": feature_config.get("anomaly_detection", True),
            "data_retention_days": feature_config.get("data_retention_days", 30),
            "quality_threshold": feature_config.get("quality_threshold", 0.85),
            "enable_validation": feature_config.get("enable_validation", True),
            "max_deviation": feature_config.get("max_deviation", 10.0),
        }

    def _generate_entity_patterns(self) -> list[str]:
        """Generate entity patterns for sensor management.

        Returns:
            List of entity patterns to listen for
        """
        patterns = [
            # Absolute humidity sensors
            "sensor.indoor_absolute_humidity_*",
            "sensor.outdoor_absolute_humidity_*",
            # Temperature sensors for validation
            "sensor.*_temperature",
            "sensor.*_temp",
            # Humidity sensors for cross-validation
            "sensor.*_humidity",
            "sensor.*_humid",
            # System sensors
            "sensor.uptime",
            "sensor.last_boot",
            "binary_sensor.*_status",
        ]

        _LOGGER.debug(f"Generated sensor management patterns: {patterns}")
        return patterns

    async def start(self) -> None:
        """Start the sensor management feature.

        Discovers sensors, initializes monitoring, and starts data processing.
        """
        _LOGGER.info("🚀 Starting Sensor Management feature")

        # Discover managed sensors
        await self._discover_sensors()

        # Load sensor configurations
        await self._load_sensor_configurations()

        # Start data processing
        asyncio.create_task(self._process_sensor_data())

        # Start base automation
        await super().start()

        _LOGGER.info("✅ Sensor Management feature started successfully")
        _LOGGER.info(f"📊 Managing {len(self._managed_sensors)} sensors")

    async def _discover_sensors(self) -> None:
        """Discover and register available sensors."""
        try:
            # Get all sensors from entity registry
            entity_registry_handler = self.hass.data.get("entity_registry")
            if not entity_registry_handler:
                _LOGGER.warning("Entity registry not available for sensor discovery")
                return

            # Find humidity-related sensors
            humidity_entities = []
            all_entities = entity_registry_handler.entities

            for entity_id, entity_entry in all_entities.items():
                if any(
                    keyword in entity_id.lower()
                    for keyword in [
                        "humidity",
                        "humid",
                        "absolute",
                        "indoor",
                        "outdoor",
                    ]
                ):
                    humidity_entities.append(entity_id)

            # Register discovered sensors
            for entity_id in humidity_entities:
                sensor_config = self._create_sensor_config(entity_id)
                if sensor_config:
                    self._managed_sensors[entity_id] = sensor_config
                    self._sensor_readings[entity_id] = []
                    self._sensor_stats[entity_id] = self._initialize_sensor_stats()

                    _LOGGER.debug(f"Registered sensor: {entity_id}")

            _LOGGER.info(f"Discovered {len(humidity_entities)} potential sensors")

        except Exception as e:
            _LOGGER.error(f"Failed to discover sensors: {e}")

    def _create_sensor_config(self, entity_id: str) -> SensorConfig | None:
        """Create sensor configuration from entity ID.

        Args:
            entity_id: Entity ID

        Returns:
            SensorConfig or None if creation failed
        """
        try:
            # Determine sensor type from entity ID
            sensor_type = "humidity"  # default
            if "indoor" in entity_id:
                sensor_type = "indoor_humidity"
            elif "outdoor" in entity_id:
                sensor_type = "outdoor_humidity"
            elif "absolute" in entity_id:
                sensor_type = "absolute_humidity"

            # Create configuration
            return SensorConfig(
                name=entity_id.replace("sensor.", "").replace("_", " ").title(),
                entity_id=entity_id,
                sensor_type=sensor_type,
                valid_range=(0.0, 100.0)
                if "humidity" in sensor_type
                else (-40.0, 80.0),
                validation_threshold=5.0,
            )

        except Exception as e:
            _LOGGER.error(f"Failed to create sensor config for {entity_id}: {e}")
            return None

    async def _load_sensor_configurations(self) -> None:
        """Load sensor configurations from storage.

        In a real implementation, this would load from persistent storage.
        For now, we'll use default configurations.
        """
        # Set maintenance schedules
        for sensor_id, config in self._managed_sensors.items():
            # Set next maintenance due date
            next_maintenance = datetime.now() + timedelta(
                days=self._sensor_config["maintenance_interval"]
            )
            self._maintenance_schedule[sensor_id] = next_maintenance
            config.maintenance_due = next_maintenance

            # Set last calibration date
            if self._sensor_config["auto_calibration"]:
                config.last_calibration = datetime.now() - timedelta(
                    days=self._sensor_config["calibration_interval"] // 2
                )

        _LOGGER.debug(f"Loaded configurations for {len(self._managed_sensors)} sensors")

    def _initialize_sensor_stats(self) -> dict[str, Any]:
        """Initialize statistics tracking for a sensor.

        Returns:
            Dictionary with initial statistics
        """
        return {
            "readings_count": 0,
            "valid_readings": 0,
            "invalid_readings": 0,
            "calibrations_performed": 0,
            "anomalies_detected": 0,
            "maintenance_required": 0,
            "last_reading": None,
            "average_value": 0.0,
            "min_value": float("inf"),
            "max_value": float("-inf"),
            "std_deviation": 0.0,
            "quality_score": 1.0,
            "drift_detected": False,
        }

    async def _process_sensor_data(self) -> None:
        """Process sensor data in background."""
        while self._active:
            try:
                await self._process_all_sensors()
                await asyncio.sleep(self._processing_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Error in sensor data processing: {e}")
                await asyncio.sleep(60)

    async def _process_all_sensors(self) -> None:
        """Process data for all managed sensors."""
        for sensor_id, config in self._managed_sensors.items():
            try:
                await self._process_sensor(sensor_id, config)
            except Exception as e:
                _LOGGER.error(f"Failed to process sensor {sensor_id}: {e}")

    async def _process_sensor(self, sensor_id: str, config: SensorConfig) -> None:
        """Process data for a specific sensor.

        Args:
            sensor_id: Sensor identifier
            config: Sensor configuration
        """
        try:
            # Get current state
            state = self.hass.states.get(sensor_id)
            if not state:
                return

            # Parse value
            try:
                raw_value = float(state.state)
            except (ValueError, TypeError):
                _LOGGER.warning(f"Invalid sensor value for {sensor_id}: {state.state}")
                return

            # Validate value
            is_valid, deviation = self._validate_sensor_value(raw_value, config)

            # Apply calibration
            calibrated_value = self._apply_calibration(raw_value, config)

            # Create reading
            reading = SensorReading(
                timestamp=datetime.now(),
                value=raw_value,
                raw_value=raw_value,
                calibrated_value=calibrated_value,
                is_valid=is_valid,
                deviation_from_normal=deviation,
                calibration_applied=(
                    config.calibration_offset != 0.0 or config.calibration_factor != 1.0
                ),
            )

            # Store reading
            self._store_reading(sensor_id, reading)

            # Update statistics
            self._update_sensor_stats(sensor_id, reading)

            # Check for anomalies
            if self._sensor_config["anomaly_detection"]:
                await self._check_for_anomalies(sensor_id, reading)

            # Check maintenance needs
            await self._check_maintenance_needs(sensor_id, config)

        except Exception as e:
            _LOGGER.error(f"Failed to process sensor {sensor_id}: {e}")

    def _validate_sensor_value(
        self, value: float, config: SensorConfig
    ) -> tuple[bool, float]:
        """Validate a sensor value.

        Args:
            value: Raw sensor value
            config: Sensor configuration

        Returns:
            Tuple of (is_valid, deviation_from_normal)
        """
        # Check if value is within valid range
        min_val, max_val = config.valid_range
        if not (min_val <= value <= max_val):
            return False, abs(value - (min_val + max_val) / 2)

        # Check for extreme values (anomalies)
        if abs(value - (min_val + max_val) / 2) > config.validation_threshold:
            return False, abs(value - (min_val + max_val) / 2)

        # Additional validation for humidity sensors
        if "humidity" in config.sensor_type:
            if not (0.0 <= value <= 100.0):
                return False, abs(value - 50.0)

        # Value is valid
        return True, 0.0

    def _apply_calibration(self, value: float, config: SensorConfig) -> float:
        """Apply calibration to sensor value.

        Args:
            value: Raw sensor value
            config: Sensor configuration

        Returns:
            Calibrated value
        """
        # Apply offset and factor
        calibrated = (value + config.calibration_offset) * config.calibration_factor
        return round(calibrated, 2)

    def _store_reading(self, sensor_id: str, reading: SensorReading) -> None:
        """Store a sensor reading.

        Args:
            sensor_id: Sensor identifier
            reading: Sensor reading
        """
        # Add to buffer
        if sensor_id not in self._sensor_readings:
            self._sensor_readings[sensor_id] = []

        self._sensor_readings[sensor_id].append(reading)

        # Limit buffer size
        if len(self._sensor_readings[sensor_id]) > self._data_buffer_size:
            self._sensor_readings[sensor_id].pop(0)

        # Remove old readings based on retention policy
        cutoff_date = datetime.now() - timedelta(
            days=self._sensor_config["data_retention_days"]
        )
        self._sensor_readings[sensor_id] = [
            r for r in self._sensor_readings[sensor_id] if r.timestamp > cutoff_date
        ]

    def _update_sensor_stats(self, sensor_id: str, reading: SensorReading) -> None:
        """Update statistics for a sensor.

        Args:
            sensor_id: Sensor identifier
            reading: Sensor reading
        """
        stats = self._sensor_stats[sensor_id]

        # Update counts
        stats["readings_count"] += 1
        if reading.is_valid:
            stats["valid_readings"] += 1
        else:
            stats["invalid_readings"] += 1

        stats["last_reading"] = reading.timestamp

        # Update value statistics
        if reading.is_valid:
            values = [
                r.calibrated_value
                for r in self._sensor_readings[sensor_id]
                if r.is_valid and r.timestamp > reading.timestamp - timedelta(hours=24)
            ]

            if values:
                stats["average_value"] = round(mean(values), 2)
                stats["min_value"] = min(values)
                stats["max_value"] = max(values)
                if len(values) > 1:
                    stats["std_deviation"] = round(stdev(values), 2)

        # Update quality score
        total_readings = stats["readings_count"]
        if total_readings > 0:
            stats["quality_score"] = stats["valid_readings"] / total_readings

    async def _check_for_anomalies(
        self, sensor_id: str, reading: SensorReading
    ) -> None:
        """Check for sensor anomalies.

        Args:
            sensor_id: Sensor identifier
            reading: Sensor reading
        """
        if not reading.is_valid:
            return

        # Check for rapid changes
        recent_readings = [
            r
            for r in self._sensor_readings[sensor_id][-10:]
            if r.is_valid and r.timestamp > reading.timestamp - timedelta(minutes=10)
        ]

        if len(recent_readings) > 3:
            changes = []
            for i in range(1, len(recent_readings)):
                change = abs(
                    recent_readings[i].calibrated_value
                    - recent_readings[i - 1].calibrated_value
                )
                changes.append(change)

            if changes and max(changes) > 20.0:  # More than 20% change in 10 minutes
                _LOGGER.warning(
                    f"Sensor anomaly detected for {sensor_id}: "
                    f"Rapid change detected ({max(changes):.1f}%)"
                )

                self._sensor_stats[sensor_id]["anomalies_detected"] += 1

                # Fire anomaly event
                self.hass.bus.async_fire(
                    "ramses_extras_sensor_anomaly",
                    {
                        "sensor_id": sensor_id,
                        "anomaly_type": "rapid_change",
                        "value": reading.calibrated_value,
                        "change_magnitude": max(changes),
                        "timestamp": reading.timestamp.isoformat(),
                    },
                )

    async def _check_maintenance_needs(
        self, sensor_id: str, config: SensorConfig
    ) -> None:
        """Check if sensor needs maintenance.

        Args:
            sensor_id: Sensor identifier
            config: Sensor configuration
        """
        now = datetime.now()
        stats = self._sensor_stats[sensor_id]

        # Check if maintenance is due
        if config.maintenance_due and now >= config.maintenance_due:
            stats["maintenance_required"] += 1

            _LOGGER.info(f"Maintenance due for sensor {sensor_id}")

            # Fire maintenance event
            self.hass.bus.async_fire(
                "ramses_extras_sensor_maintenance_due",
                {
                    "sensor_id": sensor_id,
                    "sensor_name": config.name,
                    "maintenance_type": "scheduled",
                    "due_date": config.maintenance_due.isoformat(),
                },
            )

        # Check if calibration is needed
        if (
            config.last_calibration
            and (now - config.last_calibration).days
            >= self._sensor_config["calibration_interval"]
        ):
            if sensor_id not in self._calibration_queue:
                self._calibration_queue.append(sensor_id)
                _LOGGER.info(f"Calibration due for sensor {sensor_id}")

        # Check quality score
        if stats["quality_score"] < self._sensor_config["quality_threshold"]:
            if sensor_id not in self._calibration_queue:
                self._calibration_queue.append(sensor_id)
                _LOGGER.warning(
                    f"Poor quality detected for sensor {sensor_id}: "
                    f"Quality score: {stats['quality_score']:.2f}"
                )

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict[str, float]
    ) -> None:
        """Process sensor management automation logic.

        Args:
            device_id: Device identifier
            entity_states: Validated entity state values
        """
        _LOGGER.info(
            f"Processing sensor management logic - "
            f"Feature: {self.feature_id}, Device: {device_id}"
        )

        try:
            # This method can be used for device-specific sensor processing
            # For now, we use the background data processing for all sensors
            pass

        except Exception as e:
            _LOGGER.error(f"Device {device_id}: Error in sensor management logic - {e}")

    # Calibration methods
    async def calibrate_sensor(self, sensor_id: str, reference_value: float) -> bool:
        """Calibrate a sensor using a reference value.

        Args:
            sensor_id: Sensor identifier
            reference_value: Reference value for calibration

        Returns:
            True if calibration was successful
        """
        if sensor_id not in self._managed_sensors:
            _LOGGER.error(f"Sensor {sensor_id} not found")
            return False

        config = self._managed_sensors[sensor_id]

        # Get current average reading
        recent_readings = [
            r.calibrated_value
            for r in self._sensor_readings[sensor_id][-10:]
            if r.is_valid
        ]

        if not recent_readings:
            _LOGGER.error(f"No valid readings for sensor {sensor_id}")
            return False

        current_average = mean(recent_readings)

        # Calculate calibration offset
        old_offset = config.calibration_offset
        config.calibration_offset = reference_value - current_average
        config.last_calibration = datetime.now()

        # Store calibration in history
        calibration_record = {
            "timestamp": datetime.now().isoformat(),
            "reference_value": reference_value,
            "measured_value": current_average,
            "offset_applied": config.calibration_offset,
            "old_offset": old_offset,
        }
        if config.calibration_history is None:
            config.calibration_history = []
        config.calibration_history.append(calibration_record)

        # Remove from calibration queue
        if sensor_id in self._calibration_queue:
            self._calibration_queue.remove(sensor_id)

        _LOGGER.info(
            f"Sensor {sensor_id} calibrated: "
            f"Reference: {reference_value}, Measured: {current_average:.2f}, "
            f"Offset: {config.calibration_offset:.2f}"
        )

        return True

    def get_sensor_status(self, sensor_id: str) -> dict[str, Any] | None:
        """Get status of a sensor.

        Args:
            sensor_id: Sensor identifier

        Returns:
            Sensor status dictionary or None if not found
        """
        if sensor_id not in self._managed_sensors:
            return None

        config = self._managed_sensors[sensor_id]
        stats = self._sensor_stats[sensor_id]

        # Get latest reading
        latest_reading = None
        if self._sensor_readings[sensor_id]:
            latest_reading = self._sensor_readings[sensor_id][-1]

        return {
            "sensor_id": sensor_id,
            "name": config.name,
            "type": config.sensor_type,
            "current_value": latest_reading.calibrated_value
            if latest_reading
            else None,
            "raw_value": latest_reading.raw_value if latest_reading else None,
            "is_valid": latest_reading.is_valid if latest_reading else False,
            "calibration_offset": config.calibration_offset,
            "last_calibration": config.last_calibration.isoformat()
            if config.last_calibration
            else None,
            "maintenance_due": config.maintenance_due.isoformat()
            if config.maintenance_due
            else None,
            "quality_score": stats["quality_score"],
            "readings_count": stats["readings_count"],
            "valid_readings": stats["valid_readings"],
            "anomalies_detected": stats["anomalies_detected"],
            "maintenance_required": stats["maintenance_required"],
            "average_value": stats["average_value"],
            "min_value": stats["min_value"]
            if stats["min_value"] != float("inf")
            else None,
            "max_value": stats["max_value"]
            if stats["max_value"] != float("-inf")
            else None,
        }

    def get_all_sensors_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all managed sensors.

        Returns:
            Dictionary mapping sensor IDs to status dictionaries
        """
        return {
            sensor_id: status
            for sensor_id in self._managed_sensors.keys()
            if (status := self.get_sensor_status(sensor_id)) is not None
        }

    def get_calibration_queue(self) -> list[str]:
        """Get list of sensors requiring calibration.

        Returns:
            List of sensor IDs needing calibration
        """
        return self._calibration_queue.copy()

    def get_sensor_statistics(self) -> dict[str, Any]:
        """Get overall sensor management statistics.

        Returns:
            Dictionary with statistics
        """
        total_sensors = len(self._managed_sensors)
        sensors_needing_calibration = len(self._calibration_queue)

        total_readings = sum(
            stats["readings_count"] for stats in self._sensor_stats.values()
        )
        total_valid_readings = sum(
            stats["valid_readings"] for stats in self._sensor_stats.values()
        )
        total_anomalies = sum(
            stats["anomalies_detected"] for stats in self._sensor_stats.values()
        )

        average_quality = 0.0
        if total_sensors > 0:
            average_quality = (
                sum(stats["quality_score"] for stats in self._sensor_stats.values())
                / total_sensors
            )

        return {
            "total_sensors": total_sensors,
            "sensors_needing_calibration": sensors_needing_calibration,
            "total_readings": total_readings,
            "total_valid_readings": total_valid_readings,
            "overall_quality_score": round(average_quality, 3),
            "total_anomalies_detected": total_anomalies,
            "calibration_queue": self._calibration_queue.copy(),
            "data_retention_days": self._sensor_config["data_retention_days"],
        }


# Feature registration helper
def create_sensor_management_feature(
    hass: HomeAssistant,
    feature_id: str = FEATURE_ID_HUMIDITY_SENSORS,
    binary_sensor: Any = None,
    debounce_seconds: int = 45,
) -> SensorManagementFeature:
    """Create a sensor management feature instance.

    Args:
        hass: Home Assistant instance
        feature_id: Feature identifier
        binary_sensor: Optional binary sensor
        debounce_seconds: Debounce duration

    Returns:
        SensorManagementFeature instance
    """
    return SensorManagementFeature(
        hass=hass,
        feature_id=feature_id,
        binary_sensor=binary_sensor,
        debounce_seconds=debounce_seconds,
    )


# Framework feature registration
def register_sensor_management_feature() -> None:
    """Register the sensor management feature with the framework.

    This function registers the sensor management feature so it can be
    discovered and managed by the framework's feature manager.
    """
    # entity_registry import not needed here

    feature_config = {
        "name": "Sensor Management",
        "description": "Comprehensive sensor management with "
        "calibration and validation",
        "class": "SensorManagementFeature",
        "factory": "create_sensor_management_feature",
        "dependencies": [],  # No dependencies
        "capabilities": [
            "sensor_management",
            "calibration",
            "validation",
            "anomaly_detection",
            "maintenance_scheduling",
            "data_processing",
        ],
    }

    entity_registry.register_feature_implementation(
        FEATURE_ID_HUMIDITY_SENSORS, feature_config
    )

    _LOGGER.info("Sensor management feature registered with framework")


__all__ = [
    "SensorManagementFeature",
    "SensorConfig",
    "SensorReading",
    "create_sensor_management_feature",
    "register_sensor_management_feature",
]
