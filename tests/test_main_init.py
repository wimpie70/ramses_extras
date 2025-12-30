# tests/test_init.py
"""Test main integration file."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras import DOMAIN
from custom_components.ramses_extras.const import (
    EVENT_DEVICES_UPDATED,
)


class TestIntegrationVersion:
    """Test _async_get_integration_version function."""

    @pytest.mark.asyncio
    async def test_get_integration_version_cached(self, hass):
        """Test getting cached integration version."""
        from custom_components.ramses_extras import (
            _async_get_integration_version,
        )

        hass.data[DOMAIN] = {"_integration_version": "1.2.3"}
        version = await _async_get_integration_version(hass)
        assert version == "1.2.3"

    @pytest.mark.asyncio
    async def test_get_integration_version_success(self, hass):
        """Test getting integration version successfully from manifest."""
        from custom_components.ramses_extras import (
            _async_get_integration_version,
        )

        hass.data[DOMAIN] = {}
        mock_integration = MagicMock()
        mock_integration.manifest = {"version": "2.0.0"}

        with patch(
            "custom_components.ramses_extras.async_get_integration",
            return_value=mock_integration,
        ):
            version = await _async_get_integration_version(hass)
            assert version == "2.0.0"
            assert hass.data[DOMAIN]["_integration_version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_get_integration_version_failure(self, hass):
        """Test failure handling when getting integration version."""
        from custom_components.ramses_extras import (
            _async_get_integration_version,
        )

        hass.data[DOMAIN] = {}
        with patch(
            "custom_components.ramses_extras.async_get_integration",
            side_effect=Exception("Failed"),
        ):
            version = await _async_get_integration_version(hass)
            assert version == "0.0.0"


class TestCleanupOldCardDeployments:
    """Test _cleanup_old_card_deployments function."""

    @pytest.mark.asyncio
    async def test_cleanup_no_root_dir(self, hass):
        """Test cleanup when root directory does not exist."""
        from custom_components.ramses_extras import _cleanup_old_card_deployments

        with patch("pathlib.Path.exists", return_value=False):
            await _cleanup_old_card_deployments(hass, "1.0.0")
            # Should return early without error

    @pytest.mark.asyncio
    async def test_cleanup_success(self, hass):
        """Test successful cleanup of old deployments."""
        from custom_components.ramses_extras import _cleanup_old_card_deployments

        # Create a mock for the root directory that will be iterated
        mock_root_dir = MagicMock()
        mock_root_dir.exists.return_value = True

        mock_v1 = MagicMock()
        mock_v1.is_dir.return_value = True
        mock_v1.name = "v0.9.0"

        mock_v2 = MagicMock()
        mock_v2.is_dir.return_value = True
        mock_v2.name = "v1.0.0"

        mock_root_dir.iterdir.return_value = [
            mock_v1,
            mock_v2,
        ]

        # Patch Path so that when it's called or divided, it eventually
        # returns our mock_root_dir
        with (
            patch("custom_components.ramses_extras.Path") as mock_path_class,
            patch("shutil.rmtree") as mock_rmtree,
        ):
            # Make Path() / "www" / "ramses_extras" return mock_root_dir
            mock_path = mock_path_class.return_value
            mock_path.__truediv__.return_value.__truediv__.return_value = mock_root_dir

            # These are for the shims created inside _do_cleanup
            shim_mock = mock_root_dir.__truediv__.return_value.__truediv__.return_value
            shim_mock.write_text = MagicMock()
            shim_mock.parent.mkdir = MagicMock()

            await _cleanup_old_card_deployments(hass, "1.0.0")

            # Should remove v0.9.0 but not v1.0.0
            mock_rmtree.assert_called_once_with(mock_v1, ignore_errors=True)


class TestCopyCardFiles:
    """Test _copy_all_card_files function."""

    @pytest.mark.asyncio
    async def test_copy_all_card_files_success(self, hass):
        """Test successful copying of card files."""
        from custom_components.ramses_extras import _copy_all_card_files

        with (
            patch(
                "custom_components.ramses_extras._async_get_integration_version",
                return_value="1.0.0",
            ),
            patch("custom_components.ramses_extras.INTEGRATION_DIR"),
            patch(
                "custom_components.ramses_extras.DEPLOYMENT_PATHS.get_destination_features_path"
            ),
            patch("shutil.copytree") as mock_copytree,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.mkdir"),
        ):
            await _copy_all_card_files(hass)
            assert mock_copytree.call_count == 2


class TestCopyHelperFiles:
    """Test _copy_helper_files function."""

    @pytest.mark.asyncio
    async def test_copy_helper_files_success(self, hass):
        """Test successful copying of helper files."""
        from custom_components.ramses_extras import _copy_helper_files

        with (
            patch(
                "custom_components.ramses_extras._async_get_integration_version",
                return_value="1.0.0",
            ),
            patch("custom_components.ramses_extras.INTEGRATION_DIR"),
            patch(
                "custom_components.ramses_extras.DEPLOYMENT_PATHS.get_destination_helpers_path"
            ),
            patch("shutil.copytree") as mock_copytree,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.mkdir"),
        ):
            await _copy_helper_files(hass)
            assert mock_copytree.call_count == 1

    @pytest.mark.asyncio
    async def test_copy_helper_files_source_not_exists(self, hass):
        """Test helper files copy when source doesn't exist."""
        from custom_components.ramses_extras import _copy_helper_files

        with patch(
            "custom_components.ramses_extras.INTEGRATION_DIR"
        ) as mock_integration_dir:
            mock_source_dir = MagicMock()
            mock_integration_dir.__truediv__.return_value.__truediv__.return_value = (
                mock_source_dir
            )
            mock_source_dir.exists.return_value = False

            await _copy_helper_files(hass)

    @pytest.mark.asyncio
    async def test_copy_helper_files_exception_handling(self, hass):
        """Test exception handling in helper files copy."""
        from custom_components.ramses_extras import _copy_helper_files

        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_destination_helpers_path",
            side_effect=Exception("Copy error"),
        ):
            await _copy_helper_files(hass)


