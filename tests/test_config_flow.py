# tests/test_config_flow.py
"""Test config flow functionality."""

import builtins
import json
import logging
import shutil
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from custom_components.ramses_extras.config_flow import (
    RamsesExtrasConfigFlow,
    RamsesExtrasOptionsFlowHandler,
    _copy_card_files_config_flow,
    _get_feature_details_from_module,
    _install_card_config_flow,
    _manage_cards_config_flow,
    _remove_card_config_flow,
)
from custom_components.ramses_extras.const import (
    AVAILABLE_FEATURES,
    CONF_ENABLED_FEATURES,
    DOMAIN,
)


class MockDevice:
    """Helper class for mocking device objects with real attributes."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestRamsesExtrasConfigFlow:
    """Test RamsesExtrasConfigFlow class."""

    @pytest.mark.asyncio
    async def test_async_step_user(self, hass):
        """Test user step branches."""
        # Already configured
        with patch.object(
            hass.config_entries, "async_entries", return_value=[MagicMock()]
        ):
            flow = RamsesExtrasConfigFlow()
            flow.hass = hass
            result = await flow.async_step_user()
            assert result["type"] == "abort"
            assert result["reason"] == "single_instance_allowed"

        # Create entry
        with patch.object(hass.config_entries, "async_entries", return_value=[]):
            flow = RamsesExtrasConfigFlow()
            flow.hass = hass
            result = await flow.async_step_user()
            assert result["type"] == "create_entry"
            assert result["title"] == "Ramses Extras"

    def test_async_get_options_flow(self):
        """Test getting options flow handler."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasConfigFlow.async_get_options_flow(mock_config_entry)
        assert isinstance(options_flow, RamsesExtrasOptionsFlowHandler)


