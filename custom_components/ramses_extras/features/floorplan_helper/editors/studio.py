"""Floorplan Studio adapter — the tinkersoder ``floorplan-studio-card``.

Studio keeps its projects in the browser's IndexedDB; the canonical
server-side mirror is ``ramses_extras/floorplan/projects/latest.json``,
written by ``floorplan_store_project`` (the actions card's
``studio → HA``) and read by every service when no project is passed.

The studio project format *is* the canonical plan shape — translation
is identity.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from ..importer import (
    backup_project,
    load_latest_project,
    project_backups,
    store_latest_project,
)
from .base import EditorAdapter, EditorCapabilities

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class StudioAdapter(EditorAdapter):
    """Adapter for the ``floorplan-studio-card`` editor."""

    key = "studio"
    name = "Floorplan Studio"
    capabilities = EditorCapabilities(
        marker_icons=True,
        marker_colors=True,
        marker_actions=True,
        multi_entity=True,
        stamp_extras=True,
        browser_side=True,
        # studio's editor is a card on a dashboard, not a fixed URL —
        # the editor_url option (default /floorplan-studio) points where
        # the user put it
        editor_url="",
        card_element="floorplan-studio-card",
        # the editor already is a dashboard card — embed mounts that
        # element (its module is a lovelace resource, already loaded)
        panel_element="floorplan-studio-card",
        panel_module="",
    )

    async def async_detect(self, hass: HomeAssistant) -> bool:
        """Studio counts as installed when a project is stored or the
        card's lovelace resource is registered."""
        if await hass.async_add_executor_job(load_latest_project, hass):
            return True
        try:
            from homeassistant.helpers.storage import Store

            store: Store[dict[str, Any]] = Store(hass, 1, "lovelace_resources")
            data = await store.async_load()
        except Exception:  # noqa: BLE001 — storage internals vary
            return False
        return any(
            "floorplan-studio" in str(item.get("url", "")).lower()
            for item in (data or {}).get("items", [])
        )

    async def async_load(self, hass: HomeAssistant) -> dict[str, Any] | None:
        raw = await hass.async_add_executor_job(load_latest_project, hass)
        if not raw:
            return None
        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return plan if isinstance(plan, dict) else None

    async def async_store(self, hass: HomeAssistant, plan: dict[str, Any]) -> str:
        path: str = await hass.async_add_executor_job(
            store_latest_project, hass, json.dumps(plan)
        )
        return path

    async def async_backup(self, hass: HomeAssistant, plan_text: str) -> str:
        path: str = await hass.async_add_executor_job(backup_project, hass, plan_text)
        return path

    async def async_plan_backups(self, hass: HomeAssistant) -> list[dict[str, Any]]:
        def _load() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for text in project_backups(hass):
                try:
                    plan = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(plan, dict):
                    out.append(plan)
            return out

        plans: list[dict[str, Any]] = await hass.async_add_executor_job(_load)
        return plans

    def parse(self, raw: str | dict[str, Any]) -> dict[str, Any]:
        plan = super().parse(raw)
        if not isinstance(plan.get("floors"), list):
            raise vol.Invalid("project_json is not a studio project")
        return plan


__all__ = ["StudioAdapter"]
