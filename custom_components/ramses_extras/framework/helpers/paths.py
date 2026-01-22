"""
Shared Path Constants for Ramses Extras Python Files

Provides centralized path management for all Python modules,
ensuring consistent paths across development and production environments.

This module should be imported by any Python file that needs to
reference helpers or construct feature-specific paths for deployment.
"""

from pathlib import Path
from typing import Any


class PathConstants:
    """Centralized path constants for Ramses Extras."""

    # Base path constants - these work in both dev and production
    RAMSES_EXTRAS_BASE = "/local/ramses_extras"
    HELPERS_BASE = "/local/ramses_extras/helpers"
    FEATURES_BASE = "/local/ramses_extras/features"

    @staticmethod
    def get_helper_path(helper_file_name: str) -> str:
        """Get the full path for a helper file.

        Args:
            helper_file_name: Name of the helper file (e.g., 'card-commands.js')

        Returns:
            Full path to the helper file
        """
        return f"{PathConstants.HELPERS_BASE}/{helper_file_name}"

    @staticmethod
    def get_feature_base_path(feature_name: str) -> str:
        """Get the base path for a feature.

        Args:
            feature_name: Name of the feature (e.g., 'hvac_fan_card')

        Returns:
            Base path for the feature
        """
        return f"{PathConstants.FEATURES_BASE}/{feature_name}"

    @staticmethod
    def get_feature_path(feature_name: str, asset_path: str = "") -> str:
        """Get the full path for a feature-specific asset.

        Args:
            feature_name: Name of the feature
            asset_path: Relative path within the feature's www folder

        Returns:
            Full path to the feature asset
        """
        base_path = PathConstants.get_feature_base_path(feature_name)
        return f"{base_path}/{asset_path}" if asset_path else base_path

    @staticmethod
    def get_feature_card_path(feature_name: str, card_file_name: str) -> str:
        """Get the full path for a feature card file.

        Args:
            feature_name: Name of the feature
            card_file_name: Name of the card file (e.g., 'hvac-fan-card.js')

        Returns:
            Full path to the feature card
        """
        # Remove feature_name directory from card_file_name if present
        # to avoid double directory structure
        if card_file_name.startswith(f"{feature_name}/"):
            card_file_name = card_file_name[len(feature_name) + 1 :]
        return PathConstants.get_feature_path(feature_name, card_file_name)

    @staticmethod
    def get_feature_template_path(feature_name: str, template_path: str) -> str:
        """Get the full path for a feature template.

        Args:
            feature_name: Name of the feature
            template_path: Relative path within templates folder

        Returns:
            Full path to the feature template
        """
        return PathConstants.get_feature_path(
            feature_name, f"templates/{template_path}"
        )

    @staticmethod
    def get_feature_translation_path(feature_name: str, locale: str) -> str:
        """Get the full path for feature translations.

        Args:
            feature_name: Name of the feature
            locale: Language locale (e.g., 'en', 'nl')

        Returns:
            Full path to the translation file
        """
        return PathConstants.get_feature_path(
            feature_name, f"translations/{locale}.json"
        )


class HelperPaths:
    """Pre-defined helper file paths for easy access."""

    CARD_COMMANDS = PathConstants.get_helper_path("card-commands.js")
    CARD_SERVICES = PathConstants.get_helper_path("card-services.js")
    CARD_TRANSLATIONS = PathConstants.get_helper_path("card-translations.js")
    CARD_VALIDATION = PathConstants.get_helper_path("card-validation.js")
    RAMSES_MESSAGE_BROKER = PathConstants.get_helper_path("ramses-message-broker.js")
    PATHS_CONSTANTS = PathConstants.get_helper_path("paths.js")


class DeploymentPaths:
    """Paths specifically for deployment and file operations."""

    @staticmethod
    def get_destination_root(hass_config_dir: str | Path, version: str) -> Path:
        """Get the destination root path for versioned deployment.

        Args:
            hass_config_dir: Home Assistant config directory (can be string or Path)
            version: Integration version string (e.g. "0.13.0")

        Returns:
            Destination root path for this version.
        """

        if isinstance(hass_config_dir, str):
            hass_config_dir = Path(hass_config_dir)

        version_dir = f"v{version}"
        return hass_config_dir / "www" / "ramses_extras" / version_dir

    @staticmethod
    def get_source_feature_path(integration_dir: Path, feature_name: str) -> Path:
        """Get the source path for feature files in the integration directory.

        Args:
            integration_dir: Path to the integration directory
            feature_name: Name of the feature

        Returns:
            Source path for feature files
        """
        return integration_dir / "features" / feature_name / "www" / feature_name

    @staticmethod
    def get_destination_features_path(
        hass_config_dir: str | Path,
        feature_name: str,
        version: str | None = None,
    ) -> Path:
        """Get the destination path for feature deployment.

        Args:
            hass_config_dir: Home Assistant config directory (can be string or Path)
            feature_name: Name of the feature

        Returns:
            Destination path for feature deployment
        """

        if version is None:
            if isinstance(hass_config_dir, str):
                hass_config_dir = Path(hass_config_dir)
            return hass_config_dir / "www" / "ramses_extras" / "features" / feature_name

        root = DeploymentPaths.get_destination_root(hass_config_dir, version)
        return root / "features" / feature_name

    @staticmethod
    def get_destination_helpers_path(
        hass_config_dir: str | Path,
        version: str | None = None,
    ) -> Path:
        """Get the destination path for helper files deployment.

        Args:
            hass_config_dir: Home Assistant config directory (can be string or Path)

        Returns:
            Destination path for helper files
        """

        if version is None:
            if isinstance(hass_config_dir, str):
                hass_config_dir = Path(hass_config_dir)
            return hass_config_dir / "www" / "ramses_extras" / "helpers"

        root = DeploymentPaths.get_destination_root(hass_config_dir, version)
        return root / "helpers"


def validate_path(path: str) -> bool:
    """Validate that a path is properly formatted.

    Args:
        path: Path to validate

    Returns:
        True if path is valid
    """
    return isinstance(path, str) and len(path) > 0 and path.startswith("/")


# Convenience exports for easy importing
PATHS = PathConstants()
HELPER_PATHS = HelperPaths()
DEPLOYMENT_PATHS = DeploymentPaths()

__all__ = [
    "PathConstants",
    "HelperPaths",
    "DeploymentPaths",
    "PATHS",
    "HELPER_PATHS",
    "DEPLOYMENT_PATHS",
    "validate_path",
]