class TestRamsesExtrasOptionsFlowHandler:
    """Test RamsesExtrasOptionsFlowHandler core logic and coverage branches."""

    @pytest.mark.asyncio
    async def test_main_menu_and_view_config(self, hass):
        """Test main menu and view configuration steps."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_ENABLED_FEATURES: {"default": True, "sensor_control": True}
        }
        mock_config_entry.options = {}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass
        hass.config.language = "en"

        with (
            patch.object(
                options_flow,
                "_get_feature_title_from_translations",
                return_value="Title",
            ),
            patch(
                "custom_components.ramses_extras.config_flow._LOGGER.isEnabledFor",
                return_value=True,
            ),
            patch.object(options_flow, "_refresh_config_entry"),
        ):
            result = await options_flow.async_step_main_menu()
            assert result["type"] == "menu"

        result = await options_flow.async_step_view_configuration()
        assert result["type"] == "form"
        assert "Current Configuration" in result["description_placeholders"]["info"]

    @pytest.mark.asyncio
    async def test_features_step(self, hass):
        """Test features selection step."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            CONF_ENABLED_FEATURES: {"default": True, "sensor_control": False}
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            helper_inst = mock_helper.return_value
            helper_inst.get_feature_selection_schema.return_value = vol.Schema({})

            # Show form
            result = await options_flow.async_step_features(None)
            assert result["type"] == "form"

            # Submit
            with patch.object(options_flow, "async_step_confirm") as mock_confirm:
                mock_confirm.return_value = {"type": "form"}
                await options_flow.async_step_features({"features": ["sensor_control"]})
                assert options_flow._feature_changes_detected is True
                mock_confirm.assert_called_once()

    @pytest.mark.asyncio
    async def test_advanced_settings_persists_options(self, hass):
        mock_config_entry = MagicMock()
        mock_config_entry.data = {CONF_ENABLED_FEATURES: {"default": True}}
        mock_config_entry.options = {"debug_mode": False, "log_level": "info"}

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        with (
            patch.object(
                options_flow,
                "async_step_main_menu",
                return_value={"type": "menu"},
            ),
            patch.object(options_flow, "_refresh_config_entry"),
            patch.object(hass.config_entries, "async_update_entry") as mock_update,
        ):
            result = await options_flow.async_step_advanced_settings(
                {"frontend_log_level": "debug", "log_level": "debug"}
            )
            assert result["type"] == "menu"

            args, kwargs = mock_update.call_args
            assert kwargs["options"]["frontend_log_level"] == "debug"
            assert kwargs["options"]["debug_mode"] is True
            assert kwargs["options"]["log_level"] == "debug"

    @pytest.mark.asyncio
    async def test_advanced_settings_defaults_from_options(self, hass):
        mock_config_entry = MagicMock()
        mock_config_entry.data = {CONF_ENABLED_FEATURES: {"default": True}}
        mock_config_entry.options = {
            "frontend_log_level": "warning",
            "log_level": "warning",
        }

        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        with patch.object(options_flow, "_refresh_config_entry"):
            result = await options_flow.async_step_advanced_settings(None)

        assert result["type"] == "form"
        schema = result["data_schema"]
        assert isinstance(schema, vol.Schema)

        frontend_key = vol.Optional("frontend_log_level", default="warning")
        log_key = vol.Optional("log_level", default="warning")
        assert frontend_key in schema.schema
        assert log_key in schema.schema

    @pytest.mark.asyncio
    async def test_confirm_step_branches(self, hass):
        """Test confirmation step logic branches (lines 592-601, 626-633, 650-659)."""
        mock_config_entry = MagicMock()
        mock_config_entry.data = {
            "enabled_features": {"default": True, "sensor_control": True},
            "device_feature_matrix": {"device1": {"sensor_control": True}},
        }
        mock_config_entry.options = {
            "device_feature_matrix": {"device1": {"sensor_control": True}},
            "sensor_control": {
                "sources": {"dev1": {"m1": {"kind": "external", "entity_id": "ent1"}}}
            },
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        # Scenario: Disabling sensor_control
        options_flow._pending_data = {
            "enabled_features_new": {"default": True, "sensor_control": False}
        }

        # Show form
        with patch.object(options_flow, "_get_config_flow_helper") as mock_helper:
            mock_helper.return_value.get_feature_device_summary.return_value = "Summary"
            result = await options_flow.async_step_confirm(None)
            info = result["description_placeholders"]["info"]
            assert "sensor_control" in info.lower()

        # Confirm changes
        with (
            patch.object(hass.config_entries, "async_update_entry") as mock_update,
            patch.object(
                options_flow, "async_step_main_menu", return_value={"type": "menu"}
            ),
            patch(
                "custom_components.ramses_extras.config_flow._manage_cards_config_flow"
            ),
            patch("custom_components.ramses_extras._cleanup_orphaned_devices"),
        ):
            await options_flow.async_step_confirm({"confirm": True})
            args, kwargs = mock_update.call_args
            # Verify matrix was cleaned
            assert (
                "sensor_control"
                not in kwargs["options"]["device_feature_matrix"]["device1"]
            )

    @pytest.mark.asyncio
    async def test_sensor_control_overview_metrics(self, hass):
        """Test sensor control overview metric variations."""
        mock_config_entry = MagicMock()
        mock_config_entry.options = {
            "sensor_control": {
                "sources": {
                    "device_1": {
                        "indoor_temperature": {"kind": "external"},
                        "co2": {"kind": "derived"},
                        "outdoor_humidity": {"kind": "none"},
                        "indoor_humidity": {"kind": "other"},
                    }
                },
                "abs_humidity_inputs": {
                    "device_1": {
                        "indoor_abs_humidity": {
                            "temperature": {"kind": "external_abs"},
                            "humidity": {"kind": "none"},
                        },
                        "outdoor_abs_humidity": {
                            "temperature": {
                                "kind": "external",
                                "entity_id": "sensor.t",
                            },
                            "humidity": {"kind": "external", "entity_id": "sensor.h"},
                        },
                    },
                    "device_2": {},
                },
            }
        }
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass

        result = await options_flow.async_step_sensor_control_overview()
        info = result["description_placeholders"]["info"]
        assert "derived" in info
        assert "disabled" in info
        assert "external abs" in info

    @pytest.mark.asyncio
    async def test_generic_step_logic(self, hass):
        """Test generic_step_feature_config branches."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass
        options_flow._selected_feature = "sensor_control"

        with (
            patch.object(
                options_flow, "_get_all_devices", return_value=[MockDevice(id="dev1")]
            ),
            patch.object(options_flow, "_get_config_flow_helper") as mock_get_helper,
            patch.object(
                options_flow,
                "_get_persisted_matrix_state",
                return_value={"dev1": {"sensor_control": True}},
            ),
            patch.object(options_flow, "_get_device_label", return_value="Label"),
            patch.object(options_flow, "_extract_device_id", return_value="dev1"),
        ):
            mock_helper = mock_get_helper.return_value
            mock_helper.get_devices_for_feature_selection.return_value = [
                MockDevice(id="dev1")
            ]
            mock_helper.get_enabled_devices_for_feature.return_value = ["dev1"]
            mock_helper.get_feature_device_matrix_state.return_value = {
                "dev1": {"sensor_control": True}
            }

            # PRE
            result = await options_flow.generic_step_feature_config(None)
            assert result["type"] == "form"

            # POST - Fix subscriptable error by returning dict
            with patch.object(
                options_flow,
                "_show_matrix_based_confirmation",
                return_value={"type": "form"},
            ):
                result = await options_flow.generic_step_feature_config(
                    {"enabled_devices": ["dev1"]}
                )
                assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_async_step_device_selection(self, hass):
        """Test async_step_device_selection branches."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass
        options_flow._selected_feature = "sensor_control"

        with (
            patch.object(
                options_flow, "_get_all_devices", return_value=[MockDevice(id="dev1")]
            ),
            patch.object(options_flow, "_get_config_flow_helper") as mock_get_helper,
            patch.object(options_flow, "_extract_device_id", return_value="dev1"),
            patch.object(options_flow, "_get_device_label", return_value="Label"),
        ):
            mock_helper = mock_get_helper.return_value
            mock_helper.get_devices_for_feature_selection.return_value = [
                MockDevice(id="dev1")
            ]
            mock_helper.get_enabled_devices_for_feature.return_value = ["dev1"]

            result = await options_flow.async_step_device_selection()
            assert result["type"] == "form"
            assert result["step_id"] == "device_selection"

    @pytest.mark.asyncio
    async def test_matrix_confirmation_logic(self, hass):
        """Test matrix-based confirmation building."""
        mock_config_entry = MagicMock()
        options_flow = RamsesExtrasOptionsFlowHandler(mock_config_entry)
        options_flow.hass = hass
        options_flow._selected_feature = "sensor_control"

        # Pre-computed
        options_flow._matrix_entities_to_create = ["s1"]
        options_flow._matrix_entities_to_remove = ["r1"]
        result = await options_flow._show_matrix_based_confirmation()
        assert "s1" in result["description_placeholders"]["info"]

        # Fallback
        delattr(options_flow, "_matrix_entities_to_create")
        options_flow._temp_matrix_state = {}
        with (
            patch(
                "custom_components.ramses_extras.config_flow.SimpleEntityManager"
            ) as mock_em_cls,
            patch.object(options_flow, "_get_config_flow_helper") as mock_get_helper,
            patch.object(options_flow, "_get_all_devices", return_value=[]),
        ):
            mock_em = mock_em_cls.return_value
            mock_em.calculate_entity_changes = AsyncMock(
                return_value=(["new"], ["old"])
            )
            mock_em._calculate_required_entities = AsyncMock(return_value=[])
            mock_em._get_current_entities = AsyncMock(return_value=[])
            mock_helper = mock_get_helper.return_value
            mock_helper.get_enabled_devices_for_feature.return_value = []
            mock_matrix = MagicMock()
            mock_helper.device_feature_matrix = mock_matrix
            mock_matrix.get_all_enabled_combinations.return_value = []

            result = await options_flow._show_matrix_based_confirmation()
            assert "new" in result["description_placeholders"]["info"]

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_devices(self, hass):
        """Test orphaned device removal logic."""
        config_entry = SimpleNamespace(entry_id="ramses_extras_cleanup_entry")
        options_flow = RamsesExtrasOptionsFlowHandler(config_entry)
        options_flow.hass = hass

        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)
        with patch.object(
            hass.config_entries,
            "async_get_entry",
            return_value=SimpleNamespace(entry_id=config_entry.entry_id),
        ):
            device_entry = device_registry.async_get_or_create(
                config_entry_id=config_entry.entry_id,
                identifiers={(DOMAIN, "cleanup_test_device")},
                name="Test Device",
            )
        # Ensure the cleanup path considers this device orphaned
        entity_registry.entities.pop(device_entry.id, None)

        with patch(
            "custom_components.ramses_extras.config_flow._LOGGER"
        ) as mock_logger:
            await options_flow._cleanup_orphaned_devices({}, {})
            assert any(
                "Device cleanup: function called" in str(call)
                for call in mock_logger.debug.call_args_list
            )

    def test_device_helpers(self):
        """Test device ID and label helpers."""
        options_flow = RamsesExtrasOptionsFlowHandler(MagicMock())
        assert options_flow._extract_device_id("ID") == "ID"
        assert options_flow._extract_device_id(MockDevice(id="ID")) == "ID"
        assert options_flow._extract_device_id(MockDevice(device_id="DID")) == "DID"
        assert options_flow._extract_device_id(MockDevice(_id="PID")) == "PID"
        assert options_flow._extract_device_id(MockDevice(name="NAME")) == "NAME"

        with patch(
            "custom_components.ramses_extras.framework.helpers.device.filter.DeviceFilter._get_device_slugs",
            return_value=["SLUG"],
        ):
            label = options_flow._get_device_label(MockDevice(name="NAME"))
            assert "SLUG" in label

    @pytest.mark.asyncio
    async def test_card_management(self, hass):
        """Test card management helper paths."""
        with (
            patch(
                "custom_components.ramses_extras.extras_registry.extras_registry.get_card_config",
                return_value={"location": "loc"},
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch("custom_components.ramses_extras.config_flow._LOGGER") as mock_logger,
        ):
            await _manage_cards_config_flow(hass, {"hvac_fan_card": True})
            # Check logger calls directly
            assert any(
                "automatically registered" in str(call)
                for call in mock_logger.info.call_args_list
            )

    def test_copy_card_files(self, tmp_path):
        """Test file copying logic fully."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "f.txt").write_text("content")
        dst = tmp_path / "dst"
        _copy_card_files_config_flow(src, dst)
        assert (dst / "f.txt").read_text() == "content"

    @pytest.mark.asyncio
    async def test_translations_and_reloads(self, hass):
        """Test translation loading and reload helpers."""
        mock_entry = MagicMock()
        mock_entry.entry_id = "test"
        options_flow = RamsesExtrasOptionsFlowHandler(mock_entry)
        options_flow.hass = hass
        hass.config.language = "en"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", MagicMock()),
            patch(
                "json.load",
                return_value={"config": {"step": {"feature_f": {"title": "T"}}}},
            ),
        ):
            with patch.object(hass, "async_add_executor_job", create=True):
                if hasattr(hass, "async_add_executor_job"):
                    delattr(hass, "async_add_executor_job")
                assert (
                    await options_flow._get_feature_title_from_translations("f") == "T"
                )

        with patch.object(
            options_flow, "_direct_platform_reload", new_callable=AsyncMock
        ) as mock_direct:
            await options_flow._reload_platforms_for_entity_creation()
            mock_direct.assert_called_once()

    @pytest.mark.asyncio
    async def test_direct_platform_reload_error(self, hass):
        mock_entry = SimpleNamespace(entry_id="entry1")
        options_flow = RamsesExtrasOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        with patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(side_effect=Exception("boom")),
        ):
            await options_flow._direct_platform_reload()

    @pytest.mark.asyncio
    async def test_feature_default_success_and_error(self, hass):
        mock_entry = SimpleNamespace(entry_id="entry1")
        options_flow = RamsesExtrasOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        with patch(
            "custom_components.ramses_extras.features.default.config_flow."
            "async_step_default_config",
            new=AsyncMock(return_value={"type": "form"}),
        ):
            result = await options_flow.async_step_feature_default()
            assert result["type"] == "form"
            assert options_flow._selected_feature == "default"

        with (
            patch(
                "custom_components.ramses_extras.features.default.config_flow."
                "async_step_default_config",
                new=AsyncMock(side_effect=Exception("boom")),
            ),
            patch.object(
                options_flow,
                "async_step_main_menu",
                new=AsyncMock(return_value={"type": "menu"}),
            ),
        ):
            result = await options_flow.async_step_feature_default()
            assert result["type"] == "menu"

    @pytest.mark.asyncio
    async def test_feature_config_routing_paths(self, hass):
        mock_entry = MagicMock()
        mock_entry.data = {"enabled_features": {"default": True}}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_entry)
        options_flow.hass = hass

        with patch.object(
            options_flow,
            "async_step_main_menu",
            new=AsyncMock(return_value={"type": "menu"}),
        ):
            options_flow._selected_feature = None
            result = await options_flow.async_step_feature_config()
            assert result["type"] == "menu"

        async def _feature_async(handler, user_input):
            return {"type": "form", "step_id": "feature_async"}

        module_name = (
            "custom_components.ramses_extras.features.sensor_control.config_flow"
        )
        feature_module = ModuleType("feature_module")
        feature_module.async_step_sensor_control_config = _feature_async

        original_import = builtins.__import__

        def _import_side_effect(name, globals=None, locals=None, fromlist=(), level=0):
            if name == module_name:
                return feature_module
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_import_side_effect):
            options_flow._selected_feature = "sensor_control"
            result = await options_flow.async_step_feature_config()
            assert result["type"] == "form"
            assert result["step_id"] == "feature_async"

        with (
            patch("builtins.__import__", side_effect=ImportError()),
            patch.object(
                options_flow,
                "generic_step_feature_config",
                new=AsyncMock(return_value={"type": "form", "step_id": "generic"}),
            ) as mock_generic,
        ):
            options_flow._selected_feature = "sensor_control"
            result = await options_flow.async_step_feature_config()
            assert result["step_id"] == "generic"
            assert mock_generic.called

        with (
            patch("builtins.__import__", side_effect=Exception("boom")),
            patch.object(
                options_flow,
                "generic_step_feature_config",
                new=AsyncMock(return_value={"type": "form", "step_id": "generic2"}),
            ) as mock_generic,
        ):
            options_flow._selected_feature = "sensor_control"
            result = await options_flow.async_step_feature_config()
            assert result["step_id"] == "generic2"
            assert mock_generic.called

    @pytest.mark.asyncio
    async def test_matrix_confirm_paths(self, hass):
        mock_entry = MagicMock()
        mock_entry.entry_id = "entry1"
        mock_entry.options = {"other": 1}
        mock_entry.data = {}
        options_flow = RamsesExtrasOptionsFlowHandler(mock_entry)
        options_flow.hass = hass
        options_flow._selected_feature = "sensor_control"
        options_flow._temp_matrix_state = {"d1": {"sensor_control": True}}
        options_flow._old_matrix_state = {"d1": {"sensor_control": False}}

        helper = MagicMock()
        helper.restore_matrix_state = MagicMock()

        with (
            patch.object(options_flow, "_get_config_flow_helper", return_value=helper),
            patch.object(
                hass.config_entries, "async_get_entry", return_value=mock_entry
            ),
            patch.object(hass.config_entries, "async_update_entry", new=MagicMock()),
            patch(
                "custom_components.ramses_extras.config_flow.SimpleEntityManager"
            ) as mock_em_cls,
            patch(
                "custom_components.ramses_extras._cleanup_orphaned_devices",
                new=AsyncMock(),
            ),
            patch.object(hass.config_entries, "async_reload", new=AsyncMock()),
        ):
            mock_em = mock_em_cls.return_value
            mock_em.restore_device_feature_matrix_state = MagicMock()
            mock_em.calculate_entity_changes = AsyncMock(return_value=(["c1"], ["r1"]))
            mock_em.remove_entity = AsyncMock(side_effect=Exception("boom"))

            result = await options_flow.async_step_matrix_confirm({"confirm": True})
            assert result["type"] == "create_entry"
            assert result["data"]["other"] == 1
            assert (
                result["data"]["device_feature_matrix"]["d1"]["sensor_control"] is True
            )

        with patch.object(
            options_flow,
            "_show_matrix_based_confirmation",
            new=AsyncMock(return_value={"type": "form"}),
        ):
            result = await options_flow.async_step_matrix_confirm(None)
            assert result["type"] == "form"

        options_flow._temp_matrix_state = {"d1": {"sensor_control": True}}
        with (
            patch(
                "custom_components.ramses_extras.config_flow.SimpleEntityManager"
            ) as mock_em_cls,
            patch.object(
                options_flow,
                "_show_matrix_based_confirmation",
                new=AsyncMock(return_value={"type": "form"}),
            ),
        ):
            mock_em = mock_em_cls.return_value
            mock_em.calculate_entity_changes = AsyncMock(side_effect=Exception("boom"))
            result = await options_flow.async_step_matrix_confirm({"confirm": True})
            assert result["type"] == "form"

    @pytest.mark.asyncio
    async def test_card_helpers_unhappy_paths(self, hass, tmp_path):
        with (
            patch(
                "custom_components.ramses_extras.extras_registry.extras_registry."
                "get_card_config",
                return_value={"location": "loc"},
            ),
            patch("pathlib.Path.exists", return_value=False),
            patch("custom_components.ramses_extras.config_flow._LOGGER") as mock_logger,
        ):
            await _manage_cards_config_flow(hass, {"hvac_fan_card": True})
            assert mock_logger.warning.called

        missing_path = tmp_path / "missing"
        with patch(
            "custom_components.ramses_extras.config_flow._LOGGER"
        ) as mock_logger:
            await _remove_card_config_flow(hass, missing_path)
            assert mock_logger.debug.called

        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        dst.mkdir()
        (src / "f.txt").write_text("content")
        hass.async_add_executor_job = AsyncMock(side_effect=Exception("boom"))
        with patch(
            "custom_components.ramses_extras.config_flow._LOGGER"
        ) as mock_logger:
            await _install_card_config_flow(hass, src, dst)
            assert mock_logger.error.called

    def test_standalone_helpers(self):
        """Test standalone helpers coverage."""
        assert _get_feature_details_from_module("non_existent") == {}
        details = _get_feature_details_from_module("sensor_control")
        assert "HvacVentilator" in details["supported_device_types"]
