"""Tests for Brand Customization Model configurations."""

import logging
from unittest.mock import patch

from custom_components.ramses_extras.framework.helpers.brand_customization.models import (  # noqa: E501
    DefaultModelConfig,
    ModelConfigManager,
    auto_detect_and_register_model,
    get_model_template,
    validate_model_config,
)


class TestDefaultModelConfig:
    """Test cases for DefaultModelConfig."""

    def test_get_fallback_config(self):
        """Test getting fallback configuration."""
        config = DefaultModelConfig.get_fallback_config("ModelX", "BrandY")
        assert config["model_key"] == "unknown"
        assert config["model_string"] == "ModelX"
        assert config["brand"] == "BrandY"
        assert config["max_fan_speed"] == 3


class TestModelConfigManager:
    """Test cases for ModelConfigManager."""

    def test_init_orcon(self):
        """Test initializing Orcon configurations."""
        manager = ModelConfigManager("orcon")
        assert "HRV200" in manager.model_configs
        assert "HRV300" in manager.model_configs
        assert "HRV400" in manager.model_configs

    def test_init_zehnder(self):
        """Test initializing Zehnder configurations."""
        manager = ModelConfigManager("zehnder")
        assert "ComfoAir Q350" in manager.model_configs
        assert "ComfoAir Q600" in manager.model_configs

    def test_init_generic(self):
        """Test initializing generic brand."""
        manager = ModelConfigManager("generic")
        assert manager.model_configs == {}

    def test_get_model_config_exact_match(self):
        """Test getting model config with exact match."""
        manager = ModelConfigManager("orcon")
        config = manager.get_model_config("HRV200")
        assert config["model_key"] == "HRV200"
        assert config["max_fan_speed"] == 2

    def test_get_model_config_partial_match(self):
        """Test getting model config with partial match."""
        manager = ModelConfigManager("orcon")
        # "HRV300 variant" contains "HRV300"
        config = manager.get_model_config("HRV300 variant")
        assert config["model_key"] == "HRV300"
        assert config["max_fan_speed"] == 3

    def test_get_model_config_case_insensitive(self):
        """Test getting model config case-insensitively."""
        manager = ModelConfigManager("orcon")
        config = manager.get_model_config("hrv200")
        assert config["model_key"] == "HRV200"

    def test_get_model_config_fallback(self, caplog):
        """Test getting model config with fallback for unknown model."""
        manager = ModelConfigManager("orcon")
        config = manager.get_model_config("Unknown Model")
        assert config["model_key"] == "unknown"
        assert "Unknown orcon model variant" in caplog.text

    def test_get_model_config_empty(self):
        """Test getting model config for empty model string."""
        manager = ModelConfigManager("orcon")
        assert manager.get_model_config("") is None

    def test_register_model_config(self):
        """Test registering new model config."""
        manager = ModelConfigManager("generic")
        custom_config = {"max_fan_speed": 5}
        manager.register_model_config("CustomModel", custom_config)
        assert "CustomModel" in manager.get_all_model_keys()

        config = manager.get_model_config("CustomModel")
        assert config["max_fan_speed"] == 5

    def test_has_model_config(self):
        """Test checking if model config exists."""
        manager = ModelConfigManager("orcon")
        assert manager.has_model_config("HRV200") is True
        # Unknown models return a fallback config, so has_model_config should
        #  still be True
        # unless it returns None. In current impl, it returns fallback config.
        assert manager.has_model_config("Unknown") is True

    def test_get_model_capabilities(self):
        """Test getting model capabilities."""
        manager = ModelConfigManager("orcon")
        caps = manager.get_model_capabilities("HRV300")
        assert caps["max_fan_speed"] == 3
        assert "auto" in caps["supported_modes"]
        assert caps["is_high_end"] is True

        # HRV200 is not high end
        caps_low = manager.get_model_capabilities("HRV200")
        assert caps_low["is_high_end"] is False

        # Non-existent
        manager_empty = ModelConfigManager("none")
        with patch.object(manager_empty, "get_model_config", return_value=None):
            assert manager_empty.get_model_capabilities("any") == {}

    def test_compare_models(self):
        """Test comparing two models."""
        manager = ModelConfigManager("orcon")
        comparison = manager.compare_models("HRV200", "HRV300")
        assert comparison["max_fan_speed"] == [2, 3]
        assert "mode_differences" in comparison
        assert "entity_differences" in comparison


class TestModelModuleFunctions:
    """Test top-level functions in models module."""

    def test_auto_detect_and_register_model(self):
        """Test auto detection and registration."""
        # Known brand
        config = auto_detect_and_register_model("Orcon HRV300")
        assert config["brand"] == "orcon"
        assert config["model_key"] == "HRV300"

        # Explicit brand
        config = auto_detect_and_register_model("HRV300", brand_name="orcon")
        assert config["brand"] == "orcon"

        # Fallback
        config = auto_detect_and_register_model("Unknown")
        assert config["brand"] == "generic"
        assert config["model_key"] == "unknown"

    def test_get_model_template(self):
        """Test getting model template."""
        template = get_model_template("HRV200", "orcon")
        assert template["max_fan_speed"] == 2

        # Non-existent
        template = get_model_template("NonExistent", "orcon")
        assert template["max_fan_speed"] == 3  # Default from GENERIC_CONFIG

    def test_validate_model_config(self):
        """Test validating model configuration."""
        valid_config = {
            "model_key": "K",
            "model_string": "S",
            "max_fan_speed": 3,
            "humidity_range": (30, 70),
        }
        assert validate_model_config(valid_config) is True

        # Missing fields
        assert validate_model_config({"model_key": "K"}) is False

        # Invalid numeric
        invalid_num = valid_config.copy()
        invalid_num["max_fan_speed"] = "invalid"
        assert validate_model_config(invalid_num) is False

        # Invalid range
        invalid_range = valid_config.copy()
        invalid_range["humidity_range"] = [1]
        assert validate_model_config(invalid_range) is False
