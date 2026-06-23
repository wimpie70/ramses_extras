"""Tests for SimpleEntityManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ramses_extras.const import DOMAIN
from custom_components.ramses_extras.framework.helpers.entity import (
    simple_entity_manager as sem,
)

SimpleEntityManager = sem.SimpleEntityManager


def test_get_enabled_features_prefers_injected(hass) -> None:
    manager = SimpleEntityManager(hass, enabled_features={"foo": True})

    assert manager._get_enabled_features() == {"foo": True}


def test_get_enabled_features_from_hass_data(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["enabled_features"] = {"bar": True}
    manager = SimpleEntityManager(hass)

    assert manager._get_enabled_features() == {"bar": True}


@pytest.mark.asyncio
async def test_validate_entities_on_startup_removes_extras(hass) -> None:
    manager = SimpleEntityManager(hass)

    manager._get_current_entities = AsyncMock(return_value=["sensor.extra"])  # type: ignore[assignment]
    manager._calculate_required_entities = AsyncMock(return_value=[])  # type: ignore[assignment]
    manager._is_managed_entity = MagicMock(return_value=True)  # type: ignore[assignment]
    removed: list[str] = []

    async def _remove(entity_id: str) -> None:
        removed.append(entity_id)

    manager._remove_entity_directly = _remove  # type: ignore[assignment]

    await manager.validate_entities_on_startup()

    assert removed == ["sensor.extra"]


def test_is_managed_entity_false_on_missing_entry(hass) -> None:
    manager = SimpleEntityManager(hass)

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = None

    with patch(
        "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.entity_registry.async_get",
        return_value=mock_registry,
    ):
        assert manager._is_managed_entity("sensor.not_managed") is False


@pytest.mark.asyncio
async def test_calculate_required_entities_matrix_empty_uses_global(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["devices"] = [MagicMock(id="01:123456")]
    manager = SimpleEntityManager(hass, enabled_features={"hello": True})

    # force empty matrix
    manager.device_feature_matrix.restore_device_feature_matrix_state({})

    async def fake_generate(feature_id: str, device_id: str) -> list[str]:
        return [f"{feature_id}.{device_id}"]

    manager._generate_entity_ids_for_combination = fake_generate  # type: ignore[assignment]

    with patch(
        "custom_components.ramses_extras.extras_registry.extras_registry.get_loaded_features",
        return_value=["default", "hello"],
    ):
        result = await manager._calculate_required_entities()

    assert sorted(result) == ["default.01:123456", "hello.01:123456"]


@pytest.mark.asyncio
async def test_calculate_required_entities_respects_matrix_and_disabled(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["devices"] = [MagicMock(id="01:123456")]
    manager = SimpleEntityManager(hass, enabled_features={"hello": False})

    manager.device_feature_matrix.restore_device_feature_matrix_state(
        {"01:123456": {"hello": True}}
    )

    async def fake_generate(feature_id: str, device_id: str) -> list[str]:
        return [f"{feature_id}.{device_id}"]

    manager._generate_entity_ids_for_combination = fake_generate  # type: ignore[assignment]

    with patch(
        "custom_components.ramses_extras.extras_registry.extras_registry.get_loaded_features",
        return_value=["default", "hello"],
    ):
        result = await manager._calculate_required_entities()

    # hello disabled, but default is always enabled (creates transport_state, etc.)
    assert result == ["default.01:123456"]


@pytest.mark.asyncio
async def test_calculate_required_entities_preserves_untracked_global_features(
    hass,
) -> None:
    """Globally enabled features NOT in the matrix must still get entities.

    When the matrix is non-empty (e.g. only temp_control is tracked), other
    globally enabled features that aren't in the matrix should still generate
    entities for all devices — same as the empty-matrix fallback.
    """
    hass.data.setdefault(DOMAIN, {})["devices"] = [MagicMock(id="01:123456")]
    manager = SimpleEntityManager(
        hass,
        enabled_features={"hello": True, "co2_control": True, "temp_control": True},
    )

    # Matrix only tracks temp_control — hello and co2_control are NOT in it
    manager.device_feature_matrix.restore_device_feature_matrix_state(
        {"01:123456": {"temp_control": True}}
    )

    async def fake_generate(feature_id: str, device_id: str) -> list[str]:
        return [f"{feature_id}.{device_id}"]

    manager._generate_entity_ids_for_combination = fake_generate  # type: ignore[assignment]

    with patch(
        "custom_components.ramses_extras.extras_registry.extras_registry.get_loaded_features",
        return_value=["default", "hello", "co2_control", "temp_control"],
    ):
        result = await manager._calculate_required_entities()

    expected = {
        "default.01:123456",
        "hello.01:123456",
        "co2_control.01:123456",
        "temp_control.01:123456",
    }
    assert set(result) == expected


@pytest.mark.asyncio
async def test_calculate_entity_changes_no_spurious_removals(hass) -> None:
    """Enabling a feature in the matrix must not flag others for removal.

    Old state: empty matrix, hello globally enabled -> entities for all devices.
    New state: matrix has temp_control, hello still globally enabled but not
    in the matrix. The diff should only show temp_control entities to create,
    NOT hello entities to remove.
    """
    hass.data.setdefault(DOMAIN, {})["devices"] = [MagicMock(id="01:123456")]

    async def fake_generate(feature_id: str, device_id: str) -> list[str]:
        return [f"{feature_id}.{device_id}"]

    features = ["default", "hello", "temp_control"]

    with patch(
        "custom_components.ramses_extras.extras_registry.extras_registry.get_loaded_features",
        return_value=features,
    ):
        old_mgr = SimpleEntityManager(hass, enabled_features={"hello": True})
        old_mgr.device_feature_matrix.restore_device_feature_matrix_state({})
        old_mgr._generate_entity_ids_for_combination = fake_generate  # type: ignore[assignment]
        old_required = await old_mgr._calculate_required_entities()

        new_mgr = SimpleEntityManager(
            hass, enabled_features={"hello": True, "temp_control": True}
        )
        new_mgr.device_feature_matrix.restore_device_feature_matrix_state(
            {"01:123456": {"temp_control": True}}
        )
        new_mgr._generate_entity_ids_for_combination = fake_generate  # type: ignore[assignment]
        new_required = await new_mgr._calculate_required_entities()

    to_create = set(new_required) - set(old_required)
    to_remove = set(old_required) - set(new_required)

    assert to_create == {"temp_control.01:123456"}
    assert to_remove == set()


@pytest.mark.asyncio
async def test_get_current_entities_handles_exception(hass, caplog) -> None:
    manager = SimpleEntityManager(hass)

    caplog.set_level("WARNING")

    with patch(
        "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.entity_registry.async_get",
        side_effect=RuntimeError("boom"),
    ):
        result = await manager._get_current_entities()

    assert result == []
    assert any(
        "Could not get entity registry" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_remove_feature_entities_logs_warning_on_error(hass, caplog) -> None:
    manager = SimpleEntityManager(hass)

    async def fake_generate(feature_id: str, device_id: str) -> list[str]:
        return ["sensor.bad"]

    manager._generate_entity_ids_for_combination = fake_generate  # type: ignore[assignment]

    async def failing_remove(entity_id: str) -> None:
        raise RuntimeError("oops")

    manager._remove_entity_directly = failing_remove  # type: ignore[assignment]

    caplog.set_level("WARNING")

    removed = await manager._remove_feature_entities("foo", "bar")

    assert removed == []
    assert any("Failed to remove entity" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_create_entity_directly_success(hass) -> None:
    manager = SimpleEntityManager(hass)

    mock_registry = MagicMock()
    mock_registry.async_get_or_create.return_value.id = "abc123"

    with patch(
        "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.entity_registry.async_get",
        return_value=mock_registry,
    ):
        await manager._create_entity_directly("sensor.test")

    mock_registry.async_get_or_create.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_extra_entities_logs_warning(hass, caplog) -> None:
    manager = SimpleEntityManager(hass)

    async def failing_remove(entity_id: str) -> None:
        raise RuntimeError("boom")

    manager._remove_entity_directly = failing_remove  # type: ignore[assignment]

    caplog.set_level("WARNING")

    await manager._cleanup_extra_entities(["sensor.bad"])

    assert any("Failed to cleanup entity" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_remove_entity_directly_handles_missing(hass) -> None:
    manager = SimpleEntityManager(hass)

    mock_registry = MagicMock()
    mock_registry.async_get.return_value = None

    with patch(
        "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.entity_registry.async_get",
        return_value=mock_registry,
    ):
        await manager._remove_entity_directly("sensor.missing")

    mock_registry.async_remove.assert_not_called()


@pytest.mark.asyncio
async def test_remove_entity_directly_success(hass) -> None:
    manager = SimpleEntityManager(hass)

    mock_entry = MagicMock()
    mock_registry = MagicMock()
    mock_registry.async_get.return_value = mock_entry

    with patch(
        "custom_components.ramses_extras.framework.helpers.entity.simple_entity_manager.entity_registry.async_get",
        return_value=mock_registry,
    ):
        await manager._remove_entity_directly("sensor.present")

    mock_registry.async_remove.assert_called_once_with("sensor.present")


@pytest.mark.asyncio
async def test_create_entity_wrapper_handles_error(hass, caplog) -> None:
    manager = SimpleEntityManager(hass)

    async def failing_create(entity_id: str) -> None:
        raise RuntimeError("boom")

    manager._create_entity_directly = failing_create  # type: ignore[assignment]

    caplog.set_level("ERROR")
    with pytest.raises(RuntimeError):
        await manager.create_entity("sensor.test")

    assert any("Failed to create entity" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_create_missing_entities_warns_on_failure(hass, caplog) -> None:
    manager = SimpleEntityManager(hass)

    async def failing_create(entity_id: str) -> None:
        raise RuntimeError("fail")

    manager._create_entity_directly = failing_create  # type: ignore[assignment]

    caplog.set_level("WARNING")

    await manager._create_missing_entities(["sensor.one", "sensor.two"])

    assert any(
        "Failed to create missing entity" in msg for msg in caplog.text.splitlines()
    )


@pytest.mark.asyncio
async def test_remove_entity_wrapper_handles_error(hass, caplog) -> None:
    manager = SimpleEntityManager(hass)

    async def failing_remove(entity_id: str) -> None:
        raise RuntimeError("remove_fail")

    manager._remove_entity_directly = failing_remove  # type: ignore[assignment]

    caplog.set_level("ERROR")
    with pytest.raises(RuntimeError):
        await manager.remove_entity("sensor.test")

    assert any("Failed to remove entity" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_create_entity_success_logs(hass, caplog) -> None:
    """Test create_entity logs success."""
    caplog.set_level("INFO")

    manager = SimpleEntityManager(hass)

    # Mock successful creation
    mock_entity = MagicMock()
    mock_entity.entity_id = "test.entity"

    with patch.object(
        manager, "_create_entity_directly", new=AsyncMock(return_value="test.entity")
    ):
        await manager.create_entity("test.entity")

    assert any("Entity test.entity created" in msg for msg in caplog.text.splitlines())


@pytest.mark.asyncio
async def test_remove_entity_success_logs(hass, caplog) -> None:
    """Test remove_entity logs success."""
    caplog.set_level("INFO")

    manager = SimpleEntityManager(hass)

    with patch.object(manager, "_remove_entity_directly", new=AsyncMock()):
        await manager.remove_entity("sensor.test")

    assert any("Entity sensor.test removed" in msg for msg in caplog.text.splitlines())
