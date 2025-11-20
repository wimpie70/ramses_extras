"""Tests for startup flow with EntityManager post-creation validation.

This module tests the corrected startup flow that:
1. Creates initial entities through normal platform setup
2. Validates and fixes discrepancies using EntityManager
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.ramses_extras import (
    _validate_startup_entities,
    async_setup_entry,
)
from custom_components.ramses_extras.const import AVAILABLE_FEATURES
from custom_components.ramses_extras.framework.helpers.entity.manager import (
    EntityManager,
)


class TestStartupFlow:
    """Test cases for the corrected startup flow."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.mock_entry = MagicMock()
        self.mock_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": False,
            }
        }
        # Mock the async_forward_entry_setups to avoid actual platform setup
        self.mock_hass.config_entries.async_forward_entry_setups = AsyncMock(
            return_value=True
        )
        # Mock the async_forward_entry_setups to avoid actual platform setup
        self.mock_hass.config_entries.async_forward_entry_setups = AsyncMock(
            return_value=True
        )

    @pytest.mark.asyncio
    async def test_startup_flow_completes_successfully(self):
        """Test that startup completes successfully with the new validation step."""
        # Mock all the startup steps
        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._validate_startup_entities",
                new_callable=AsyncMock,
            ) as mock_validate,
        ):
            # Call the main startup function
            result = await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify startup completed successfully
            assert result is True

            # Verify all steps were called
            self.mock_hass.config_entries.async_forward_entry_setups.assert_called_once()

            # Verify the validation step was called
            mock_validate.assert_called_once_with(self.mock_hass, self.mock_entry)

    @pytest.mark.asyncio
    async def test_entity_manager_validation_called_after_startup(self):
        """Test that EntityManager validation is called after
        initial entity creation."""
        # Mock EntityManager to track its usage
        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(return_value=[])
        mock_entity_manager.get_entities_to_create = Mock(return_value=[])
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
        ):
            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify EntityManager was created
            mock_entity_manager.build_entity_catalog.assert_called_once()

            # Verify it was called with correct parameters
            args, kwargs = mock_entity_manager.build_entity_catalog.call_args
            assert args[0] == AVAILABLE_FEATURES  # available_features
            assert args[1] == self.mock_entry.data.get(
                "enabled_features", {}
            )  # current_features

    @pytest.mark.asyncio
    async def test_startup_validation_fixes_discrepancies(self):
        """Test that validation fixes entity discrepancies found during startup."""
        # Mock EntityManager to return discrepancies
        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(
            return_value=["sensor.unwanted_entity"]
        )
        mock_entity_manager.get_entities_to_create = Mock(
            return_value=["sensor.missing_entity"]
        )
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
        ):
            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify apply_entity_changes was called to fix discrepancies
            mock_entity_manager.apply_entity_changes.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_validation_no_discrepancies(self):
        """Test that validation reports success when no discrepancies are found."""
        # Mock EntityManager to return no discrepancies
        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(return_value=[])
        mock_entity_manager.get_entities_to_create = Mock(return_value=[])
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
            patch("custom_components.ramses_extras._LOGGER") as mock_logger,
        ):
            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify apply_entity_changes was NOT called (no discrepancies)
            mock_entity_manager.apply_entity_changes.assert_not_called()

            # Verify success message was logged
            mock_logger.info.assert_any_call(
                "✅ Startup validation: all entities match expected configuration"
            )

    @pytest.mark.asyncio
    async def test_startup_validation_graceful_failure(self):
        """Test that startup continues even if validation fails."""
        # Mock EntityManager to raise an exception
        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock(
            side_effect=Exception("Validation failed")
        )

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
            patch("custom_components.ramses_extras._LOGGER") as mock_logger,
        ):
            # Startup should NOT fail due to validation error
            result = await async_setup_entry(self.mock_hass, self.mock_entry)
            assert result is True

            # Verify error was logged but startup continued
            mock_logger.error.assert_called_once()
            assert "EntityManager startup validation failed" in str(
                mock_logger.error.call_args
            )

    @pytest.mark.asyncio
    async def test_validate_startup_entities_function(self):
        """Test the standalone validation function."""
        # Mock EntityManager for the standalone validation function
        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(
            return_value=["sensor.bad_entity"]
        )
        mock_entity_manager.get_entities_to_create = Mock(
            return_value=["sensor.good_entity"]
        )
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
            patch("custom_components.ramses_extras._LOGGER") as mock_logger,
        ):
            await _validate_startup_entities(self.mock_hass, self.mock_entry)

            # Verify EntityManager was called correctly
            mock_entity_manager.build_entity_catalog.assert_called_once()
            mock_entity_manager.apply_entity_changes.assert_called_once()

            # Verify discrepancy warning was logged
            mock_logger.warning.assert_any_call(
                "Startup validation found discrepancies: remove 1, create 1"
            )

    @pytest.mark.asyncio
    async def test_startup_flow_with_all_features_enabled(self):
        """Test startup with all features enabled."""
        # Enable all features
        self.mock_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": True,
                "hvac_fan_card": True,
            }
        }

        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(return_value=[])
        mock_entity_manager.get_entities_to_create = Mock(return_value=[])
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
        ):
            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify all enabled features were passed to validation
            args, kwargs = mock_entity_manager.build_entity_catalog.call_args
            current_features = args[1]
            assert current_features["default"] is True
            assert current_features["humidity_control"] is True
            assert current_features["hvac_fan_card"] is True

    @pytest.mark.asyncio
    async def test_startup_flow_with_no_features_enabled(self):
        """Test startup with only default feature enabled."""
        # Only default feature enabled
        self.mock_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": False,
                "hvac_fan_card": False,
            }
        }

        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(return_value=[])
        mock_entity_manager.get_entities_to_create = Mock(return_value=[])
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
        ):
            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify only default feature was passed to validation
            args, kwargs = mock_entity_manager.build_entity_catalog.call_args
            current_features = args[1]
            assert current_features["default"] is True
            assert current_features["humidity_control"] is False
            assert current_features["hvac_fan_card"] is False

    @pytest.mark.asyncio
    async def test_startup_sequence_order(self):
        """Test that startup steps happen in the correct order."""
        call_order = []

        # Mock functions to track call order
        async def mock_register_services(hass):
            call_order.append("_register_services")

        async def mock_discover_devices(hass):
            call_order.append("_discover_and_store_devices")

        async def mock_platform_setup(hass):
            call_order.append("async_setup_platforms")

        async def mock_validate_startup(hass, entry):
            call_order.append("_validate_startup_entities")

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                mock_register_services,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                mock_discover_devices,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                mock_platform_setup,
            ),
            patch(
                "custom_components.ramses_extras._validate_startup_entities",
                mock_validate_startup,
            ),
        ):
            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify correct order
            expected_order = [
                "_register_services",
                "_discover_and_store_devices",
                "async_setup_platforms",
                "_validate_startup_entities",
            ]
            assert call_order == expected_order

    @pytest.mark.asyncio
    async def test_platform_filtering_works_with_validation(self):
        """Test that platform filtering still works
        alongside EntityManager validation."""
        # This test would be more meaningful with actual platform setup
        # For now, verify that the validation step doesn't interfere with platform setup

        mock_entity_manager = MagicMock()
        mock_entity_manager.build_entity_catalog = AsyncMock()
        mock_entity_manager.get_entities_to_remove = Mock(return_value=[])
        mock_entity_manager.get_entities_to_create = Mock(return_value=[])
        mock_entity_manager.apply_entity_changes = AsyncMock()

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager",
                return_value=mock_entity_manager,
            ),
        ):
            # This should complete without issues
            result = await async_setup_entry(self.mock_hass, self.mock_entry)
            assert result is True

            # Platform setup should have been called
            # (actual platform filtering happens inside the platforms themselves)