class TestImportFeaturePlatformModules:
    """Test _import_feature_platform_modules function."""

    @pytest.mark.asyncio
    async def test_import_feature_platform_modules_success(self):
        """Test successful platform module imports."""
        from custom_components.ramses_extras import _import_feature_platform_modules

        with patch("asyncio.to_thread") as mock_to_thread:
            await _import_feature_platform_modules(["feat1"])
            assert mock_to_thread.call_count == 4

    @pytest.mark.asyncio
    async def test_import_feature_platform_modules_missing(self):
        """Test handling of missing platform modules."""
        from custom_components.ramses_extras import _import_feature_platform_modules

        with patch(
            "asyncio.to_thread",
            side_effect=ModuleNotFoundError("No module", name="feat1.platforms.sensor"),
        ):
            await _import_feature_platform_modules(["feat1"])


class TestAsyncUnloadEntry:
    """Test async_unload_entry function."""

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(self, hass):
        """Test successful entry unloading."""
        from custom_components.ramses_extras import async_unload_entry

        entry = MagicMock()
        hass.data[DOMAIN] = {"some": "data"}

        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=True
        ) as mock_unload:
            result = await async_unload_entry(hass, entry)

            assert result is True
            assert DOMAIN not in hass.data
            mock_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_unload_entry_failure(self, hass):
        """Test entry unloading failure."""
        from custom_components.ramses_extras import async_unload_entry

        entry = MagicMock()
        hass.data[DOMAIN] = {"some": "data"}

        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=False
        ):
            result = await async_unload_entry(hass, entry)

            assert result is False
            assert DOMAIN in hass.data


