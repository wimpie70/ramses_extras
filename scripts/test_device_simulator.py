#!/usr/bin/env python3
"""Test script for device_simulator feature
- validates imports and basic functionality."""

from __future__ import annotations

import sys
from pathlib import Path

# Add custom_components to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))


def test_imports() -> bool:
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from ramses_extras.features.device_simulator import const, device_db
        from ramses_extras.features.device_simulator.scenario_engine import (
            SCENARIO_STATE_IDLE,
            ScenarioEngine,
        )

        print(f"  ✓ const: MQTT_TOPIC_BASE = {const.MQTT_TOPIC_BASE}")
        print("  ✓ device_db: DeviceDatabase class available")
        print("  ✓ scenario_engine: ScenarioEngine, states defined")
        return True
    except ImportError as err:
        print(f"  ✗ Import failed: {err}")
        return False


def test_device_database() -> bool:
    """Test device database loading."""
    print("\nTesting device database...")
    try:
        from ramses_extras.features.device_simulator.device_db import DeviceDatabase

        db = DeviceDatabase()
        db.load_all()

        device_count = len(db._device_types)
        conv_count = len(db._conversations)

        print(f"  ✓ Loaded {device_count} device types")
        print(f"  ✓ Loaded {conv_count} conversations")

        # Show some examples
        if device_count > 0:
            examples = list(db._device_types.keys())[:3]
            print(f"  ✓ Examples: {', '.join(examples)}")

        return True
    except Exception as err:
        print(f"  ✗ Database load failed: {err}")
        return False


def test_conversation_files() -> bool:
    """Test conversation YAML files are valid."""
    print("\nTesting conversation files...")
    try:
        from ramses_extras.features.device_simulator.device_db import DeviceDatabase

        db = DeviceDatabase()
        db._load_conversations()

        print(f"  ✓ Found {len(db._conversations)} conversation files")

        for ref, conv in list(db._conversations.items())[:3]:
            print(f"  ✓ {ref}: {len(conv.frames)} frames, peers: {conv.peers}")

        return True
    except Exception as err:
        print(f"  ✗ Conversation load failed: {err}")
        return False


def test_scenario_engine_creation() -> bool:
    """Test ScenarioEngine can be instantiated (without HA)."""
    print("\nTesting scenario engine structure...")
    try:
        from ramses_extras.features.device_simulator.scenario_engine import (
            ScenarioEngine,
        )

        # Check class has expected methods
        methods = [
            "async_activate_device",
            "async_silence_device",
            "async_play_conversation",
            "async_run_device_playback",
            "async_run_device_suite",
        ]

        for method in methods:
            if hasattr(ScenarioEngine, method):
                print(f"  ✓ {method} defined")
            else:
                print(f"  ✗ {method} missing")
                return False

        return True
    except Exception as err:
        print(f"  ✗ Scenario engine check failed: {err}")
        return False


def test_websocket_commands() -> bool:
    """Test WebSocket command handlers are defined."""
    print("\nTesting WebSocket commands...")
    try:
        from ramses_extras.features.device_simulator import websocket

        commands = [
            "ws_get_status",
            "ws_get_devices",
            "ws_get_active_devices",
            "ws_activate_device",
            "ws_silence_device",
            "ws_get_conversations",
            "ws_run_conversation",
            "ws_get_messages",
        ]

        for cmd in commands:
            if hasattr(websocket, cmd):
                print(f"  ✓ {cmd} defined")
            else:
                print(f"  ✗ {cmd} missing")
                return False

        return True
    except Exception as err:
        print(f"  ✗ WebSocket check failed: {err}")
        return False


def test_services() -> bool:
    """Test service handlers are defined."""
    print("\nTesting services...")
    try:
        from ramses_extras.features.device_simulator import services, websocket

        # Check key functions exist
        funcs = [
            "async_setup_services",
            "_get_engine",
        ]

        for func in funcs:
            if hasattr(services, func):
                print(f"  ✓ services.{func} defined")
            else:
                print(f"  ✗ services.{func} missing")
                return False

        # _get_db is in websocket module
        if hasattr(websocket, "_get_db"):
            print("  ✓ websocket._get_db defined")
        else:
            print("  ✗ websocket._get_db missing")
            return False

        return True
    except Exception as err:
        print(f"  ✗ Services check failed: {err}")
        return False


def main() -> int:
    """Run all tests."""
    print("=" * 60)
    print("Device Simulator Feature - End-to-End Verification")
    print("=" * 60)

    tests = [
        test_imports,
        test_device_database,
        test_conversation_files,
        test_scenario_engine_creation,
        test_websocket_commands,
        test_services,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as err:
            print(f"  ✗ Test crashed: {err}")
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("✓ All tests passed! Feature is ready for HA integration.")
        return 0
    print("✗ Some tests failed. Review output above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
