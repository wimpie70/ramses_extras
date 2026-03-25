from custom_components.ramses_extras.framework.helpers.config.model import (
    CONFIG_DEVICES_KEY,
    CONFIG_FANS_KEY,
    SENSOR_CONTROL_ABS_HUMIDITY_INPUTS_KEY,
    SENSOR_CONTROL_AREA_SENSORS_KEY,
    SENSOR_CONTROL_SOURCES_KEY,
    find_areas_for_zone,
    find_entities_for_zone,
    get_fan_ids,
    get_sensor_control_device_section,
    make_empty_config_model,
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
