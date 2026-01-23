# Tests for hello_world feature

from unittest.mock import MagicMock

import pytest

from custom_components.ramses_extras.features.hello_world import (
    create_hello_world_feature,
)


@pytest.mark.asyncio
async def test_create_hello_world_feature(hass) -> None:
    """Test creating hello world feature."""
    hass.data.setdefault("ramses_extras", {})

    config_entry = MagicMock()
    config_entry.entry_id = "test"

    feature = create_hello_world_feature(hass, config_entry)

    assert "entities" in feature
    assert "automation" in feature
    assert "platforms" in feature
    assert "feature_name" in feature
    assert feature["feature_name"] == "hello_world"

    # Check platforms
    assert "switch" in feature["platforms"]
    assert "binary_sensor" in feature["platforms"]
    assert "sensor" in feature["platforms"]
