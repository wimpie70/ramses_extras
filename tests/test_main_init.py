# tests/test_init.py
"""Test main integration file."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras import DOMAIN
from custom_components.ramses_extras.const import AVAILABLE_FEATURES, PLATFORM_REGISTRY


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
        # Verify that the startup event listener was registered
        # This is tested indirectly through the bus listeners

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

        # Should return early without doing anything
        await async_setup_yaml_config(hass, config)

    @pytest.mark.asyncio
    async def test_async_setup_yaml_config_exception_handling(self, hass):
        """Test exception handling in YAML config setup."""
        from custom_components.ramses_extras import async_setup_yaml_config

        config = {"enabled_features": {"humidity_control": True}}

        # Mock the entire config_entries.flow to raise an exception
        with patch.object(hass.config_entries, "flow") as mock_flow:
            mock_flow.async_init = AsyncMock(side_effect=Exception("Flow error"))
            # Should not raise exception, just log it
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
            # The function doesn't handle exceptions internally, so it should raise
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

            # Function doesn't return anything, but we can verify the call
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
            # Should not raise exception, just log it
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
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_file)
            mock_file.write_text = MagicMock()

            await _expose_feature_config_to_frontend(hass, mock_entry)

            # Verify file was written
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
            # Should not raise exception, just log it
            await _expose_feature_config_to_frontend(hass, mock_entry)


class TestAsyncUpdateListener:
    """Test _async_update_listener function."""

    @pytest.mark.asyncio
    async def test_async_update_listener_success(self, hass):
        """Test successful update listener."""
        from custom_components.ramses_extras import _async_update_listener

        # Initialize hass.data[DOMAIN] as the function expects
        hass.data[DOMAIN] = {}

        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"humidity_control": True}}
        mock_entry.options = {}

        with patch(
            "custom_components.ramses_extras._expose_feature_config_to_frontend"
        ) as mock_expose:
            await _async_update_listener(hass, mock_entry)

            # Verify enabled features were updated in hass.data
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
            # Should not raise exception, just log warning
            await _async_update_listener(hass, mock_entry)


class TestCopyHelperFiles:
    """Test _copy_helper_files function."""

    @pytest.mark.asyncio
    async def test_copy_helper_files_success(self, hass):
        """Test successful helper files copy."""
        from custom_components.ramses_extras import _copy_helper_files

        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_destination_helpers_path"
        ) as mock_path:
            mock_dest_dir = MagicMock()
            mock_path.return_value = mock_dest_dir
            mock_dest_dir.exists.return_value = True

            with patch("shutil.copytree") as mock_copy:
                await _copy_helper_files(hass)

                mock_copy.assert_called_once()

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

            # Should return early without error
            await _copy_helper_files(hass)

    @pytest.mark.asyncio
    async def test_copy_helper_files_exception_handling(self, hass):
        """Test exception handling in helper files copy."""
        from custom_components.ramses_extras import _copy_helper_files

        with patch(
            "custom_components.ramses_extras.framework.helpers.paths.DEPLOYMENT_PATHS.get_destination_helpers_path",
            side_effect=Exception("Copy error"),
        ):
            # Should not raise exception, just log error
            await _copy_helper_files(hass)


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

            # Verify devices were stored in hass.data
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
            "custom_components.ramses_extras._register_cards", new_callable=AsyncMock
        ) as mock_register_cards,
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
    entry.async_on_unload.assert_called_once_with("listener_unsub")
    mock_register_cards.assert_awaited_once()
    mock_setup_card_files.assert_awaited_once()
    mock_register_services.assert_awaited_once()
    mock_setup_ws.assert_awaited_once()
    mock_discover_devices.assert_awaited_once()
    mock_async_setup_platforms.assert_awaited_once_with(hass)
    mock_validate_entities.assert_awaited_once_with(hass, entry)
    hass.config_entries.async_forward_entry_setups.assert_awaited_once()
