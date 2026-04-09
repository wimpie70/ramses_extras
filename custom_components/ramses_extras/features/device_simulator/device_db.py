# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Device Database loader for Device Simulator.

Loads the structured YAML device database built offline from ramses_rf sources.
Provides fast lookup for the response engine and periodic emitter.

Database structure (under device_db/):
  heat/        — Layer 1+2: device type files with variant overrides
  hvac/        — Layer 1+2: device type files with variant overrides
  conversations/ — Layer 3: shared multi-device exchange blocks

Each device type YAML has:
  - variants:      hardware variants with fingerprints + optional overrides
  - autonomous:    baseline periodic / state-change messages
  - responses:     1:1 RQ→RP entries
  - conversations: refs into conversations/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .const import (
    DB_SUBDIR_CONVERSATIONS,
    DB_SUBDIR_HEAT,
    DB_SUBDIR_HVAC,
    LOGGER,
    TRIGGER_PERIODIC,
    VERB_I,
    VERB_RP,
    VERB_RQ,
)

_DB_DIR = Path(__file__).parent / "device_db"


@dataclass
class AutonomousEntry:
    """A message the device emits without being asked.

    :param code: RAMSES code (e.g. '31DA').
    :param verb: Always 'I'.
    :param trigger: 'periodic' or 'state_change'.
    :param interval_seconds: Interval for periodic trigger.
    :param payloads: List of example payloads to cycle through.
    :param notes: Human-readable description.
    """

    code: str
    verb: str = VERB_I
    trigger: str = TRIGGER_PERIODIC
    interval_seconds: float = 60.0
    payloads: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ResponseEntry:
    """A 1:1 RQ→RP response the device sends when queried.

    :param code: RAMSES code.
    :param rq_verb: Incoming verb (usually 'RQ').
    :param rp_verb: Reply verb (usually 'RP').
    :param delay_ms: Simulated response delay.
    :param payloads: List of example payloads.
    :param notes: Human-readable description.
    """

    code: str
    rq_verb: str = VERB_RQ
    rp_verb: str = VERB_RP
    delay_ms: int = 100
    payloads: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ConversationFrame:
    """A single frame within a conversation block.

    :param t: Relative timestamp in seconds from start of block.
    :param src: Source device slug (e.g. 'FAN', 'REM').
    :param dst: Destination slug or 'ALL' for broadcast.
    :param code: RAMSES code.
    :param verb: Message verb (I/RQ/RP/W).
    :param payload: Hex payload string.
    """

    t: float
    src: str
    dst: str
    code: str
    verb: str
    payload: str


@dataclass
class Conversation:
    """A multi-device exchange block.

    :param id: Unique conversation identifier.
    :param peers: List of device type slugs involved.
    :param description: Human-readable description.
    :param scheme: Optional scheme name (e.g. 'itho', 'orcon') for code semantics.
    :param frames: Ordered list of frames with relative timestamps.
    """

    id: str
    peers: list[str]
    description: str = ""
    scheme: str | None = None
    frames: list[ConversationFrame] = field(default_factory=list)


@dataclass
class DeviceVariant:
    """A hardware variant within a device type.

    :param id: Variant identifier (e.g. 'itho_cve_rf').
    :param fingerprint: Hardware fingerprint hex string.
    :param desc: Hardware description.
    :param brand: Brand name.
    :param date: Firmware/hardware date.
    :param codes: Codes supported by this variant (subset/superset of type baseline).
    :param scheme_22f1: Fan speed payload scheme ('itho', 'orcon', 'nuaire', 'vasco').
    :param overrides: Per-variant overrides for autonomous/responses entries.
    :param broadcast_safe: Whether this variant is safe to run in an isolated container.
    """

    id: str
    fingerprint: str = ""
    desc: str = ""
    brand: str = ""
    date: str = ""
    codes: list[str] = field(default_factory=list)
    scheme_22f1: str | None = None
    overrides: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    broadcast_safe: bool = False


@dataclass
class DeviceTypeEntry:
    """A device type with all variants, baseline behaviour, and conversation refs.

    :param device_type: Device type slug (e.g. 'FAN').
    :param domain: 'heat' or 'hvac'.
    :param broadcast_safe: Type-level broadcast safety flag.
    :param variants: List of hardware variants.
    :param autonomous: Baseline autonomous message list.
    :param responses: Baseline response list.
    :param conversation_refs: Refs into the conversations library.
    """

    device_type: str
    domain: str
    broadcast_safe: bool = False
    variants: list[DeviceVariant] = field(default_factory=list)
    autonomous: list[AutonomousEntry] = field(default_factory=list)
    responses: list[ResponseEntry] = field(default_factory=list)
    conversation_refs: list[str] = field(default_factory=list)


