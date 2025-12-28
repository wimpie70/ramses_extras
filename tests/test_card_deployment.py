import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras import (
    _cleanup_old_card_deployments,
    _copy_all_card_files,
)


@pytest.fixture
def mock_hass(tmp_path):
    """Mock HomeAssistant instance with a temporary config directory."""
    hass = MagicMock()
    hass.config = MagicMock()
    hass.config.config_dir = str(tmp_path)
    hass.data = {}
    return hass


@pytest.mark.asyncio
async def test_cleanup_old_card_deployments(mock_hass):
    """Test that old versioned directories are removed and legacy shims are created."""
    config_dir = Path(mock_hass.config.config_dir)
    www_dir = config_dir / "www" / "ramses_extras"
    www_dir.mkdir(parents=True)

    # Create some old versioned directories
    v1_dir = www_dir / "v1.0.0"
    v1_dir.mkdir()
    v2_dir = www_dir / "v2.0.0"
    v2_dir.mkdir()

    # Create current version directory
    current_version = "3.0.0"
    v3_dir = www_dir / "v3.0.0"
    v3_dir.mkdir()

    # Create legacy directories
    legacy_helpers = www_dir / "helpers"
    legacy_helpers.mkdir()
    legacy_features = www_dir / "features" / "hello_world"
    legacy_features.mkdir(parents=True)

    await _cleanup_old_card_deployments(mock_hass, current_version)

    # Old versions should be gone
    assert not v1_dir.exists()
    assert not v2_dir.exists()

    # Current version should remain
    assert v3_dir.exists()

    # Legacy shims should be created
    assert (legacy_helpers / "main.js").exists()
    assert (legacy_features / "hello-world.js").exists()

    shim_content = (legacy_helpers / "main.js").read_text()
    expected_shim = f'import "/local/ramses_extras/v{current_version}/helpers/main.js";'
    assert expected_shim in shim_content


@pytest.mark.asyncio
async def test_copy_all_card_files(mock_hass):
    """Test that card files are copied to the versioned directory."""
    current_version = "1.2.3"
    mock_hass.data["ramses_extras"] = {"_integration_version": current_version}

    # Use a simpler side effect for Path that just returns string-like mocks
    with patch("custom_components.ramses_extras.Path") as mock_path:

        def create_mock_path(path_input=""):
            m = MagicMock()
            # Use configure_mock to set the return value of __str__
            m.configure_mock(**{"__str__.return_value": str(path_input)})
            m.exists.return_value = True
            m.__truediv__.side_effect = lambda x: create_mock_path(
                f"{path_input}/{x}" if path_input else str(x)
            )
            return m

        mock_path.side_effect = create_mock_path

        with patch("shutil.copytree") as mock_copy:
            await _copy_all_card_files(mock_hass)

            # Check if copytree was called for each card
            assert mock_copy.call_count == 2

            # Verify destination paths include the version
            calls = mock_copy.call_args_list
            # Each call is copytree(src, dst, ...)
            # We get the string representation of the second argument
            dest_paths = [str(call[0][1]) for call in calls]

            assert any(f"v{current_version}" in path for path in dest_paths)
            assert any("hello_world" in path for path in dest_paths)
            assert any("hvac_fan_card" in path for path in dest_paths)