class TestAsyncRemoveEntry:
    """Test async_remove_entry function."""

    @pytest.mark.asyncio
    async def test_async_remove_entry(self, hass):
        """Test removing a config entry and its entities/devices."""
        from custom_components.ramses_extras import async_remove_entry

        entry = MagicMock()
        entry.id = "test_entry_id"

        mock_entity_reg = MagicMock()
        entity1 = MagicMock(entity_id="sensor.test1", platform=DOMAIN)
        entity2 = MagicMock(entity_id="sensor.other", platform="other")
        mock_entity_reg.entities = {"sensor.test1": entity1, "sensor.other": entity2}

        mock_device_reg = MagicMock()
        device1 = MagicMock(id="dev1", config_entries={"test_entry_id"})
        device2 = MagicMock(id="dev2", config_entries={"other_entry"})
        mock_device_reg.devices = {"dev1": device1, "dev2": device2}

        with (
            patch(
                "custom_components.ramses_extras.er.async_get",
                return_value=mock_entity_reg,
            ),
            patch(
                "custom_components.ramses_extras.dr.async_get",
                return_value=mock_device_reg,
            ),
        ):
            await async_remove_entry(hass, entry)

            mock_entity_reg.async_remove.assert_called_once_with("sensor.test1")
            mock_device_reg.async_remove_device.assert_called_once_with("dev1")


class TestImportModuleInExecutor:
    """Test _import_module_in_executor function."""

    @pytest.mark.asyncio
    async def test_import_module_in_executor_success(self):
        """Test successful module import in executor."""
        from custom_components.ramses_extras import _import_module_in_executor

        mock_module = MagicMock()
        mock_module.__name__ = "test_module"

        with patch("importlib.import_module", return_value=mock_module) as mock_import:
            result = await _import_module_in_executor("test_module")

            assert result == mock_module
            mock_import.assert_called_once_with("test_module")

    @pytest.mark.asyncio
    async def test_import_module_in_executor_exception(self):
        """Test exception handling in module import."""
        from custom_components.ramses_extras import _import_module_in_executor

        with patch(
            "importlib.import_module", side_effect=ImportError("Module not found")
        ):
            with pytest.raises(ImportError):
                await _import_module_in_executor("nonexistent_module")


class TestAsyncSetup:
    """Test async_setup function."""

    @pytest.mark.asyncio
    async def test_async_setup_registers_startup_listener(self, hass):
        """Test that async_setup registers a startup event listener."""
        from custom_components.ramses_extras import async_setup

        config = {"ramses_extras": {"enabled_features": {"humidity_control": True}}}

        result = await async_setup(hass, config)

        assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_empty_config(self, hass):
        """Test async_setup with empty config."""
        from custom_components.ramses_extras import async_setup

        config = {}

        result = await async_setup(hass, config)

        assert result is True


class TestAsyncSetupYamlConfig:
    """Test async_setup_yaml_config function."""

    @pytest.mark.asyncio
    async def test_async_setup_yaml_config_empty_config(self, hass):
        """Test YAML config setup with empty config."""
        from custom_components.ramses_extras import async_setup_yaml_config

        config = {}

        await async_setup_yaml_config(hass, config)

    @pytest.mark.asyncio
    async def test_async_setup_yaml_config_exception_handling(self, hass):
        """Test exception handling in YAML config setup."""
        from custom_components.ramses_extras import async_setup_yaml_config

        config = {"enabled_features": {"humidity_control": True}}

        with patch.object(hass.config_entries, "flow") as mock_flow:
            mock_flow.async_init = AsyncMock(side_effect=Exception("Flow error"))
            await async_setup_yaml_config(hass, config)


class TestRegisterServices:
    """Test _register_services function."""

    @pytest.mark.asyncio
    async def test_register_services_success(self, hass):
        """Test successful service registration."""
        from custom_components.ramses_extras import _register_services

        with patch(
            "custom_components.ramses_extras.features.default.services.async_setup_services"
        ) as mock_setup:
            mock_setup.return_value = None
            await _register_services(hass)

            mock_setup.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_register_services_exception_handling(self, hass):
        """Test exception handling in service registration."""
        from custom_components.ramses_extras import _register_services

        with patch(
            "custom_components.ramses_extras.features.default.services.async_setup_services",
            side_effect=Exception("Setup failed"),
        ):
            with pytest.raises(Exception, match="Setup failed"):
                await _register_services(hass)


