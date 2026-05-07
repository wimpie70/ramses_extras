"""Tests for profile_loader.py."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from custom_components.ramses_extras.features.device_simulator.profile_loader import (
    _ensure_hgi_entry,
    _reload_ramses_cc,
    _trigger_ramses_discovery,
    _update_known_list_and_reload,
    async_apply_profile,
    build_profile_from_payload,
    build_profile_from_yaml,
    parse_profile_yaml,
    profile_to_yaml,
)


class TestEnsureHgiEntry:
    """Test _ensure_hgi_entry function."""

    def test_ensure_hgi_entry_missing(self):
        """Test adding HGI entry when missing."""
        known_list = {"32:168270": {"class": "FAN"}}
        result = _ensure_hgi_entry(known_list)
        assert "18:001234" in result
        assert result["18:001234"]["class"] == "HGI"

    def test_ensure_hgi_entry_present(self):
        """Test when HGI entry already present."""
        known_list = {"18:001234": {"class": "HGI"}}
        result = _ensure_hgi_entry(known_list)
        assert "18:001234" in result
        assert result["18:001234"]["class"] == "HGI"


class TestParseProfileYaml:
    """Test parse_profile_yaml function."""

    def test_parse_profile_yaml_valid(self):
        """Test parsing valid YAML."""
        yaml_text = """
known_list:
  "32:168270":
    class: FAN
"""
        result = parse_profile_yaml(yaml_text)
        assert "known_list" in result
        assert "32:168270" in result["known_list"]

    def test_parse_profile_yaml_invalid_yaml(self):
        """Test parsing invalid YAML."""
        yaml_text = "invalid: yaml: content: [unclosed"
        with pytest.raises(ValueError, match="Invalid YAML"):
            parse_profile_yaml(yaml_text)

    def test_parse_profile_yaml_not_dict(self):
        """Test parsing YAML that is not a dict."""
        yaml_text = "just a string"
        with pytest.raises(ValueError, match="must define a mapping"):
            parse_profile_yaml(yaml_text)

    def test_parse_profile_yaml_empty_dict(self):
        """Test parsing empty YAML."""
        yaml_text = "{}"
        with pytest.raises(ValueError, match="must define a mapping"):
            parse_profile_yaml(yaml_text)


class TestBuildProfileFromPayload:
    """Test build_profile_from_payload function."""

    def test_build_profile_from_payload_basic(self):
        """Test building profile from basic payload."""
        payload = {
            "known_list": {
                "32:168270": {"class": "FAN"},
            }
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.name == "test_profile"
        assert "32:168270" in profile.device_configs["_known_list"]
        assert "18:001234" in profile.device_configs["_known_list"]

    def test_build_profile_from_payload_with_known_list_alt(self):
        """Test building profile with known_list (underscore variant)."""
        payload = {
            "_known_list": {
                "32:168270": {"class": "FAN"},
            }
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.name == "test_profile"
        assert "32:168270" in profile.device_configs["_known_list"]

    def test_build_profile_from_payload_no_known_list(self):
        """Test building profile without known_list."""
        payload = {"32:168270": {"class": "FAN"}}
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.name == "test_profile"
        assert "32:168270" in profile.device_configs["_known_list"]

    def test_build_profile_from_payload_empty_known_list(self):
        """Test building profile with empty known_list."""
        payload = {}
        with pytest.raises(ValueError, match="must include a 'known_list'"):
            build_profile_from_payload("test_profile", payload)

    def test_build_profile_from_payload_with_enforce_known_list(self):
        """Test building profile with enforce_known_list."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "_enforce_known_list": {"enabled": True},
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.device_configs["_enforce_known_list"]["enabled"] is True

    def test_build_profile_from_payload_default_enforce(self):
        """Test default enforce_known_list when not provided."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.device_configs["_enforce_known_list"]["enabled"] is True

    def test_build_profile_from_payload_with_schema(self):
        """Test building profile with schema."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"32:168270": {"zones": ["zone1"]}},  # Internal format
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.device_configs["_schema"]["32:168270"]["zones"] == ["zone1"]

    def test_build_profile_from_payload_with_device_overrides(self):
        """Test building profile with device-specific overrides."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "32:168270": {"excluded_codes": ["1FC9"]},
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.device_configs["32:168270"]["excluded_codes"] == ["1FC9"]

    def test_build_profile_from_payload_with_timeout_scale(self):
        """Test building profile with timeout_scale."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "timeout_scale": 2.0,
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.timeout_scale == 2.0

    def test_build_profile_from_payload_invalid_timeout_scale(self):
        """Test building profile with invalid timeout_scale."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "timeout_scale": "invalid",
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.timeout_scale == 1.0

    def test_build_profile_from_payload_with_description(self):
        """Test building profile with description."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "description": "Test profile",
        }
        profile = build_profile_from_payload("test_profile", payload)
        assert profile.description == "Test profile"

    def test_build_profile_from_payload_custom_description(self):
        """Test building profile with custom description parameter."""
        payload = {
            "known_list": {"32:168270": {"class": "FAN"}},
            "description": "Original",
        }
        profile = build_profile_from_payload(
            "test_profile", payload, description="Custom"
        )
        assert profile.description == "Custom"


