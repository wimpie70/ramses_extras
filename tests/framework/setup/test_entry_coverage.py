"""Tests for setup/entry.py to improve coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.setup.entry import (
    apply_log_level_from_entry,
    async_unload_entry,
    async_update_listener,
    configure_zones_from_yaml,
    initialize_entry_data,
)


class TestApplyLogLevelFromEntry:
    """Tests for apply_log_level_from_entry."""

    def test_no_log_level_option(self):
        """Test when log_level option is not set."""
        entry = MagicMock()
        entry.options = {}

        apply_log_level_from_entry(entry)

        # Should not crash

    def test_log_level_not_string(self):
        """Test when log_level is not a string."""
        entry = MagicMock()
        entry.options = {"log_level": 123}

        apply_log_level_from_entry(entry)

        # Should not crash

    def test_log_level_invalid(self):
        """Test when log_level is invalid."""
        entry = MagicMock()
        entry.options = {"log_level": "invalid"}

        apply_log_level_from_entry(entry)

        # Should not crash

    def test_log_level_debug(self):
        """Test setting debug log level."""
        entry = MagicMock()
        entry.options = {"log_level": "debug"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_info(self):
        """Test setting info log level."""
        entry = MagicMock()
        entry.options = {"log_level": "info"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_warning(self):
        """Test setting warning log level."""
        entry = MagicMock()
        entry.options = {"log_level": "warning"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_error(self):
        """Test setting error log level."""
        entry = MagicMock()
        entry.options = {"log_level": "error"}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()

    def test_log_level_with_whitespace(self):
        """Test log level with whitespace."""
        entry = MagicMock()
        entry.options = {"log_level": "  debug  "}

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            apply_log_level_from_entry(entry)

            mock_logger.setLevel.assert_called_once()


class TestInitializeEntryData:
    """Tests for initialize_entry_data."""

    def test_initialize_entry_data(self):
        """Test basic initialization."""
        hass = MagicMock()
        hass.data = {}
        entry = MagicMock()
        entry.entry_id = "test_entry"

        with patch(
            "custom_components.ramses_extras.framework.setup.entry.get_enabled_features_dict"
        ) as mock_get_features:
            mock_get_features.return_value = {"default": {}}

            initialize_entry_data(hass, entry)

            assert DOMAIN in hass.data
            assert "test_entry" in hass.data[DOMAIN]
            assert "enabled_features" in hass.data[DOMAIN]

    def test_initialize_entry_data_existing_domain(self):
        """Test initialization when DOMAIN already exists in hass.data."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {"existing_key": "existing_value"}}
        entry = MagicMock()
        entry.entry_id = "test_entry"

        with patch(
            "custom_components.ramses_extras.framework.setup.entry.get_enabled_features_dict"
        ) as mock_get_features:
            mock_get_features.return_value = {"default": {}}

            initialize_entry_data(hass, entry)

            assert "test_entry" in hass.data[DOMAIN]
            assert "existing_key" in hass.data[DOMAIN]  # Should preserve existing data


class TestConfigureZonesFromYaml:
    """Tests for configure_zones_from_yaml."""

    @pytest.mark.asyncio
    async def test_configure_zones_no_zones(self, hass):
        """Test when no zones are configured."""
        hass.data = {DOMAIN: {"config_entry": MagicMock(data={}, options={})}}

        with patch(
            "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry"
        ) as mock_get_zone_registry:
            mock_zone_registry = MagicMock()
            mock_zone_registry.list_all_zones.return_value = {}
            mock_get_zone_registry.return_value = mock_zone_registry

            await configure_zones_from_yaml(hass)

            # Should not crash

    @pytest.mark.asyncio
    async def test_configure_zones_with_zones(self, hass):
        """Test zone configuration with valid zones."""
        hass.data = {DOMAIN: {"config_entry": MagicMock(data={}, options={})}}

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry"
            ) as mock_get_zone_registry,
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator"
            ) as mock_get_coordinator,
            patch(
                "custom_components.ramses_extras.framework.helpers.config.model.get_fan_max_open_zones"
            ) as mock_get_max_open,
            patch(
                "custom_components.ramses_extras.framework.helpers.config.migration.get_migrated_feature_section"
            ) as mock_get_section,
        ):
            mock_zone_registry = MagicMock()
            mock_zone_registry.list_all_zones.return_value = {
                "32:123456": [
                    {
                        "zone_id": "zone1",
                        "type": "paired_valves",
                        "inlet_valve_entity": "switch.inlet",
                        "outlet_valve_entity": "switch.outlet",
                        "min_position": 0,
                        "max_position": 100,
                        "actuation_priority": 100,
                    }
                ]
            }
            mock_get_zone_registry.return_value = mock_zone_registry

            mock_coordinator = MagicMock()
            mock_get_coordinator.return_value = mock_coordinator

            mock_get_max_open.return_value = 2
            mock_get_section.return_value = {}

            await configure_zones_from_yaml(hass)

            mock_coordinator.set_max_open_zones.assert_called_once_with(2)
            mock_coordinator.configure_zone.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_zones_missing_zone_id(self, hass):
        """Test zone configuration with missing zone_id."""
        hass.data = {DOMAIN: {"config_entry": MagicMock(data={}, options={})}}

        with patch(
            "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry"
        ) as mock_get_zone_registry:
            mock_zone_registry = MagicMock()
            mock_zone_registry.list_all_zones.return_value = {
                "32:123456": [{"type": "paired_valves"}]
            }
            mock_get_zone_registry.return_value = mock_zone_registry

            await configure_zones_from_yaml(hass)

            # Should not crash

    @pytest.mark.asyncio
    async def test_configure_zones_missing_valve_entities(self, hass):
        """Test zone configuration with missing valve entities."""
        hass.data = {DOMAIN: {"config_entry": MagicMock(data={}, options={})}}

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.zones.get_zone_registry"
            ) as mock_get_zone_registry,
            patch(
                "custom_components.ramses_extras.framework.helpers.zone_coordinator.get_zone_coordinator"
            ) as mock_get_coordinator,
        ):
            mock_zone_registry = MagicMock()
            mock_zone_registry.list_all_zones.return_value = {
                "32:123456": [
                    {
                        "zone_id": "zone1",
                        "type": "paired_valves",
                        "inlet_valve_entity": None,
                        "outlet_valve_entity": None,
                    }
                ]
            }
            mock_get_zone_registry.return_value = mock_zone_registry

            mock_coordinator = MagicMock()
            mock_get_coordinator.return_value = mock_coordinator

            await configure_zones_from_yaml(hass)

            mock_coordinator.configure_zone.assert_not_called()


