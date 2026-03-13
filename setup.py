"""Setup script for Ramses Extras development."""

from setuptools import setup

setup(
    name="ramses_extras",
    version="0.16.1",
    packages=[
        "custom_components.ramses_extras",
        "custom_components.ramses_extras.framework",
    ],
    package_dir={
        "custom_components.ramses_extras": "custom_components/ramses_extras",
        "custom_components.ramses_extras.framework": "custom_components/ramses_extras/framework",
    },
    install_requires=[
        "homeassistant>=2026.3.1",
    ],
    extras_require={
        "test": [
            "pytest>=7.0.0",
            "pytest-cov>=3.0.0",
            "pytest-asyncio>=0.20.0",
            "pytest-mock>=3.10.0",
            "mypy>=0.910",
            "types-requests",
            "prek",
            "ruff",
        ],
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.24.0",
            "mypy>=1.11.0",
            "black>=24.0.0",
            "isort>=5.13.0",
            "flake8>=7.0.0",
            "prek>=0.3.4",
            "typing-extensions>=4.15.0",
        ],
    },
    python_requires=">=3.13",
)
