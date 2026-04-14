from __future__ import annotations

import importlib
import pkgutil
from typing import Dict

from .base import ScenarioDefinition

_SCENARIO_MODULE_PREFIX = __name__ + "."


def discover_scenarios() -> dict[str, ScenarioDefinition]:
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