class TestSetupWebsocketIntegration:
    """Test _setup_websocket_integration function."""

    @pytest.mark.asyncio
    async def test_setup_websocket_integration_success(self, hass):
        """Test successful WebSocket integration setup."""
        from custom_components.ramses_extras import _setup_websocket_integration

        with patch(
            "custom_components.ramses_extras.websocket_integration.async_setup_websocket_integration",
            return_value=True,
        ) as mock_setup:
            await _setup_websocket_integration(hass)

            mock_setup.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_setup_websocket_integration_failure(self, hass):
        """Test WebSocket integration setup failure."""
        from custom_components.ramses_extras import _setup_websocket_integration

        with patch(
            "custom_components.ramses_extras.websocket_integration.async_setup_websocket_integration",
            return_value=False,
        ) as mock_setup:
            await _setup_websocket_integration(hass)

            mock_setup.assert_called_once_with(hass)

    @pytest.mark.asyncio
    async def test_setup_websocket_integration_exception(self, hass):
        """Test exception handling in WebSocket integration setup."""
        from custom_components.ramses_extras import _setup_websocket_integration

        with patch(
            "custom_components.ramses_extras.websocket_integration.async_setup_websocket_integration",
            side_effect=Exception("Setup error"),
        ):
            await _setup_websocket_integration(hass)


class TestExposeFeatureConfigToFrontend:
    """Test _expose_feature_config_to_frontend function."""

    @pytest.mark.asyncio
    async def test_expose_feature_config_success(self, hass):
        """Test successful feature config exposure."""
        from custom_components.ramses_extras import _expose_feature_config_to_frontend

        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"humidity_control": True}}
        mock_entry.options = {}

        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_destination_helpers_path"
        ) as mock_path:
            mock_path.return_value = MagicMock()
            mock_file = MagicMock()
            mock_path.return_value.__truediv__.return_value = mock_file
            mock_file.write_text = MagicMock()

            await _expose_feature_config_to_frontend(hass, mock_entry)

            mock_file.write_text.assert_called_once()
            content = mock_file.write_text.call_args[0][0]
            assert '"humidity_control": true' in content

    @pytest.mark.asyncio
    async def test_expose_feature_config_exception_handling(self, hass):
        """Test exception handling in feature config exposure."""
        from custom_components.ramses_extras import _expose_feature_config_to_frontend

        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"humidity_control": True}}

        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_destination_helpers_path",
            side_effect=Exception("Path error"),
        ):
            await _expose_feature_config_to_frontend(hass, mock_entry)


class TestAsyncUpdateListener:
    """Test _async_update_listener function."""

    @pytest.mark.asyncio
    async def test_async_update_listener_success(self, hass):
        """Test successful update listener."""
        from custom_components.ramses_extras import _async_update_listener

        hass.data[DOMAIN] = {}

        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"humidity_control": True}}
        mock_entry.options = {}

        with patch(
            "custom_components.ramses_extras._expose_feature_config_to_frontend"
        ) as mock_expose:
            await _async_update_listener(hass, mock_entry)

            assert hass.data[DOMAIN]["enabled_features"] == {"humidity_control": True}
            mock_expose.assert_called_once_with(hass, mock_entry)

    @pytest.mark.asyncio
    async def test_async_update_listener_exception_handling(self, hass):
        """Test exception handling in update listener."""
        from custom_components.ramses_extras import _async_update_listener

        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"humidity_control": True}}

        with patch(
            "custom_components.ramses_extras._expose_feature_config_to_frontend",
            side_effect=Exception("Expose error"),
        ):
            await _async_update_listener(hass, mock_entry)


