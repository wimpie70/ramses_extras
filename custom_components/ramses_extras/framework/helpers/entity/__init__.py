"""Framework entity helper modules."""

from .core import (
    EntityHelpers,
    filter_entities_by_patterns,
    generate_entity_patterns_for_feature,
    get_entities_for_device,
    get_entity_device_id,
    get_feature_entity_mappings,
    parse_entity_id,
)
from .entity_id_fallbacks import (
    iter_ramses_cc_entity_id_fallbacks,
    iter_ramses_cc_entity_ids,
)
from .simple_entity_manager import (
    EntityInfo,
    SimpleEntityManager,
)

__all__ = [
    "EntityHelpers",
    "SimpleEntityManager",
    "EntityInfo",
    "filter_entities_by_patterns",
    "generate_entity_patterns_for_feature",
    "get_entities_for_device",
    "get_entity_device_id",
    "parse_entity_id",
    "get_feature_entity_mappings",
    "iter_ramses_cc_entity_ids",
    "iter_ramses_cc_entity_id_fallbacks",
]
