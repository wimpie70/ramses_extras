from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from .migration import migrate_to_canonical_config

REDACTED_VALUE = "<redacted>"
DEFAULT_SENSITIVE_KEYS = {
    "api_key",
    "passphrase",
    "password",
    "secret",
    "token",
}
DEFAULT_RUNTIME_ONLY_KEYS = {
    "binding_health_cache",
    "cache",
    "discovery_hints",
    "health_cache",
    "last_seen",
    "last_seen_at",
    "runtime_state",
    "suggestions",
    "transport_snapshot",
    "ui_state",
}


def build_exportable_config(
    raw_config: dict[str, Any],
    *,
    sensitive_keys: set[str] | None = None,
    runtime_only_keys: set[str] | None = None,
) -> dict[str, Any]:
    canonical_config = migrate_to_canonical_config(raw_config)
    return redact_config_for_export(
        canonical_config,
        sensitive_keys=sensitive_keys,
        runtime_only_keys=runtime_only_keys,
    )


def redact_config_for_export(
    config: dict[str, Any],
    *,
    sensitive_keys: set[str] | None = None,
    runtime_only_keys: set[str] | None = None,
) -> dict[str, Any]:
    effective_sensitive_keys = {
        key.lower() for key in (sensitive_keys or DEFAULT_SENSITIVE_KEYS)
    }
    effective_runtime_only_keys = {
        key.lower() for key in (runtime_only_keys or DEFAULT_RUNTIME_ONLY_KEYS)
    }

    result = _redact_value(
        deepcopy(config),
        sensitive_keys=effective_sensitive_keys,
        runtime_only_keys=effective_runtime_only_keys,
    )
    return result if isinstance(result, dict) else {}


def export_config_to_yaml(
    raw_config: dict[str, Any],
    *,
    sensitive_keys: set[str] | None = None,
    runtime_only_keys: set[str] | None = None,
) -> str:
    exportable = build_exportable_config(
        raw_config,
        sensitive_keys=sensitive_keys,
        runtime_only_keys=runtime_only_keys,
    )
    return yaml.safe_dump(exportable, sort_keys=False, allow_unicode=True) or ""


def _redact_value(
    value: Any,
    *,
    sensitive_keys: set[str],
    runtime_only_keys: set[str],
) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = key.lower() if isinstance(key, str) else key
            if isinstance(normalized_key, str):
                if normalized_key in runtime_only_keys:
                    continue
                if normalized_key in sensitive_keys:
                    redacted[key] = REDACTED_VALUE
                    continue

            redacted[key] = _redact_value(
                item,
                sensitive_keys=sensitive_keys,
                runtime_only_keys=runtime_only_keys,
            )

        return redacted

    if isinstance(value, list):
        return [
            _redact_value(
                item,
                sensitive_keys=sensitive_keys,
                runtime_only_keys=runtime_only_keys,
            )
            for item in value
        ]

    return value


__all__ = [
    "DEFAULT_RUNTIME_ONLY_KEYS",
    "DEFAULT_SENSITIVE_KEYS",
    "REDACTED_VALUE",
    "build_exportable_config",
    "export_config_to_yaml",
    "redact_config_for_export",
]