class TestDiscoverDevices:
    """Test device discovery functions."""

    @pytest.mark.asyncio
    async def test_discover_devices_from_entity_registry(self, hass):
        """Test discovering devices from entity registry."""
        from custom_components.ramses_extras import (
            _discover_devices_from_entity_registry,
        )

        mock_entity_reg = MagicMock()
        entity1 = MagicMock(
            domain="sensor", platform="ramses_cc", device_id="32:123456"
        )
        entity2 = MagicMock(
            domain="switch", platform="ramses_cc", device_id="32:654321"
        )
        entity3 = MagicMock(domain="light", platform="other", device_id="other_dev")
        mock_entity_reg.entities = {
            "sensor.e1": entity1,
            "switch.e2": entity2,
            "light.e3": entity3,
        }

        with patch(
            "custom_components.ramses_extras.er.async_get", return_value=mock_entity_reg
        ):
            devices = await _discover_devices_from_entity_registry(hass)
            assert "32:123456" in devices
            assert "32:654321" in devices
            assert "other_dev" not in devices
            assert len(devices) == 2

    @pytest.mark.asyncio
    async def test_discover_ramses_devices_broker_found(self, hass):
        """Test discover_ramses_devices when broker is found in hass.data."""
        from custom_components.ramses_extras import _discover_ramses_devices

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_broker = MagicMock()
        mock_device = MagicMock()
        mock_device.id = "32:111111"
        mock_broker.broker._devices = [mock_device]

        hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
        hass.data["ramses_cc"] = {"test_entry": mock_broker}

        devices = await _discover_ramses_devices(hass)
        assert len(devices) == 1
        assert devices[0].id == "32:111111"

    @pytest.mark.asyncio
    async def test_discover_ramses_devices_fallback_to_registry(self, hass):
        """Test discover_ramses_devices falls back to entity registry."""
        from custom_components.ramses_extras import _discover_ramses_devices

        hass.config_entries.async_entries = MagicMock(return_value=[])

        with patch(
            "custom_components.ramses_extras._discover_devices_from_entity_registry",
            new_callable=AsyncMock,
            return_value=["32:222222"],
        ) as mock_fallback:
            devices = await _discover_ramses_devices(hass)
            assert devices == ["32:222222"]
            mock_fallback.assert_called_once()


class TestCleanupOrphanedDevices:
    """Test _cleanup_orphaned_devices function."""

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_devices_success(self, hass):
        """Test successful removal of orphaned devices."""
        from custom_components.ramses_extras import DOMAIN, _cleanup_orphaned_devices

        entry = MagicMock()
        entry.entry_id = "test_entry"

        # Mock device registry
        mock_device_reg = MagicMock()
        device1 = MagicMock(
            id="dev1",
            identifiers={(DOMAIN, "32:111111")},
            config_entries={"test_entry"},
        )
        device2 = MagicMock(
            id="dev2",
            identifiers={(DOMAIN, "32:222222")},
            config_entries={"test_entry"},
        )
        mock_device_reg.devices = {"dev1": device1, "dev2": device2}

        # Mock entity registry - dev1 has entities, dev2 has none
        mock_entity_reg = MagicMock()
        mock_entity_reg.entities = {
            "dev1": [MagicMock()],
            "dev2": [],
        }

        await _cleanup_orphaned_devices(
            hass,
            entry,
            device_registry=mock_device_reg,
            entity_registry=mock_entity_reg,
        )

        # Should remove dev2 but not dev1
        mock_device_reg.async_remove_device.assert_called_once_with("dev2")


class TestAsyncSetupPlatforms:
    """Test async_setup_platforms function."""

    @pytest.mark.asyncio
    async def test_async_setup_platforms_success(self, hass):
        """Test successful platform setup."""
        from custom_components.ramses_extras import async_setup_platforms

        hass.config.components.add("ramses_cc")
        hass.data[DOMAIN] = {
            "devices": [MagicMock(id="32:111111")],
            "device_discovery_complete": True,
        }

        # Should return early since discovery is complete
        await async_setup_platforms(hass)

    @pytest.mark.asyncio
    async def test_async_setup_platforms_retry(self, hass):
        """Test platform setup retry when ramses_cc is not loaded."""
        from custom_components.ramses_extras import async_setup_platforms

        hass.config.components = set()  # No ramses_cc
        with patch(
            "custom_components.ramses_extras.async_call_later"
        ) as mock_call_later:
            await async_setup_platforms(hass)
            mock_call_later.assert_called_once()


