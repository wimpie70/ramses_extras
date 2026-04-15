# Part of the Ramses Extra integration
# See https://github.com/wimpie70/ramses_extras for more information
#
"""Tests for device_simulator DeviceDatabase."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from custom_components.ramses_extras.features.device_simulator.device_db import (
    AutonomousEntry,
    Conversation,
    ConversationFrame,
    DeviceDatabase,
    DeviceTypeEntry,
    DeviceVariant,
    ResponseEntry,
)


class TestAutonomousEntry:
    """Tests for AutonomousEntry dataclass."""

    def test_default_values(self) -> None:
        """Test AutonomousEntry default values."""
        entry = AutonomousEntry(code="31DA")
        assert entry.code == "31DA"
        assert entry.verb == "I"
        assert entry.trigger == "periodic"
        assert entry.interval_seconds == 60.0
        assert entry.payloads == []
        assert entry.notes == ""

    def test_custom_values(self) -> None:
        """Test AutonomousEntry with custom values."""
        entry = AutonomousEntry(
            code="31DA",
            verb="I",
            trigger="state_change",
            interval_seconds=30.0,
            payloads=["payload1", "payload2"],
            notes="Test notes",
        )
        assert entry.code == "31DA"
        assert entry.trigger == "state_change"
        assert entry.interval_seconds == 30.0
        assert entry.payloads == ["payload1", "payload2"]
        assert entry.notes == "Test notes"


class TestResponseEntry:
    """Tests for ResponseEntry dataclass."""

    def test_default_values(self) -> None:
        """Test ResponseEntry default values."""
        entry = ResponseEntry(code="31DA")
        assert entry.code == "31DA"
        assert entry.rq_verb == "RQ"
        assert entry.rp_verb == "RP"
        assert entry.delay_ms == 100
        assert entry.payloads == []
        assert entry.notes == ""

    def test_custom_values(self) -> None:
        """Test ResponseEntry with custom values."""
        entry = ResponseEntry(
            code="31DA",
            rq_verb="RQ",
            rp_verb="RP",
            delay_ms=200,
            payloads=["payload1"],
            notes="Response notes",
        )
        assert entry.code == "31DA"
        assert entry.delay_ms == 200
        assert entry.payloads == ["payload1"]
        assert entry.notes == "Response notes"


class TestConversationFrame:
    """Tests for ConversationFrame dataclass."""

    def test_frame_creation(self) -> None:
        """Test ConversationFrame creation."""
        frame = ConversationFrame(
            t=0.0,
            src="FAN",
            dst="REM",
            code="31DA",
            verb="I",
            payload="01020304",
        )
        assert frame.t == 0.0
        assert frame.src == "FAN"
        assert frame.dst == "REM"
        assert frame.code == "31DA"
        assert frame.verb == "I"
        assert frame.payload == "01020304"


class TestConversation:
    """Tests for Conversation dataclass."""

    def test_conversation_creation(self) -> None:
        """Test Conversation creation."""
        frame = ConversationFrame(
            t=0.0, src="FAN", dst="REM", code="31DA", verb="I", payload="0102"
        )
        conv = Conversation(
            id="speed_change",
            peers=["FAN", "REM"],
            description="Speed change exchange",
            scheme="itho",
            frames=[frame],
        )
        assert conv.id == "speed_change"
        assert conv.peers == ["FAN", "REM"]
        assert conv.description == "Speed change exchange"
        assert conv.scheme == "itho"
        assert len(conv.frames) == 1


class TestDeviceVariant:
    """Tests for DeviceVariant dataclass."""

    def test_default_values(self) -> None:
        """Test DeviceVariant default values."""
        variant = DeviceVariant(id="itho_cve_rf")
        assert variant.id == "itho_cve_rf"
        assert variant.fingerprint == ""
        assert variant.desc == ""
        assert variant.brand == ""
        assert variant.date == ""
        assert variant.codes == []
        assert variant.scheme_22f1 is None
        assert variant.overrides == {}
        assert variant.broadcast_safe is False


class TestDeviceTypeEntry:
    """Tests for DeviceTypeEntry dataclass."""

    def test_default_values(self) -> None:
        """Test DeviceTypeEntry default values."""
        entry = DeviceTypeEntry(device_type="FAN", domain="hvac")
        assert entry.device_type == "FAN"
        assert entry.domain == "hvac"
        assert entry.broadcast_safe is False
        assert entry.variants == []
        assert entry.autonomous == []
        assert entry.responses == []
        assert entry.conversation_refs == []


class TestDeviceDatabaseInit:
    """Tests for DeviceDatabase initialization."""

    def test_default_db_dir(self) -> None:
        """Test default database directory."""
        db = DeviceDatabase()
        assert db._db_dir.name == "device_db"

    def test_custom_db_dir(self) -> None:
        """Test custom database directory."""
        custom_path = Path("/tmp/test_db")
        db = DeviceDatabase(db_dir=custom_path)
        assert db._db_dir == custom_path

    def test_empty_state(self) -> None:
        """Test initial empty state."""
        db = DeviceDatabase()
        assert db._device_types == {}
        assert db._conversations == {}


class TestDeviceDatabaseParsing:
    """Tests for DeviceDatabase YAML parsing."""

    @pytest.fixture
    def temp_db_dir(self, tmp_path: Path) -> Path:
        """Create a temporary database directory with test YAML files."""
        # Create heat directory and test file
        heat_dir = tmp_path / "heat"
        heat_dir.mkdir()
        heat_yaml = heat_dir / "DHW.yaml"
        heat_data = {
            "device_type": "DHW",
            "domain": "heat",
            "broadcast_safe": True,
            "variants": [
                {
                    "id": "base",
                    "fingerprint": "0001",
                    "desc": "DHW sensor",
                    "brand": "Honeywell",
                    "date": "2024",
                    "codes": ["10E0", "1260"],
                }
            ],
            "autonomous": [
                {
                    "code": "10E0",
                    "interval_seconds": 60.0,
                    "payloads": ["payload1"],
                    "notes": "DHW status",
                }
            ],
            "responses": [
                {
                    "code": "10E0",
                    "rq_verb": "RQ",
                    "rp_verb": "RP",
                    "delay_ms": 100,
                    "payloads": ["response1"],
                    "notes": "DHW fingerprint",
                }
            ],
        }
        heat_yaml.write_text(yaml.dump(heat_data))

        # Create hvac directory and test file
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            "device_type": "FAN",
            "domain": "hvac",
            "broadcast_safe": True,
            "variants": [
                {
                    "id": "itho_cve_rf",
                    "fingerprint": "00-00-00-1F-82",
                    "desc": "Itho CVE RF fan",
                    "brand": "Itho",
                    "date": "2024",
                    "codes": ["31DA", "22F1"],
                    "scheme_22f1": "itho",
                    "broadcast_safe": True,
                }
            ],
            "autonomous": [
                {
                    "code": "31DA",
                    "interval_seconds": 30.0,
                    "payloads": ["21..."],
                    "notes": "Fan status",
                }
            ],
            "responses": [
                {
                    "code": "22F1",
                    "delay_ms": 50,
                    "payloads": ["0001"],
                    "notes": "Speed response",
                }
            ],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        # Create conversations directory and test file
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        conv_yaml = conv_dir / "fan_rem.yaml"
        conv_data = {
            "peers": ["FAN", "REM"],
            "conversations": [
                {
                    "id": "speed_change",
                    "description": "Speed change sequence",
                    "scheme": "itho",
                    "frames": [
                        {
                            "t": 0.0,
                            "src": "REM",
                            "dst": "FAN",
                            "code": "22F1",
                            "verb": "RQ",
                            "payload": "01",
                        },
                        {
                            "t": 0.1,
                            "src": "FAN",
                            "dst": "REM",
                            "code": "22F1",
                            "verb": "RP",
                            "payload": "0001",
                        },
                    ],
                }
            ],
        }
        conv_yaml.write_text(yaml.dump(conv_data))

        return tmp_path

    def test_load_all(self, temp_db_dir: Path) -> None:
        """Test loading all YAML files."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        assert len(db._device_types) == 2
        assert "DHW" in db._device_types
        assert "FAN" in db._device_types
        assert len(db._conversations) == 1

    def test_get_device_type(self, temp_db_dir: Path) -> None:
        """Test get_device_type method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        # Test case insensitive lookup
        fan = db.get_device_type("FAN")
        assert fan is not None
        assert fan.device_type == "FAN"

        fan_lower = db.get_device_type("fan")
        assert fan_lower is not None

        missing = db.get_device_type("NONEXISTENT")
        assert missing is None

    def test_get_variant(self, temp_db_dir: Path) -> None:
        """Test get_variant method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        result = db.get_variant("FAN", "itho_cve_rf")
        assert result is not None
        entry, variant = result
        assert entry.device_type == "FAN"
        assert variant.id == "itho_cve_rf"
        assert variant.scheme_22f1 == "itho"

        missing = db.get_variant("FAN", "nonexistent")
        assert missing is None

        missing_type = db.get_variant("NONEXISTENT", "base")
        assert missing_type is None

    def test_find_response(self, temp_db_dir: Path) -> None:
        """Test find_response method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        # Test finding response
        resp = db.find_response("FAN", "22F1")
        assert resp is not None
        assert resp.code == "22F1"
        assert resp.payloads == ["0001"]
        assert resp.delay_ms == 50

        # Test missing response
        missing = db.find_response("FAN", "9999")
        assert missing is None

        # Test missing device type
        missing_type = db.find_response("NONEXISTENT", "22F1")
        assert missing_type is None

    def test_find_response_with_variant(self, temp_db_dir: Path) -> None:
        """Test find_response with variant override."""
        # Create device with variant override
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        # For now, test without variant (baseline behavior)
        resp = db.find_response("FAN", "22F1", variant_id="itho_cve_rf")
        assert resp is not None

    def test_get_periodic(self, temp_db_dir: Path) -> None:
        """Test get_periodic method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        periodic = db.get_periodic("FAN")
        assert len(periodic) == 1
        assert periodic[0].code == "31DA"
        assert periodic[0].interval_seconds == 30.0

        # Test missing device
        missing = db.get_periodic("NONEXISTENT")
        assert missing == []

    def test_get_conversation(self, temp_db_dir: Path) -> None:
        """Test get_conversation method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        conv = db.get_conversation("fan+rem/speed_change")
        assert conv is not None
        assert conv.id == "speed_change"
        assert conv.scheme == "itho"
        assert len(conv.frames) == 2

        # Test missing conversation
        missing = db.get_conversation("nonexistent")
        assert missing is None

        # Test scheme filtering
        wrong_scheme = db.get_conversation("fan+rem/speed_change", scheme="orcon")
        assert wrong_scheme is None

        # Test matching scheme
        matching_scheme = db.get_conversation("fan+rem/speed_change", scheme="itho")
        assert matching_scheme is not None

    def test_get_fingerprint_payload(self, temp_db_dir: Path) -> None:
        """Test get_fingerprint_payload method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        # Test with matching fingerprint
        # Note: The FAN variant has fingerprint "00-00-00-1F-82"
        # but DHW has the 10E0 response, so this should return the fingerprint
        # as fallback
        payload = db.get_fingerprint_payload("00-00-00-1F-82")
        # FAN doesn't have 10E0 response, so returns fingerprint itself
        assert payload == "00-00-00-1F-82"

        # Test non-matching fingerprint
        missing = db.get_fingerprint_payload("NONEXISTENT")
        assert missing is None

    def test_stats(self, temp_db_dir: Path) -> None:
        """Test stats method."""
        db = DeviceDatabase(db_dir=temp_db_dir)
        db.load_all()

        stats = db.stats()
        assert stats["device_types"] == 2
        assert stats["conversations"] == 1
        assert "DHW" in stats["types"]
        assert "FAN" in stats["types"]

    def test_load_all_missing_yaml(self, tmp_path: Path) -> None:
        """Test load_all with missing yaml module."""
        db = DeviceDatabase(db_dir=tmp_path)

        with patch.dict("sys.modules", {"yaml": None}):
            # Should not raise, just log error and return
            db.load_all()
            assert db._device_types == {}