class TestBuildProfileFromYaml:
    """Test build_profile_from_yaml function."""

    def test_build_profile_from_yaml_valid(self):
        """Test building profile from valid YAML."""
        yaml_text = """
known_list:
  "32:168270":
    class: FAN
"""
        profile = build_profile_from_yaml("test_profile", yaml_text)
        assert profile.name == "test_profile"
        assert profile.source_yaml == yaml_text
        assert "32:168270" in profile.device_configs["_known_list"]


class TestProfileToYaml:
    """Test profile_to_yaml function."""

    def test_profile_to_yaml_with_source_yaml(self):
        """Test profile_to_yaml when source_yaml exists."""
        profile = MagicMock()
        profile.source_yaml = "original yaml"
        profile.device_configs = {}
        result = profile_to_yaml(profile)
        assert result == "original yaml"

    def test_profile_to_yaml_without_source_yaml(self):
        """Test profile_to_yaml without source_yaml."""
        profile = MagicMock()
        profile.source_yaml = None
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_enforce_known_list": {"enabled": True},
        }
        profile.description = "Test profile"
        profile.timeout_scale = 1.0

        result = profile_to_yaml(profile)
        assert "known_list" in result
        assert "_enforce_known_list" in result
        assert profile.source_yaml == result

    def test_profile_to_yaml_with_schema(self):
        """Test profile_to_yaml with schema."""
        profile = MagicMock()
        profile.source_yaml = None
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"test": "schema"},
        }
        profile.description = None
        profile.timeout_scale = 1.0

        result = profile_to_yaml(profile)
        assert "_schema" in result

    def test_profile_to_yaml_with_device_overrides(self):
        """Test profile_to_yaml with device overrides."""
        profile = MagicMock()
        profile.source_yaml = None
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "32:168270": {"excluded_codes": ["1FC9"]},
        }
        profile.description = None
        profile.timeout_scale = 1.0

        result = profile_to_yaml(profile)
        assert "32:168270" in result

    def test_profile_to_yaml_with_custom_timeout_scale(self):
        """Test profile_to_yaml with custom timeout_scale."""
        profile = MagicMock()
        profile.source_yaml = None
        profile.device_configs = {"_known_list": {"32:168270": {"class": "FAN"}}}
        profile.description = None
        profile.timeout_scale = 2.0

        result = profile_to_yaml(profile)
        assert "timeout_scale" in result


class TestTriggerRamsesDiscovery:
    """Test _trigger_ramses_discovery function."""

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_success(self):
        """Test successful ramses_cc discovery trigger."""
        hass = MagicMock()
        coordinator = MagicMock()
        discover = AsyncMock()
        coordinator._async_discovery_task = discover
        hass.data = {"ramses_cc": {"entry_id": coordinator}}
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(
            return_value=[MagicMock(entry_id="entry_id")]
        )

        await _trigger_ramses_discovery(hass)
        discover.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_no_entries(self):
        """Test when no ramses_cc entries exist."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[])

        await _trigger_ramses_discovery(hass)
        # Should not raise

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_no_coordinator(self):
        """Test when coordinator is None."""
        hass = MagicMock()
        hass.data = {"ramses_cc": {}}
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(
            return_value=[MagicMock(entry_id="entry_id")]
        )

        await _trigger_ramses_discovery(hass)
        # Should not raise

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_no_discover_attr(self):
        """Test when discover attribute is not callable."""
        hass = MagicMock()
        coordinator = MagicMock()
        coordinator._async_discovery_task = None
        hass.data = {"ramses_cc": {"entry_id": coordinator}}
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(
            return_value=[MagicMock(entry_id="entry_id")]
        )

        await _trigger_ramses_discovery(hass)
        # Should not raise

    @pytest.mark.asyncio
    async def test_trigger_ramses_discovery_exception(self):
        """Test exception handling."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(
            side_effect=Exception("test error")
        )

        await _trigger_ramses_discovery(hass)
        # Should not raise