class TestValidateStartupEntities:
    """Test _validate_startup_entities_simple function."""

    @pytest.mark.asyncio
    async def test_validate_startup_entities_success(self, hass):
        """Test successful entity validation."""
        from custom_components.ramses_extras import _validate_startup_entities_simple

        entry = MagicMock()
        entry.data = {"device_feature_matrix": {"dev1": {"feat1": True}}}

        with patch(
            "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.SimpleEntityManager"
        ) as mock_manager_class:
            mock_manager = mock_manager_class.return_value
            mock_manager.validate_entities_on_startup = AsyncMock()

            await _validate_startup_entities_simple(hass, entry)

            mock_manager.restore_device_feature_matrix_state.assert_called_once_with(
                entry.data["device_feature_matrix"]
            )
            mock_manager.validate_entities_on_startup.assert_awaited_once()


class TestRegisterCards:
    """Test _register_cards function."""

    @pytest.mark.asyncio
    async def test_register_cards_success(self, hass):
        """Test successful card registration."""
        from custom_components.ramses_extras import _register_cards

        with (
            patch(
                "custom_components.ramses_extras._async_get_integration_version",
                return_value="1.0.0",
            ),
            patch(
                "custom_components.ramses_extras.CardRegistry"
            ) as mock_registry_class,
        ):
            mock_registry = mock_registry_class.return_value
            mock_registry.register_bootstrap = AsyncMock()

            await _register_cards(hass)

            mock_registry.register_bootstrap.assert_awaited_once_with("1.0.0")


class TestSetupCardFilesAndConfig:
    """Test _setup_card_files_and_config function."""

    @pytest.mark.asyncio
    async def test_setup_card_files_and_config_success(self, hass):
        """Test successful card files and config setup."""
        from custom_components.ramses_extras import _setup_card_files_and_config

        entry = MagicMock()

        with (
            patch(
                "custom_components.ramses_extras._copy_helper_files",
                new_callable=AsyncMock,
            ) as mock_copy_helpers,
            patch(
                "custom_components.ramses_extras._register_cards",
                new_callable=AsyncMock,
            ) as mock_reg_cards,
            patch(
                "custom_components.ramses_extras._cleanup_old_card_deployments",
                new_callable=AsyncMock,
            ) as mock_cleanup,
            patch(
                "custom_components.ramses_extras._copy_all_card_files",
                new_callable=AsyncMock,
            ) as mock_copy_all,
            patch(
                "custom_components.ramses_extras._expose_feature_config_to_frontend",
                new_callable=AsyncMock,
            ) as mock_expose,
            patch(
                "custom_components.ramses_extras._async_get_integration_version",
                return_value="1.0.0",
            ),
        ):
            await _setup_card_files_and_config(hass, entry)

            mock_copy_helpers.assert_awaited_once()
            mock_reg_cards.assert_awaited_once()
            mock_cleanup.assert_awaited_once_with(hass, "1.0.0")
            mock_copy_all.assert_awaited_once()
            mock_expose.assert_awaited_once_with(hass, entry)


class TestDiscoverAndStoreDevices:
    """Test _discover_and_store_devices function."""

    @pytest.mark.asyncio
    async def test_discover_and_store_devices_success(self, hass):
        """Test successful device discovery and storage."""
        from custom_components.ramses_extras import _discover_and_store_devices

        mock_devices = [MagicMock(id="32:153289"), MagicMock(id="32:153290")]

        with patch(
            "custom_components.ramses_extras._discover_ramses_devices",
            return_value=mock_devices,
        ):
            await _discover_and_store_devices(hass)

            assert hass.data[DOMAIN]["devices"] == mock_devices
            assert hass.data[DOMAIN]["device_discovery_complete"] is True


