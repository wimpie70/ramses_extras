"""Tests for framework setup utils."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.framework.setup import utils


class TestFrameworkSetupUtils:
    """Test framework setup utils."""

    @pytest.mark.asyncio
    async def test_import_module_in_executor_success(self):
        """Test successful module import in executor."""
        with patch("importlib.import_module", return_value=MagicMock()):
            result = await utils.import_module_in_executor("test_module")
            assert result is not None

    @pytest.mark.asyncio
    async def test_import_module_in_executor_failure(self):
        """Test module import failure in executor."""
        with patch(
            "importlib.import_module", side_effect=ImportError("Module not found")
        ):
            with pytest.raises(ImportError):
                await utils.import_module_in_executor("nonexistent_module")

    @pytest.mark.asyncio
    async def test_import_module_in_executor_with_real_module(self):
        """Test importing a real module."""
        result = await utils.import_module_in_executor("os")
        assert result is not None
        assert hasattr(result, "path")
