from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers.config.core import (
    ExtrasConfigManager,
)
from custom_components.ramses_extras.framework.helpers.config.model import (
    CONFIG_FANS_KEY,
    FEATURE_REMOTE_BINDING,
    FEATURE_SENSOR_CONTROL,
    SENSOR_CONTROL_SOURCES_KEY,
)


def _make_manager() -> ExtrasConfigManager:
    hass = MagicMock(spec=HomeAssistant)
    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.options = {}
    config_entry.data = {}
    return ExtrasConfigManager(hass, config_entry, "test_feature", {})


def test_get_feature_section_canonical_from_legacy() -> None:
    manager = _make_manager()
    manager._config = {
        FEATURE_SENSOR_CONTROL: {
            SENSOR_CONTROL_SOURCES_KEY: {
                "32_153289": {"indoor_temperature": {"kind": "internal"}}
            }
        }
    }

    result = manager.get_feature_section(FEATURE_SENSOR_CONTROL, canonical=True)

    assert result == {
        "devices": {
            "32:153289": {
                SENSOR_CONTROL_SOURCES_KEY: {"indoor_temperature": {"kind": "internal"}}
            }
        }
    }


def test_get_fan_section_for_sensor_control_legacy_shape() -> None:
    manager = _make_manager()
    manager._config = {
        FEATURE_SENSOR_CONTROL: {
            SENSOR_CONTROL_SOURCES_KEY: {
                "32_153289": {"indoor_temperature": {"kind": "internal"}}
            }
        }
    }

    result = manager.get_fan_section(FEATURE_SENSOR_CONTROL, "32:153289")

    assert result == {
        SENSOR_CONTROL_SOURCES_KEY: {"indoor_temperature": {"kind": "internal"}}
    }


def test_list_configured_fans_from_canonical_section() -> None:
    manager = _make_manager()
    manager._config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                FEATURE_REMOTE_BINDING: {
                    CONFIG_FANS_KEY: {
                        "32:153289": {"REMs": []},
                        "32_111111": {"REMs": []},
                    }
                }
            },
        }
    }

    result = manager.list_configured_fans(FEATURE_REMOTE_BINDING, canonical=False)

    assert result == ["32:111111", "32:153289"]


def test_get_fan_section_for_remote_binding_legacy_fan_key() -> None:
    manager = _make_manager()
    manager._config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                FEATURE_REMOTE_BINDING: {
                    CONFIG_FANS_KEY: {
                        "32_153289": {
                            "REMs": [{"rem_id": "37:169161", "role": "primary"}]
                        }
                    }
                }
            },
        }
    }

    result = manager.get_fan_section(FEATURE_REMOTE_BINDING, "32:153289")

    assert result == {"REMs": [{"rem_id": "37:169161", "role": "primary"}]}


def test_set_feature_section_canonical_promotes_root_model() -> None:
    manager = _make_manager()
    manager._config = {
        FEATURE_SENSOR_CONTROL: {
            SENSOR_CONTROL_SOURCES_KEY: {
                "32_153289": {"indoor_temperature": {"kind": "internal"}}
            }
        }
    }

    manager.set_feature_section(
        FEATURE_REMOTE_BINDING,
        {CONFIG_FANS_KEY: {"32:153289": {"REMs": [{"rem_id": "37:169161"}]}}},
        canonical=True,
    )

    assert "ramses_extras" in manager._config
    result = manager.get_feature_section(FEATURE_REMOTE_BINDING)
    assert result == {
        CONFIG_FANS_KEY: {"32:153289": {"REMs": [{"rem_id": "37:169161"}]}}
    }


def test_validate_canonical_config_from_manager() -> None:
    manager = _make_manager()
    manager._config = {
        FEATURE_SENSOR_CONTROL: {
            "area_sensors": {
                "32_153289": [
                    {"zone_id": "office"},
                ]
            }
        },
        "zones": {
            "fans": {
                "32_153289": [
                    {"zone_id": "bathroom"},
                ]
            }
        },
        FEATURE_REMOTE_BINDING: {
            "bindings": [
                {"fan_id": "32_153289", "remote_id": "37_169161", "role": "primary"},
                {"fan_id": "32_111111", "remote_id": "37_169161", "role": "primary"},
            ]
        },
    }

    is_valid, errors = manager.validate_canonical_config()

    assert is_valid is False
    assert (
        "area sensor 0 for FAN 32:153289 references unknown zone_id 'office'" in errors
    )
    assert (
        "primary REM '37:169161' cannot be assigned to both 32:153289 and 32:111111"
        in errors
    )


def test_validate_feature_section_canonical_for_zones() -> None:
    manager = _make_manager()
    manager._config = {
        FEATURE_SENSOR_CONTROL: {
            "area_sensors": {
                "32_153289": [
                    {"zone_id": "bathroom"},
                ]
            }
        },
        "zones": {
            "fans": {
                "32_153289": [
                    {
                        "zone_id": "bathroom",
                        "actuator": {"min_position": 20, "max_position": 10},
                    },
                ]
            }
        },
    }

    is_valid, errors = manager.validate_feature_section_canonical("zones")

    assert is_valid is False
    assert (
        "zone 'bathroom' for FAN 32:153289: 'min_position' must be <= 'max_position'"
        in errors
    )


def test_validate_feature_section_canonical_for_remote_binding_legacy_remote_id() -> (
    None
):
    manager = _make_manager()
    manager._config = {
        "ramses_extras": {
            "schema_version": 1,
            "features": {
                FEATURE_REMOTE_BINDING: {
                    CONFIG_FANS_KEY: {
                        "32_153289": {
                            "REMs": [{"remote_id": "37_169161", "role": "primary"}]
                        },
                        "32:111111": {
                            "REMs": [{"remote_id": "37:169161", "role": "primary"}]
                        },
                    }
                }
            },
        }
    }

    is_valid, errors = manager.validate_feature_section_canonical(
        FEATURE_REMOTE_BINDING
    )

    assert is_valid is False
    assert (
        "primary REM '37:169161' cannot be assigned to both 32:153289 and 32:111111"
        in errors
    )
