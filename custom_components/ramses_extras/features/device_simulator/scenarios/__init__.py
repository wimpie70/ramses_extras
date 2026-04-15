from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from typing import TYPE_CHECKING, cast

from .base import ScenarioDefinition

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_SCENARIO_MODULE_PREFIX = __name__ + "."


@lru_cache(maxsize=1)
def _discover_scenarios_sync() -> dict[str, ScenarioDefinition]:
    """Import scenario modules and return definitions keyed by scenario_id."""

    definitions: dict[str, ScenarioDefinition] = {}

    package = importlib.import_module(__name__)
    for module_info in pkgutil.iter_modules(package.__path__, _SCENARIO_MODULE_PREFIX):
        module = importlib.import_module(module_info.name)
        definition = getattr(module, "SCENARIO_DEFINITION", None)
        if definition is None:
            continue
        definitions[definition.scenario_id] = definition

    return definitions


def discover_scenarios() -> dict[str, ScenarioDefinition]:
    """Return cached scenario definitions (synchronous callers)."""

    return _discover_scenarios_sync().copy()


async def async_discover_scenarios(
    hass: HomeAssistant,
) -> dict[str, ScenarioDefinition]:
    """Run scenario discovery off the event loop and return definitions."""

    loop = hass.loop
    result = await loop.run_in_executor(None, _discover_scenarios_sync)
    return cast(dict[str, ScenarioDefinition], result.copy())
