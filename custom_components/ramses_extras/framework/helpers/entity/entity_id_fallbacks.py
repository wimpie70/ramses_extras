from __future__ import annotations


def _unique_in_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _device_id_to_underscore(device_id: str) -> str:
    return device_id.replace(":", "_").lower()


def _iter_key_variants(key: str) -> list[str]:
    variants: list[str] = [key]

    if key == "co2_level":
        variants.append("carbon_dioxide")
    elif key == "carbon_dioxide":
        variants.append("co2_level")

    if key.endswith("_temp"):
        variants.append(f"{key[:-5]}_temperature")
    elif key.endswith("_temperature"):
        variants.append(f"{key[:-12]}_temp")

    return _unique_in_order(variants)


def iter_ramses_cc_entity_ids(
    domain: str,
    key: str,
    *,
    device_id: str | None = None,
    device_id_underscore: str | None = None,
    slugs: tuple[str, ...] = ("", "fan", "co2"),
) -> list[str]:
    if not domain or not key:
        return []

    if device_id_underscore is None:
        if not device_id:
            return []
        device_id_underscore = _device_id_to_underscore(device_id)
    else:
        device_id_underscore = device_id_underscore.lower()

    base_variants = _iter_key_variants(key)

    result: list[str] = []
    for slug in slugs:
        if slug:
            prefix = f"{slug}_{device_id_underscore}_"
        else:
            prefix = f"{device_id_underscore}_"

        key_variants = list(base_variants)

        if slug == "fan":
            key_variants.sort(
                key=lambda k: (
                    0 if k.endswith("_temperature") else 1 if k.endswith("_temp") else 2
                )
            )
        elif slug == "co2":
            key_variants.sort(
                key=lambda k: (
                    0 if k == "carbon_dioxide" else 1 if k == "co2_level" else 2
                )
            )

        for key_variant in key_variants:
            result.append(f"{domain}.{prefix}{key_variant}")

    return _unique_in_order(result)


def iter_ramses_cc_entity_id_fallbacks(
    entity_id: str,
    *,
    device_id: str | None = None,
    device_id_underscore: str | None = None,
) -> list[str]:
    if not isinstance(entity_id, str) or "." not in entity_id:
        return []

    domain, object_id = entity_id.split(".", 1)
    if not domain or not object_id:
        return []

    if device_id_underscore is None:
        if not device_id:
            return []
        device_id_underscore = _device_id_to_underscore(device_id)
    else:
        device_id_underscore = device_id_underscore.lower()

    slug_prefixes = (
        f"{device_id_underscore}_",
        f"fan_{device_id_underscore}_",
        f"co2_{device_id_underscore}_",
    )

    key: str | None = None
    for slug_prefix in slug_prefixes:
        if object_id.startswith(slug_prefix):
            key = object_id[len(slug_prefix) :]
            break

    if not key:
        return []

    candidates = iter_ramses_cc_entity_ids(
        domain,
        key,
        device_id_underscore=device_id_underscore,
    )

    return [c for c in candidates if c != entity_id]
