"""Tests for humidity brand customizers and enhanced feature paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control import (
    EnhancedHumidityControl,
    OrconDeviceCustomizer,
    ZehnderDeviceCustomizer,
    is_orcon_device,
    is_zehnder_device,
)


@pytest.fixture
def hass() -> MagicMock:
    """Mock Home Assistant."""
    mock_hass = MagicMock(spec=HomeAssistant)
    mock_hass.data = {}
    return mock_hass


@pytest.fixture
def config_entry() -> MagicMock:
    """Mock config entry."""
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    return entry


def test_orcon_customizer_extract_model_info(hass) -> None:
    """Orcon model extraction should handle known, unknown, and empty models."""
    customizer = OrconDeviceCustomizer(hass)

    known = customizer._extract_orcon_model_info("Orcon Hrv400")
    unknown = customizer._extract_orcon_model_info("Mystery Fan")

    assert known is not None
    assert known["model_key"] == "HRV400"
    assert unknown is not None
    assert unknown["model_key"] == "unknown"
    assert customizer._extract_orcon_model_info("") is None


@pytest.mark.asyncio
async def test_orcon_customize_device_populates_event_data(hass) -> None:
    """Orcon customizer should enrich entity, config, and default data."""
    customizer = OrconDeviceCustomizer(hass)
    device = MagicMock()
    device.id = "32_123456"
    device.model = "Orcon HRV400"
    event_data = {"device_id": "32_123456", "entity_ids": []}

    result = await customizer.customize_orcon_device(device, event_data)

    assert result["model_config"]["model_key"] == "HRV400"
    assert "sensor.orcon_filter_usage_32_123456" in result["entity_ids"]
    assert "number.orcon_filter_timer_32_123456" in result["entity_ids"]
    assert "switch.orcon_eco_mode_32_123456" in result["entity_ids"]
    assert result["orcon_config"]["fan_speed_levels"] == [1, 2, 3, 4, 5]
    assert result["orcon_defaults"]["target_humidity"] == 55
    assert (
        result["default_enabled_entities"]["sensor.orcon_air_quality_index_32_123456"]
        is True
    )


@pytest.mark.asyncio
async def test_orcon_customize_unknown_model_returns_original_event_data(hass) -> None:
    """Unknown Orcon models should leave the event data unchanged."""
    customizer = OrconDeviceCustomizer(hass)
    device = MagicMock()
    device.id = "32_000000"
    device.model = ""
    event_data = {"device_id": "32_000000", "entity_ids": []}

    result = await customizer.customize_orcon_device(device, event_data)

    assert result is event_data
    assert result["entity_ids"] == []


@pytest.mark.asyncio
async def test_zehnder_customize_device_populates_event_data(hass) -> None:
    """Zehnder customizer should enrich entity, config, and default data."""
    customizer = ZehnderDeviceCustomizer(hass)
    device = MagicMock()
    device.id = "32_654321"
    device.model = "Zehnder ComfoAir Q450"
    event_data = {"device_id": "32_654321", "entity_ids": []}

    result = await customizer.customize_zehnder_device(device, event_data)

    assert result["model_config"]["model_key"] == "ComfoAir Q450"
    assert "sensor.zehnder_filter_usage_32_654321" in result["entity_ids"]
    assert "sensor.zehnder_co2_level_32_654321" in result["entity_ids"]
    assert "switch.zehnder_away_mode_32_654321" in result["entity_ids"]
    assert result["zehnder_config"]["fan_speed_levels"] == [1, 2, 3, 4, 5]
    assert result["zehnder_defaults"]["target_humidity"] == 52
    assert (
        result["default_enabled_entities"]["sensor.zehnder_co2_level_32_654321"] is True
    )


def test_brand_detection_helpers() -> None:
    """Brand detection helpers should recognize known strings."""
    assert is_orcon_device(MagicMock(model="Orcon HRC-300")) is True
    assert is_orcon_device(MagicMock(model="Soler & Palau unit")) is True
    assert is_orcon_device(MagicMock(model=None)) is False
    assert is_zehnder_device(MagicMock(model="Zehnder ComfoAir")) is True
    assert is_zehnder_device(MagicMock(model="ComfoAir Q350")) is True
    assert is_zehnder_device(MagicMock(model=None)) is False


def test_zehnder_customizer_extract_model_info_edge_cases(hass) -> None:
    """Zehnder model extraction should handle known, unknown, and empty models."""
    customizer = ZehnderDeviceCustomizer(hass)

    known = customizer._extract_zehnder_model_info("Zehnder ComfoAir Q350")
    unknown = customizer._extract_zehnder_model_info("Unknown Model")

    assert known is not None
    assert known["model_key"] == "ComfoAir Q350"
    assert unknown is not None
    assert unknown["model_key"] == "unknown"
    assert customizer._extract_zehnder_model_info("") is None


@pytest.mark.asyncio
async def test_zehnder_customize_unknown_model_returns_original_event_data(
    hass,
) -> None:
    """Unknown Zehnder models should leave the event data unchanged."""
    customizer = ZehnderDeviceCustomizer(hass)
    device = MagicMock()
    device.id = "32_000001"
    device.model = ""
    event_data = {"device_id": "32_000001", "entity_ids": []}

    result = await customizer.customize_zehnder_device(device, event_data)

    assert result is event_data
    assert result["entity_ids"] == []


@pytest.fixture
def enhanced_feature(hass, config_entry) -> EnhancedHumidityControl:
    """Enhanced humidity control instance with patched dependencies."""
    with (
        patch(
            "custom_components.ramses_extras.features.humidity_control.HumidityEntities"
        ),
        patch(
            "custom_components.ramses_extras.features.humidity_control.HumidityAutomationManager"
        ) as automation_cls,
        patch(
            "custom_components.ramses_extras.features.humidity_control.HumidityConfig"
        ),
    ):
        automation = MagicMock()
        automation.start = AsyncMock()
        automation_cls.return_value = automation
        feature = EnhancedHumidityControl(hass, config_entry)
        feature.automation = automation
        return feature


@pytest.mark.asyncio
async def test_enhanced_feature_apply_customizations_and_accessors(
    enhanced_feature: EnhancedHumidityControl,
) -> None:
    """Enhanced feature should store per-brand customization metadata."""
    generic_device = MagicMock(id="dev_generic")
    generic_event = {"device_object": generic_device, "entity_ids": []}
    await enhanced_feature._apply_humidity_customizations(generic_event, "generic")

    orcon_device = MagicMock(id="dev_orcon")
    orcon_event = {"device_object": orcon_device, "entity_ids": []}
    await enhanced_feature._apply_humidity_customizations(orcon_event, "orcon")

    zehnder_device = MagicMock(id="dev_zehnder")
    zehnder_event = {"device_object": zehnder_device, "entity_ids": []}
    await enhanced_feature._apply_humidity_customizations(zehnder_event, "zehnder")

    assert (
        "sensor.generic_humidity_efficiency_dev_generic" in generic_event["entity_ids"]
    )
    assert "switch.orcon_smart_humidity_dev_orcon" in orcon_event["entity_ids"]
    assert (
        "sensor.zehnder_co2_humidity_correlation_dev_zehnder"
        in zehnder_event["entity_ids"]
    )
    assert enhanced_feature.should_create_entity("dev_orcon", "entity.test") is True
    assert enhanced_feature.get_brand_info("dev_orcon")["target_humidity"] == 55
    assert (
        enhanced_feature.get_entity_customizations("dev_zehnder")["brand"] == "zehnder"
    )


@pytest.mark.asyncio
async def test_enhanced_feature_routes_ready_events(enhanced_feature) -> None:
    """Ready events should route to the correct brand handler."""
    enhanced_feature._handle_orcon_device = AsyncMock()
    enhanced_feature._handle_zehnder_device = AsyncMock()
    enhanced_feature._handle_generic_device = AsyncMock()

    orcon_event = {
        "handled_by": "humidity_control",
        "device_id": "dev1",
        "device_object": MagicMock(id="dev1", model="Orcon HRV300"),
    }
    await enhanced_feature._on_device_ready_for_entities(orcon_event)
    enhanced_feature._handle_orcon_device.assert_awaited_once_with(orcon_event)

    zehnder_event = {
        "handled_by": "humidity_control",
        "device_id": "dev2",
        "device_object": MagicMock(id="dev2", model="ComfoAir Q350"),
    }
    await enhanced_feature._on_device_ready_for_entities(zehnder_event)
    enhanced_feature._handle_zehnder_device.assert_awaited_once_with(zehnder_event)

    generic_event = {
        "handled_by": "humidity_control",
        "device_id": "dev3",
        "device_object": MagicMock(id="dev3", model="Plain Fan"),
    }
    await enhanced_feature._on_device_ready_for_entities(generic_event)
    enhanced_feature._handle_generic_device.assert_awaited_once_with(generic_event)

    ignored_event = {
        "handled_by": "other_feature",
        "device_id": "dev4",
        "device_object": MagicMock(id="dev4", model="Orcon HRV300"),
    }
    await enhanced_feature._on_device_ready_for_entities(ignored_event)
    assert enhanced_feature._handle_orcon_device.await_count == 1


@pytest.mark.asyncio
async def test_enhanced_feature_logs_processing_errors(enhanced_feature) -> None:
    """Device-processing errors should be caught by the ready-event handler."""
    enhanced_feature._handle_generic_device = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    event = {
        "handled_by": "humidity_control",
        "device_id": "dev_error",
        "device_object": MagicMock(id="dev_error", model="Plain Fan"),
    }

    await enhanced_feature._on_device_ready_for_entities(event)
    enhanced_feature._handle_generic_device.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_enhanced_feature_setup_cleanup_and_error_paths(
    enhanced_feature: EnhancedHumidityControl,
) -> None:
    """Setup, cleanup, and error handling should behave predictably."""
    enhanced_feature._setup_event_listeners = AsyncMock()
    assert await enhanced_feature.async_setup() is True
    enhanced_feature._setup_event_listeners.assert_awaited_once()
    enhanced_feature.automation.start.assert_awaited_once()

    enhanced_feature._entity_modifications["dev1"] = {"brand": "generic"}
    await enhanced_feature.async_cleanup()
    assert enhanced_feature._entity_modifications == {}

    enhanced_feature._setup_event_listeners = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    assert await enhanced_feature.async_setup() is False


@pytest.mark.asyncio
async def test_enhanced_feature_device_handler_methods(enhanced_feature) -> None:
    """Device-specific handlers should call the expected customizer/apply paths."""
    event_data = {
        "device_object": MagicMock(id="dev_orcon", model="Orcon HRV300"),
        "entity_ids": [],
    }
    orcon_customizer = MagicMock()
    orcon_customizer.customize_orcon_device = AsyncMock()
    zehnder_customizer = MagicMock()
    zehnder_customizer.customize_zehnder_device = AsyncMock()
    enhanced_feature._brand_customizers = {
        "orcon": orcon_customizer,
        "zehnder": zehnder_customizer,
    }
    enhanced_feature._apply_humidity_customizations = AsyncMock()

    await enhanced_feature._handle_orcon_device(event_data)
    orcon_customizer.customize_orcon_device.assert_awaited_once_with(
        event_data["device_object"], event_data
    )
    enhanced_feature._apply_humidity_customizations.assert_awaited_once_with(
        event_data, "orcon"
    )

    enhanced_feature._apply_humidity_customizations.reset_mock()
    zehnder_event = {
        "device_object": MagicMock(id="dev_zehnder", model="ComfoAir Q350"),
        "entity_ids": [],
    }
    await enhanced_feature._handle_zehnder_device(zehnder_event)
    zehnder_customizer.customize_zehnder_device.assert_awaited_once_with(
        zehnder_event["device_object"], zehnder_event
    )
    enhanced_feature._apply_humidity_customizations.assert_awaited_once_with(
        zehnder_event, "zehnder"
    )

    enhanced_feature._apply_humidity_customizations.reset_mock()
    generic_event = {
        "device_object": MagicMock(id="dev_generic", model="Any"),
        "entity_ids": [],
    }
    await enhanced_feature._handle_generic_device(generic_event)
    enhanced_feature._apply_humidity_customizations.assert_awaited_once_with(
        generic_event, "generic"
    )
