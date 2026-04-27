"""Tests for extras_registry module."""

from custom_components.ramses_extras.extras_registry import extras_registry


def test_register_card_config_missing_card_id():
    """Test register_card_config with missing card_id (covers lines 78-82)."""
    # Clear registry first
    extras_registry.clear()

    card_config = {"name": "test_card"}  # Missing card_id

    extras_registry.register_card_config("test_feature", card_config)

    # Should not register the card
    card = extras_registry.get_card_config("test_feature")
    assert card is None


def test_load_feature_definitions_already_loaded():
    """Test load_feature_definitions when feature already loaded (covers lines 111-112)."""  # noqa: E501
    # Clear registry first
    extras_registry.clear()

    # Load default feature
    extras_registry.load_feature_definitions(
        "default", "custom_components.ramses_extras.features.default"
    )

    # Try to load again - should skip
    extras_registry.load_feature_definitions(
        "default", "custom_components.ramses_extras.features.default"
    )

    # Should still work
    loaded_features = extras_registry.get_loaded_features()
    assert "default" in loaded_features


def test_register_card_config_with_card_id():
    """Test register_card_config with valid card_id (covers line 340)."""
    # Clear registry first
    extras_registry.clear()

    card_config = {"card_id": "test_card", "name": "Test Card"}

    extras_registry.register_card_config("test_feature", card_config)

    # Should register the card
    card = extras_registry.get_card_config("test_feature", "test_card")
    assert card is not None
    assert card["card_id"] == "test_card"


def test_register_device_mappings_merge():
    """Test register_device_mappings with merging (covers lines 168-169, 171-172)."""
    # Clear registry first
    extras_registry.clear()

    # First registration
    mappings1 = {
        "FAN": {
            "sensor": ["sensor1", "sensor2"],
        }
    }
    extras_registry.register_device_mappings(mappings1)

    # Second registration with new entities
    mappings2 = {
        "FAN": {
            "sensor": ["sensor3"],
            "switch": ["switch1"],
        }
    }
    extras_registry.register_device_mappings(mappings2)

    # Check merged result
    all_mappings = extras_registry.get_all_device_mappings()
    assert "FAN" in all_mappings
    assert "sensor3" in all_mappings["FAN"]["sensor"]
    assert "switch1" in all_mappings["FAN"]["switch"]


def test_clear_all():
    """Test clear_all method."""
    # Clear registry first
    extras_registry.clear()

    # Add some data
    extras_registry.register_sensor_configs({"sensor1": {"name": "Sensor 1"}})
    extras_registry.register_feature("test_feature")

    # Clear all
    extras_registry.clear_all()

    # Verify cleared
    assert len(extras_registry.get_all_sensor_configs()) == 0
    assert len(extras_registry.get_loaded_features()) == 0


def test_get_features_with_websocket_commands():
    """Test get_features_with_websocket_commands."""
    # Clear registry first
    extras_registry.clear()

    # Register websocket commands
    extras_registry.register_websocket_commands("feature1", {"cmd1": "desc1"})
    extras_registry.register_websocket_commands("feature2", {})

    features = extras_registry.get_features_with_websocket_commands()

    assert "feature1" in features
    assert "feature2" not in features  # Empty commands
