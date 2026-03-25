from custom_components.ramses_extras.framework.helpers.config.export import (
    REDACTED_VALUE,
    build_exportable_config,
    export_config_to_yaml,
    redact_config_for_export,
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


def test_build_exportable_config_migrates_legacy_shape() -> None:
    raw_config = {
        FEATURE_SENSOR_CONTROL: {
            SENSOR_CONTROL_SOURCES_KEY: {
                "32_153289": {"indoor_temperature": {"kind": "internal"}}
            },
            SENSOR_CONTROL_AREA_SENSORS_KEY: {"32_153289": [{"zone_id": "bathroom"}]},
        },
        FEATURE_REMOTE_BINDING: {
            "bindings": [
                {"fan_id": "32_153289", "remote_id": "37_169161", "role": "primary"}
            ]
        },
        FEATURE_ZONES: {"fans": {"32_153289": [{"zone_id": "bathroom"}]}},
    }

    result = build_exportable_config(raw_config)

    features = result["ramses_extras"]["features"]
    assert features[FEATURE_SENSOR_CONTROL][CONFIG_DEVICES_KEY]["32:153289"]
    assert features[FEATURE_REMOTE_BINDING][CONFIG_FANS_KEY]["32:153289"]["REMs"]
    assert features[FEATURE_ZONES][CONFIG_FANS_KEY]["32:153289"] == [
        {"zone_id": "bathroom"}
    ]


def test_redact_config_for_export_redacts_sensitive_and_runtime_keys() -> None:
    canonical_config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                FEATURE_REMOTE_BINDING: {
                    CONFIG_FANS_KEY: {
                        "32:153289": {
                            "REMs": [
                                {
                                    "rem_id": "37:169161",
                                    "password": "secret-value",
                                    "last_seen": "2026-03-25T09:00:00",
                                }
                            ],
                            "transport_snapshot": {"state": "ok"},
                        }
                    }
                }
            },
            "api_key": "abc123",
            "discovery_hints": {"fans": ["32:153289"]},
        }
    }

    result = redact_config_for_export(canonical_config)

    root = result["ramses_extras"]
    rem = root["features"][FEATURE_REMOTE_BINDING][CONFIG_FANS_KEY]["32:153289"][
        "REMs"
    ][0]
    assert root["api_key"] == REDACTED_VALUE
    assert "discovery_hints" not in root
    assert rem["password"] == REDACTED_VALUE
    assert "last_seen" not in rem
    assert (
        "transport_snapshot"
        not in root["features"][FEATURE_REMOTE_BINDING][CONFIG_FANS_KEY]["32:153289"]
    )


def test_export_config_to_yaml_returns_strict_yaml_text() -> None:
    raw_config = {
        FEATURE_ZONES: {
            "fans": {
                "32_153289": [
                    {
                        "zone_id": "bathroom",
                        "actuator": {
                            "min_position": 15,
                            "max_position": 90,
                            "token": "do-not-export",
                        },
                    }
                ]
            }
        }
    }

    result = export_config_to_yaml(raw_config)

    assert isinstance(result, str)
    assert "ramses_extras:" in result
    assert "schema_version: 1" in result
    assert "32:153289:" in result
    assert "token: <redacted>" in result
    assert "min_position: 15" in result
    assert "max_position: 90" in result
