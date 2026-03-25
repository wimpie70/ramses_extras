from custom_components.ramses_extras.framework.helpers.config.migration import (
    get_migrated_feature_section,
    migrate_remote_binding_section,
    migrate_sensor_control_section,
    migrate_to_canonical_config,
    migrate_zones_section,
)
from custom_components.ramses_extras.framework.helpers.config.model import (
    CONFIG_DEVICES_KEY,
    CONFIG_FANS_KEY,
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
)


def test_migrate_sensor_control_section_legacy_shape() -> None:
    section = {
        SENSOR_CONTROL_SOURCES_KEY: {
            "32_153289": {"indoor_temperature": {"kind": "internal"}}
        },
        SENSOR_CONTROL_AREA_SENSORS_KEY: {"32_153289": [{"zone_id": "bathroom"}]},
    }

    result = migrate_sensor_control_section(section)

    assert result == {
        CONFIG_DEVICES_KEY: {
            "32:153289": {
                SENSOR_CONTROL_SOURCES_KEY: {
                    "indoor_temperature": {"kind": "internal"}
                },
                SENSOR_CONTROL_AREA_SENSORS_KEY: [{"zone_id": "bathroom"}],
            }
        }
    }


def test_migrate_remote_binding_section_from_bindings_list() -> None:
    section = {
        "bindings": [
            {
                "fan_id": "32_153289",
                "remote_id": "37_169161",
                "role": "primary",
                "enabled": True,
            }
        ]
    }

    result = migrate_remote_binding_section(section)

    assert result == {
        CONFIG_FANS_KEY: {
            "32:153289": {
                "REMs": [
                    {
                        "rem_id": "37:169161",
                        "role": "primary",
                        "enabled": True,
                    }
                ]
            }
        }
    }


def test_migrate_zones_section_normalizes_fan_keys() -> None:
    section = {"fans": {"32_153289": [{"zone_id": "bathroom"}]}}

    result = migrate_zones_section(section)

    assert result == {CONFIG_FANS_KEY: {"32:153289": [{"zone_id": "bathroom"}]}}


def test_migrate_to_canonical_config_collects_feature_sections() -> None:
    raw_config = {
        FEATURE_SENSOR_CONTROL: {
            SENSOR_CONTROL_SOURCES_KEY: {
                "32_153289": {"indoor_temperature": {"kind": "internal"}}
            }
        },
        FEATURE_REMOTE_BINDING: {
            "bindings": [
                {
                    "fan_id": "32_153289",
                    "remote_id": "37_169161",
                    "role": "primary",
                }
            ]
        },
        FEATURE_ZONES: {"fans": {"32_153289": [{"zone_id": "bathroom"}]}},
    }

    result = migrate_to_canonical_config(raw_config)

    features = result["ramses_extras"]["features"]
    assert set(features) == {
        FEATURE_SENSOR_CONTROL,
        FEATURE_REMOTE_BINDING,
        FEATURE_ZONES,
    }
    assert features[FEATURE_SENSOR_CONTROL][CONFIG_DEVICES_KEY]["32:153289"]
    assert features[FEATURE_REMOTE_BINDING][CONFIG_FANS_KEY]["32:153289"]["REMs"]
    assert features[FEATURE_ZONES][CONFIG_FANS_KEY]["32:153289"] == [
        {"zone_id": "bathroom"}
    ]


def test_get_migrated_feature_section_reads_root_features() -> None:
    raw_config = {
        "ramses_extras": {
            "features": {
                FEATURE_ZONES: {"fans": {"32_153289": [{"zone_id": "bathroom"}]}}
            }
        }
    }

    result = get_migrated_feature_section(raw_config, FEATURE_ZONES)

    assert result == {CONFIG_FANS_KEY: {"32:153289": [{"zone_id": "bathroom"}]}}
