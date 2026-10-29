"""Pluggable plan editors — registry and resolution.

The actions card (and every service that touches the plan) resolves an
:py:class:`EditorAdapter` through :func:`resolve_editor`:

1. an explicit ``editor`` key — a service field the actions card sets
   from its yaml ``editor:`` option
2. the stored ``editor`` option (the config flow's default)
3. ``auto`` — the first installed adapter that already holds a plan,
   then the first installed adapter, then studio (status quo)

Two editors may coexist (different dashboards, or even the same one —
each actions card pins its own), so resolution never mutates global
state.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import EditorAdapter, EditorCapabilities
from .hfs import HfsAdapter
from .studio import StudioAdapter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

EDITOR_AUTO = "auto"

_ADAPTERS: dict[str, EditorAdapter] = {
    a.key: a for a in (StudioAdapter(), HfsAdapter())
}


def editor_keys() -> list[str]:
    """All registered editor keys, stable order (studio first)."""
    return list(_ADAPTERS)


def adapter_for(key: str) -> EditorAdapter:
    """Return the adapter for ``key`` (raises ``KeyError`` if unknown)."""
    return _ADAPTERS[key]


async def detect_editors(hass: HomeAssistant) -> list[str]:
    """Keys of installed editors, registry order."""
    out: list[str] = []
    for adapter in _ADAPTERS.values():
        try:
            if await adapter.async_detect(hass):
                out.append(adapter.key)
        except Exception:  # noqa: BLE001 — a broken editor must not
            continue  # take the others down with it
    return out


async def resolve_editor(
    hass: HomeAssistant,
    options: dict[str, Any] | None = None,
    requested: str | None = None,
) -> EditorAdapter:
    """Pick the editor adapter for one call.

    ``requested`` (a service/card field) wins; otherwise the stored
    ``editor`` option; ``auto`` (or anything unknown) falls back to
    detection — an adapter already holding a plan beats one that is
    merely installed, and studio remains the default when nothing can
    be detected (the historical behaviour).
    """
    from ..const import OPTION_EDITOR  # noqa: PLC0415 — import cycle

    key = str(requested or (options or {}).get(OPTION_EDITOR) or EDITOR_AUTO)
    if key != EDITOR_AUTO and key in _ADAPTERS:
        return _ADAPTERS[key]

    installed = await detect_editors(hass)
    for adapter_key in installed:
        if await _ADAPTERS[adapter_key].async_load(hass) is not None:
            return _ADAPTERS[adapter_key]
    if installed:
        return _ADAPTERS[installed[0]]
    return _ADAPTERS["studio"]


__all__ = [
    "EDITOR_AUTO",
    "EditorAdapter",
    "EditorCapabilities",
    "adapter_for",
    "detect_editors",
    "editor_keys",
    "resolve_editor",
]
