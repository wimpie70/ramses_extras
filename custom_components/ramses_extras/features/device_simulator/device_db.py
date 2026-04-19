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

import asyncio
import re as _re
from dataclasses import dataclass, field
from datetime import datetime as _datetime
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


# Matches both ISO "2026-04-18T18:51:46.915588" and classic "2024-01-01 12:00:00.123"
_TS_PATTERN = _re.compile(r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\b")
_VERBS = ("RQ", "RP", "I", "W")
_DEVICE_ID = _re.compile(r"(?:\d{2}:\d{6}|--:------|\d{3}:\d{6})")


def _parse_timestamp(raw: str) -> _datetime | None:
    """Parse an ISO or classic ramses timestamp."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return _datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_ramses_log(
    content: str,
) -> tuple[list[ConversationFrame], set[str]]:
    """Parse a ramses log blob into chronologically sorted frames.

    Accepts three styles (fields may be tab- or space-separated):

    * **Classic ramses.log**: ``timestamp RSSI verb src dst code payload``
      e.g. ``2024-01-01 12:00:00.123 082 I 20:123456 --:------ 31DA 0001020304``
    * **Newer tab-separated dumps**: ``timestamp verb code src dst length payload``
      e.g. ``2026-04-18T18:51:46.915588\tRP\t2349\t01:150000\t18:000730\t013 0807C0...``
    * **Device-name format**: ``timestamp verb code_hex device_slug target``
      ``length payload``
      e.g. ``2025-01-01T00:00:00.000000\tI\t31E0\tCO2\tALL\t007\t6400CD03E803E8``

    The parser splits input by detected timestamps, tokenises each record, and
    identifies verb/code/src/dst positions dynamically to tolerate various orderings.

    Returns ``(frames, peers_set)`` where frames are sorted chronologically and
    peer device_ids (excluding broadcast ``--:------``) are collected.

    :param content: Raw log content as a single string.
    """
    # Split the content into chunks that each start with a timestamp
    matches = list(_TS_PATTERN.finditer(content))
    if not matches:
        return [], set()

    records: list[tuple[_datetime, list[str]]] = []
    for idx, m in enumerate(matches):
        ts_raw = m.group(1)
        ts = _parse_timestamp(ts_raw)
        if ts is None:
            continue
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        rest = content[start:end]
        tokens = [tok for tok in _re.split(r"[\t ]+", rest.strip()) if tok]
        if not tokens:
            continue
        records.append((ts, tokens))

    # Parse each record into a ConversationFrame candidate
    frames: list[ConversationFrame] = []
    raw_frames: list[tuple[_datetime, ConversationFrame]] = []
    peers_set: set[str] = set()

    for ts, tokens in records:
        # Find verb
        verb_idx = next((i for i, t in enumerate(tokens) if t in _VERBS), None)
        if verb_idx is None:
            continue
        verb = tokens[verb_idx]

        # Try to find two device-id tokens (src, dst) — in that order
        dev_idxs = [i for i, t in enumerate(tokens) if _DEVICE_ID.fullmatch(t)]

        # If we don't have 2 device IDs, try alternate format:
        # timestamp verb code_hex device_name broadcast_flag length payload
        if len(dev_idxs) < 2:
            # Look for a 4-hex code right after verb
            code_candidates = [
                (i, t)
                for i, t in enumerate(tokens)
                if i > verb_idx
                and len(t) == 4
                and all(c in "0123456789ABCDEFabcdef" for c in t)
            ]
            if not code_candidates:
                continue
            code_idx, code = code_candidates[0]
            # In this format, src/dst are slugs immediately following the code
            src_idx = code_idx + 1
            dst_idx = code_idx + 2
            src = tokens[src_idx].upper() if src_idx < len(tokens) else "UNKNOWN"
            dst = tokens[dst_idx].upper() if dst_idx < len(tokens) else "ALL"
            # Payload is the last hex token (skip length prefix if present)
            hex_tokens = [
                (i, t)
                for i, t in enumerate(tokens)
                if i > code_idx and all(c in "0123456789ABCDEFabcdef" for c in t)
            ]
            if not hex_tokens:
                continue
            # Skip 3-digit length prefix if present
            if len(hex_tokens) > 1 and len(hex_tokens[0][1]) == 3:
                payload = hex_tokens[-1][1].upper()
            elif len(hex_tokens) == 1 and len(hex_tokens[0][1]) == 3:
                continue
            else:
                payload = hex_tokens[-1][1].upper()
        else:
            # Standard format with device IDs
            if len(dev_idxs) < 2:
                continue
            src = tokens[dev_idxs[0]]
            dst = tokens[dev_idxs[1]]

            # Find the 4-hex-digit code (appears once, separate from payload)
            code_candidates = [
                (i, t)
                for i, t in enumerate(tokens)
                if len(t) == 4
                and all(c in "0123456789ABCDEFabcdef" for c in t)
                and i != verb_idx
                and i not in dev_idxs
            ]
            if not code_candidates:
                continue
            code_idx, code = code_candidates[0]

            # Payload = last long hex token after code (skip length prefix if present).
            hex_tokens = [
                (i, t)
                for i, t in enumerate(tokens)
                if i > max(verb_idx, code_idx, *dev_idxs)
                and all(c in "0123456789ABCDEFabcdef" for c in t)
            ]
            if not hex_tokens:
                continue
            # If the first hex token is 3 digits, it's likely a length prefix
            if len(hex_tokens) > 1 and len(hex_tokens[0][1]) == 3:
                payload = hex_tokens[-1][1].upper()
            elif len(hex_tokens) == 1 and len(hex_tokens[0][1]) == 3:
                continue
            else:
                payload = hex_tokens[-1][1].upper()

        frame_src = src
        frame_dst = dst
        raw_frames.append(
            (
                ts,
                ConversationFrame(
                    t=0.0,  # filled in after sorting
                    src=frame_src,
                    dst=frame_dst,
                    code=code.upper(),
                    verb=verb,
                    payload=payload,
                ),
            )
        )

        peers_set.add(frame_src)
        if frame_dst != "--:------" and frame_dst != "ALL":
            peers_set.add(frame_dst)

    if not raw_frames:
        return [], peers_set

    # Sort chronologically, compute relative t from first frame
    raw_frames.sort(key=lambda pair: pair[0])
    t0 = raw_frames[0][0]
    for ts, fr in raw_frames:
        fr.t = (ts - t0).total_seconds()
        frames.append(fr)

    return frames, peers_set


class DeviceDatabase:
    """Runtime loader for the YAML device database.

    Loads all YAML files from device_db/ at startup.
    Provides fast lookup by device type slug, code, and variant.
    """

    def __init__(
        self,
        db_dir: Path | None = None,
        *,
        user_conversations_dir: Path | None = None,
    ) -> None:
        """Initialize the device database.

        :param db_dir: Path to device_db directory. Defaults to the bundled one.
        :param user_conversations_dir: Optional directory for user-imported
            conversation YAMLs. Defaults to ``<db_dir>/conversations/imported`` but
            can point to the Home Assistant config folder so imports survive
            deployments.
        """
        self._db_dir = db_dir or _DB_DIR
        self._device_types: dict[str, DeviceTypeEntry] = {}
        self._conversations: dict[str, Conversation] = {}
        default_import_dir = self._db_dir / DB_SUBDIR_CONVERSATIONS / "imported"
        self._user_conversations_dir = user_conversations_dir or default_import_dir

    def _import_directories(self) -> list[Path]:
        """Return all directories that may contain user-provided conversations."""

        dirs: list[Path] = []
        seen: set[str] = set()
        for candidate in (
            self._db_dir / DB_SUBDIR_CONVERSATIONS / "imported",
            self._user_conversations_dir,
        ):
            key = str(candidate)
            if key in seen:
                continue
            dirs.append(candidate)
            seen.add(key)
        return dirs

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
            for yaml_file in sorted(conv_path.glob("*.yaml")):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    self._parse_conversations(data)
                except Exception as err:
                    LOGGER.warning(
                        "Failed to load conversation %s: %s", yaml_file.name, err
                    )
        for import_dir in self._import_directories():
            if not import_dir.exists():
                continue
            for yaml_file in sorted(import_dir.glob("*.yaml")):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    self._parse_conversations(data)
                except Exception as err:  # noqa: BLE001
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

        :param ref: Conversation reference key or conversation ID.
        :param scheme: Optional scheme filter (e.g. 'itho').
        """
        # Try direct lookup by full key first (peers/id)
        conv = self._conversations.get(ref.lower())
        if conv is None:
            # Try lookup by conversation ID only (search all conversations)
            ref_lower = ref.lower()
            for c in self._conversations.values():
                if c.id.lower() == ref_lower:
                    conv = c
                    break
        if conv is None:
            return None
        if scheme and conv.scheme and conv.scheme != scheme:
            return None
        return conv

    async def import_user_log(
        self,
        path: str | None,
        name: str,
        content: str | None = None,
        save_yaml: bool = True,
    ) -> bool:
        """Import a user's ramses log and convert to a replayable conversation.

        Supports multiple log formats (see :func:`parse_ramses_log`). Entries may be
        spread across multiple lines or concatenated on a single line with tab
        separators; the parser splits by detected timestamps. Frames are sorted
        chronologically before being stored so out-of-order log dumps still replay
        correctly.

        :param path: Path to a log file (optional if ``content`` is provided).
        :param name: Name used for the generated conversation id.
        :param content: Raw log content (optional if ``path`` is provided).
        :param save_yaml: When True (default) persist a reusable YAML conversation
            under the configured user conversation directory (defaults to
            ``device_db/conversations/imported``) so imports survive restarts and
            deployments.
        :return: True if import succeeded, False otherwise.
        """
        from pathlib import Path

        if content is None:
            if not path:
                LOGGER.error("Either path or content must be provided")
                return False

            log_path = Path(path)
            if not log_path.exists():
                LOGGER.error("Log file not found: %s", path)
                return False

            def _read_file() -> str:
                with open(log_path, encoding="utf-8", errors="ignore") as f:
                    return f.read()

            content = await asyncio.to_thread(_read_file)

        if not content:
            LOGGER.error("No log content to import")
            return False

        try:
            frames, peers_set = parse_ramses_log(content)
        except Exception as err:
            LOGGER.error("Failed to parse log: %s", err)
            return False

        if not frames:
            LOGGER.error("No valid frames found in log")
            return False

        # Create conversation
        peers = sorted(peers_set)
        conv_id = name.lower().replace(" ", "_")
        source = Path(path).name if path else "pasted content"
        conv = Conversation(
            id=conv_id,
            peers=peers,
            description=f"Imported from {source}",
            scheme=None,
            frames=frames,
        )

        # Store in runtime conversations
        key = f"{'+'.join(peers).lower()}/{conv.id}"
        self._conversations[key] = conv
        # Also index by bare id for easy lookup from UI
        self._conversations[conv.id] = conv

        # Optionally persist as YAML for reuse across restarts
        if save_yaml:
            try:
                await asyncio.to_thread(self._save_conversation_yaml, conv)
            except Exception as err:
                LOGGER.warning("Imported but failed to save YAML: %s", err)

        LOGGER.info(
            "Imported conversation '%s' from %s (%d frames, %d peers: %s)",
            name,
            source,
            len(frames),
            len(peers),
            ", ".join(peers),
        )
        return True

    async def async_list_saved_playbacks(self) -> list[dict[str, Any]]:
        """List conversations available for playback.

        Includes both built-in conversations (``conversations/*.yaml``, marked
        ``builtin: True``) and user-imported ones (``conversations/imported/
        *.yaml``, ``builtin: False``). Built-ins are always present in the
        dropdown so there is at least one default playback and cannot be
        deleted. Sorted with built-ins first, then alphabetical.
        """
        import asyncio

        import yaml

        conv_dir = self._db_dir / DB_SUBDIR_CONVERSATIONS

        def _collect_sync(directory: Path, builtin: bool) -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            for fp in sorted(directory.glob("*.yaml")):
                try:
                    with open(fp, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    peers = data.get("peers") or []
                    convs = data.get("conversations") or []
                    for conv in convs:
                        items.append(
                            {
                                "id": conv.get("id", fp.stem),
                                "file": fp.name,
                                "peers": peers,
                                "frames": len(conv.get("frames") or []),
                                "description": conv.get("description"),
                                "builtin": builtin,
                            }
                        )
                except Exception as err:  # noqa: BLE001
                    LOGGER.warning("Failed to read playback %s: %s", fp, err)
            return items

        builtins: list[dict[str, Any]] = []
        if conv_dir.exists():
            builtins = await asyncio.to_thread(_collect_sync, conv_dir, True)
        imported: list[dict[str, Any]] = []
        for import_dir in self._import_directories():
            if import_dir.exists():
                imported.extend(
                    await asyncio.to_thread(_collect_sync, import_dir, False)
                )
        return builtins + imported

    def delete_saved_playback(self, identifier: str) -> bool:
        """Delete a saved playback by conversation id or YAML filename.

        Also removes the in-memory conversation entries so the dropdown stays
        in sync without requiring a full DB reload.

        :param identifier: Either the conversation ``id`` or the bare filename.
        :return: True if something was removed.
        """

        def _resolve_candidate(directory: Path) -> Path | None:
            target_file = directory / identifier
            if not target_file.exists() and not identifier.endswith(".yaml"):
                target_file = directory / f"{identifier}.yaml"
            if target_file.exists():
                return target_file
            # Last resort: search by id inside each file
            for fp in directory.glob("*.yaml"):
                try:
                    import yaml

                    with open(fp, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    convs = data.get("conversations") or []
                    if any(c.get("id") == identifier for c in convs):
                        return fp
                except Exception:  # noqa: BLE001
                    continue
            return None

        target_file: Path | None = None
        for import_dir in self._import_directories():
            if not import_dir.exists():
                continue
            target_file = _resolve_candidate(import_dir)
            if target_file is not None:
                break

        if target_file is None:
            LOGGER.warning("Saved playback '%s' not found", identifier)
            return False

        removed_ids: list[str] = []
        try:
            import yaml

            with open(target_file, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            for c in data.get("conversations") or []:
                cid = c.get("id")
                if cid:
                    removed_ids.append(cid)
        except Exception:  # noqa: BLE001
            pass

        try:
            target_file.unlink()
        except Exception as err:  # noqa: BLE001
            LOGGER.error("Failed to delete %s: %s", target_file, err)
            return False

        for cid in removed_ids:
            self._conversations.pop(cid, None)
            for key in list(self._conversations):
                if key.endswith(f"/{cid}"):
                    self._conversations.pop(key, None)

        LOGGER.info("Deleted saved playback %s (%s)", target_file.name, removed_ids)
        return True

    def get_playback_log_text(self, identifier: str) -> str | None:
        """Serialize a saved playback back to a ramses.log-style text blob.

        The produced text is round-trippable through :func:`parse_ramses_log`
        *for imported logs* (where ``src``/``dst`` are real device IDs like
        ``32:155617``). Built-in conversations that use peer slugs (e.g.
        ``FAN``, ``REM``) will still render, but re-importing the edited text
        requires replacing the slugs with actual device IDs first.

        Uses an arbitrary base timestamp of ``2025-01-01T00:00:00.000000`` so
        relative frame times are preserved verbatim.

        :param identifier: Conversation ``id`` or YAML filename.
        :return: Tab-separated log text (one line per frame) or ``None`` if
            the conversation cannot be located.
        """
        from datetime import datetime, timedelta

        conv = self._conversations.get(identifier.lower()) or next(
            (
                c
                for c in self._conversations.values()
                if c.id.lower() == identifier.lower()
            ),
            None,
        )
        if conv is None:
            return None

        base = datetime(2025, 1, 1, 0, 0, 0)
        lines: list[str] = []
        for frame in conv.frames:
            ts = base + timedelta(seconds=float(frame.t))
            ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S.%f")
            # Length prefix is byte count = len(payload)//2, zero-padded to 3
            try:
                length = f"{len(frame.payload) // 2:03d}"
            except Exception:  # noqa: BLE001
                length = "000"
            lines.append(
                "\t".join(
                    [
                        ts_str,
                        frame.verb,
                        frame.code,
                        frame.src,
                        frame.dst,
                        length,
                        frame.payload,
                    ]
                )
            )
        return "\n".join(lines)

    def _save_conversation_yaml(self, conv: Conversation) -> Path:
        """Write an imported conversation to device_db/conversations/imported/."""
        import yaml

        target_dir = self._user_conversations_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{conv.id}.yaml"

        data = {
            "peers": conv.peers,
            "conversations": [
                {
                    "id": conv.id,
                    "description": conv.description,
                    "scheme": conv.scheme,
                    "frames": [
                        {
                            "t": round(f.t, 6),
                            "src": f.src,
                            "dst": f.dst,
                            "code": f.code,
                            "verb": f.verb,
                            "payload": f.payload,
                        }
                        for f in conv.frames
                    ],
                }
            ],
        }
        with open(target_file, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False)
        LOGGER.info("Saved imported conversation YAML → %s", target_file)
        return target_file

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
