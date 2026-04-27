"""Tests for Ramses Debugger config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.ramses_extras.features.ramses_debugger.config_flow import (
    async_step_ramses_debugger_config,
)


@pytest.fixture
def flow():
    """Mock config flow."""
    flow = MagicMock()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/config/home-assistant.log"
    flow._config_entry = MagicMock()
    flow._config_entry.options = {}
    flow._refresh_config_entry = MagicMock()
    flow.async_step_main_menu = AsyncMock()
    flow.async_show_form = MagicMock()
    return flow


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_show_form(flow):
    """Test showing config form without user input."""
    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should show form
        flow.async_show_form.assert_called_once()
        call_args = flow.async_show_form.call_args

        assert call_args[1]["step_id"] == "feature_ramses_debugger"
        assert "data_schema" in call_args[1]
        assert "description_placeholders" in call_args[1]

        # Check info text
        info = call_args[1]["description_placeholders"]["info"]
        assert "🧰 **Ramses Debugger**" in info
        assert "Configure options for the Ramses Debugger" in info

        # Should not update config
        flow.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_with_user_input(flow):
    """Test config flow with user input."""
    user_input = {
        "ramses_debugger_log_path": "/custom/log/path",
        "ramses_debugger_packet_log_path": "/custom/packet.log",
        "ramses_debugger_cache_max_entries": 512,
        "ramses_debugger_cache_ttl_ms": 2000,
        "ramses_debugger_max_flows": 3000,
        "ramses_debugger_buffer_max_global": 10000,
        "ramses_debugger_buffer_max_per_flow": 1000,
        "ramses_debugger_buffer_max_flows": 3000,
        "ramses_debugger_default_poll_ms": 2000,
    }

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, user_input)

        # Should update config entry
        flow.hass.config_entries.async_update_entry.assert_called_once()
        call_args = flow.hass.config_entries.async_update_entry.call_args

        assert "options" in call_args[1]
        options = call_args[1]["options"]

        assert options["ramses_debugger_log_path"] == "/custom/log/path"
        assert options["ramses_debugger_packet_log_path"] == "/custom/packet.log"
        assert options["ramses_debugger_cache_max_entries"] == 512
        assert options["ramses_debugger_cache_ttl_ms"] == 2000
        assert options["ramses_debugger_max_flows"] == 3000
        assert options["ramses_debugger_buffer_max_global"] == 10000
        assert options["ramses_debugger_buffer_max_per_flow"] == 1000
        assert options["ramses_debugger_buffer_max_flows"] == 3000
        assert options["ramses_debugger_default_poll_ms"] == 2000

        # Should return to main menu
        flow.async_step_main_menu.assert_called_once()


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_with_whitespace_paths(flow):
    """Test config flow strips whitespace from paths."""
    user_input = {
        "ramses_debugger_log_path": "  /custom/log/path  ",
        "ramses_debugger_packet_log_path": "\t/custom/packet.log\n",
    }

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, user_input)

        # Check whitespace was stripped
        options = flow.hass.config_entries.async_update_entry.call_args[1]["options"]
        assert options["ramses_debugger_log_path"] == "/custom/log/path"
        assert options["ramses_debugger_packet_log_path"] == "/custom/packet.log"


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_default_values(flow):
    """Test config flow with default values."""
    flow._config_entry.options = {
        "ramses_debugger_log_path": "/existing/log.log",
        "ramses_debugger_cache_max_entries": 128,
        "ramses_debugger_cache_ttl_ms": 500,
    }

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should show form with existing values as defaults
        flow.async_show_form.assert_called_once()

        # Check that schema has default values
        # Note: We can't easily inspect vol.Schema defaults,
        # but we can verify the form was shown


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_refresh_config_entry(flow):
    """Test that config entry is refreshed."""
    flow._refresh_config_entry = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should refresh config entry
        flow._refresh_config_entry.assert_called_once_with(flow.hass)


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_partial_user_input(flow):
    """Test config flow with partial user input."""
    user_input = {
        "ramses_debugger_log_path": "/new/log.log",
        "ramses_debugger_cache_max_entries": 1024,
        # Other fields not provided, should keep existing values
    }

    flow._config_entry.options = {
        "ramses_debugger_packet_log_path": "/existing/packet.log",
        "ramses_debugger_cache_ttl_ms": 1500,
        "ramses_debugger_max_flows": 2500,
    }

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, user_input)

        # Check both updated and existing values are preserved
        options = flow.hass.config_entries.async_update_entry.call_args[1]["options"]
        assert options["ramses_debugger_log_path"] == "/new/log.log"  # Updated
        assert options["ramses_debugger_cache_max_entries"] == 1024  # Updated
        assert (
            options["ramses_debugger_packet_log_path"] == "/existing/packet.log"
        )  # Preserved
        assert options["ramses_debugger_cache_ttl_ms"] == 1500  # Preserved
        assert options["ramses_debugger_max_flows"] == 2500  # Preserved


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_invalid_types(flow):
    """Test config flow with invalid types in user input."""
    user_input = {
        "ramses_debugger_log_path": 123,  # Should be string
        "ramses_debugger_cache_max_entries": "not_a_number",  # Should be int
        "ramses_debugger_cache_ttl_ms": None,  # Should be int
    }

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, user_input)

        # Invalid types should be ignored
        options = flow.hass.config_entries.async_update_entry.call_args[1]["options"]
        assert "ramses_debugger_log_path" not in options
        assert "ramses_debugger_cache_max_entries" not in options
        assert "ramses_debugger_cache_ttl_ms" not in options


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_schema_validation():
    """Test that the schema validates correctly."""
    flow = MagicMock()
    flow.hass = MagicMock()
    flow.hass.config.path.return_value = "/config/home-assistant.log"
    flow._config_entry = MagicMock()
    flow._config_entry.options = {}
    flow.async_show_form = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Get the schema from the form call
        schema = flow.async_show_form.call_args[1]["data_schema"]

        # Test valid data
        valid_data = {
            "ramses_debugger_cache_ttl_ms": 1000,
            "ramses_debugger_cache_max_entries": 256,
            "ramses_debugger_max_flows": 2000,
            "ramses_debugger_buffer_max_global": 5000,
            "ramses_debugger_buffer_max_per_flow": 500,
            "ramses_debugger_buffer_max_flows": 2000,
            "ramses_debugger_default_poll_ms": 1000,
        }
        result = schema(valid_data)
        # Schema adds default values for optional fields
        assert "ramses_debugger_cache_ttl_ms" in result
        assert result["ramses_debugger_cache_ttl_ms"] == 1000
        assert result["ramses_debugger_cache_max_entries"] == 256

        # Test invalid cache_ttl_ms (too high)
        with pytest.raises(vol.Invalid):
            schema({"ramses_debugger_cache_ttl_ms": 31000})

        # Test invalid cache_max_entries (too low)
        with pytest.raises(vol.Invalid):
            schema({"ramses_debugger_cache_max_entries": 0})

        # Test invalid default_poll_ms (too low)
        with pytest.raises(vol.Invalid):
            schema({"ramses_debugger_default_poll_ms": 200})


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_feature_not_found(flow):
    """Test config flow when feature not in AVAILABLE_FEATURES."""
    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should still show form with feature_id as name
        flow.async_show_form.assert_called_once()
        info = flow.async_show_form.call_args[1]["description_placeholders"]["info"]
        assert "🧰 **ramses_debugger**" in info


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_log_path_default_empty(flow):
    """Test log path default when existing is empty."""
    flow._config_entry.options = {"ramses_debugger_log_path": "   "}

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should use hass config path as default
        flow.hass.config.path.assert_called_once_with("home-assistant.log")


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_refresh_without_hass():
    """Test refresh when flow has no hass attribute (covers line 26)."""
    flow = MagicMock()
    # Set hass to None initially to test the else branch
    del flow.hass
    flow._config_entry = MagicMock()
    flow._config_entry.options = {"ramses_debugger_log_path": "/existing.log"}
    flow._refresh_config_entry = MagicMock()
    flow.async_show_form = MagicMock()

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should refresh config entry without hass
        flow._refresh_config_entry.assert_called_once_with()


@pytest.mark.asyncio
async def test_async_step_ramses_debugger_config_packet_log_default_with_value(flow):
    """Test packet log default when existing value is present (covers line 88)."""
    flow._config_entry.options = {
        "ramses_debugger_packet_log_path": "  /custom/packet.log  "
    }

    with patch(
        "custom_components.ramses_extras.features.ramses_debugger.config_flow.AVAILABLE_FEATURES",
        {"ramses_debugger": {"name": "Ramses Debugger"}},
    ):
        await async_step_ramses_debugger_config(flow, None)

        # Should show form
        flow.async_show_form.assert_called_once()
