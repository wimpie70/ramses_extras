#!/usr/bin/env python3
"""Test what exceptions parse_full_config_yaml actually raises."""

import sys

sys.path.insert(0, "/home/willem/dev/ramses_extras")

from custom_components.ramses_extras.framework.helpers.config.import_full import (
    parse_full_config_yaml,
)

# Test 1: Invalid zone type
yaml_content = """
ramses_extras:
  schema_version: 1
  features:
    zones:
      FANs:
        "32:153289":
          - zone_id: bathroom
            type: not_a_valid_type
"""

print("Test 1: Invalid zone type")
try:
    result = parse_full_config_yaml(yaml_content)
    print(f"  Result: {result}")
except Exception as e:
    print(f"  Exception type: {type(e).__name__}")
    print(f"  Exception message: {e}")

# Test 2: Invalid role
yaml_content2 = """
ramses_extras:
  schema_version: 1
  features:
    remote_binding:
      FANs:
        "32:153289":
          REMs:
            - rem_id: "37:169161"
              role: invalid_role
"""

print("\nTest 2: Invalid REM role")
try:
    result = parse_full_config_yaml(yaml_content2)
    print(f"  Result: {result}")
except Exception as e:
    print(f"  Exception type: {type(e).__name__}")
    print(f"  Exception message: {e}")

# Test 3: Invalid kind
yaml_content3 = """
ramses_extras:
  schema_version: 1
  features:
    sensor_control:
      abs_humidity_inputs:
        input1:
          temperature:
            kind: invalid_kind
          humidity:
            kind: internal
"""

print("\nTest 3: Invalid kind value")
try:
    result = parse_full_config_yaml(yaml_content3)
    print(f"  Result: {result}")
except Exception as e:
    print(f"  Exception type: {type(e).__name__}")
    print(f"  Exception message: {e}")