class TestStartupEntityCreationVsValidation:
    """Test the separation between initial creation and EntityManager validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = MagicMock()
        self.mock_entry = MagicMock()
        self.mock_entry.data = {
            "enabled_features": {
                "default": True,
                "humidity_control": False,
            }
        }
        # Mock the async_forward_entry_setups to avoid actual platform setup
        self.mock_hass.config_entries.async_forward_entry_setups = AsyncMock(
            return_value=True
        )

    @pytest.mark.asyncio
    async def test_entity_manager_not_used_for_initial_creation(self):
        """Test that EntityManager is not used for initial
        entity creation during startup."""
        # This test verifies our architectural decision:
        # - Initial entity creation happens through normal platform setup
        # - EntityManager is only used for post-creation validation

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                new_callable=AsyncMock,
            ),
        ):
            # Start with a mock EntityManager that should only be used for validation
            with patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager"
            ) as mock_entity_manager_class:
                await async_setup_entry(self.mock_hass, self.mock_entry)

                # EntityManager should be instantiated but NOT used for creation
                # It's only used for validation (which would happen in a separate step)
                mock_entity_manager_class.assert_called_once()

                # The created instance should have its methods called for validation
                entity_manager_instance = mock_entity_manager_class.return_value
                entity_manager_instance.build_entity_catalog.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_flow_clearly_separates_concerns(self):
        """Test that startup flow clearly separates initial creation from validation."""
        # This test verifies the architectural separation:
        # 1. Platform setup creates entities (should work without EntityManager)
        # 2. EntityManager validates and fixes (safety net, not primary mechanism)

        creation_steps = []
        validation_steps = []

        # Mock functions to track what happens during each phase
        async def mock_platform_setup(hass):
            creation_steps.append("platform_setup")

        def mock_entity_manager_init(hass):
            # Track EntityManager creation for validation phase
            validation_steps.append("entity_manager_created")
            return mock_em

        async def mock_build_catalog(available_features, current_features):
            validation_steps.append("validation_executed")

        with (
            patch(
                "custom_components.ramses_extras._register_services",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras._discover_and_store_devices",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.ramses_extras.async_setup_platforms",
                mock_platform_setup,
            ),
            patch(
                "custom_components.ramses_extras.framework.helpers.entity.manager.EntityManager"
            ) as mock_em_class,
        ):
            # Configure the EntityManager mock
            mock_em = MagicMock()
            mock_em.build_entity_catalog = mock_build_catalog
            # Set up the constructor to track when it's called
            mock_em_class.side_effect = lambda hass: (
                validation_steps.append("entity_manager_created"),
                mock_em,
            )[1]

            await async_setup_entry(self.mock_hass, self.mock_entry)

            # Verify clear separation
            assert "platform_setup" in creation_steps
            assert "entity_manager_created" in validation_steps
            assert "validation_executed" in validation_steps

            # Entity creation should happen first, then validation
            assert creation_steps[0] == "platform_setup"
            assert validation_steps[0] == "entity_manager_created"
