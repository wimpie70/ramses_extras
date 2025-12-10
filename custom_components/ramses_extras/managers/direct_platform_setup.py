"""Direct platform setup for Ramses Extras integration.

This module provides direct platform setup functionality that replaces
the complex PlatformReloader with simple direct platform calls during
config flow confirmation.
"""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def setup_platforms_directly(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Direct platform setup during config flow confirmation step.

    This function replaces the complex PlatformReloader by making direct
    platform setup calls during the config flow confirmation step.

    Args:
        hass: Home Assistant instance
        config_entry: The Ramses Extras config entry
    """
    _LOGGER.info("Setting up platforms directly during config flow confirmation")

    try:
        # Call feature platform setup functions directly during confirmation
        await _setup_default_sensors(hass, config_entry)
        await _setup_default_switches(hass, config_entry)
        await _setup_humidity_control_sensors(hass, config_entry)
        await _setup_humidity_control_switches(hass, config_entry)

        _LOGGER.info("✅ Direct platform setup completed successfully")

    except Exception as e:
        _LOGGER.error(f"❌ Error during direct platform setup: {e}")
        # Don't re-raise - platform setup failure shouldn't break the flow


async def _setup_default_sensors(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Setup default sensors directly.

    Args:
        hass: Home Assistant instance
        config_entry: The Ramses Extras config entry
    """
    try:
        # Import and call the sensor platform setup function directly
        from ..features.default.platforms.sensor import async_setup_entry

        _LOGGER.debug("Calling default sensor platform setup directly")

        # Use real async_add_entities to actually create entities
        # Import the real async_add_entities from Home Assistant
        from homeassistant.helpers.entity_platform import async_add_entities

        await async_setup_entry(hass, config_entry, async_add_entities)

    except ImportError as e:
        _LOGGER.warning(f"Could not import default sensor platform: {e}")
    except Exception as e:
        _LOGGER.error(f"Failed to setup default sensors: {e}")


async def _setup_default_switches(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Setup default switches directly.

    Args:
        hass: Home Assistant instance
        config_entry: The Ramses Extras config entry
    """
    try:
        # Import and call the switch platform setup function directly
        from ..features.default.platforms.switch import async_setup_entry

        _LOGGER.debug("Calling default switch platform setup directly")

        # Use SimpleEntityManager to create entities directly
        # This is the proper way to create entities in the new architecture
        try:
            from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
                SimpleEntityManager,
            )

            entity_manager = SimpleEntityManager(hass)

            # Get the entities that would be created by the switch platform
            entities_to_create = await entity_manager._calculate_required_entities()

            _LOGGER.info(
                f"Direct platform setup: Found {len(entities_to_create)} "
                "switch entities to create"
            )

            # Create the entities using SimpleEntityManager
            if entities_to_create:
                await entity_manager._create_missing_entities(entities_to_create)
                _LOGGER.info(
                    f"✅ Created {len(entities_to_create)} switch entities via "
                    "SimpleEntityManager"
                )

        except Exception as e:
            _LOGGER.error(
                f"Failed to create switch entities via SimpleEntityManager: {e}"
            )

    except ImportError as e:
        _LOGGER.warning(f"Could not import default switch platform: {e}")
    except Exception as e:
        _LOGGER.error(f"Failed to setup default switches: {e}")


async def _setup_humidity_control_sensors(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Setup humidity control sensors directly.

    Args:
        hass: Home Assistant instance
        config_entry: The Ramses Extras config entry
    """
    try:
        # Import and call the humidity control sensor platform setup function directly
        from ..features.humidity_control.platforms.sensor import async_setup_entry

        _LOGGER.debug("Calling humidity control sensor platform setup directly")

        # Use SimpleEntityManager to create entities directly
        # This is the proper way to create entities in the new architecture
        try:
            from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
                SimpleEntityManager,
            )

            entity_manager = SimpleEntityManager(hass)

            # Get the entities that would be created by the
            #  humidity control sensor platform
            entities_to_create = await entity_manager._calculate_required_entities()

            _LOGGER.info(
                f"Direct platform setup: Found {len(entities_to_create)} "
                "humidity control sensor entities to create"
            )

            # Create the entities using SimpleEntityManager
            if entities_to_create:
                await entity_manager._create_missing_entities(entities_to_create)
                _LOGGER.info(
                    f"✅ Created {len(entities_to_create)} "
                    "humidity control sensor entities via SimpleEntityManager"
                )

        except Exception as e:
            _LOGGER.error(
                f"Failed to create humidity control sensor entities "
                f"via SimpleEntityManager: {e}"
            )

    except ImportError as e:
        _LOGGER.warning(f"Could not import humidity control sensor platform: {e}")
    except Exception as e:
        _LOGGER.error(f"Failed to setup humidity control sensors: {e}")


async def _setup_humidity_control_switches(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Setup humidity control switches directly.

    Args:
        hass: Home Assistant instance
        config_entry: The Ramses Extras config entry
    """
    try:
        # Import and call the humidity control switch platform setup function directly
        from ..features.humidity_control.platforms.switch import async_setup_entry

        _LOGGER.debug("Calling humidity control switch platform setup directly")

        # Use SimpleEntityManager to create entities directly
        # This is the proper way to create entities in the new architecture
        try:
            from custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager import (  # noqa: E501
                SimpleEntityManager,
            )

            entity_manager = SimpleEntityManager(hass)

            # Get the entities that would be created by the
            #  humidity control switch platform
            entities_to_create = await entity_manager.get_entities_to_create()

            _LOGGER.info(
                f"Direct platform setup: Found {len(entities_to_create)} "
                "humidity control switch entities to create"
            )

            # Create the entities using SimpleEntityManager
            if entities_to_create:
                await entity_manager._create_missing_entities(entities_to_create)
                _LOGGER.info(
                    f"✅ Created {len(entities_to_create)} "
                    "humidity control switch entities via SimpleEntityManager"
                )

        except Exception as e:
            _LOGGER.error(
                f"Failed to create humidity control switch "
                f"entities via SimpleEntityManager: {e}"
            )

    except ImportError as e:
        _LOGGER.warning(f"Could not import humidity control switch platform: {e}")
    except Exception as e:
        _LOGGER.error(f"Failed to setup humidity control switches: {e}")


# Export main function
__all__ = ["setup_platforms_directly"]
