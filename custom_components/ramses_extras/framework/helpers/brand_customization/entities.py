"""Entity generation patterns for Ramses Extras brand customization.

This module provides utilities for generating brand-specific entities,
extracting common patterns from existing brand customizers to enable
consistent entity generation across different brands and features.
"""

import logging
from typing import Any, Dict, List

from .models import ModelConfigManager

_LOGGER = logging.getLogger(__name__)


class StandardEntityTemplates:
    """Standard entity templates for brand-specific devices.

    This class defines the standard entity patterns that are commonly
    used across different brands and device types.
    """

    # Standard entity templates for different device types
    STANDARD_ENTITY_TEMPLATES = {
        "sensor": [
            "{brand}_filter_usage_{device_id}",
            "{brand}_operating_hours_{device_id}",
        ],
        "select": [
            "{brand}_operation_mode_{device_id}",
        ],
        "number": [
            "{brand}_target_humidity_{device_id}",
        ],
        "switch": [
            "{brand}_eco_mode_{device_id}",
        ],
    }

    @classmethod
    def get_standard_entities(cls, brand_name: str, device_id: str) -> list[str]:
        """Get standard entities for a brand and device.

        Args:
            brand_name: Brand identifier
            device_id: Device identifier

        Returns:
            List of standard entity IDs
        """
        entities = []
        for entity_type, templates in cls.STANDARD_ENTITY_TEMPLATES.items():
            for template in templates:
                entity_id = template.format(brand=brand_name, device_id=device_id)
                entities.append(entity_id)

        return entities


class SpecialEntityTemplates:
    """Special entity templates for specific device capabilities.

    This class defines special entities that are added based on
    device capabilities and model features.
    """

    # Special entity mappings by capability
    SPECIAL_ENTITIES = {
        "filter_timer": [
            "number.{brand}_filter_timer_{device_id}",
        ],
        "boost_timer": [
            "number.{brand}_boost_timer_{device_id}",
        ],
        "eco_mode": [
            "switch.{brand}_eco_mode_{device_id}",
        ],
        "co2_sensor": [
            "sensor.{brand}_co2_level_{device_id}",
        ],
        "auto_mode": [
            "switch.{brand}_auto_mode_{device_id}",
        ],
        "away_mode": [
            "switch.{brand}_away_mode_{device_id}",
        ],
    }

    @classmethod
    def get_special_entities(
        cls, capabilities: list[str], brand_name: str, device_id: str
    ) -> list[str]:
        """Get special entities based on device capabilities.

        Args:
            capabilities: List of device capabilities
            brand_name: Brand identifier
            device_id: Device identifier

        Returns:
            List of special entity IDs
        """
        entities = []
        for capability in capabilities:
            templates = cls.SPECIAL_ENTITIES.get(capability, [])
            for template in templates:
                entity_id = template.format(brand=brand_name, device_id=device_id)
                entities.append(entity_id)

        return entities


class HighEndEntityTemplates:
    """High-end entity templates for premium device models.

    This class defines entities that are only available on
    high-end or premium device models.
    """

    # High-end entity templates
    HIGH_END_ENTITIES = [
        "sensor.{brand}_air_quality_index_{device_id}",
        "number.{brand}_fan_speed_override_{device_id}",
        "switch.{brand}_smart_boost_{device_id}",
    ]

    @classmethod
    def get_high_end_entities(cls, brand_name: str, device_id: str) -> list[str]:
        """Get high-end entities for a brand and device.

        Args:
            brand_name: Brand identifier
            device_id: Device identifier

        Returns:
            List of high-end entity IDs
        """
        return [
            entity_id.format(brand=brand_name, device_id=device_id)
            for entity_id in cls.HIGH_END_ENTITIES
        ]


