import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ramses_extras.framework.setup.cards import (
    cleanup_old_card_deployments,
    copy_all_card_files,
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
    """Test that old versioned directories and legacy dirs are removed."""
    config_dir = Path(mock_hass.config.config_dir)
    www_dir = config_dir / "www" / "ramses_extras"
    www_dir.mkdir(parents=True)

    current_version = "3.0.0"

    # Create some old versioned directories
    version_dirs = [www_dir / "v1.0.0", www_dir / "v2.0.0", www_dir / "v3.0.0"]
    for version_dir in version_dirs:
        version_dir.mkdir()

    # Create stable directories that should remain
    stable_helpers = www_dir / "helpers"
    stable_helpers.mkdir()
    (stable_helpers / "file.txt").write_text("content")
    stable_features = www_dir / "features" / "hello_world"
    stable_features.mkdir(parents=True)

    await cleanup_old_card_deployments(mock_hass, current_version, [])

    # All versioned directories should be removed
    assert not any(version_dir.exists() for version_dir in version_dirs)

    # Stable directories should remain untouched
    assert stable_helpers.exists()
    assert stable_features.exists()


@pytest.mark.asyncio
async def test_copy_all_card_files(mock_hass):
    """Test that card files are copied to the versioned directory."""
    current_version = "1.2.3"
    mock_hass.data["ramses_extras"] = {"_integration_version": current_version}

    # Use a simpler side effect for Path that just returns string-like mocks
    with patch(
        "custom_components.ramses_extras.framework.setup.cards.Path"
    ) as mock_path:

        def create_mock_path(path_input=""):
            m = MagicMock()
            m.configure_mock(**{"__str__.return_value": str(path_input)})
            m.exists.return_value = True
            m.mkdir = MagicMock()
            m.rglob = MagicMock(return_value=[])
            m.__truediv__.side_effect = lambda x: create_mock_path(
                f"{path_input}/{x}" if path_input else str(x)
            )
            return m

        mock_path.side_effect = create_mock_path

        # Mock card features using the patched Path
        card_features = [
            {
                "feature_name": "hello_world",
                "source_dir": mock_path("/fake/source/hello_world"),
                "js_files": ["hello-world.js"],
            },
            {
                "feature_name": "hvac_fan_card",
                "source_dir": mock_path("/fake/source/hvac_fan_card"),
                "js_files": ["hvac-fan-card.js"],
            },
        ]

        with patch("shutil.copytree") as mock_copy:
            await copy_all_card_files(mock_hass, card_features)

            # Check if copytree was called for each card
            assert mock_copy.call_count == 2

            # Verify destination paths point to stable feature directories
            calls = mock_copy.call_args_list
            # Each call is copytree(src, dst, ...)
            # We get the string representation of the second argument
            dest_paths = [str(call[0][1]) for call in calls]

            assert any("hello_world" in path for path in dest_paths)
            assert any("hvac_fan_card" in path for path in dest_paths)
            assert all("/features/" in path for path in dest_paths)
