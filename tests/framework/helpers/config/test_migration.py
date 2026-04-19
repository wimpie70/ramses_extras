from custom_components.ramses_extras.framework.helpers.config.migration import (
    get_migrated_feature_section,
    migrate_feature_section,
    migrate_remote_binding_section,
    migrate_sensor_control_section,
    migrate_to_canonical_config,
    migrate_zones_section,
)
from custom_components.ramses_extras.framework.helpers.config.model import (
    CONFIG_DEVICES_KEY,
    CONFIG_FANS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
)
from custom_components.ramses_extras.framework.helpers.config.validation import (
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    FEATURE_ZONES,
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


def test_migrate_sensor_control_section_with_devices() -> None:
    """Test migration when devices key already exists."""
    section = {
        CONFIG_DEVICES_KEY: {"32_153289": {"indoor_temperature": {"kind": "internal"}}}
    }

    result = migrate_sensor_control_section(section)

    assert result == {
        CONFIG_DEVICES_KEY: {"32:153289": {"indoor_temperature": {"kind": "internal"}}}
    }


def test_migrate_sensor_control_section_non_dict_device() -> None:
    """Test migration when device section is not a dict."""
    section = {CONFIG_DEVICES_KEY: {"32_153289": "not a dict"}}

    result = migrate_sensor_control_section(section)

    # Should skip non-dict devices
    assert result == {CONFIG_DEVICES_KEY: {}}


def test_migrate_sensor_control_section_non_dict_config_group() -> None:
    """Test migration when config group is not a dict."""
    section = {SENSOR_CONTROL_SOURCES_KEY: "not a dict"}

    result = migrate_sensor_control_section(section)

    assert result == {CONFIG_DEVICES_KEY: {}}


def test_migrate_remote_binding_section_with_fans_key() -> None:
    """Test migration when fans key exists."""
    section = {
        CONFIG_FANS_KEY: {
            "32_153289": {"REMs": [{"rem_id": "37_169161", "role": "primary"}]}
        }
    }

    result = migrate_remote_binding_section(section)

    assert result == {
        CONFIG_FANS_KEY: {
            "32:153289": {"REMs": [{"rem_id": "37:169161", "role": "primary"}]}
        }
    }


def test_migrate_remote_binding_section_non_dict_fan_section() -> None:
    """Test migration when fan section is not a dict."""
    section = {CONFIG_FANS_KEY: {"32_153289": "not a dict"}}

    result = migrate_remote_binding_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_remote_binding_section_non_list_bindings() -> None:
    """Test migration when bindings is not a list."""
    section = {"bindings": "not a list"}

    result = migrate_remote_binding_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_remote_binding_section_non_dict_binding() -> None:
    """Test migration when binding is not a dict."""
    section = {"bindings": ["not a dict"]}

    result = migrate_remote_binding_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_remote_binding_section_missing_fan_id() -> None:
    """Test migration when fan_id is missing."""
    section = {"bindings": [{"rem_id": "37_169161", "role": "primary"}]}

    result = migrate_remote_binding_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_remote_binding_section_missing_rem_id() -> None:
    """Test migration when rem_id is missing."""
    section = {"bindings": [{"fan_id": "32_153289", "role": "primary"}]}

    result = migrate_remote_binding_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_remote_binding_section_with_remote_id_key() -> None:
    """Test migration when remote_id key is used."""
    section = {
        "bindings": [
            {
                "fan_id": "32_153289",
                "remote_id": "37_169161",
                "role": "primary",
            }
        ]
    }

    result = migrate_remote_binding_section(section)

    assert result == {
        CONFIG_FANS_KEY: {
            "32:153289": {"REMs": [{"rem_id": "37:169161", "role": "primary"}]}
        }
    }


def test_migrate_zones_section_with_legacy_zones() -> None:
    """Test migration with legacy zones list."""
    section = {"zones": [{"zone_id": "bathroom", "fan_id": "32_153289"}]}

    result = migrate_zones_section(section)

    assert result == {
        CONFIG_FANS_KEY: {"32:153289": [{"zone_id": "bathroom", "fan_id": "32_153289"}]}
    }


def test_migrate_zones_section_non_list_zones() -> None:
    """Test migration when zones is not a list."""
    section = {"zones": "not a list"}

    result = migrate_zones_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_zones_section_non_dict_zone() -> None:
    """Test migration when zone is not a dict."""
    section = {"zones": ["not a dict"]}

    result = migrate_zones_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_zones_section_missing_fan_id() -> None:
    """Test migration when fan_id is missing."""
    section = {"zones": [{"zone_id": "bathroom"}]}

    result = migrate_zones_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_zones_section_with_fallback_fan_id() -> None:
    """Test migration with fallback fan_id."""
    section = {"zones": [{"zone_id": "bathroom"}], "fan_id": "32_153289"}

    result = migrate_zones_section(section)

    assert result == {CONFIG_FANS_KEY: {"32:153289": [{"zone_id": "bathroom"}]}}


def test_migrate_zones_section_non_list_zones_in_fan_group() -> None:
    """Test migration when zones in fan group is not a list."""
    section = {CONFIG_FANS_KEY: {"32_153289": "not a list"}}

    result = migrate_zones_section(section)

    assert result == {CONFIG_FANS_KEY: {}}


def test_migrate_feature_section_unknown_feature() -> None:
    """Test migration for unknown feature."""
    section = {"some_key": "some_value"}

    result = migrate_feature_section("unknown_feature", section)

    assert result == {"some_key": "some_value"}


def test_migrate_to_canonical_config_with_debug_levels() -> None:
    """Test migration with debug levels."""
    raw_config = {"log_level": "debug", "ramses_log_level": "info"}

    result = migrate_to_canonical_config(raw_config)

    framework = result["ramses_extras"].get("framework", {})
    assert "debug_levels" in framework


def test_migrate_to_canonical_config_with_debugger_options() -> None:
    """Test migration with debugger options."""
    raw_config = {"ramses_debugger_enabled": "true", "ramses_debugger_port": 1234}

    result = migrate_to_canonical_config(raw_config)

    # Just verify it doesn't crash
    assert result is not None


def test_migrate_to_canonical_config_with_enabled_features() -> None:
    """Test migration with enabled features."""
    raw_config = {"enabled_features": {"sensor_control": {"enabled": True}}}

    result = migrate_to_canonical_config(raw_config)

    assert "enabled_features" in result["ramses_extras"]


def test_migrate_to_canonical_config_with_device_feature_matrix() -> None:
    """Test migration with device feature matrix."""
    raw_config = {"device_feature_matrix": {"32:153289": {"sensor_control": True}}}

    result = migrate_to_canonical_config(raw_config)

    assert "device_feature_matrix" in result["ramses_extras"]


def test_migrate_to_canonical_config_ramses_extras_framework() -> None:
    """Test migration with ramses_extras framework section."""
    raw_config = {
        "ramses_extras": {"framework": {"debug_levels": {"ramses_cc": "debug"}}}
    }

    result = migrate_to_canonical_config(raw_config)

    framework = result["ramses_extras"]["framework"]
    assert "debug_levels" in framework
