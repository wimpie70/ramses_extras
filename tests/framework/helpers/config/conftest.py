"""Test configuration for config import tests.

Loads feature validators so they're available for all tests in this directory.
"""

import pytest

from custom_components.ramses_extras.framework.helpers.config.import_validation import (
    _feature_validators,
    get_registered_validators,
)


@pytest.fixture(autouse=True)
def reset_validators():
    """Reset validators before each test to ensure clean state."""
    _feature_validators.clear()
    yield


@pytest.fixture(autouse=True)
def load_feature_validators(reset_validators):
    """Load all feature validators for testing.

    This ensures validators are registered from the actual feature modules,
    matching production behavior. Runs after reset_validators to ensure
    clean state for each test.
    """
    # Load validators from sensor_control feature (includes zones and remote_binding)
    from custom_components.ramses_extras.features.sensor_control import (
        remote_binding_yaml as rb_yaml,
    )
    from custom_components.ramses_extras.features.sensor_control import (
        sensor_control_yaml as sc_yaml,
    )
    from custom_components.ramses_extras.features.sensor_control import zones_yaml

    zones_yaml.load_validator()
    rb_yaml.load_validator()
    sc_yaml.load_validator()

    yield

    # Cleanup: unregister validators after tests
    from custom_components.ramses_extras.framework.helpers.config import (
        import_validation as iv,
    )

    validators = get_registered_validators()
    for feature_id in list(validators.keys()):
        iv.unregister_config_validator(feature_id)
