from custom_components.ramses_extras.framework.helpers.config.validation import (
    ConfigValidator,
)


def test_validate_device_id_value_accepts_legacy_and_canonical_shapes() -> None:
    validator = ConfigValidator("test_feature")

    is_valid_canonical, canonical_error = validator.validate_device_id_value(
        "32:153289", "fan_id"
    )
    is_valid_legacy, legacy_error = validator.validate_device_id_value(
        "32_153289", "fan_id"
    )

    assert is_valid_canonical is True
    assert canonical_error is None
    assert is_valid_legacy is True
    assert legacy_error is None


def test_validate_position_limits_rejects_invalid_values() -> None:
    validator = ConfigValidator("test_feature")

    is_valid, errors = validator.validate_position_limits(
        {"min_position": 110, "max_position": 10}
    )

    assert is_valid is False
    assert "'min_position' must be between 0 and 100" in errors
    assert "'min_position' must be <= 'max_position'" in errors


def test_validate_zone_fans_valid_with_area_sensor_links() -> None:
    validator = ConfigValidator("test_feature")
    zones_section = {
        "FANs": {
            "32:153289": [
                {
                    "zone_id": "bathroom",
                    "actuator": {"min_position": 15, "max_position": 90},
                },
                {
                    "zone_id": "office",
                    "actuator": {"min_position": 0, "max_position": 100},
                },
            ]
        }
    }
    sensor_control_section = {
        "devices": {
            "32:153289": {
                "area_sensors": [
                    {"zone_id": "bathroom", "temperature_entity": "sensor.bath_temp"},
                    {"zone_id": "office", "temperature_entity": "sensor.office_temp"},
                ]
            }
        }
    }

    is_valid, errors = validator.validate_zone_fans(
        zones_section, sensor_control_section
    )

    assert is_valid is True
    assert errors == []


def test_validate_zone_fans_rejects_duplicate_zone_and_unknown_area_reference() -> None:
    validator = ConfigValidator("test_feature")
    zones_section = {
        "FANs": {
            "32:153289": [
                {"zone_id": "bathroom"},
                {
                    "zone_id": "bathroom",
                    "actuator": {"min_position": 80, "max_position": 50},
                },
            ]
        }
    }
    sensor_control_section = {
        "devices": {
            "32:153289": {
                "area_sensors": [
                    {"zone_id": "bathroom"},
                    {"zone_id": "office"},
                ]
            }
        }
    }

    is_valid, errors = validator.validate_zone_fans(
        zones_section, sensor_control_section
    )

    assert is_valid is False
    assert "duplicate zone_id 'bathroom' for FAN 32:153289" in errors
    assert (
        "zone 'bathroom' for FAN 32:153289: 'min_position' must be <= 'max_position'"
        in errors
    )
    assert (
        "area sensor 1 for FAN 32:153289 references unknown zone_id 'office'" in errors
    )


def test_validate_remote_binding_fans_rejects_duplicates() -> None:
    validator = ConfigValidator("test_feature")
    remote_binding_section = {
        "FANs": {
            "32:153289": {
                "REMs": [
                    {"rem_id": "37:169161", "role": "primary"},
                    {"rem_id": "37:169161", "role": "secondary"},
                ]
            },
            "32:111111": {
                "REMs": [
                    {"rem_id": "37_169161", "role": "primary"},
                ]
            },
        }
    }

    is_valid, errors = validator.validate_remote_binding_fans(remote_binding_section)

    assert is_valid is False
    assert "duplicate REM '37:169161' for FAN 32:153289" in errors
    assert (
        "primary REM '37:169161' cannot be assigned to both 32:153289 and 32:111111"
        in errors
    )


def test_validate_canonical_config_combines_zone_and_remote_errors() -> None:
    validator = ConfigValidator("test_feature")
    canonical_config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                "sensor_control": {
                    "devices": {
                        "32:153289": {
                            "area_sensors": [
                                {"zone_id": "office"},
                            ]
                        }
                    }
                },
                "zones": {
                    "FANs": {
                        "32:153289": [
                            {"zone_id": "bathroom"},
                        ]
                    }
                },
                "remote_binding": {
                    "FANs": {
                        "32:153289": {
                            "REMs": [
                                {"rem_id": "37:169161", "role": "primary"},
                            ]
                        },
                        "32:111111": {
                            "REMs": [
                                {"rem_id": "37_169161", "role": "primary"},
                            ]
                        },
                    }
                },
            },
        }
    }

    is_valid, errors = validator.validate_canonical_config(canonical_config)

    assert is_valid is False
    assert (
        "area sensor 0 for FAN 32:153289 references unknown zone_id 'office'" in errors
    )
    assert (
        "primary REM '37:169161' cannot be assigned to both 32:153289 and 32:111111"
        in errors
    )