class TestUpdateKnownListAndReload:
    """Test _update_known_list_and_reload function."""

    @pytest.mark.asyncio
    async def test_update_known_list_and_reload_success(self):
        """Test successful update and reload."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"known_list": {}, "ramses_rf": {}}
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_setup = AsyncMock()
        hass.async_create_task = MagicMock()

        with patch("homeassistant.helpers.storage.Store") as mock_store_class:
            mock_store = MagicMock()
            mock_store.async_load = AsyncMock(
                return_value={"entries": [{"entry_id": "test_entry"}]}
            )
            mock_store.async_save = AsyncMock()
            mock_store_class.return_value = mock_store

            result = await _update_known_list_and_reload(
                hass,
                {"32:168270": {"class": "FAN"}},
                {"enabled": False},
                True,
                auto_start_on_reload=True,
                schema={"01:150000": {"zones": {}}},
            )

            assert "updated_known_list" in result
            assert "reloading_ramses_cc" in result

    @pytest.mark.asyncio
    async def test_update_known_list_and_reload_no_entries(self):
        """Test when no ramses_cc entries exist."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[])

        result = await _update_known_list_and_reload(
            hass,
            {"32:168270": {"class": "FAN"}},
            {"enabled": False},
            True,
            schema={"01:150000": {"zones": {}}},
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_update_known_list_and_reload_no_reload(self):
        """Test update without reload."""
        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {"known_list": {}, "ramses_rf": {}}
        hass.config_entries = MagicMock()
        hass.config_entries.async_entries = MagicMock(return_value=[entry])
        hass.config_entries.async_update_entry = MagicMock()

        with patch("homeassistant.helpers.storage.Store") as mock_store_class:
            mock_store = MagicMock()
            mock_store.async_load = AsyncMock(
                return_value={"entries": [{"entry_id": "test_entry"}]}
            )
            mock_store.async_save = AsyncMock()
            mock_store_class.return_value = mock_store

            result = await _update_known_list_and_reload(
                hass,
                {"32:168270": {"class": "FAN"}},
                {"enabled": False},
                False,
                schema={"01:150000": {"zones": {}}},
            )

            assert "updated_known_list" in result
            assert "skipped_reload" in result


class TestReloadRamsesCc:
    """Test _reload_ramses_cc function."""

    @pytest.mark.asyncio
    async def test_reload_ramses_cc_with_wipe(self):
        """Test reload with schema wipe."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload = AsyncMock()
        hass.config_entries.async_setup = AsyncMock()
        hass.data = {"ramses_extras": {}}

        with patch("homeassistant.helpers.device_registry") as mock_dr:
            with patch("homeassistant.helpers.storage.Store") as mock_store_class:
                mock_dr.async_get = MagicMock(
                    return_value=MagicMock(
                        async_entries_for_config_entry=MagicMock(return_value=[])
                    )
                )
                mock_store = MagicMock()
                mock_store.async_load = AsyncMock(
                    return_value={"client_state": {"schema": {}, "packets": {}}}
                )
                mock_store.async_save = AsyncMock()
                mock_store_class.return_value = mock_store

                await _reload_ramses_cc(hass, "test_entry", True, {}, {})

                hass.config_entries.async_unload.assert_called_once_with("test_entry")
                hass.config_entries.async_setup.assert_called_once_with("test_entry")

    @pytest.mark.asyncio
    async def test_reload_ramses_cc_without_wipe(self):
        """Test reload without schema wipe."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload = AsyncMock()
        hass.config_entries.async_setup = AsyncMock()
        hass.data = {"ramses_extras": {}}

        await _reload_ramses_cc(hass, "test_entry", False, {}, {})

        hass.config_entries.async_unload.assert_called_once_with("test_entry")
        hass.config_entries.async_setup.assert_called_once_with("test_entry")


class TestAsyncApplyProfile:
    """Test async_apply_profile function."""

    @pytest.mark.asyncio
    async def test_async_apply_profile_success(self):
        """Test successful profile application."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_stop_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }
        profile.timeout_scale = 1.0

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ) as mock_reload:
            result = await async_apply_profile(hass, "test_profile", profile)

        mock_reload.assert_awaited_once()
        _, kwargs = mock_reload.await_args
        assert kwargs.get("auto_start_on_reload") is False
        assert kwargs.get("schema") == {"01:150000": {"zones": {}}}

        assert result["success"] is True
        assert "stopped_devices" in result["actions"]

    @pytest.mark.asyncio
    async def test_async_apply_profile_no_engine(self):
        """Test profile application without engine."""
        hass = MagicMock()
        hass.data = {"ramses_extras": {}}

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ) as mock_reload:
            result = await async_apply_profile(hass, "test_profile", profile)

        mock_reload.assert_awaited_once()
        _, kwargs = mock_reload.await_args
        assert kwargs.get("auto_start_on_reload") is False
        assert kwargs.get("schema") == {"01:150000": {"zones": {}}}

        assert result["success"] is True
        assert "stopped_devices" not in result["actions"]

    @pytest.mark.asyncio
    async def test_async_apply_profile_auto_start_opt_out(self):
        """Allow callers to disable auto-start when needed."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_stop_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }
        profile.timeout_scale = 1.0

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ) as mock_reload:
            await async_apply_profile(
                hass,
                "test_profile",
                profile,
                auto_start_devices=False,
            )

        mock_reload.assert_awaited_once()
        _, kwargs = mock_reload.await_args
        assert kwargs.get("auto_start_on_reload") is False

    @pytest.mark.asyncio
    async def test_async_apply_profile_with_custom_speed(self):
        """Test profile application with custom speed."""
        hass = MagicMock()
        engine = MagicMock()
        engine.async_stop_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }
        profile.timeout_scale = 1.0

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ) as mock_reload:
            result = await async_apply_profile(hass, "test_profile", profile, speed=2.0)

        mock_reload.assert_awaited_once()
        _, kwargs = mock_reload.await_args
        assert kwargs.get("auto_start_on_reload") is False
        assert kwargs.get("schema") == {"01:150000": {"zones": {}}}

        assert result["success"] is True
        assert "timeout_scale=2.0" in result["actions"]

    @pytest.mark.asyncio
    async def test_async_apply_profile_without_schema_preload(self):
        """Schema payload should be omitted when preload_schema=False."""

        hass = MagicMock()
        engine = MagicMock()
        engine.async_stop_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }
        profile.timeout_scale = 1.0

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ) as mock_reload:
            await async_apply_profile(
                hass,
                "test_profile",
                profile,
                preload_schema=False,
            )

        mock_reload.assert_awaited_once()
        _, kwargs = mock_reload.await_args
        assert kwargs.get("schema") is None

    @pytest.mark.asyncio
    async def test_async_apply_profile_resets_rf_cache(self):
        """Verify optional RF cache clearing helper is invoked."""

        hass = MagicMock()
        engine = MagicMock()
        engine.async_stop_all = AsyncMock()
        hass.data = {"ramses_extras": {"device_simulator_engine": engine}}

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }
        profile.timeout_scale = 1.0

        with (
            patch(
                "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
                AsyncMock(return_value=["updated_known_list"]),
            ),
            patch(
                "custom_components.ramses_extras.features.device_simulator.profile_loader._clear_ramses_rf_cache",
                AsyncMock(),
            ) as mock_clear,
        ):
            await async_apply_profile(
                hass,
                "test_profile",
                profile,
                reset_rf_cache=True,
            )

        mock_clear.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_apply_profile_skip_rf_hydrate(self):
        """Ensure config_store remove_database flag is set when requested."""

        hass = MagicMock()
        engine = MagicMock()
        engine.async_stop_all = AsyncMock()
        config_store = MagicMock()
        config_store.set_remove_database = MagicMock()
        config_store.async_save_state = AsyncMock()
        hass.data = {
            "ramses_extras": {
                "device_simulator_engine": engine,
                "device_simulator_config_store": config_store,
            }
        }

        profile = MagicMock()
        profile.device_configs = {
            "_known_list": {"32:168270": {"class": "FAN"}},
            "_schema": {"01:150000": {"zones": {}}},
        }
        profile.timeout_scale = 1.0

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ):
            await async_apply_profile(
                hass,
                "test_profile",
                profile,
                skip_rf_hydrate=True,
            )

        config_store.set_remove_database.assert_called_once_with(True)
        config_store.async_save_state.assert_awaited_once()

        config_store.reset_mock()

        with patch(
            "custom_components.ramses_extras.features.device_simulator.profile_loader._update_known_list_and_reload",
            AsyncMock(return_value=["updated_known_list"]),
        ):
            await async_apply_profile(
                hass,
                "test_profile",
                profile,
                skip_rf_hydrate=False,
            )

        config_store.set_remove_database.assert_called_once_with(False)
        config_store.async_save_state.assert_awaited_once()
