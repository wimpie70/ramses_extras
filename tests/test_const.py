"""Tests for core constants module."""

from custom_components.ramses_extras.const import (
    DOMAIN,
    GITHUB_URL,
    GITHUB_WIKI_URL,
    get_feature_platform_setups,
)


def test_domain_constant():
    """Test DOMAIN constant."""
    assert DOMAIN == "ramses_extras"


def test_github_urls():
    """Test GitHub URL constants."""
    assert GITHUB_URL == "https://github.com/wimpie70/ramses_extras"
    assert GITHUB_WIKI_URL == f"{GITHUB_URL}/wiki"


def test_get_feature_platform_setups_non_existent_platform():
    """Test get_feature_platform_setups with non-existent platform (covers line 60)."""
    setups = get_feature_platform_setups("non_existent_platform")
    assert setups == []
