"""Tests for Brand Customization Entity generation."""

import logging

from custom_components.ramses_extras.framework.helpers.brand_customization.entities import (  # noqa: E501
    EntityGenerationManager,
    HighEndEntityTemplates,
    SpecialEntityTemplates,
    StandardEntityTemplates,
    create_humidity_entities,
    generate_entity_templates_for_feature,
    get_entity_count_metrics,
    optimize_entity_generation,
    validate_entity_ids,
)


class TestEntityTemplates:
    """Test cases for entity template classes."""

    def test_standard_entity_templates(self):
        """Test getting standard entities."""
        entities = StandardEntityTemplates.get_standard_entities("orcon", "123")
        assert "orcon_filter_usage_123" in entities
        assert "orcon_operation_mode_123" in entities

    def test_special_entity_templates(self):
        """Test getting special entities."""
        caps = ["filter_timer", "co2_sensor"]
        entities = SpecialEntityTemplates.get_special_entities(caps, "zehnder", "456")
        assert "number.zehnder_filter_timer_456" in entities
        assert "sensor.zehnder_co2_level_456" in entities

        # Non-existent capability
        assert SpecialEntityTemplates.get_special_entities(["unknown"], "b", "d") == []

    def test_high_end_entity_templates(self):
        """Test getting high-end entities."""
        entities = HighEndEntityTemplates.get_high_end_entities("orcon", "789")
        assert "sensor.orcon_air_quality_index_789" in entities
        assert "switch.orcon_smart_boost_789" in entities


class TestEntityGenerationManager:
    """Test cases for EntityGenerationManager."""

    def test_init(self):
        """Test initialization."""
        manager = EntityGenerationManager("orcon")
        assert manager.brand_name == "orcon"

    def test_generate_standard_entities(self):
        """Test generating standard entities."""
        manager = EntityGenerationManager("orcon")
        entities = manager.generate_standard_entities("123", {})
        assert "orcon_filter_usage_123" in entities

    def test_generate_special_entities(self):
        """Test generating special entities."""
        manager = EntityGenerationManager("orcon")
        model_info = {"special_entities": ["filter_timer"]}
        entities = manager.generate_special_entities("123", model_info)
        assert "number.orcon_filter_timer_123" in entities

    def test_generate_high_end_entities(self):
        """Test generating high-end entities."""
        manager = EntityGenerationManager("orcon")
        model_info = {"model_key": "H1", "high_end_models": ["H1"]}
        entities = manager.generate_high_end_entities("123", model_info)
        assert "sensor.orcon_air_quality_index_123" in entities

        # Not high end
        model_info_low = {"model_key": "L1", "high_end_models": ["H1"]}
        assert manager.generate_high_end_entities("123", model_info_low) == []

    def test_generate_all_entities(self):
        """Test generating all entities."""
        manager = EntityGenerationManager("orcon")
        model_info = {
            "model_key": "H1",
            "high_end_models": ["H1"],
            "special_entities": ["filter_timer"],
        }
        entities = manager.generate_all_entities("123", model_info)
        assert "orcon_filter_usage_123" in entities
        assert "number.orcon_filter_timer_123" in entities
        assert "sensor.orcon_air_quality_index_123" in entities

    def test_get_entity_enablement_config_orcon(self):
        """Test getting entity enablement config for Orcon."""
        manager = EntityGenerationManager("orcon")
        model_info = {
            "model_key": "HRV400",
            "special_entities": [],
            "high_end_models": [],
        }
        config = manager.get_entity_enablement_config("123", model_info)
        assert config.get("select.orcon_operation_mode_123") is True
        assert config.get("sensor.orcon_air_quality_index_123") is True

        # HRV200 should have eco mode disabled
        model_info_200 = {
            "model_key": "HRV200",
            "special_entities": [],
            "high_end_models": [],
        }
        config_200 = manager.get_entity_enablement_config("123", model_info_200)
        assert config_200.get("switch.orcon_eco_mode_123") is False

    def test_get_entity_enablement_config_zehnder(self):
        """Test getting entity enablement config for Zehnder."""
        manager = EntityGenerationManager("zehnder")
        model_info = {
            "model_key": "Q350",
            "special_entities": ["co2_sensor"],
            "high_end_models": ["Q350"],
        }
        config = manager.get_entity_enablement_config("123", model_info)
        assert config.get("switch.zehnder_auto_mode_123") is True
        assert config.get("sensor.zehnder_co2_level_123") is True


class TestEntityModuleFunctions:
    """Test top-level functions in entities module."""

    def test_generate_entity_templates_for_feature(self):
        """Test generating entity templates for feature."""
        templates = generate_entity_templates_for_feature("f", "orcon")
        assert "orcon_filter_usage_{device_id}" in templates["sensor"]

    def test_validate_entity_ids(self):
        """Test validating entity IDs."""
        assert validate_entity_ids(["sensor.test"]) is True
        assert validate_entity_ids(["invalid"]) is False
        assert validate_entity_ids([123]) is False
        assert validate_entity_ids([""]) is False

    def test_optimize_entity_generation(self):
        """Test optimizing entity generation."""
        input_ids = ["b.test", "a.test", "b.test"]
        optimized = optimize_entity_generation(input_ids)
        assert optimized == ["a.test", "b.test"]

    def test_get_entity_count_metrics(self):
        """Test getting entity count metrics."""
        entities = ["sensor.1", "sensor.2", "binary_sensor.1"]
        metrics = get_entity_count_metrics(entities)
        assert metrics["sensor"] == 2
        assert metrics["binary_sensor"] == 1

    def test_create_humidity_entities(self):
        """Test creating humidity entities."""
        # Orcon
        entities_orcon = create_humidity_entities("orcon", "123")
        assert "switch.orcon_smart_humidity_123" in entities_orcon

        # Zehnder
        entities_zehnder = create_humidity_entities("zehnder", "456")
        assert "switch.zehnder_auto_humidity_456" in entities_zehnder
        assert "sensor.zehnder_co2_humidity_correlation_456" in entities_zehnder

        # Other
        assert len(create_humidity_entities("generic", "789")) == 2
