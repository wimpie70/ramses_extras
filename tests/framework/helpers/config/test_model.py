from custom_components.ramses_extras.framework.helpers.config.model import (
    CONFIG_DEVICES_KEY,
    CONFIG_FANS_KEY,
    SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
    find_areas_for_zone,
    find_entities_for_zone,
    find_zone_for_fan,
    get_fan_ids,
    get_fan_section,
    get_primary_rem_id,
    get_remote_binding_rem_ids,
    get_remote_binding_rems,
    get_sensor_control_device_section,
    get_zone_ids_for_fan,
    get_zones_for_fan,
    make_empty_config_model,
    set_fan_section,
)


def test_make_empty_config_model() -> None:
    config = make_empty_config_model()

    assert config == {
        "ramses_extras": {
            "schema_version": 1,
            "features": {},
        }
    }


def test_get_sensor_control_device_section_reads_legacy_shape() -> None:
    section = {
        SENSOR_CONTROL_SOURCES_KEY: {
            "32_153289": {"indoor_temperature": {"kind": "internal"}}
        },
        SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY: {
            "32_153289": {"indoor_abs_humidity": {"temperature": {"kind": "external"}}}
        },
        SENSOR_CONTROL_AREA_SENSORS_KEY: {
            "32_153289": [{"zone_id": "bathroom", "temperature_entity": "sensor.bath"}]
        },
    }

    result = get_sensor_control_device_section(section, "32:153289")

    assert result == {
        SENSOR_CONTROL_SOURCES_KEY: {"indoor_temperature": {"kind": "internal"}},
        SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY: {
            "indoor_abs_humidity": {"temperature": {"kind": "external"}}
        },
        SENSOR_CONTROL_AREA_SENSORS_KEY: [
            {"zone_id": "bathroom", "temperature_entity": "sensor.bath"}
        ],
    }


def test_find_areas_for_zone_and_entities() -> None:
    section = {
        CONFIG_DEVICES_KEY: {
            "32:153289": {
                SENSOR_CONTROL_AREA_SENSORS_KEY: [
                    {
                        "zone_id": "bathroom",
                        "temperature_entity": "sensor.bath_temp",
                        "humidity_entity": "sensor.bath_humidity",
                    },
                    {
                        "zone_id": "bathroom",
                        "co2_entity": "sensor.bath_co2",
                        "temperature_entity": "sensor.bath_temp",
                    },
                    {
                        "zone_id": "office",
                        "temperature_entity": "sensor.office_temp",
                    },
                ]
            }
        }
    }

    areas = find_areas_for_zone(section, "32:153289", "bathroom")
    entities = find_entities_for_zone(section, "32:153289", "bathroom")

    assert len(areas) == 2
    assert entities == [
        "sensor.bath_temp",
        "sensor.bath_humidity",
        "sensor.bath_co2",
    ]


def test_get_fan_ids_normalizes_mapping_keys() -> None:
    section = {
        CONFIG_FANS_KEY: {
            "32_153289": [{"zone_id": "bathroom"}],
            "32:111111": [{"zone_id": "office"}],
        }
    }

    result = get_fan_ids(section)

    assert result == ["32:111111", "32:153289"]


def test_get_fan_section_reads_legacy_fan_mapping_keys() -> None:
    section = {
        CONFIG_FANS_KEY: {
            "32_153289": {"REMs": [{"rem_id": "37:169161", "role": "primary"}]}
        }
    }

    result = get_fan_section(section, "32:153289")

    assert result == {"REMs": [{"rem_id": "37:169161", "role": "primary"}]}


def test_set_fan_section_normalizes_device_id_into_devices_mapping() -> None:
    section = {CONFIG_DEVICES_KEY: {}}

    stored = set_fan_section(
        section,
        "32_153289",
        {"sources": {"indoor_temperature": {"kind": "internal"}}},
    )

    assert stored == {"sources": {"indoor_temperature": {"kind": "internal"}}}
    assert section == {
        CONFIG_DEVICES_KEY: {
            "32:153289": {"sources": {"indoor_temperature": {"kind": "internal"}}}
        }
    }


def test_get_remote_binding_helpers_normalize_rems_and_primary() -> None:
    section = {
        CONFIG_FANS_KEY: {
            "32_153289": {
                "REMs": [
                    {"remote_id": "37_169161", "role": "primary"},
                    {"rem_id": "37:000002", "role": "secondary"},
                    {"rem_id": "37_169161", "role": "secondary"},
                ]
            }
        }
    }

    rems = get_remote_binding_rems(section, "32:153289")
    rem_ids = get_remote_binding_rem_ids(section, "32:153289")
    primary_rem_id = get_primary_rem_id(section, "32:153289")

    assert rems == [
        {"rem_id": "37:169161", "role": "primary"},
        {"rem_id": "37:000002", "role": "secondary"},
        {"rem_id": "37:169161", "role": "secondary"},
    ]
    assert rem_ids == ["37:169161", "37:000002"]
    assert primary_rem_id == "37:169161"


def test_zone_helpers_normalize_and_find_zone_entries() -> None:
    section = {
        CONFIG_FANS_KEY: {
            "32_153289": [
                {"zone_id": " bathroom ", "actuator": {"min_position": 15}},
                {"zone_id": "office"},
                {"zone_id": "bathroom"},
            ]
        }
    }

    zones = get_zones_for_fan(section, "32:153289")
    zone_ids = get_zone_ids_for_fan(section, "32:153289")
    bathroom_zone = find_zone_for_fan(section, "32:153289", "bathroom")

    assert zones == [
        {"zone_id": "bathroom", "actuator": {"min_position": 15}},
        {"zone_id": "office"},
        {"zone_id": "bathroom"},
    ]
    assert zone_ids == ["bathroom", "office"]
    assert bathroom_zone == {
        "zone_id": "bathroom",
        "actuator": {"min_position": 15},
    }
