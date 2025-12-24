"""Tests for platform.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.helpers import platform


@pytest.mark.asyncio
async def test_async_create_and_add_platform_entities_success(hass):
    """Test successful creation and addition of platform entities."""
    # Mock config entry
    config_entry = MagicMock()

    # Mock entity configs
    entity_configs = {
        "entity1": {"type": "number", "name": "Test Entity"},
        "entity2": {"type": "switch", "name": "Test Switch"},
    }

    # Mock entity factory
    mock_entity1 = MagicMock()
    mock_entity2 = MagicMock()

    async def entity_factory(hass, device_id, entity_configs, config_entry):
        entities = []
        for entity_name in entity_configs:
            if entity_name == "entity1":
                entities.append(mock_entity1)
            elif entity_name == "entity2":
                entities.append(mock_entity2)
        return entities

    # Mock async_add_entities
    async_add_entities = AsyncMock()

    # Mock device ready for entities
    mock_device = MagicMock()
    mock_device.id = "32_123456"

    with (
        patch(
            "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
            return_value=[mock_device],
        ),
        patch(
            "custom_components.ramses_extras.framework.helpers.platform._get_required_entities_from_feature",
            return_value=entity_configs,
        ),
    ):
        # Call the function
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="number",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=entity_factory,
            feature_id="test_feature",
            store_entities_for_automation=True,
        )

        # Verify entities were added
        async_add_entities.assert_called_once()
        args = async_add_entities.call_args[0][0]
        assert len(args) == 2  # Two entities created


@pytest.mark.asyncio
async def test_async_create_and_add_platform_entities_no_devices(hass):
    """Test platform setup with no devices ready."""
    config_entry = MagicMock()
    entity_configs = {}
    entity_factory = MagicMock(return_value=[])
    async_add_entities = AsyncMock()

    with patch(
        "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
        return_value=[],
    ):
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="sensor",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=entity_factory,
            feature_id="test_feature",
        )

        # Verify no entities were added
        async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_create_and_add_platform_entities_factory_error(hass):
    """Test platform setup with entity factory error."""
    config_entry = MagicMock()
    entity_configs = {"entity1": {"type": "sensor"}}
    async_add_entities = AsyncMock()

    async def failing_factory(hass, device_id, entity_configs, config_entry):
        raise Exception("Factory error")

    mock_device = MagicMock()
    mock_device.id = "32_123456"

    with (
        patch(
            "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
            return_value=[mock_device],
        ),
        patch(
            "custom_components.ramses_extras.framework.helpers.platform._get_required_entities_from_feature",
            return_value=entity_configs,
        ),
    ):
        # Should not raise, but log error
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="sensor",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=failing_factory,
            feature_id="test_feature",
        )

        # Verify no entities were added due to error
        async_add_entities.assert_not_called()
