"""Automation Manager for Ramses Extras integration."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import yaml

from ..const import AVAILABLE_FEATURES, INTEGRATION_DIR

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class AutomationManager:
    """Manages creation and removal of integration automations."""

    def __init__(self, hass: "HomeAssistant") -> None:
        """Initialize automation manager."""
        self.hass = hass
        self.automation_path = Path(hass.config.path("automations.yaml"))

    async def create_device_automations(
        self, device_ids: list[str], enabled_automations: list[str]
    ) -> None:
        """Create automations for enabled features and discovered devices."""
        _LOGGER.info(
            f"Creating automations for devices {device_ids} "
            f"with features {enabled_automations}"
        )

        if not device_ids or not enabled_automations:
            return

        try:
            for feature_key in enabled_automations:
                feature_config = AVAILABLE_FEATURES.get(feature_key)
                if (
                    not feature_config
                    or feature_config.get("category") != "automations"
                ):
                    continue

                template_location = feature_config.get("location")
                if not template_location:
                    _LOGGER.warning(f"No automation template for feature {feature_key}")
                    continue

                # Ensure template_location is a string
                if not isinstance(template_location, str):
                    _LOGGER.error(
                        "Template location for feature %s must be a string, got %s",
                        feature_key,
                        type(template_location),
                    )
                    continue

                await self._create_automations_from_template(
                    feature_key, template_location, device_ids
                )

        except Exception as e:
            _LOGGER.error(f"Failed to create automations: {e}")

    async def remove_device_automations(
        self, device_ids: list[str], disabled_automations: list[str]
    ) -> None:
        """Remove automations for disabled features."""
        _LOGGER.info(
            f"Removing automations for devices {device_ids}, "
            f"disabled features {disabled_automations}"
        )

        if not device_ids or not disabled_automations:
            return

        try:
            for feature_key in disabled_automations:
                await self._remove_automations_for_feature(feature_key, device_ids)

        except Exception as e:
            _LOGGER.error(f"Failed to remove automations: {e}")

    async def _create_automations_from_template(
        self, feature_key: str, template_location: str, device_ids: list[str]
    ) -> None:
        """Create automations from template for specific devices."""
        try:
            template_path = INTEGRATION_DIR / template_location

            if not template_path.exists():
                _LOGGER.error(f"Automation template not found: {template_path}")
                return

            # Read template
            def read_template() -> str:
                with open(template_path, encoding="utf-8") as f:
                    return f.read()

            template_content = await self.hass.async_add_executor_job(read_template)

            # Create automation for each device
            new_automations = []

            for device_id in device_ids:
                device_id_underscore = device_id.replace(":", "_")

                # Replace template variables
                device_automation_yaml = self._replace_template_variables(
                    template_content, device_id, device_id_underscore
                )

                # Parse YAML
                device_automation = yaml.safe_load(device_automation_yaml)
                if device_automation and isinstance(device_automation, list):
                    new_automations.extend(device_automation)

            if new_automations:
                await self._add_automations_to_file(new_automations)
                _LOGGER.info(
                    f"Created {len(new_automations)} automations "
                    f"for feature {feature_key}"
                )

        except Exception as e:
            _LOGGER.error(
                f"Failed to create automations from template {template_location}: {e}"
            )

    async def _remove_automations_for_feature(
        self, feature_key: str, device_ids: list[str]
    ) -> None:
        """Remove automations for a specific feature."""
        try:
            if not self.automation_path.exists():
                return

            # Read current automations
            def read_automations_file() -> str:
                with open(self.automation_path, encoding="utf-8") as f:
                    return f.read()

            content_str = await self.hass.async_add_executor_job(read_automations_file)
            content = yaml.safe_load(content_str)

            if not content:
                return

            # Handle both formats
            if isinstance(content, list):
                automations_to_filter = content
            elif isinstance(content, dict) and "automation" in content:
                automations_to_filter = content["automation"]
            else:
                return

            # Filter out automations for this feature
            filtered_automations = []

            for auto in automations_to_filter:
                automation_id = auto.get("id", "")
                should_remove = False

                # Check if automation belongs to this feature
                for device_id in device_ids:
                    device_pattern = f"_{device_id.replace(':', '_')}"
                    if feature_key in automation_id or device_pattern in automation_id:
                        should_remove = True
                        break

                if not should_remove:
                    filtered_automations.append(auto)

            # Write back if automations were removed
            if len(filtered_automations) != len(automations_to_filter):

                def write_automations_file() -> None:
                    if isinstance(content, list):
                        with open(self.automation_path, "w", encoding="utf-8") as f:
                            yaml.dump(
                                filtered_automations,
                                f,
                                default_flow_style=False,
                                sort_keys=False,
                            )
                    else:
                        content["automation"] = filtered_automations
                        with open(self.automation_path, "w", encoding="utf-8") as f:
                            yaml.dump(
                                content, f, default_flow_style=False, sort_keys=False
                            )

                await self.hass.async_add_executor_job(write_automations_file)
                _LOGGER.info(f"Removed automations for feature {feature_key}")

        except Exception as e:
            _LOGGER.error(
                f"Failed to remove automations for feature {feature_key}: {e}"
            )

    async def _add_automations_to_file(
        self, new_automations: list[dict[str, Any]]
    ) -> None:
        """Add new automations to the automations.yaml file."""
        try:
            if not self.automation_path.exists():
                # Create new file
                def create_automations_file() -> None:
                    with open(self.automation_path, "w", encoding="utf-8") as f:
                        yaml.dump(
                            new_automations,
                            f,
                            default_flow_style=False,
                            sort_keys=False,
                        )

                await self.hass.async_add_executor_job(create_automations_file)
                return

            # Read existing content
            def read_existing_automations() -> str:
                with open(self.automation_path, encoding="utf-8") as f:
                    return f.read()

            content_str = await self.hass.async_add_executor_job(
                read_existing_automations
            )
            content = yaml.safe_load(content_str)

            if content is None:
                content = []

            # Handle both formats
            if isinstance(content, list):
                existing_automations = content
            elif isinstance(content, dict) and "automation" in content:
                existing_automations = content["automation"]
            else:
                existing_automations = []

            # Add new automations that don't already exist
            for new_auto in new_automations:
                automation_id = new_auto.get("id", "")
                exists = any(
                    auto.get("id") == automation_id for auto in existing_automations
                )
                if not exists:
                    existing_automations.append(new_auto)

            # Write back
            def write_automations_file() -> None:
                if isinstance(content, list):
                    with open(self.automation_path, "w", encoding="utf-8") as f:
                        yaml.dump(
                            existing_automations,
                            f,
                            default_flow_style=False,
                            sort_keys=False,
                        )
                else:
                    content["automation"] = existing_automations
                    with open(self.automation_path, "w", encoding="utf-8") as f:
                        yaml.dump(content, f, default_flow_style=False, sort_keys=False)

            await self.hass.async_add_executor_job(write_automations_file)

        except Exception as e:
            _LOGGER.error(f"Failed to add automations to file: {e}")

    def _replace_template_variables(
        self, template_content: str, device_id: str, device_id_underscore: str
    ) -> str:
        """Replace template variables in automation content."""
        # Do multiple replacement passes to handle nested template expressions
        max_iterations = 5
        for _ in range(max_iterations):
            old_content = template_content
            template_content = template_content.replace("{{ device_id }}", device_id)
            template_content = template_content.replace(
                "{{ device_id_underscore }}", device_id_underscore
            )

            if old_content == template_content:
                break  # No more changes

        return template_content
