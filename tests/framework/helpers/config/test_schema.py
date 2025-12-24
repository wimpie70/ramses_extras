"""Tests for ConfigSchema in framework/helpers/config/schema.py."""

import pytest

from custom_components.ramses_extras.framework.helpers.config.schema import ConfigSchema


class TestConfigSchema:
    """Test cases for ConfigSchema."""

    def setup_method(self):
        """Set up test fixtures."""
        self.schema = ConfigSchema("test_feature")

    def test_init(self):
        """Test initialization of ConfigSchema."""
        assert self.schema.feature_id == "test_feature"

    def test_generate_basic_schema_simple(self):
        """Test generating basic schema with simple fields."""
        fields = {
            "enabled": {
                "type": "boolean",
                "title": "Enable Feature",
                "description": "Enable or disable the feature",
                "default": False,
            },
            "name": {
                "type": "string",
                "title": "Feature Name",
                "description": "Name of the feature",
                "default": "Default Name",
            },
        }

        result = self.schema.generate_basic_schema(fields)

        expected = {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "Enable Feature",
                    "description": "Enable or disable the feature",
                    "default": False,
                },
                "name": {
                    "type": "string",
                    "title": "Feature Name",
                    "description": "Name of the feature",
                    "default": "Default Name",
                },
            },
        }

        assert result == expected

    def test_generate_basic_schema_with_required_fields(self):
        """Test generating basic schema with required fields."""
        fields = {
            "enabled": {
                "type": "boolean",
                "required": True,
            },
            "name": {
                "type": "string",
                "required": True,
            },
            "optional_field": {
                "type": "string",
            },
        }

        result = self.schema.generate_basic_schema(fields)

        assert "required" in result
        assert "enabled" in result["required"]
        assert "name" in result["required"]
        assert "optional_field" not in result["required"]

    def test_generate_basic_schema_boolean_field(self):
        """Test generating schema for boolean field."""
        field_config = {
            "type": "boolean",
            "title": "Test Boolean",
            "description": "A test boolean field",
            "default": True,
        }

        result = self.schema._generate_property_schema("test_bool", field_config)

        expected = {
            "type": "boolean",
            "title": "Test Boolean",
            "description": "A test boolean field",
            "default": True,
        }

        assert result == expected

    def test_generate_basic_schema_numeric_field(self):
        """Test generating schema for numeric field."""
        field_config = {
            "type": "numeric",
            "title": "Test Number",
            "description": "A test numeric field",
            "min": 0,
            "max": 100,
            "step": 0.5,
            "default": 50,
        }

        result = self.schema._generate_property_schema("test_num", field_config)

        expected = {
            "type": "number",
            "title": "Test Number",
            "description": "A test numeric field",
            "minimum": 0,
            "maximum": 100,
            "multipleOf": 0.5,
            "default": 50,
        }

        assert result == expected

    def test_generate_basic_schema_integer_field(self):
        """Test generating schema for integer field."""
        field_config = {
            "type": "integer",
            "title": "Test Integer",
            "description": "A test integer field",
            "min": 1,
            "max": 10,
            "default": 5,
        }

        result = self.schema._generate_property_schema("test_int", field_config)

        expected = {
            "type": "integer",
            "title": "Test Integer",
            "description": "A test integer field",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        }

        assert result == expected

    def test_generate_basic_schema_string_field(self):
        """Test generating schema for string field."""
        field_config = {
            "type": "string",
            "title": "Test String",
            "description": "A test string field",
            "min_length": 3,
            "max_length": 50,
            "choices": ["option1", "option2", "option3"],
            "default": "option1",
        }

        result = self.schema._generate_property_schema("test_str", field_config)

        expected = {
            "type": "string",
            "title": "Test String",
            "description": "A test string field",
            "minLength": 3,
            "maxLength": 50,
            "enum": ["option1", "option2", "option3"],
            "default": "option1",
        }

        assert result == expected

    def test_generate_basic_schema_list_field(self):
        """Test generating schema for list field."""
        field_config = {
            "type": "list",
            "title": "Test List",
            "description": "A test list field",
            "item_type": "string",
            "default": [],
        }

        result = self.schema._generate_property_schema("test_list", field_config)

        expected = {
            "type": "array",
            "title": "Test List",
            "description": "A test list field",
            "items": {"type": "string"},
            "default": [],
        }

        assert result == expected

    def test_generate_basic_schema_with_entity_selector(self):
        """Test generating schema with entity selector."""
        field_config = {
            "type": "string",
            "title": "Test Entity",
            "entity_type": "sensor",
        }

        result = self.schema._generate_property_schema("test_entity", field_config)

        assert "entity_type" in result
        assert "selector" in result
        assert result["selector"] == {"entity": {"filter": {"domain": "sensor"}}}

    def test_generate_basic_schema_with_device_selector(self):
        """Test generating schema with device selector."""
        field_config = {
            "type": "string",
            "title": "Test Device",
            "device_type": "ramses_device",
        }

        result = self.schema._generate_property_schema("test_device", field_config)

        assert "device_type" in result
        assert "selector" in result
        assert result["selector"] == {"device": {"integration": "ramses_extras"}}

    def test_generate_property_schema_default_title(self):
        """Test generating property schema with default title."""
        field_config = {"type": "boolean"}

        result = self.schema._generate_property_schema("test_field", field_config)

        assert result["title"] == "Test Field"  # Title case with spaces

    def test_generate_property_schema_no_description(self):
        """Test generating property schema without description."""
        field_config = {"type": "boolean", "title": "Custom Title"}

        result = self.schema._generate_property_schema("test_field", field_config)

        assert "description" not in result

    def test_generate_basic_schema_empty_fields(self):
        """Test generating schema with empty fields dict."""
        result = self.schema.generate_basic_schema({})

        expected = {
            "type": "object",
            "properties": {},
        }

        assert result == expected

    def test_generate_basic_schema_mixed_field_types(self):
        """Test generating schema with mixed field types."""
        fields = {
            "bool_field": {"type": "boolean", "default": False},
            "num_field": {"type": "numeric", "min": 0, "max": 100, "default": 50},
            "str_field": {"type": "string", "default": "test"},
            "list_field": {"type": "list", "item_type": "string", "default": []},
        }

        result = self.schema.generate_basic_schema(fields)

        assert result["type"] == "object"
        assert len(result["properties"]) == 4

        # Check each field type
        assert result["properties"]["bool_field"]["type"] == "boolean"
        assert result["properties"]["num_field"]["type"] == "number"
        assert result["properties"]["str_field"]["type"] == "string"
        assert result["properties"]["list_field"]["type"] == "array"