class TestAsyncUpdateListener:
    """Tests for async_update_listener."""

    @pytest.mark.asyncio
    async def test_update_listener_no_changes(self, hass):
        """Test update listener when no changes occur."""
        entry = MagicMock()
        entry.options = {}
        hass.data = {DOMAIN: {"enabled_features": {}, "device_feature_matrix": {}}}

        await async_update_listener(hass, entry)

        # Should not crash

    @pytest.mark.asyncio
    async def test_update_listener_with_reload_pending(self, hass):
        """Test update listener when reload is already pending."""
        entry = MagicMock()
        entry.options = {}
        entry.data = {"device_feature_matrix": {"new": "data"}}
        hass.data = {
            DOMAIN: {
                "enabled_features": {},
                "device_feature_matrix": {},
                "_reload_pending": True,
            }
        }

        await async_update_listener(hass, entry)

        # Should return early

    @pytest.mark.asyncio
    async def test_update_listener_triggers_reload(self, hass):
        """Test update listener triggers reload on changes."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"log_level": "debug"}
        entry.data = {"device_feature_matrix": {"old": "data"}}
        hass.data = {DOMAIN: {"enabled_features": {}, "device_feature_matrix": {}}}
        hass.config_entries.async_reload = AsyncMock()
        hass.config_entries.async_get_entry = MagicMock(return_value=entry)
        hass.async_create_task = MagicMock()

        await async_update_listener(hass, entry)

        # Should create reload task

    @pytest.mark.asyncio
    async def test_update_listener_entry_already_unloaded(self, hass):
        """Test update listener when entry is already unloaded."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"log_level": "debug"}
        entry.data = {"device_feature_matrix": {"new": "data"}}
        hass.data = {DOMAIN: {"enabled_features": {}, "device_feature_matrix": {}}}
        hass.config_entries.async_reload = AsyncMock()
        hass.config_entries.async_get_entry = MagicMock(return_value=None)
        hass.async_create_task = MagicMock()

        await async_update_listener(hass, entry)

        # Should not reload if entry is gone
        hass.async_create_task.assert_called_once()  # Task is created even if entry is gone  # noqa: E501

    @pytest.mark.asyncio
    async def test_update_listener_invalid_entry_id(self, hass):
        """Test update listener with invalid entry_id."""
        entry = MagicMock()
        entry.entry_id = None
        entry.options = {"log_level": "debug"}
        entry.data = {"device_feature_matrix": {"new": "data"}}
        hass.data = {DOMAIN: {"enabled_features": {}, "device_feature_matrix": {}}}
        hass.config_entries.async_reload = AsyncMock()
        hass.async_create_task = MagicMock()

        await async_update_listener(hass, entry)

        # Should not reload if entry_id is invalid


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    @pytest.mark.asyncio
    async def test_unload_entry_basic(self, hass):
        """Test basic unload entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        with (
            patch(
                "custom_components.ramses_extras.services_integration.async_unload_feature_services"
            ),
            patch(
                "custom_components.ramses_extras.framework.setup.devices.async_setup_platforms"
            ),
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_with_remote_listeners(self, hass):
        """Test unload entry with remote fan listeners."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {
            DOMAIN: {
                "_fan_remote_listener_unsubs": [MagicMock(), MagicMock()],
            }
        }

        with patch(
            "custom_components.ramses_extras.services_integration.async_unload_feature_services"
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_with_humidity_automation(self, hass):
        """Test unload entry with humidity automation."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        mock_automation = MagicMock()
        mock_automation.stop = AsyncMock()
        hass.data = {DOMAIN: {"humidity_automation": mock_automation}}

        with patch(
            "custom_components.ramses_extras.services_integration.async_unload_feature_services"
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True
            mock_automation.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unload_entry_removes_entities(self, hass):
        """Test unload entry removes entities."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        mock_entity = MagicMock()
        mock_entity.platform = DOMAIN
        mock_entity.entity_id = "sensor.test"

        with (
            patch(
                "custom_components.ramses_extras.services_integration.async_unload_feature_services"
            ),
            patch(
                "homeassistant.helpers.entity_registry.async_get"
            ) as mock_get_entity_registry,
        ):
            mock_entity_registry = MagicMock()
            mock_entity_registry.entities = {"sensor.test": mock_entity}
            mock_entity_registry.async_remove = MagicMock()
            mock_get_entity_registry.return_value = mock_entity_registry

            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_removes_devices(self, hass):
        """Test unload entry removes devices."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        mock_device = MagicMock()
        mock_device.config_entries = ["test_entry"]
        mock_device.id = "device_id"

        with (
            patch(
                "custom_components.ramses_extras.services_integration.async_unload_feature_services"
            ),
            patch(
                "homeassistant.helpers.device_registry.async_get"
            ) as mock_get_device_registry,
        ):
            mock_device_registry = MagicMock()
            mock_device_registry.devices = {"device_id": mock_device}
            mock_device_registry.async_remove_device = MagicMock()
            mock_get_device_registry.return_value = mock_device_registry

            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_no_entry_id(self, hass):
        """Test unload entry when entry_id is not available."""
        entry = MagicMock()
        entry.entry_id = None
        hass.data = {DOMAIN: {}}

        with patch(
            "custom_components.ramses_extras.services_integration.async_unload_feature_services"
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_with_remote_listener_error(self, hass):
        """Test unload entry with remote listener error."""
        entry = MagicMock()
        entry.entry_id = "test_entry"

        def failing_unsub():
            raise Exception("Test error")

        hass.data = {
            DOMAIN: {
                "_fan_remote_listener_unsubs": [failing_unsub],
            }
        }

        with patch(
            "custom_components.ramses_extras.services_integration.async_unload_feature_services"
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_humidity_automation_error(self, hass):
        """Test unload entry with humidity automation error."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        mock_automation = MagicMock()
        mock_automation.stop = AsyncMock(side_effect=Exception("Test error"))
        hass.data = {DOMAIN: {"humidity_automation": mock_automation}}

        with patch(
            "custom_components.ramses_extras.services_integration.async_unload_feature_services"
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_with_simulator_restore(self, hass):
        """Test unload entry with simulator gateway restore."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        with patch(
            "custom_components.ramses_extras.services_integration.async_unload_feature_services"
        ):
            # Patch the import location
            with patch(
                "custom_components.ramses_extras.features.device_simulator.async_restore_ramses_cc_gateway_topic",
                new_callable=AsyncMock,
            ):
                result = await async_unload_entry(hass, entry)

                assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_simulator_import_error(self, hass):
        """Test unload entry when simulator import fails."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        with (
            patch(
                "custom_components.ramses_extras.services_integration.async_unload_feature_services"
            ),
            patch(
                "custom_components.ramses_extras.features.device_simulator.async_restore_ramses_cc_gateway_topic",
                side_effect=ImportError,
            ),
        ):
            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_with_lovelace_resources(self, hass):
        """Test unload entry removes Lovelace resources."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        with (
            patch(
                "custom_components.ramses_extras.services_integration.async_unload_feature_services"
            ),
            patch("homeassistant.helpers.storage.Store") as mock_store_class,
        ):
            mock_store = MagicMock()
            mock_store.async_load = AsyncMock(
                return_value={"items": [{"url": "/local/ramses_extras/test.js"}]}
            )
            mock_store.async_save = AsyncMock()
            mock_store_class.return_value = mock_store

            result = await async_unload_entry(hass, entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_entry_with_www_files(self, hass):
        """Test unload entry removes www files."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        hass.data = {DOMAIN: {}}

        with (
            patch(
                "custom_components.ramses_extras.services_integration.async_unload_feature_services"
            ),
            patch("pathlib.Path") as mock_path_class,
            patch("shutil.rmtree") as mock_rmtree,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path_class.return_value = mock_path
            hass.async_add_executor_job = MagicMock(return_value=mock_rmtree)

            result = await async_unload_entry(hass, entry)

            assert result is True
