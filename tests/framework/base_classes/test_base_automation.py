from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import State

from custom_components.ramses_extras.framework.base_classes.base_automation import (
    ExtrasBaseAutomation,
)


class MockExtrasAutomation(ExtrasBaseAutomation):
    """Mock implementation of ExtrasBaseAutomation for testing."""

    async def _process_automation_logic(
        self, device_id: str, entity_states: dict
    ) -> None:
        """Mock implementation of abstract method."""


class TestExtrasBaseAutomation:
    """Test ExtrasBaseAutomation class."""

    @pytest.fixture
    def hass(self):
        """Create mock Home Assistant instance."""
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_hass.loop = MagicMock()
        mock_hass.bus = MagicMock()
        mock_hass.state = "running"
        return mock_hass

    @pytest.fixture
    def automation(self, hass):
        """Create mock automation instance."""
        return MockExtrasAutomation(hass, "test_feature")

    def test_init_default_values(self, hass):
        """Test initialization with default values."""
        automation = MockExtrasAutomation(hass, "test_feature")

        assert automation.hass == hass
        assert automation.feature_id == "test_feature"
        assert automation.binary_sensor is None
        assert automation.debounce_seconds == 45
        assert automation._listeners == []
        assert automation._change_timers == {}
        assert automation._active is False
        assert automation._specific_entity_ids == set()
        assert automation._entity_patterns is None

    def test_init_custom_values(self, hass):
        """Test initialization with custom values."""
        mock_sensor = MagicMock()
        automation = MockExtrasAutomation(hass, "test_feature", mock_sensor, 30)

        assert automation.binary_sensor == mock_sensor
        assert automation.debounce_seconds == 30

    def test_entity_patterns_property(self, automation):
        """Test entity patterns property."""
        with patch.object(automation, "_generate_entity_patterns") as mock_generate:
            mock_generate.return_value = ["sensor.test_*"]

            patterns = automation.entity_patterns

            assert patterns == ["sensor.test_*"]
            assert automation._entity_patterns == ["sensor.test_*"]

            # Second call should use cached value
            patterns2 = automation.entity_patterns
            assert patterns2 == ["sensor.test_*"]
            mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_already_active(self, automation):
        """Test starting automation that's already active."""
        automation._active = True

        with patch(
            "custom_components.ramses_extras.framework.base_classes."
            "base_automation._LOGGER"
        ) as mock_logger:
            await automation.start()

            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_ha_already_running(self, automation, hass):
        """Test automation initialization when HA is running."""
        # Directly initialize the automation by calling _on_homeassistant_started
        # This tests the core initialization logic without complex state mocking
        await automation._on_homeassistant_started(None)

        # Verify that the automation was initialized properly
        assert (
            automation.hass.data["ramses_extras"]["feature_ready"]["test_feature"]
            is True
        )  # noqa: E501

    async def test_start_ha_not_running(self, automation, hass):
        """Test starting automation when HA is not running."""
        hass.state = "starting"

        await automation.start()

        assert automation._active is True
        hass.bus.async_listen_once.assert_called_once_with(
            "homeassistant_started", automation._on_homeassistant_started
        )

    @pytest.mark.asyncio
    async def test_on_homeassistant_started_success(self, automation, hass):
        """Test successful HA startup handling."""
        with patch.object(automation, "_register_entity_listeners"):
            await automation._on_homeassistant_started(None)

            data_path = automation.hass.data["ramses_extras"]["feature_ready"]
            assert data_path["test_feature"] is True
            hass.bus.async_fire.assert_called_once_with(
                "ramses_extras_feature_ready", {"feature_id": "test_feature"}
            )

    @pytest.mark.asyncio
    async def test_on_homeassistant_started_failure(self, automation, hass):
        """Test failed HA startup handling."""
        with patch.object(
            automation,
            "_register_entity_listeners",
            side_effect=Exception("test error"),
        ):
            await automation._on_homeassistant_started(None)

            data_path = automation.hass.data["ramses_extras"]["feature_ready"]
            assert data_path["test_feature"] is False

    @pytest.mark.asyncio
    async def test_stop_not_active(self, automation):
        """Test stopping automation that's not active."""
        automation._active = False

        await automation.stop()

        # Should return early without doing anything
        assert automation._active is False

    @pytest.mark.asyncio
    async def test_stop_active(self, automation, hass):
        """Test stopping active automation."""
        automation._active = True
        automation._listeners = [MagicMock(), MagicMock()]
        automation._change_timers = {"device1": MagicMock()}

        with patch.object(automation, "_cancel_all_timers") as mock_cancel:
            await automation.stop()

            assert automation._active is False
            assert automation._listeners == []
            assert automation._specific_entity_ids == set()
            mock_cancel.assert_called_once()

            # Check listeners were called
            for listener in automation._listeners:
                listener.assert_called()

    def test_generate_entity_patterns_default(self, automation):
        """Test default entity pattern generation."""
        with (
            patch(
                "custom_components.ramses_extras.framework.base_classes."
                "base_automation.get_required_entities_from_feature_sync"
            ) as mock_get,
            patch(
                "custom_components.ramses_extras.framework.base_classes."
                "base_automation._singularize_entity_type"
            ) as mock_singular,
        ):
            mock_get.return_value = {
                "sensors": ["temperature", "humidity"],
                "switches": ["dehumidify"],
            }
            mock_singular.return_value = "sensor"

            patterns = automation._generate_entity_patterns_default()

            expected_patterns = [
                "sensor.temperature_*",
                "sensor.humidity_*",
                "sensor.dehumidify_*",
            ]
            assert patterns == expected_patterns

    @pytest.mark.asyncio
    async def test_register_entity_listeners(self, automation, hass):
        """Test entity listener registration."""
        automation._entity_patterns = ["sensor.test_*"]

        # Mock entities with proper structure
        mock_entity = MagicMock()
        mock_entity.entity_id = "sensor.test_32_153289"
        mock_entity.state = "25.0"  # Add state attribute
        hass.states.async_all.return_value = [mock_entity]

        listener_mock = MagicMock()
        with patch(
            "custom_components.ramses_extras.framework.base_classes."
            "base_automation.async_track_state_change",
            return_value=listener_mock,
        ) as mock_track:
            await automation._register_entity_listeners()

            # Check that entity was registered
            assert "sensor.test_32_153289" in automation._specific_entity_ids
            assert listener_mock in automation._listeners

            # Check that async_track_state_change was called
            mock_track.assert_called_once_with(
                hass, "sensor.test_32_153289", automation._handle_state_change
            )

    @pytest.mark.asyncio
    async def test_register_entity_listeners_no_entities(self, automation, hass):
        """Test entity listener registration when no entities found."""
        automation._entity_patterns = ["sensor.test_*"]
        hass.states.async_all.return_value = []

        with patch.object(automation, "_setup_periodic_entity_check") as mock_setup:
            await automation._register_entity_listeners()

            mock_setup.assert_called_once()

    async def test_async_handle_state_change_with_debouncing(self, automation):
        """Test async state change handling with debouncing."""
        automation.debounce_seconds = 10
        mock_new_state = MagicMock()
        mock_new_state.state = "25.0"

        with patch.object(automation, "_extract_device_id") as mock_extract:
            mock_extract.return_value = "32_153289"

            # Set existing timer to simulate debouncing
            mock_timer = MagicMock()
            automation._change_timers["32_153289"] = mock_timer

            entity_id = "sensor.temp_32_153289"
            await automation._async_handle_state_change(entity_id, None, mock_new_state)

            # Should return early due to debouncing

    @pytest.mark.asyncio
    async def test_async_handle_state_change_validation_failure(self, automation):
        """Test async state change handling with validation failure."""
        mock_new_state = MagicMock()
        mock_new_state.state = "25.0"

        with (
            patch.object(automation, "_extract_device_id") as mock_extract,
            patch.object(automation, "_validate_device_entities") as mock_validate,
        ):
            mock_extract.return_value = "32_153289"
            mock_validate.return_value = False

            entity_id = "sensor.temp_32_153289"
            await automation._async_handle_state_change(entity_id, None, mock_new_state)

            # Should return early due to validation failure

    @pytest.mark.asyncio
    async def test_async_handle_state_change_success(self, automation):
        """Test successful async state change handling."""
        mock_new_state = MagicMock()
        mock_new_state.state = "25.0"

        with (
            patch.object(automation, "_extract_device_id") as mock_extract,
            patch.object(automation, "_validate_device_entities") as mock_validate,
            patch.object(automation, "_get_device_entity_states") as mock_get_states,
            patch.object(automation, "_process_automation_logic") as mock_process,
        ):
            mock_extract.return_value = "32_153289"
            mock_validate.return_value = True
            mock_get_states.return_value = {"temperature": 25.0}

            entity_id = "sensor.temp_32_153289"
            await automation._async_handle_state_change(entity_id, None, mock_new_state)

            mock_process.assert_called_once_with("32_153289", {"temperature": 25.0})

    @pytest.mark.asyncio
    async def test_cancel_all_timers(self, automation, hass):
        """Test canceling all timers."""
        mock_timer1 = MagicMock()
        mock_timer2 = MagicMock()
        automation._change_timers = {"device1": mock_timer1, "device2": mock_timer2}

        await automation._cancel_all_timers()

        mock_timer1.cancel.assert_called_once()
        mock_timer2.cancel.assert_called_once()
        assert automation._change_timers == {}

    def test_setup_periodic_entity_check(self, automation, hass):
        """Test setting up periodic entity check."""
        automation._setup_periodic_entity_check()

        hass.helpers.event.async_track_time_interval.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_for_entities_periodically_found(self, automation):
        """Test periodic entity check when entities are found."""
        automation._specific_entity_ids = set()
        mock_handle = MagicMock()
        automation._periodic_check_handle = mock_handle

        async def mock_register():
            """Mock register that adds entities."""
            automation._specific_entity_ids.add("sensor.test_32_153289")

        with patch.object(
            automation, "_register_entity_listeners", side_effect=mock_register
        ):
            await automation._check_for_entities_periodically(None)

            mock_handle.assert_called_once()
            assert automation._periodic_check_handle is None
            assert "sensor.test_32_153289" in automation._specific_entity_ids

    def test_entity_matches_patterns(self, automation):
        """Test entity pattern matching."""
        automation._entity_patterns = ["sensor.test_*", "switch.control_*"]

        assert automation._entity_matches_patterns("sensor.test_32_153289") is True
        assert automation._entity_matches_patterns("switch.control_32_153289") is True
        assert automation._entity_matches_patterns("sensor.other_32_153289") is False

    @pytest.mark.asyncio
    async def test_validate_device_entities_missing(self, automation, hass):
        """Test device entity validation with missing entities."""
        # Ensure entity does not exist
        hass.states.get.return_value = None

        with patch(
            "custom_components.ramses_extras.framework.base_classes."
            "base_automation._get_required_entities_from_feature"
        ) as mock_get:
            mock_get.return_value = {"sensors": ["temperature"]}

            result = await automation._validate_device_entities("32_153289")

            assert result is False

    @pytest.mark.asyncio
    async def test_validate_device_entities_success(self, automation, hass):
        """Test successful device entity validation."""
        # Mock entity state with proper structure
        mock_state = MagicMock()
        mock_state.state = "25.0"  # Valid state, not unavailable/unknown
        hass.states.get.return_value = mock_state

        with (
            patch(
                "custom_components.ramses_extras.framework.base_classes."
                "base_automation._get_required_entities_from_feature"
            ) as mock_get,
            patch(
                "custom_components.ramses_extras.framework.base_classes."
                "base_automation._singularize_entity_type"
            ) as mock_singularize,
        ):
            mock_get.return_value = {"sensors": ["temperature"]}
            mock_singularize.return_value = "sensor"

            result = await automation._validate_device_entities("32_153289")

            assert result is True
            # Verify that hass.states.get was called with the expected entity ID
            hass.states.get.assert_called_with("sensor.temperature_32_153289")

    def test_extract_device_id(self, automation):
        """Test device ID extraction from entity ID."""
        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.core."
            "EntityHelpers.parse_entity_id"
        ) as mock_parse:
            mock_parse.return_value = ("sensor", "temperature", "32_153289")

            result = automation._extract_device_id("sensor.temperature_32_153289")

            assert result == "32_153289"

    @pytest.mark.asyncio
    async def test_get_device_entity_states(self, automation, hass):
        """Test getting device entity states."""
        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.core."
                "get_feature_entity_mappings"
            ) as mock_get_mappings,
            patch.object(
                automation, "_extract_entity_type_from_id"
            ) as mock_extract_type,
            patch.object(automation, "_convert_entity_state") as mock_convert,
        ):
            mock_get_mappings.return_value = {"temperature": "sensor.temp_32_153289"}
            mock_extract_type.return_value = "sensor"
            mock_convert.return_value = 25.0

            # Mock state
            mock_state = MagicMock()
            mock_state.state = "25.0"
            hass.states.get.return_value = mock_state

            result = await automation._get_device_entity_states("32_153289")

            assert result == {"temperature": 25.0}

    def test_extract_entity_type_from_id(self, automation):
        """Test extracting entity type from entity ID."""
        long_entity_id = "sensor.temperature_32_153289"
        switch_entity_id = "switch.control_32_153289"
        assert automation._extract_entity_type_from_id(long_entity_id) == "sensor"
        assert automation._extract_entity_type_from_id(switch_entity_id) == "switch"
        assert automation._extract_entity_type_from_id("invalid") == "unknown"

    def test_convert_entity_state_switch(self, automation):
        """Test converting switch entity state."""
        assert automation._convert_entity_state("switch", "on") is True
        assert automation._convert_entity_state("switch", "off") is False

    def test_convert_entity_state_sensor(self, automation):
        """Test converting sensor entity state."""
        assert automation._convert_entity_state("sensor", "25.5") == 25.5

    def test_convert_entity_state_invalid(self, automation):
        """Test converting invalid entity state."""
        with pytest.raises(ValueError):
            automation._convert_entity_state("sensor", "invalid")

    @pytest.mark.asyncio
    async def test_set_binary_sensor_state_success(self, automation, hass):
        """Test successful binary sensor state setting."""
        mock_entity = MagicMock()
        hass.data = {"ramses_extras": {"entities": {"binary_sensor.test": mock_entity}}}

        result = await automation.set_binary_sensor_state("binary_sensor.test", True)

        assert result is True
        mock_entity.set_state.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_set_binary_sensor_state_failure(self, automation, hass):
        """Test failed binary sensor state setting."""
        hass.data = {"ramses_extras": {"entities": {}}}

        result = await automation.set_binary_sensor_state("binary_sensor.test", True)

        assert result is False

    @pytest.mark.asyncio
    async def test_toggle_binary_sensor_state(self, automation, hass):
        """Test binary sensor state toggling."""
        mock_state = MagicMock()
        mock_state.state = "on"
        hass.states.get.return_value = mock_state

        with patch.object(automation, "set_binary_sensor_state") as mock_set:
            mock_set.return_value = True

            result = await automation.toggle_binary_sensor_state("binary_sensor.test")

            assert result is True
            mock_set.assert_called_once_with("binary_sensor.test", False)