class EntityGenerationManager:
    """Manager for brand-specific entity generation.

    This class provides a centralized way to generate entities
    for brand-specific devices based on their configuration.
    """

    def __init__(self, brand_name: str) -> None:
        """Initialize entity generation manager.

        Args:
            brand_name: Brand identifier
        """
        self.brand_name = brand_name
        self.standard_templates = StandardEntityTemplates()
        self.special_templates = SpecialEntityTemplates()
        self.high_end_templates = HighEndEntityTemplates()

    def generate_standard_entities(
        self, device_id: str, model_info: dict[str, Any]
    ) -> list[str]:
        """Generate standard entities for a device.

        Args:
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            List of standard entity IDs
        """
        entities = self.standard_templates.get_standard_entities(
            self.brand_name, device_id
        )

        _LOGGER.debug(
            f"Generated {len(entities)} standard entities for "
            f"{self.brand_name} device {device_id}"
        )
        return entities

    def generate_special_entities(
        self, device_id: str, model_info: dict[str, Any]
    ) -> list[str]:
        """Generate special entities based on device capabilities.

        Args:
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            List of special entity IDs
        """
        special_entities = model_info.get("special_entities", [])
        entities = self.special_templates.get_special_entities(
            special_entities, self.brand_name, device_id
        )

        _LOGGER.debug(
            f"Generated {len(entities)} special entities for "
            f"{self.brand_name} device {device_id}: {special_entities}"
        )
        return entities

    def generate_high_end_entities(
        self, device_id: str, model_info: dict[str, Any]
    ) -> list[str]:
        """Generate high-end entities for premium models.

        Args:
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            List of high-end entity IDs
        """
        # Check if this is a high-end model
        model_key = model_info.get("model_key")
        high_end_models = model_info.get("high_end_models", [])

        if model_key in high_end_models:
            entities = self.high_end_templates.get_high_end_entities(
                self.brand_name, device_id
            )
            _LOGGER.debug(
                f"Generated {len(entities)} high-end entities for "
                f"{self.brand_name} device {device_id}"
            )
            return entities

        return []

    def generate_all_entities(
        self, device_id: str, model_info: dict[str, Any]
    ) -> list[str]:
        """Generate all entities for a device (standard + special + high-end).

        Args:
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            List of all entity IDs
        """
        all_entities = []

        # Add standard entities
        all_entities.extend(self.generate_standard_entities(device_id, model_info))

        # Add special entities
        all_entities.extend(self.generate_special_entities(device_id, model_info))

        # Add high-end entities (if applicable)
        all_entities.extend(self.generate_high_end_entities(device_id, model_info))

        _LOGGER.info(
            f"Generated {len(all_entities)} total entities for "
            f"{self.brand_name} device {device_id}"
        )
        return all_entities

    def get_entity_enablement_config(
        self, device_id: str, model_info: dict[str, Any]
    ) -> dict[str, bool]:
        """Get entity enablement configuration for a device.

        Args:
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            Dictionary mapping entity IDs to enablement status
        """
        entity_enablement = {}
        model_key = model_info.get("model_key") or ""

        # Standard entity enablement
        standard_entities = self.generate_standard_entities(device_id, model_info)
        for entity_id in standard_entities:
            entity_enablement[entity_id] = True

        # Special entity enablement (brand/model specific)
        special_enablement = self._get_special_entity_enablement(
            model_key, device_id, model_info
        )
        entity_enablement.update(special_enablement)

        # High-end entity enablement (premium models only)
        if model_key in model_info.get("high_end_models", []):
            high_end_entities = self.generate_high_end_entities(device_id, model_info)
            for entity_id in high_end_entities:
                entity_enablement[entity_id] = True

        _LOGGER.debug(
            f"Generated enablement config for {len(entity_enablement)} entities "
            f"for {self.brand_name} device {device_id}"
        )
        return entity_enablement

    def _get_special_entity_enablement(
        self, model_key: str, device_id: str, model_info: dict[str, Any]
    ) -> dict[str, bool]:
        """Get enablement configuration for special entities.

        Args:
            model_key: Model key
            device_id: Device identifier
            model_info: Model configuration information

        Returns:
            Dictionary mapping special entity IDs to enablement status
        """
        enablement = {}

        # Brand-specific special entity logic
        if self.brand_name == "orcon":
            enablement.update(
                {
                    f"switch.orcon_eco_mode_{device_id}": model_key != "HRV200",
                    f"select.orcon_operation_mode_{device_id}": True,
                    f"number.orcon_target_humidity_{device_id}": True,
                    f"sensor.orcon_air_quality_index_{device_id}": model_key
                    == "HRV400",
                }
            )
        elif self.brand_name == "zehnder":
            enablement.update(
                {
                    f"switch.zehnder_auto_mode_{device_id}": True,
                    f"select.zehnder_operation_mode_{device_id}": True,
                    f"number.zehnder_target_humidity_{device_id}": True,
                    f"sensor.zehnder_co2_level_{device_id}": "co2_sensor"
                    in model_info.get("special_entities", []),
                }
            )

        return enablement


