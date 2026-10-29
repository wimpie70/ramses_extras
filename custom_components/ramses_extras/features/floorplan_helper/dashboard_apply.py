"""Dashboard card update and export notification helpers for Floorplan Helper.

:platform: Home Assistant
:feature: Floorplan Helper
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_ID = "ramses_extras_floorplan_export"


def notify_export(hass: HomeAssistant, bundle: dict[str, Any]) -> None:
    """Raise a persistent_notification summarising an export.

    Needed because tap_action service calls (the in-SVG export button)
    can't display a service response.
    """
    changes = bundle.get("changes") or {}
    lines = [
        f"{len(bundle.get('rules', []))} rules, "
        f"{len(bundle.get('files_written', []))} files written.",
    ]
    if changes.get("first_export"):
        lines.append("First export — snapshot stored.")
    else:
        for key in ("devices_added", "devices_removed", "devices_changed"):
            if changes.get(key):
                lines.append(f"{key.replace('_', ' ')}: {', '.join(changes[key])}")
    for warning in bundle.get("warnings", []):
        lines.append(f"⚠ {warning}")
    persistent_notification.async_create(
        hass,
        "\n".join(lines),
        title="Floorplan bundle regenerated",
        notification_id=NOTIFICATION_ID,
    )


async def apply_cards_to_dashboards(
    hass: HomeAssistant,
    cards: dict[str, dict[str, Any]],
    match: str | None = None,
    url_path: str | None = None,
) -> dict[str, int]:
    """Replace generated floorplan card(s) on storage dashboards.

    A card is matched by the map file it displays: exact
    ``config.image.location`` against each generated card — so
    several floorplan cards with different maps each get their own
    update and hand-made cards stay untouched — or the ``match``
    substring override. ``url_path`` limits the scan to one
    dashboard; yaml-mode dashboards can't be patched.
    """
    try:
        from homeassistant.components.lovelace import LOVELACE_DATA
        from homeassistant.components.lovelace.const import ConfigNotFound
        from homeassistant.components.lovelace.dashboard import LovelaceStorage
    except ImportError:
        return {"dashboards": 0, "cards": 0}

    data = hass.data.get(LOVELACE_DATA)
    if data is None:
        return {"dashboards": 0, "cards": 0}

    def _image_of(card: Any) -> str:
        if not isinstance(card, dict):
            return ""
        img = (card.get("config") or {}).get("image") or {}
        return str(img.get("location") or "")

    def _replacement(card: Any) -> dict[str, Any] | None:
        if not isinstance(card, dict):
            return None
        if card.get("type") != "custom:floorplan-card":
            return None
        if match:
            return next(iter(cards.values())) if match in _image_of(card) else None
        for cfg in cards.values():
            img = (cfg.get("config") or {}).get("image") or {}
            if img.get("location") == _image_of(card):
                return cfg
        return None

    n_cards = 0
    n_dashes = 0
    for path, dash in (data.dashboards or {}).items():
        if url_path is not None and path != url_path:
            continue
        if not isinstance(dash, LovelaceStorage):
            continue  # yaml-mode dashboards can't be patched
        try:
            conf = await dash.async_load(False)
        except ConfigNotFound:
            continue
        except Exception:  # noqa: BLE001 — one bad dashboard must
            _LOGGER.debug(  # not fail the export
                "floorplan apply: skipping dashboard %s", path, exc_info=True
            )
            continue
        n = 0
        for view in (conf or {}).get("views", []) or []:
            for i, card in enumerate(view.get("cards") or []):
                rep = _replacement(card)
                if rep:
                    view["cards"][i] = rep
                    n += 1
            for sec in view.get("sections") or []:
                for i, card in enumerate(sec.get("cards") or []):
                    rep = _replacement(card)
                    if rep:
                        sec["cards"][i] = rep
                        n += 1
        if n:
            await dash.async_save(conf)
            n_cards += n
            n_dashes += 1
    return {"dashboards": n_dashes, "cards": n_cards}


__all__ = ["NOTIFICATION_ID", "apply_cards_to_dashboards", "notify_export"]
