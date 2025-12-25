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
    async_add_entities = MagicMock()

    # Mock device ready for entities
    mock_device = MagicMock()
    mock_device.id = "32_123456"

    with patch(
        "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
        return_value=[mock_device],
    ):
        # Call the function
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="number",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=entity_factory,
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
    async_add_entities = MagicMock()

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
        )

        # Verify no entities were added
        async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_create_and_add_platform_entities_filters_devices_for_feature(
    hass: HomeAssistant,
) -> None:
    """Ensure non-default features use filtered device list."""
    config_entry = MagicMock()
    entity_configs = {"entity": {"type": "sensor"}}
    async_add_entities = MagicMock()
    entity_factory = AsyncMock(return_value=[MagicMock()])

    with (
        patch(
            "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
            return_value=["32:153289", "18:149488"],
        ),
        patch.object(
            platform.PlatformSetup,
            "get_filtered_devices_for_feature",
            return_value=["32:153289"],
        ) as mock_filter,
    ):
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="sensor",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=entity_factory,
            feature_id="hello_world",
        )

    mock_filter.assert_called_once()
    entity_factory.assert_awaited_once()
    async_add_entities.assert_called_once()


@pytest.mark.asyncio
async def test_async_create_and_add_platform_entities_default_feature_no_filter(
    hass: HomeAssistant,
) -> None:
    """Ensure default feature skips filtering helper."""
    config_entry = MagicMock()
    entity_configs = {"entity": {"type": "sensor"}}
    async_add_entities = MagicMock()
    entity_factory = AsyncMock(return_value=[MagicMock()])

    with (
        patch(
            "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
            return_value=["32:153289", "18:149488"],
        ),
        patch.object(
            platform.PlatformSetup, "get_filtered_devices_for_feature"
        ) as mock_filter,
    ):
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="sensor",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=entity_factory,
            feature_id="default",
        )

    mock_filter.assert_not_called()
    assert entity_factory.await_count == 2
    async_add_entities.assert_called_once()


@pytest.mark.asyncio
async def test_async_create_and_add_platform_entities_factory_error(hass):
    """Test platform setup with entity factory error."""
    config_entry = MagicMock()
    entity_configs = {"entity1": {"type": "sensor"}}
    async_add_entities = MagicMock()

    async def failing_factory(hass, device_id, entity_configs, config_entry):
        raise Exception("Factory error")

    mock_device = MagicMock()
    mock_device.id = "32_123456"

    with patch(
        "custom_components.ramses_extras.framework.helpers.platform._get_devices_ready_for_entities",
        return_value=[mock_device],
    ):
        # Should not raise, but log error
        await platform.PlatformSetup.async_create_and_add_platform_entities(
            platform="sensor",
            hass=hass,
            config_entry=config_entry,
            async_add_entities=async_add_entities,
            entity_configs=entity_configs,
            entity_factory=failing_factory,
        )

        # Verify no entities were added due to error
        async_add_entities.assert_not_called()
