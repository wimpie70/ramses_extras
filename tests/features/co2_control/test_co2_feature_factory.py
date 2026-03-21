"""Tests for CO2 feature factory wiring."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.co2_control import (
    CO2ControlFeature,
    _get_co2_automation,
    async_create_co2_control_feature,
    create_co2_control_feature,
)


@pytest.mark.asyncio
async def test_create_co2_control_feature_wires_humidity_manager() -> None:
    """Factory should set humidity manager when present."""
    hass = MagicMock(spec=HomeAssistant)
    humidity_automation = MagicMock()
    hass.data = {
        "ramses_extras": {
            "features": {
                "humidity_control": {
                    "automation": humidity_automation,
                }
            }
        }
    }

    config_entry = MagicMock()
    config_entry.options = {"co2_control": {"automation_enabled": True}}

    with patch(
        "custom_components.ramses_extras.features.co2_control.C02AutomationManager",
        create=True,
    ):
        with patch(
            "custom_components.ramses_extras.features.co2_control.CO2AutomationManager"
        ) as mgr_cls:
            automation = MagicMock()
            mgr_cls.return_value = automation

            result = await create_co2_control_feature(hass, config_entry)

    assert result["automation"] is automation
    assert "platforms" in result
    automation.set_humidity_manager.assert_called_once_with(humidity_automation)
    humidity_automation.set_co2_manager.assert_called_once_with(automation)


@pytest.mark.asyncio
async def test_create_co2_control_feature_without_humidity_manager() -> None:
    """Factory should still create CO2 feature when humidity is absent."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {"ramses_extras": {"features": {}}}

    config_entry = MagicMock()
    config_entry.options = {"co2_control": {}}

    with patch(
        "custom_components.ramses_extras.features.co2_control.CO2AutomationManager"
    ) as mgr_cls:
        automation = MagicMock()
        mgr_cls.return_value = automation

        result = await create_co2_control_feature(hass, config_entry)

    assert result["automation"] is automation
    assert callable(result["platforms"]["switch"]["async_setup_entry"])
    automation.set_humidity_manager.assert_not_called()


@pytest.mark.asyncio
async def test_co2_control_feature_setup_and_unload() -> None:
    """CO2ControlFeature should validate config on setup and unload cleanly."""
    hass = MagicMock(spec=HomeAssistant)

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.CO2Config"
        ) as config_cls,
        patch("custom_components.ramses_extras.features.co2_control.CO2ZoneManager"),
    ):
        config = MagicMock()
        config.validate.return_value = (True, [])
        config_cls.return_value = config
        feature = CO2ControlFeature(hass, "32:123456", {"enabled": True})

        assert await feature.async_setup() is True
        assert await feature.async_unload() is True


@pytest.mark.asyncio
async def test_co2_control_feature_setup_validation_failure() -> None:
    """Invalid config should make CO2ControlFeature setup fail."""
    hass = MagicMock(spec=HomeAssistant)

    with (
        patch(
            "custom_components.ramses_extras.features.co2_control.CO2Config"
        ) as config_cls,
        patch("custom_components.ramses_extras.features.co2_control.CO2ZoneManager"),
    ):
        config = MagicMock()
        config.validate.return_value = (False, ["bad config"])
        config_cls.return_value = config
        feature = CO2ControlFeature(hass, "32:123456", {"enabled": True})

        assert await feature.async_setup() is False


@pytest.mark.asyncio
async def test_async_create_co2_control_feature_calls_setup() -> None:
    """Async feature factory should create and set up the feature instance."""
    hass = MagicMock(spec=HomeAssistant)

    with patch(
        "custom_components.ramses_extras.features.co2_control.CO2ControlFeature"
    ) as feature_cls:
        feature = MagicMock()
        feature.async_setup = AsyncMock(return_value=True)
        feature_cls.return_value = feature

        result = await async_create_co2_control_feature(
            hass,
            "32:123456",
            {"enabled": True},
        )

    feature.async_setup.assert_awaited_once()
    assert result is feature


def test_get_co2_automation_helper_returns_feature_automation() -> None:
    """Internal helper should return the CO2 automation when present."""
    automation = MagicMock()
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {
        "ramses_extras": {
            "features": {
                "co2_control": {"automation": automation},
            }
        }
    }

    assert _get_co2_automation(hass) is automation
    hass.data = {"ramses_extras": {"features": {"co2_control": None}}}
    assert _get_co2_automation(hass) is None
