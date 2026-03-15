"""Tests for Humidity Control Platforms and Entities."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.features.humidity_control.platforms import (
    binary_sensor as humidity_binary_sensor_platform,
)
from custom_components.ramses_extras.features.humidity_control.platforms import (
    number as humidity_number_platform,
)
from custom_components.ramses_extras.features.humidity_control.platforms import (
    sensor as humidity_sensor_platform,
)
from custom_components.ramses_extras.features.humidity_control.platforms import (
    switch as humidity_switch_platform,
)


class TestHumidityPlatforms:
    """Test cases for humidity control platform entities."""

    def setup_method(self):
        """Set up test fixtures."""
        self.hass = MagicMock(spec=HomeAssistant)
        # Mock Home Assistant integrations data to prevent loader KeyError
        self.hass.data = {"integrations": {}}
        # Mock states
        self.hass.states = MagicMock()
        # Mock thread ID for async_write_ha_state
        import threading

        self.hass.loop_thread_id = threading.get_ident()
        self.hass.bus = MagicMock()
        self.hass.config_entries = MagicMock()

        self.config_entry = MagicMock(spec=ConfigEntry)
        self.config_entry.options = {}
        self.config_entry.data = {}
        self.device_id = "32_123456"

    async def test_humidity_switch(self):
        """Test HumidityControlSwitch."""
        config = {
            "name": "Balance",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidify_{device_id}",
        }
        entity = humidity_switch_platform.HumidityControlSwitch(
            self.hass, self.device_id, "dehumidify", config
        )

        # Manually set internal state since we're testing the logic
        entity._is_on = False

        assert entity.is_on is False
        assert entity.extra_state_attributes["dehumidifying"] is False

        await entity.async_turn_on()
        assert entity.is_on is True

        await entity.async_turn_off()
        assert entity.is_on is False

    async def test_create_humidity_switch(self):
        """Test create_humidity_switch factory."""
        switches = await humidity_switch_platform.create_humidity_switch(
            self.hass, self.device_id, self.config_entry
        )
        assert len(switches) == 1
        assert isinstance(switches[0], humidity_switch_platform.HumidityControlSwitch)

    async def test_humidity_switch_restores_last_state(self):
        """Test HumidityControlSwitch restores its last persisted state."""
        config = {
            "name": "Balance",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidify_{device_id}",
        }
        entity = humidity_switch_platform.HumidityControlSwitch(
            self.hass, self.device_id, "dehumidify", config
        )

        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.platforms.switch.ExtrasSwitchEntity.async_added_to_hass",
                new=AsyncMock(),
            ),
            patch.object(
                entity,
                "async_get_last_state",
                new=AsyncMock(return_value=MagicMock(state=STATE_ON)),
            ),
        ):
            await entity.async_added_to_hass()

        assert entity.is_on is True

    async def test_humidity_switch_restores_default_without_last_state(self):
        """Test HumidityControlSwitch keeps default state without persisted state."""
        config = {
            "name": "Balance",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidify_{device_id}",
        }
        entity = humidity_switch_platform.HumidityControlSwitch(
            self.hass, self.device_id, "dehumidify", config
        )
        entity._is_on = False

        with (
            patch(
                "custom_components.ramses_extras.features.humidity_control.platforms.switch.ExtrasSwitchEntity.async_added_to_hass",
                new=AsyncMock(),
            ),
            patch.object(
                entity,
                "async_get_last_state",
                new=AsyncMock(return_value=None),
            ),
        ):
            await entity.async_added_to_hass()

        assert entity.is_on is False

    async def test_humidity_number(self):
        """Test HumidityControlNumber."""
        config = {
            "name": "Min Humidity",
            "default_value": 45.0,
            "supported_device_types": ["HvacVentilator"],
        }
        entity = humidity_number_platform.HumidityControlNumber(
            self.hass,
            self.device_id,
            "relative_humidity_minimum",
            config,
            self.config_entry,
        )

        # Initialize native value if not already set by constructor
        entity._native_value = 45.0

        assert entity.native_value == 45.0

        # Test setting value
        with patch(
            "custom_components.ramses_extras.framework.base_classes.platform_entities.ExtrasNumberEntity.async_set_native_value",
            new_callable=AsyncMock,
        ) as mock_super_set:
            await entity.async_set_native_value(50.0)
            mock_super_set.assert_called_once_with(50.0)
            # Update value manually for the test since we're mocking the super call
            entity._native_value = 50.0
            assert entity.native_value == 50.0

    async def test_humidity_number_loads_from_config(self):
        """Test HumidityControlNumber loads persisted config values."""
        self.config_entry.options = {
            "humidity_control": {
                self.device_id: {"relative_humidity_minimum": 47.5},
            }
        }
        config = {
            "name": "Min Humidity",
            "default_value": 45.0,
            "supported_device_types": ["HvacVentilator"],
        }
        entity = humidity_number_platform.HumidityControlNumber(
            self.hass,
            self.device_id,
            "relative_humidity_minimum",
            config,
            self.config_entry,
        )

        assert entity.native_value == 47.5

    async def test_humidity_number_save_value_to_config(self):
        """Test HumidityControlNumber saves values to config entry options."""
        config = {
            "name": "Min Humidity",
            "default_value": 45.0,
            "supported_device_types": ["HvacVentilator"],
        }
        entity = humidity_number_platform.HumidityControlNumber(
            self.hass,
            self.device_id,
            "relative_humidity_minimum",
            config,
            self.config_entry,
        )

        await entity._save_value_to_config(52.0)

        self.hass.config_entries.async_update_entry.assert_called_once()
        _, kwargs = self.hass.config_entries.async_update_entry.call_args
        assert (
            kwargs["options"]["humidity_control"][self.device_id][
                "relative_humidity_minimum"
            ]
            == 52.0
        )

    async def test_create_humidity_number(self):
        """Test create_humidity_number factory."""
        numbers = await humidity_number_platform.create_humidity_number(
            self.hass, self.device_id, self.config_entry
        )
        assert len(numbers) == 3
        assert any(n._entity_type == "relative_humidity_minimum" for n in numbers)

    async def test_humidity_binary_sensor(self):
        """Test HumidityControlBinarySensor."""
        config = {
            "name": "Balance Active",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidifying_active_{device_id}",
        }
        entity = humidity_binary_sensor_platform.HumidityControlBinarySensor(
            self.hass, self.device_id, "dehumidifying_active", config
        )

        # Initialize internal state
        entity._is_on = False

        assert entity.is_on is False

        # Test state setting
        entity.set_state(True)
        assert entity.is_on is True

        # Test turn off
        await entity.async_turn_off()
        assert entity.is_on is False

    async def test_humidity_binary_sensor_extra_attributes(self):
        """Test binary sensor extra attributes."""
        config = {
            "name": "Balance Active",
            "supported_device_types": ["HvacVentilator"],
            "entity_template": "dehumidifying_active_{device_id}",
        }
        entity = humidity_binary_sensor_platform.HumidityControlBinarySensor(
            self.hass, self.device_id, "dehumidifying_active", config
        )

        attrs = entity.extra_state_attributes

        assert attrs["binary_type"] == "dehumidifying_active"
        assert attrs["controlled_by"] == "automation"
        assert attrs["current_fan_speed"] == "auto"

    async def test_create_humidity_binary_sensor(self):
        """Test create_humidity_control_binary_sensor factory."""
        sensors = (
            await humidity_binary_sensor_platform.create_humidity_control_binary_sensor(
                self.hass, self.device_id, self.config_entry
            )
        )
        assert len(sensors) == 1
        assert isinstance(
            sensors[0], humidity_binary_sensor_platform.HumidityControlBinarySensor
        )

    async def test_create_humidity_sensor_placeholder(self):
        """Test create_humidity_sensor (placeholder)."""
        # This currently returns empty list as sensors are handled by default feature
        sensors = await humidity_sensor_platform.create_humidity_sensor(
            self.hass, self.device_id, {}, self.config_entry
        )
        assert isinstance(sensors, list)
        assert len(sensors) == 0

    async def test_switch_async_setup_entry_no_devices(self):
        """Test switch platform setup with no filtered devices."""
        async_add_entities = MagicMock()

        with patch(
            "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.get_filtered_devices_for_feature",
            return_value=[],
        ):
            await humidity_switch_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        async_add_entities.assert_not_called()

    async def test_switch_async_setup_entry_adds_entities(self):
        """Test switch platform setup adds created entities."""
        async_add_entities = MagicMock()
        mock_entity = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.get_filtered_devices_for_feature",
                return_value=[self.device_id],
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.platforms.switch.create_humidity_switch",
                new=AsyncMock(return_value=[mock_entity]),
            ),
        ):
            await humidity_switch_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        async_add_entities.assert_called_once_with([mock_entity], True)

    async def test_number_async_setup_entry_no_devices(self):
        """Test number platform setup with no filtered devices."""
        async_add_entities = MagicMock()

        with patch(
            "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.get_filtered_devices_for_feature",
            return_value=[],
        ):
            await humidity_number_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        async_add_entities.assert_not_called()

    async def test_number_async_setup_entry_adds_entities(self):
        """Test number platform setup adds created entities."""
        async_add_entities = MagicMock()
        mock_entity = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.get_filtered_devices_for_feature",
                return_value=[self.device_id],
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.platforms.number.create_humidity_number",
                new=AsyncMock(return_value=[mock_entity]),
            ),
        ):
            await humidity_number_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        async_add_entities.assert_called_once_with([mock_entity], True)

    async def test_binary_sensor_async_setup_entry_no_devices(self):
        """Test binary sensor platform setup with no filtered devices."""
        async_add_entities = MagicMock()

        with patch(
            "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.get_filtered_devices_for_feature",
            return_value=[],
        ):
            await humidity_binary_sensor_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        async_add_entities.assert_not_called()

    async def test_binary_sensor_async_setup_entry_adds_entities(self):
        """Test binary sensor platform setup adds and stores entities."""
        async_add_entities = MagicMock()
        mock_entity = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.get_filtered_devices_for_feature",
                return_value=[self.device_id],
            ),
            patch(
                "custom_components.ramses_extras.features.humidity_control.platforms.binary_sensor.create_humidity_control_binary_sensor",
                new=AsyncMock(return_value=[mock_entity]),
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup._store_entities_for_automation",
            ) as mock_store,
        ):
            await humidity_binary_sensor_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        async_add_entities.assert_called_once_with([mock_entity], True)
        mock_store.assert_called_once_with(self.hass, [mock_entity])

    async def test_sensor_async_setup_entry_uses_platform_helper(self):
        """Test sensor platform setup delegates to platform helper."""
        async_add_entities = MagicMock()

        with patch(
            "custom_components.ramses_extras.framework.helpers.platform.PlatformSetup.async_create_and_add_platform_entities",
            new=AsyncMock(),
        ) as mock_helper:
            await humidity_sensor_platform.async_setup_entry(
                self.hass, self.config_entry, async_add_entities
            )

        mock_helper.assert_called_once()
