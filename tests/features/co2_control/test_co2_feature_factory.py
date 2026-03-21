"""Tests for CO2 feature factory wiring."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.co2_control import (
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
