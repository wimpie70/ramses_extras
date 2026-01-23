# Tests for humidity_control feature

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.features.humidity_control import (
    create_humidity_control_feature,
)


@pytest.mark.asyncio
async def test_create_humidity_control_feature(hass) -> None:
    """Test creating humidity control feature."""
    hass.data.setdefault("ramses_extras", {})

    config_entry = MagicMock()
    config_entry.entry_id = "test"

    feature = await create_humidity_control_feature(hass, config_entry)

    assert "automation" in feature
    assert "entities" in feature
    assert "services" in feature
    assert "config" in feature
    assert "enhanced" in feature
    assert "platforms" in feature

    # Check platforms
    assert "sensor" in feature["platforms"]
    assert "binary_sensor" in feature["platforms"]
    assert "switch" in feature["platforms"]
    assert "number" in feature["platforms"]
