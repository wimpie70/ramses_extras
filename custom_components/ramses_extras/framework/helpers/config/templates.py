"""Configuration templates for Ramses Extras framework.

This module provides reusable default configuration templates that are shared across
all features, providing sensible defaults for common configuration patterns.
"""

from typing import Any


class ConfigTemplates:
    """Utility class for default configuration templates.

    This class provides default configuration templates that can be used by
    features to provide sensible defaults for their configuration.
    """

    # Generic automation template
    GENERIC_AUTOMATION: dict[str, Any] = {
        # General settings
        "enabled": True,
        "auto_start": True,
        # Automation settings
        "automation_enabled": True,
        "automation_debounce_seconds": 15,
        "decision_interval_seconds": 60,
        # Performance settings
        "max_decision_history": 100,
        "enable_performance_logging": True,
        "enable_automation_status": True,
        # Entity settings
        "auto_create_entities": True,
        "entity_update_interval": 5,  # seconds
        # Safety settings
        "max_runtime_minutes": 120,
        "cooldown_period_minutes": 15,
        "emergency_stop_enabled": True,
    }

    # Basic feature template
    BASIC_FEATURE: dict[str, Any] = {
        "enabled": True,
        "auto_start": True,
        "automation_enabled": True,
        "auto_create_entities": True,
        "enable_logging": False,
    }

    # Threshold-based automation template
    THRESHOLD_AUTOMATION: dict[str, Any] = {
        # Default thresholds
        "default_min_threshold": 40.0,
        "default_max_threshold": 60.0,
        # Decision thresholds
        "activation_threshold": 1.0,  # units above/below target
        "deactivation_threshold": -1.0,  # units above/below target
        "high_confidence_threshold": 2.0,  # units above/below target
        # Threshold validation
        "validate_thresholds": True,
        "auto_adjust_thresholds": False,
    }

    # Sensor-based template
    SENSOR_BASED = {
        # Sensor settings
        "indoor_sensor_entity": None,
        "outdoor_sensor_entity": None,
        "sensor_update_interval": 10,  # seconds
        "sensor_timeout": 30,  # seconds
        "sensor_validation": True,
        # Sensor filtering
        "enable_filtering": True,
        "filter_window_size": 5,
        "filter_type": "moving_average",
    }

    # Performance optimization template
    PERFORMANCE_OPTIMIZED = {
        # Update intervals
        "entity_update_interval": 5,  # seconds
        "sensor_read_interval": 10,  # seconds
        "decision_interval": 60,  # seconds
        # History management
        "max_history_size": 100,
        "history_cleanup_interval": 3600,  # seconds
        # Memory management
        "enable_memory_management": True,
        "memory_cleanup_threshold": 80,  # percentage
        # Logging
        "log_level": "INFO",
        "enable_debug_logging": False,
        "log_performance_metrics": True,
    }

    # Safety and reliability template
    SAFETY_FOCUSED = {
        # Safety limits
        "max_runtime_minutes": 120,
        "min_cooldown_minutes": 15,
        "max_activations_per_hour": 10,
        # Emergency controls
        "emergency_stop_enabled": True,
        "emergency_stop_timeout": 300,  # seconds
        "recovery_mode_enabled": True,
        # Monitoring
        "enable_health_monitoring": True,
        "health_check_interval": 300,  # seconds
        "failure_detection_enabled": True,
        "auto_recovery_enabled": True,
    }

    # Advanced automation template
    ADVANCED_AUTOMATION = {
        # Advanced decision logic
        "enable_predictive_control": False,
        "learning_enabled": False,
        "adaptation_rate": 0.1,
        # Multi-sensor fusion
        "fusion_algorithm": "weighted_average",
        "sensor_weight": 1.0,
        # Environmental adaptation
        "seasonal_adjustment": False,
        "weather_integration": False,
        "occupancy_detection": False,
        # Optimization
        "energy_optimization": False,
        "cost_optimization": False,
        "comfort_priority": True,
    }

    @classmethod
    def get_automation_template(
        cls,
        include_thresholds: bool = True,
        include_sensors: bool = True,
        include_performance: bool = True,
        include_safety: bool = True,
        include_advanced: bool = False,
    ) -> dict[str, Any]:
        """Get a comprehensive automation configuration template.

        Args:
            include_thresholds: Include threshold settings
            include_sensors: Include sensor settings
            include_performance: Include performance settings
            include_safety: Include safety settings
            include_advanced: Include advanced settings

        Returns:
            Complete configuration template
        """
        template = cls.GENERIC_AUTOMATION.copy()

        if include_thresholds:
            template.update(cls.THRESHOLD_AUTOMATION)

        if include_sensors:
            template.update(cls.SENSOR_BASED)

        if include_performance:
            template.update(cls.PERFORMANCE_OPTIMIZED)

        if include_safety:
            template.update(cls.SAFETY_FOCUSED)

        if include_advanced:
            template.update(cls.ADVANCED_AUTOMATION)

        return template

    @classmethod
    def get_minimal_template(cls) -> dict[str, Any]:
        """Get a minimal configuration template.

        Returns:
            Minimal configuration with just essential settings
        """
        return {
            "enabled": True,
            "automation_enabled": True,
        }

    @classmethod
    def get_humidity_control_template(cls) -> dict[str, Any]:
        """Get a humidity control specific configuration template.

        Returns:
            Configuration template for humidity control feature
        """
        template = cls.get_automation_template(
            include_thresholds=True,
            include_sensors=True,
            include_performance=True,
            include_safety=True,
            include_advanced=False,
        )

        # Humidity-specific overrides
        template.update(
            {
                # Humidity-specific thresholds
                "default_min_humidity": 40.0,
                "default_max_humidity": 60.0,
                "default_offset": 0.4,
                # Humidity decision thresholds
                "activation_threshold": 1.0,  # g/m³
                "deactivation_threshold": -1.0,  # g/m³
                "high_confidence_threshold": 2.0,  # g/m³
                # Humidity-specific settings
                "humidity_unit": "g/m³",
                "enable_dehumidification": True,
                "enable_humidification": False,
                # Sensor requirements
                "require_indoor_sensor": True,
                "require_outdoor_sensor": True,
                # Performance tuning
                "sensor_read_interval": 5,  # seconds
                "decision_interval": 30,  # seconds
            }
        )

        return template

    @classmethod
    def get_temperature_control_template(cls) -> dict[str, Any]:
        """Get a temperature control specific configuration template.

        Returns:
            Configuration template for temperature control feature
        """
        template = cls.get_automation_template(
            include_thresholds=True,
            include_sensors=True,
            include_performance=True,
            include_safety=True,
            include_advanced=False,
        )

        # Temperature-specific overrides
        template.update(
            {
                # Temperature-specific thresholds
                "default_min_temperature": 18.0,
                "default_max_temperature": 24.0,
                "default_offset": 0.5,
                # Temperature decision thresholds
                "activation_threshold": 0.5,  # °C
                "deactivation_threshold": -0.5,  # °C
                "high_confidence_threshold": 1.0,  # °C
                # Temperature-specific settings
                "temperature_unit": "°C",
                "enable_heating": True,
                "enable_cooling": True,
                # Sensor requirements
                "require_indoor_sensor": True,
                "require_outdoor_sensor": False,
                # Performance tuning
                "sensor_read_interval": 10,  # seconds
                "decision_interval": 60,  # seconds
            }
        )

        return template

    @classmethod
    def get_fan_control_template(cls) -> dict[str, Any]:
        """Get a fan control specific configuration template.

        Returns:
            Configuration template for fan control feature
        """
        template = cls.get_automation_template(
            include_thresholds=False,
            include_sensors=True,
            include_performance=True,
            include_safety=True,
            include_advanced=False,
        )

        # Fan-specific overrides
        template.update(
            {
                # Fan-specific settings
                "default_fan_speed": 2,
                "max_fan_speed": 5,
                "min_fan_speed": 1,
                # Fan control thresholds
                "auto_mode_enabled": True,
                "boost_mode_enabled": True,
                "eco_mode_enabled": True,
                "night_mode_enabled": False,
                # Performance thresholds
                "air_quality_threshold": 50,
                "co2_threshold": 1000,  # ppm
                "humidity_threshold": 65,  # %
                # Fan behavior
                "ramp_up_time": 30,  # seconds
                "ramp_down_time": 60,  # seconds
                "boost_duration": 15,  # minutes
                # Safety
                "filter_replacement_interval": 8760,  # hours (1 year)
                "maintenance_reminder": True,
            }
        )

        return template

    @classmethod
    def get_air_quality_template(cls) -> dict[str, Any]:
        """Get an air quality specific configuration template.

        Returns:
            Configuration template for air quality feature
        """
        template = cls.get_automation_template(
            include_thresholds=True,
            include_sensors=True,
            include_performance=True,
            include_safety=True,
            include_advanced=True,
        )

        # Air quality-specific overrides
        template.update(
            {
                # Air quality thresholds
                "good_aqi_threshold": 50,
                "moderate_aqi_threshold": 100,
                "unhealthy_aqi_threshold": 150,
                # Sensor types
                "enable_pm2_5": True,
                "enable_pm10": True,
                "enable_co2": True,
                "enable_voc": False,
                "enable_o3": False,
                # Control actions
                "auto_ventilation": True,
                "air_purification": False,
                "window_alerts": True,
                # Integration
                "weather_integration": True,
                "pollen_data": False,
                "traffic_data": False,
            }
        )

        return template

    @classmethod
    def merge_templates(cls, *templates: dict[str, Any]) -> dict[str, Any]:
        """Merge multiple configuration templates.

        Args:
            templates: Variable number of configuration templates

        Returns:
            Merged configuration dictionary
        """
        merged = {}

        for template in templates:
            merged.update(template)

        return merged

    @classmethod
    def customize_template(
        cls,
        base_template: dict[str, Any],
        customizations: dict[str, Any],
        overrides: bool = False,
    ) -> dict[str, Any]:
        """Customize a configuration template.

        Args:
            base_template: Base configuration template
            customizations: Customizations to apply
            overrides: If True, customizations override base template values

        Returns:
            Customized configuration dictionary
        """
        customized = base_template.copy()

        for key, value in customizations.items():
            if overrides or key not in customized:
                customized[key] = value

        return customized


# Pre-built templates for common features
HUMIDITY_CONTROL_DEFAULTS = ConfigTemplates.get_humidity_control_template()
TEMPERATURE_CONTROL_DEFAULTS = ConfigTemplates.get_temperature_control_template()
FAN_CONTROL_DEFAULTS = ConfigTemplates.get_fan_control_template()
AIR_QUALITY_DEFAULTS = ConfigTemplates.get_air_quality_template()

# Minimal templates for simple features
MINIMAL_AUTOMATION = ConfigTemplates.get_minimal_template()
BASIC_FEATURE = ConfigTemplates.BASIC_FEATURE
PERFORMANCE_OPTIMIZED = ConfigTemplates.PERFORMANCE_OPTIMIZED


__all__ = [
    "ConfigTemplates",
    "HUMIDITY_CONTROL_DEFAULTS",
    "TEMPERATURE_CONTROL_DEFAULTS",
    "FAN_CONTROL_DEFAULTS",
    "AIR_QUALITY_DEFAULTS",
    "MINIMAL_AUTOMATION",
    "BASIC_FEATURE",
    "PERFORMANCE_OPTIMIZED",
]
