"""Tests for Default feature in features/default/__init__.py."""

from custom_components.ramses_extras.features.default import (
    DEFAULT_BOOLEAN_CONFIGS,
    DEFAULT_DEVICE_ENTITY_MAPPING,
    DEFAULT_NUMBER_CONFIGS,
    DEFAULT_SENSOR_CONFIGS,
    DEFAULT_SWITCH_CONFIGS,
)


class TestDefaultFeatureConstants:
    """Test cases for default feature constants and configurations."""

    def test_default_sensor_configs_structure(self):
        """Test that default sensor configs have expected structure."""
        assert isinstance(DEFAULT_SENSOR_CONFIGS, dict)

        # Should contain expected sensor types
        expected_sensors = [
            "indoor_absolute_humidity",
            "outdoor_absolute_humidity",
        ]
        for sensor in expected_sensors:
            assert sensor in DEFAULT_SENSOR_CONFIGS, f"Missing sensor config: {sensor}"

            config = DEFAULT_SENSOR_CONFIGS[sensor]
            assert isinstance(config, dict)
            assert "entity_template" in config
            assert "name_template" in config

    def test_default_switch_configs_structure(self):
        """Test that default switch configs have expected structure."""
        assert isinstance(DEFAULT_SWITCH_CONFIGS, dict)

        # Should contain expected switch types
        expected_switches = []
        for switch in expected_switches:
            assert switch in DEFAULT_SWITCH_CONFIGS, f"Missing switch config: {switch}"

            config = DEFAULT_SWITCH_CONFIGS[switch]
            assert isinstance(config, dict)
            assert "entity_template" in config
            assert "name" in config

    def test_default_number_configs_structure(self):
        """Test that default number configs have expected structure."""
        assert isinstance(DEFAULT_NUMBER_CONFIGS, dict)

        # Should contain expected number types
        expected_numbers = []
        for number in expected_numbers:
            assert number in DEFAULT_NUMBER_CONFIGS, f"Missing number config: {number}"

            config = DEFAULT_NUMBER_CONFIGS[number]
            assert isinstance(config, dict)
            assert "entity_template" in config
            assert "name" in config

    def test_default_boolean_configs_structure(self):
        """Test that default boolean configs have expected structure."""
        assert isinstance(DEFAULT_BOOLEAN_CONFIGS, dict)

        # Should contain expected boolean sensor types
        expected_booleans = []
        for boolean in expected_booleans:
            assert boolean in DEFAULT_BOOLEAN_CONFIGS, (
                f"Missing boolean config: {boolean}"
            )

            config = DEFAULT_BOOLEAN_CONFIGS[boolean]
            assert isinstance(config, dict)
            assert "entity_template" in config
            assert "name" in config

    def test_default_device_entity_mapping_structure(self):
        """Test that default device entity mapping has expected structure."""
        assert isinstance(DEFAULT_DEVICE_ENTITY_MAPPING, dict)

        # Should contain mappings for different device types
        assert "FAN" in DEFAULT_DEVICE_ENTITY_MAPPING

        # FAN device mapping
        fan_mapping = DEFAULT_DEVICE_ENTITY_MAPPING["FAN"]
        assert isinstance(fan_mapping, dict)

        # Should contain entity type mappings
        assert "sensor" in fan_mapping

    def test_entity_templates_contain_device_id_placeholder(self):
        """Test that entity templates contain {device_id} placeholder."""
        all_configs = [
            DEFAULT_SENSOR_CONFIGS,
            DEFAULT_SWITCH_CONFIGS,
            DEFAULT_NUMBER_CONFIGS,
            DEFAULT_BOOLEAN_CONFIGS,
        ]
        for config_dict in all_configs:
            for entity_name, config in config_dict.items():
                template = config.get("entity_template", "")
                assert "{device_id}" in template, (
                    f"Template for {entity_name} missing {{device_id}} placeholder: "
                    f"{template}"
                )

    def test_config_names_are_descriptive(self):
        """Test that config names are descriptive and not empty."""
        all_configs = [
            DEFAULT_SENSOR_CONFIGS,
            DEFAULT_SWITCH_CONFIGS,
            DEFAULT_NUMBER_CONFIGS,
            DEFAULT_BOOLEAN_CONFIGS,
        ]
        for config_dict in all_configs:
            for entity_name, config in config_dict.items():
                name = config.get("name_template", config.get("name", ""))
                assert name, f"Config for {entity_name} has empty name"
                assert len(name) > 3, (
                    f"Config name for {entity_name} is too short: {name}"
                )

    def test_device_entity_mapping_templates_valid(self):
        """Test that device entity mapping templates are valid."""
        for device_type, mapping in DEFAULT_DEVICE_ENTITY_MAPPING.items():
            for entity_type, entities in mapping.items():
                assert isinstance(entities, list), (
                    f"Entities for {device_type}.{entity_type} should be a list"
                )
                for entity_name in entities:
                    assert isinstance(entity_name, str), (
                        f"Entity name should be string: {entity_name}"
                    )
                    assert len(entity_name) > 0, (
                        f"Entity name should not be empty: {entity_name}"
                    )

    def test_no_duplicate_entity_names_within_device_type(self):
        """Test that there are no duplicate entity names within a device type."""
        for device_type, mapping in DEFAULT_DEVICE_ENTITY_MAPPING.items():
            all_entities = []
            for entity_type, entities in mapping.items():
                all_entities.extend(entities)

            # Check for duplicates
            unique_entities = set(all_entities)
            assert len(all_entities) == len(unique_entities), (
                f"Duplicate entities found in {device_type}: {all_entities}"
            )

    def test_all_exports_available(self):
        """Test that all expected exports are available."""
        # Test that imports work without error
        assert DEFAULT_SENSOR_CONFIGS is not None
        assert DEFAULT_SWITCH_CONFIGS is not None
        assert DEFAULT_NUMBER_CONFIGS is not None
        assert DEFAULT_BOOLEAN_CONFIGS is not None
        assert DEFAULT_DEVICE_ENTITY_MAPPING is not None
