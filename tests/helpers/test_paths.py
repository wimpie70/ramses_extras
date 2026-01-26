"""Tests for framework/helpers/paths.py."""

from pathlib import Path

import pytest

from custom_components.ramses_extras.framework.helpers.paths import (
    DeploymentPaths,
    PathConstants,
    validate_path,
)


def test_path_constants():
    """Test PathConstants static methods."""
    assert (
        PathConstants.get_helper_path("test.js")
        == "/local/ramses_extras/helpers/test.js"
    )
    assert (
        PathConstants.get_feature_base_path("feat1")
        == "/local/ramses_extras/features/feat1"
    )
    assert (
        PathConstants.get_feature_path("feat1", "asset.js")
        == "/local/ramses_extras/features/feat1/asset.js"
    )
    assert (
        PathConstants.get_feature_path("feat1") == "/local/ramses_extras/features/feat1"
    )

    # Test get_feature_card_path
    assert (
        PathConstants.get_feature_card_path("feat1", "card.js")
        == "/local/ramses_extras/features/feat1/card.js"
    )
    assert (
        PathConstants.get_feature_card_path("feat1", "feat1/card.js")
        == "/local/ramses_extras/features/feat1/card.js"
    )

    # Test other helper methods
    assert (
        PathConstants.get_feature_template_path("feat1", "t.html")
        == "/local/ramses_extras/features/feat1/templates/t.html"
    )
    assert (
        PathConstants.get_feature_translation_path("feat1", "en")
        == "/local/ramses_extras/features/feat1/translations/en.json"
    )


def test_deployment_paths():
    """Test DeploymentPaths static methods."""
    config_dir = "/config"
    version = "1.0.0"

    # get_destination_root
    expected_root = Path("/config/www/ramses_extras")
    assert DeploymentPaths.get_destination_root(config_dir, version) == expected_root
    assert (
        DeploymentPaths.get_destination_root(Path(config_dir), version) == expected_root
    )

    # get_source_feature_path
    int_dir = Path("/int")
    assert DeploymentPaths.get_source_feature_path(int_dir, "feat1") == Path(
        "/int/features/feat1/www/feat1"
    )

    # get_destination_features_path
    assert DeploymentPaths.get_destination_features_path(config_dir, "feat1") == Path(
        "/config/www/ramses_extras/features/feat1"
    )
    assert (
        DeploymentPaths.get_destination_features_path(config_dir, "feat1", version)
        == expected_root / "features" / "feat1"
    )

    # get_destination_helpers_path
    assert DeploymentPaths.get_destination_helpers_path(config_dir) == Path(
        "/config/www/ramses_extras/helpers"
    )
    assert (
        DeploymentPaths.get_destination_helpers_path(config_dir, version)
        == expected_root / "helpers"
    )


def test_validate_path():
    """Test validate_path function."""
    assert validate_path("/valid/path") is True
    assert validate_path("invalid/path") is False
    assert validate_path("") is False
    assert validate_path(None) is False  # type: ignore[arg-type]
    assert validate_path(123) is False  # type: ignore[arg-type]