class DeviceDatabase:
    """Runtime loader for the YAML device database.

    Loads all YAML files from device_db/ at startup.
    Provides fast lookup by device type slug, code, and variant.
    """

    def __init__(self, db_dir: Path | None = None) -> None:
        """Initialize the device database.

        :param db_dir: Path to device_db directory. Defaults to the bundled one.
        """
        self._db_dir = db_dir or _DB_DIR
        self._device_types: dict[str, DeviceTypeEntry] = {}
        self._conversations: dict[str, Conversation] = {}

    def load_all(self) -> None:
        """Load all YAML files from the database directory."""
        try:
            import yaml
        except ImportError:
            LOGGER.error("PyYAML not available — cannot load device database")
            return

        loaded = 0
        for subdir in (DB_SUBDIR_HEAT, DB_SUBDIR_HVAC):
            subpath = self._db_dir / subdir
            if not subpath.exists():
                LOGGER.debug("Device DB subdir not found (expected): %s", subpath)
                continue
            for yaml_file in subpath.glob("*.yaml"):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    entry = self._parse_device_type(data, subdir)
                    self._device_types[entry.device_type] = entry
                    loaded += 1
                except Exception as err:
                    LOGGER.warning("Failed to load %s: %s", yaml_file.name, err)

        conv_path = self._db_dir / DB_SUBDIR_CONVERSATIONS
        if conv_path.exists():
            for yaml_file in conv_path.glob("*.yaml"):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    self._parse_conversations(data)
                except Exception as err:
                    LOGGER.warning(
                        "Failed to load conversation %s: %s", yaml_file.name, err
                    )

        LOGGER.info(
            "Device DB loaded: %d device types, %d conversations",
            loaded,
            len(self._conversations),
        )

    def _parse_device_type(self, data: dict[str, Any], domain: str) -> DeviceTypeEntry:
        """Parse a device type YAML file into a DeviceTypeEntry."""
        variants = [
            DeviceVariant(
                id=v.get("id", ""),
                fingerprint=v.get("fingerprint", ""),
                desc=v.get("desc", ""),
                brand=v.get("brand", ""),
                date=v.get("date", ""),
                codes=[str(c) for c in v.get("codes", [])],
                scheme_22f1=v.get("scheme_22f1"),
                overrides=v.get("overrides", {}),
                broadcast_safe=v.get("broadcast_safe", False),
            )
            for v in (data.get("variants") or [])
        ]
        autonomous = [
            AutonomousEntry(
                code=str(a["code"]),
                verb=a.get("verb", VERB_I),
                trigger=a.get("trigger", TRIGGER_PERIODIC),
                interval_seconds=float(a.get("interval_seconds", 60)),
                payloads=a.get("payloads") or [],
                notes=a.get("notes", ""),
            )
            for a in (data.get("autonomous") or [])
        ]
        responses = [
            ResponseEntry(
                code=str(r["code"]),
                rq_verb=r.get("rq_verb", VERB_RQ),
                rp_verb=r.get("rp_verb", VERB_RP),
                delay_ms=int(r.get("delay_ms", 100)),
                payloads=r.get("payloads") or [],
                notes=r.get("notes", ""),
            )
            for r in (data.get("responses") or [])
        ]
        conv_refs = [c.get("ref", "") for c in (data.get("conversations") or [])]

        return DeviceTypeEntry(
            device_type=data["device_type"],
            domain=data.get("domain", domain),
            broadcast_safe=data.get("broadcast_safe", False),
            variants=variants,
            autonomous=autonomous,
            responses=responses,
            conversation_refs=conv_refs,
        )

    def _parse_conversations(self, data: dict[str, Any]) -> None:
        """Parse a conversations YAML file."""
        peers = data.get("peers", [])
        for conv in data.get("conversations") or []:
            frames = [
                ConversationFrame(
                    t=float(f["t"]),
                    src=str(f["src"]),
                    dst=str(f["dst"]),
                    code=str(f["code"]),
                    verb=str(f["verb"]),
                    payload=str(f["payload"]),
                )
                for f in (conv.get("frames") or [])
            ]
            c = Conversation(
                id=conv["id"],
                peers=list(peers),
                description=conv.get("description", ""),
                scheme=conv.get("scheme"),
                frames=frames,
            )
            key = f"{'+'.join(peers).lower()}/{c.id}"
            self._conversations[key] = c

    def get_device_type(self, slug: str) -> DeviceTypeEntry | None:
        """Return a DeviceTypeEntry by slug.

        :param slug: Device type slug, e.g. 'FAN'.
        """
        return self._device_types.get(slug.upper())

    def get_variant(
        self, slug: str, variant_id: str
    ) -> tuple[DeviceTypeEntry, DeviceVariant] | None:
        """Return (DeviceTypeEntry, DeviceVariant) merged with baseline.

        Variant overrides are applied on top of the type baseline.

        :param slug: Device type slug.
        :param variant_id: Variant id.
        """
        entry = self.get_device_type(slug)
        if not entry:
            return None
        for variant in entry.variants:
            if variant.id == variant_id:
                return entry, variant
        return None

    def find_response(
        self, slug: str, code: str, variant_id: str | None = None
    ) -> ResponseEntry | None:
        """Find a response entry for a given slug + code.

        Checks variant overrides first, then type baseline.

        :param slug: Device type slug.
        :param code: RAMSES code.
        :param variant_id: Optional variant id for override lookup.
        """
        entry = self.get_device_type(slug)
        if not entry:
            return None

        if variant_id:
            for variant in entry.variants:
                if variant.id == variant_id:
                    for override in variant.overrides.get("responses", []):
                        if str(override.get("code")) == code:
                            return ResponseEntry(
                                code=code,
                                rq_verb=override.get("rq_verb", VERB_RQ),
                                rp_verb=override.get("rp_verb", VERB_RP),
                                delay_ms=int(override.get("delay_ms", 100)),
                                payloads=override.get("payloads") or [],
                            )
                    break

        for response_entry in entry.responses:
            if response_entry.code == code:
                return response_entry
        return None

    def get_periodic(
        self, slug: str, variant_id: str | None = None
    ) -> list[AutonomousEntry]:
        """Return autonomous periodic entries for a slug, with variant overrides
        applied.

        :param slug: Device type slug.
        :param variant_id: Optional variant id.
        """
        entry = self.get_device_type(slug)
        if not entry:
            return []

        baseline = {a.code: a for a in entry.autonomous}

        if variant_id:
            for variant in entry.variants:
                if variant.id == variant_id:
                    for override in variant.overrides.get("autonomous", []):
                        code = str(override.get("code", ""))
                        if code in baseline:
                            orig = baseline[code]
                            baseline[code] = AutonomousEntry(
                                code=code,
                                verb=override.get("verb", orig.verb),
                                trigger=override.get("trigger", orig.trigger),
                                interval_seconds=float(
                                    override.get(
                                        "interval_seconds", orig.interval_seconds
                                    )
                                ),
                                payloads=override.get("payloads") or orig.payloads,
                                notes=override.get("notes", orig.notes),
                            )
                    # Filter to codes supported by this variant
                    if variant.codes:
                        baseline = {
                            k: v for k, v in baseline.items() if k in variant.codes
                        }
                    break

        return list(baseline.values())

    def get_conversation(
        self, ref: str, scheme: str | None = None
    ) -> Conversation | None:
        """Return a conversation by ref string (e.g. 'fan+rem/speed_change').

        If scheme is given, prefers conversations with matching scheme.

        :param ref: Conversation reference key.
        :param scheme: Optional scheme filter (e.g. 'itho').
        """
        conv = self._conversations.get(ref.lower())
        if conv is None:
            return None
        if scheme and conv.scheme and conv.scheme != scheme:
            return None
        return conv

    def get_fingerprint_payload(self, fingerprint: str) -> str | None:
        """Return the 10E0 RP payload for a given hardware fingerprint.

        :param fingerprint: Hardware fingerprint hex string.
        """
        for entry in self._device_types.values():
            for variant in entry.variants:
                if variant.fingerprint == fingerprint:
                    resp = self.find_response(entry.device_type, "10E0", variant.id)
                    if resp and resp.payloads:
                        return resp.payloads[0]
                    return fingerprint
        return None

    def stats(self) -> dict[str, Any]:
        """Return database statistics."""
        return {
            "device_types": len(self._device_types),
            "conversations": len(self._conversations),
            "types": list(self._device_types.keys()),
        }