@pytest.mark.asyncio
async def test_async_setup_entry_runs_core_steps(hass):
    """Ensure async_setup_entry runs the expected setup phases."""
    from custom_components.ramses_extras import async_setup_entry

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"enabled_features": {}}
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value="listener_unsub")
    entry.async_on_unload = MagicMock()

    hass.config_entries.async_forward_entry_setups = AsyncMock()

    extras_registry_mock = MagicMock()
    extras_registry_mock.get_all_sensor_configs.return_value = {}
    extras_registry_mock.get_all_switch_configs.return_value = {}
    extras_registry_mock.get_all_number_configs.return_value = {}
    extras_registry_mock.get_all_boolean_configs.return_value = {}

    with (
        patch(
            "custom_components.ramses_extras.extras_registry.extras_registry",
            extras_registry_mock,
        ),
        patch("custom_components.ramses_extras.features.default.const.load_feature"),
        patch(
            "custom_components.ramses_extras.features.default.commands.register_default_commands"
        ),
        patch(
            "custom_components.ramses_extras._setup_card_files_and_config",
            new_callable=AsyncMock,
        ) as mock_setup_card_files,
        patch(
            "custom_components.ramses_extras._register_services",
            new_callable=AsyncMock,
        ) as mock_register_services,
        patch(
            "custom_components.ramses_extras._setup_websocket_integration",
            new_callable=AsyncMock,
        ) as mock_setup_ws,
        patch(
            "custom_components.ramses_extras._discover_and_store_devices",
            new_callable=AsyncMock,
        ) as mock_discover_devices,
        patch(
            "custom_components.ramses_extras.async_setup_platforms",
            new_callable=AsyncMock,
        ) as mock_async_setup_platforms,
        patch(
            "custom_components.ramses_extras._validate_startup_entities_simple",
            new_callable=AsyncMock,
        ) as mock_validate_entities,
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    entry.add_update_listener.assert_called_once()
    entry.async_on_unload.assert_any_call("listener_unsub")
    mock_setup_card_files.assert_awaited_once()
    mock_register_services.assert_awaited_once()
    mock_setup_ws.assert_awaited_once()
    mock_discover_devices.assert_awaited_once()
    mock_async_setup_platforms.assert_awaited_once_with(hass)
    mock_validate_entities.assert_awaited_once_with(hass, entry)
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()


@pytest.mark.asyncio
async def test_entity_registry_create_triggers_device_refresh(hass):
    """Ensure new ramses_cc entities trigger device list refresh."""
    from custom_components.ramses_extras import async_setup_entry

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"enabled_features": {}}
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value="listener_unsub")
    entry.async_on_unload = MagicMock()

    hass.config_entries.async_forward_entry_setups = AsyncMock()

    extras_registry_mock = MagicMock()
    extras_registry_mock.get_all_sensor_configs.return_value = {}
    extras_registry_mock.get_all_switch_configs.return_value = {}
    extras_registry_mock.get_all_number_configs.return_value = {}
    extras_registry_mock.get_all_boolean_configs.return_value = {}

    entity_reg = MagicMock()
    ramses_cc_entity_entry = MagicMock()
    ramses_cc_entity_entry.platform = "ramses_cc"
    entity_reg.async_get.return_value = ramses_cc_entity_entry

    with (
        patch(
            "custom_components.ramses_extras.extras_registry.extras_registry",
            extras_registry_mock,
        ),
        patch("custom_components.ramses_extras.features.default.const.load_feature"),
        patch(
            "custom_components.ramses_extras.features.default.commands.register_default_commands"
        ),
        patch(
            "custom_components.ramses_extras._setup_card_files_and_config",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.ramses_extras._register_services",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.ramses_extras._setup_websocket_integration",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.ramses_extras._discover_and_store_devices",
            new_callable=AsyncMock,
        ) as mock_discover_devices,
        patch(
            "custom_components.ramses_extras.async_setup_platforms",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.ramses_extras._validate_startup_entities_simple",
            new_callable=AsyncMock,
        ),
        patch("custom_components.ramses_extras.er.async_get", return_value=entity_reg),
        patch("custom_components.ramses_extras.async_dispatcher_send") as mock_send,
        patch("custom_components.ramses_extras.asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await async_setup_entry(hass, entry)
        assert result is True

        # Initial discovery happens during setup.
        assert mock_discover_devices.await_count == 1

        # Fire an entity registry "create" event for a ramses_cc entity.
        hass.bus.async_fire(
            "entity_registry_updated",
            {"action": "create", "entity_id": "sensor.test_32_153289"},
        )
        await hass.async_block_till_done()

        # One additional refresh should have been scheduled.
        assert mock_discover_devices.await_count == 2
        mock_send.assert_any_call(hass, EVENT_DEVICES_UPDATED)