class TestDeviceDatabaseVariantOverrides:
    """Tests for variant override functionality."""

    @pytest.fixture
    def db_with_overrides(self, tmp_path: Path) -> DeviceDatabase:
        """Create a database with variant overrides."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            "device_type": "FAN",
            "domain": "hvac",
            "variants": [
                {
                    "id": "base",
                    "codes": ["31DA"],
                },
                {
                    "id": "premium",
                    "codes": ["31DA", "31D9"],
                    "overrides": {
                        "responses": [
                            {
                                "code": "31DA",
                                "delay_ms": 200,
                                "payloads": ["premium_payload"],
                            }
                        ],
                        "autonomous": [
                            {
                                "code": "31DA",
                                "interval_seconds": 15.0,
                                "payloads": ["premium_auto"],
                            }
                        ],
                    },
                },
            ],
            "autonomous": [
                {"code": "31DA", "interval_seconds": 30.0, "payloads": ["base_payload"]}
            ],
            "responses": [
                {"code": "31DA", "delay_ms": 100, "payloads": ["base_response"]}
            ],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()
        return db

    def test_find_response_with_variant_override(
        self, db_with_overrides: DeviceDatabase
    ) -> None:
        """Test response lookup with variant override."""
        # Base variant should use baseline response
        resp_base = db_with_overrides.find_response("FAN", "31DA", variant_id="base")
        assert resp_base is not None
        assert resp_base.delay_ms == 100
        assert resp_base.payloads == ["base_response"]

        # Premium variant should use override
        resp_premium = db_with_overrides.find_response(
            "FAN", "31DA", variant_id="premium"
        )
        assert resp_premium is not None
        assert resp_premium.delay_ms == 200
        assert resp_premium.payloads == ["premium_payload"]

    def test_find_response_override_partial_fields(
        self, db_with_overrides: DeviceDatabase
    ) -> None:
        """Test response lookup with override that only specifies some fields."""
        # Add a variant with partial override
        hvac_dir = db_with_overrides._db_dir / "hvac"
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = yaml.safe_load(fan_yaml.read_text())
        fan_data["variants"].append(
            {
                "id": "partial",
                "codes": ["31DA"],
                "overrides": {
                    "responses": [
                        {
                            "code": "31DA",
                            # Only override delay_ms, not payloads
                            "delay_ms": 300,
                        }
                    ]
                },
            }
        )
        fan_yaml.write_text(yaml.dump(fan_data))

        db_with_overrides.load_all()

        resp = db_with_overrides.find_response("FAN", "31DA", variant_id="partial")
        assert resp is not None
        assert resp.delay_ms == 300
        # Payloads should be empty since not specified in override
        assert resp.payloads == []

    def test_get_periodic_with_variant_override(
        self, db_with_overrides: DeviceDatabase
    ) -> None:
        """Test periodic lookup with variant override."""
        # Base variant should use baseline
        periodic_base = db_with_overrides.get_periodic("FAN", variant_id="base")
        assert len(periodic_base) == 1
        assert periodic_base[0].interval_seconds == 30.0
        assert periodic_base[0].payloads == ["base_payload"]

        # Premium variant should use override
        periodic_premium = db_with_overrides.get_periodic("FAN", variant_id="premium")
        assert len(periodic_premium) == 1
        assert periodic_premium[0].interval_seconds == 15.0
        assert periodic_premium[0].payloads == ["premium_auto"]

    def test_get_periodic_variant_code_filtering(
        self, db_with_overrides: DeviceDatabase
    ) -> None:
        """Test that variant codes filter the periodic entries."""
        # Premium variant supports 31DA and 31D9
        # Since baseline only has 31DA, filtered result should still have 31DA
        periodic_premium = db_with_overrides.get_periodic("FAN", variant_id="premium")
        assert len(periodic_premium) == 1
        assert periodic_premium[0].code == "31DA"

    def test_get_periodic_variant_filters_out_unsupported_codes(
        self, db_with_overrides: DeviceDatabase
    ) -> None:
        """Test that variant codes filter removes unsupported codes."""
        # Add a code to baseline that's not in the variant
        hvac_dir = db_with_overrides._db_dir / "hvac"
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = yaml.safe_load(fan_yaml.read_text())
        fan_data["autonomous"].append(
            {"code": "31D9", "interval_seconds": 45.0, "payloads": ["extra"]}
        )
        # Change base variant to only support 31DA
        fan_data["variants"][0]["codes"] = ["31DA"]
        fan_yaml.write_text(yaml.dump(fan_data))

        # Reload
        db_with_overrides.load_all()

        # Base variant should only have 31DA (filtered by codes)
        periodic_base = db_with_overrides.get_periodic("FAN", variant_id="base")
        assert len(periodic_base) == 1
        assert periodic_base[0].code == "31DA"

        # Premium variant has 31DA and 31D9 in its codes list
        periodic_premium = db_with_overrides.get_periodic("FAN", variant_id="premium")
        # Premium codes list is ["31DA", "31D9"], so it should have both
        assert len(periodic_premium) == 2


class TestDeviceDatabaseLoadAllEdgeCases:
    """Tests for load_all edge cases."""

    def test_load_all_yaml_parse_error(self, tmp_path: Path) -> None:
        """Test load_all with YAML parse error."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_yaml.write_text("invalid: yaml: content: [unclosed")

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise, just log warning
        assert db._device_types == {}

    def test_load_all_missing_subdirectories(self, tmp_path: Path) -> None:
        """Test load_all when subdirectories don't exist."""
        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise
        assert db._device_types == {}
        assert db._conversations == {}

    def test_load_all_empty_yaml(self, tmp_path: Path) -> None:
        """Test load_all with empty YAML file."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_yaml.write_text("")

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise
        assert db._device_types == {}

    def test_load_all_conversation_parse_error(self, tmp_path: Path) -> None:
        """Test load_all with conversation parse error."""
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        conv_yaml = conv_dir / "test.yaml"
        conv_yaml.write_text("invalid: yaml: content: [unclosed")

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise, just log warning
        assert db._conversations == {}


class TestDeviceDatabaseParseEdgeCases:
    """Tests for parsing edge cases."""

    def test_parse_device_type_missing_required_field(self, tmp_path: Path) -> None:
        """Test parsing device type without required device_type field."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            # Missing device_type field
            "domain": "hvac",
            "variants": [],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise, just log warning
        assert db._device_types == {}

    def test_parse_conversations_empty_list(self, tmp_path: Path) -> None:
        """Test parsing conversations with empty list."""
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        conv_yaml = conv_dir / "test.yaml"
        conv_data = {
            "peers": ["FAN", "REM"],
            "conversations": [],
        }
        conv_yaml.write_text(yaml.dump(conv_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise
        assert db._conversations == {}

    def test_parse_conversations_missing_peers(self, tmp_path: Path) -> None:
        """Test parsing conversations without peers field."""
        conv_dir = tmp_path / "conversations"
        conv_dir.mkdir()
        conv_yaml = conv_dir / "test.yaml"
        conv_data = {
            "conversations": [
                {
                    "id": "test",
                    "frames": [],
                }
            ],
        }
        conv_yaml.write_text(yaml.dump(conv_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Should not raise, creates conversation with empty peers list
        assert len(db._conversations) == 1
        assert db._conversations["/test"].peers == []


class TestDeviceDatabaseFingerprintPayload:
    """Tests for get_fingerprint_payload edge cases."""

    def test_get_fingerprint_payload_with_10e0_response(self, tmp_path: Path) -> None:
        """Test get_fingerprint_payload when variant has 10E0 response."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            "device_type": "FAN",
            "domain": "hvac",
            "variants": [
                {
                    "id": "test_variant",
                    "fingerprint": "00-00-00-1F-82",
                }
            ],
            "responses": [
                {
                    "code": "10E0",
                    "delay_ms": 100,
                    "payloads": ["fingerprint_payload"],
                }
            ],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        payload = db.get_fingerprint_payload("00-00-00-1F-82")
        assert payload == "fingerprint_payload"

    def test_get_fingerprint_payload_empty_fingerprint(self, tmp_path: Path) -> None:
        """Test get_fingerprint_payload with empty fingerprint."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            "device_type": "FAN",
            "domain": "hvac",
            "variants": [
                {
                    "id": "test_variant",
                    "fingerprint": "",
                }
            ],
            "responses": [
                {
                    "code": "10E0",
                    "delay_ms": 100,
                    "payloads": ["fingerprint_payload"],
                }
            ],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Empty fingerprint matches the empty fingerprint in the variant
        payload = db.get_fingerprint_payload("")
        assert payload == "fingerprint_payload"


class TestDeviceDatabaseFindResponseEdgeCases:
    """Tests for find_response edge cases."""

    def test_find_response_variant_not_found(self, tmp_path: Path) -> None:
        """Test find_response when variant_id doesn't exist."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            "device_type": "FAN",
            "domain": "hvac",
            "variants": [
                {
                    "id": "base",
                    "overrides": {
                        "responses": [
                            {"code": "31DA", "delay_ms": 200, "payloads": ["override"]}
                        ]
                    },
                }
            ],
            "responses": [{"code": "31DA", "delay_ms": 100, "payloads": ["base"]}],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        # Non-existent variant should fall back to baseline
        resp = db.find_response("FAN", "31DA", variant_id="nonexistent")
        assert resp is not None
        assert resp.delay_ms == 100
        assert resp.payloads == ["base"]

    def test_find_response_override_without_payloads(self, tmp_path: Path) -> None:
        """Test find_response with override that has no payloads."""
        hvac_dir = tmp_path / "hvac"
        hvac_dir.mkdir()
        fan_yaml = hvac_dir / "FAN.yaml"
        fan_data = {
            "device_type": "FAN",
            "domain": "hvac",
            "variants": [
                {
                    "id": "base",
                    "overrides": {
                        "responses": [{"code": "31DA", "delay_ms": 200, "payloads": []}]
                    },
                }
            ],
            "responses": [{"code": "31DA", "delay_ms": 100, "payloads": ["base"]}],
        }
        fan_yaml.write_text(yaml.dump(fan_data))

        db = DeviceDatabase(db_dir=tmp_path)
        db.load_all()

        resp = db.find_response("FAN", "31DA", variant_id="base")
        assert resp is not None
        assert resp.delay_ms == 200
        assert resp.payloads == []