def generate_entity_templates_for_feature(
    feature_name: str, brand_name: str
) -> dict[str, list[str]]:
    """Generate entity templates for a specific feature and brand.

    Args:
        feature_name: Feature identifier
        brand_name: Brand identifier

    Returns:
        Dictionary mapping entity types to template lists
    """
    # This could be extended to support feature-specific entity templates
    # For now, return standard templates
    templates = StandardEntityTemplates.STANDARD_ENTITY_TEMPLATES.copy()

    # Replace {brand} placeholder with actual brand name
    for entity_type, template_list in templates.items():
        templates[entity_type] = [
            template.format(brand=brand_name) for template in template_list
        ]

    return templates


def validate_entity_ids(entity_ids: list[str]) -> bool:
    """Validate a list of entity IDs.

    Args:
        entity_ids: List of entity IDs to validate

    Returns:
        True if all entity IDs are valid, False otherwise
    """
    for entity_id in entity_ids:
        if not isinstance(entity_id, str) or not entity_id:
            _LOGGER.error(f"Invalid entity ID: {entity_id}")
            return False

        # Check basic format (domain.entity_name)
        if "." not in entity_id:
            _LOGGER.error(f"Entity ID missing domain separator: {entity_id}")
            return False

    return True


def optimize_entity_generation(entity_ids: list[str]) -> list[str]:
    """Optimize entity generation by removing duplicates and validating.

    Args:
        entity_ids: List of entity IDs to optimize

    Returns:
        Optimized list of entity IDs
    """
    # Remove duplicates while preserving order
    unique_entities = []
    seen = set()

    for entity_id in entity_ids:
        if entity_id not in seen:
            unique_entities.append(entity_id)
            seen.add(entity_id)

    # Sort for consistency
    unique_entities.sort()

    _LOGGER.debug(
        f"Optimized entity list: {len(entity_ids)} -> {len(unique_entities)} entities"
    )
    return unique_entities


def get_entity_count_metrics(entity_ids: list[str]) -> dict[str, int]:
    """Get metrics about entity counts by type.

    Args:
        entity_ids: List of entity IDs

    Returns:
        Dictionary mapping entity types to counts
    """
    metrics: dict[str, int] = {}
    for entity_id in entity_ids:
        if "." in entity_id:
            domain = entity_id.split(".")[0]
            metrics[domain] = metrics.get(domain, 0) + 1

    return metrics


# Convenience functions for common entity generation patterns


def create_humidity_entities(brand_name: str, device_id: str) -> list[str]:
    """Create standard humidity control entities.

    Args:
        brand_name: Brand identifier
        device_id: Device identifier

    Returns:
        List of humidity control entity IDs
    """
    entities = [
        f"sensor.{brand_name}_humidity_efficiency_{device_id}",
        f"number.{brand_name}_humidity_target_{device_id}",
    ]

    # Add brand-specific humidity entities
    if brand_name == "orcon":
        entities.extend(
            [
                f"switch.{brand_name}_smart_humidity_{device_id}",
                f"select.{brand_name}_humidity_mode_{device_id}",
            ]
        )
    elif brand_name == "zehnder":
        entities.extend(
            [
                f"sensor.{brand_name}_co2_humidity_correlation_{device_id}",
                f"switch.{brand_name}_auto_humidity_{device_id}",
            ]
        )

    return entities
