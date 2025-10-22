"""Setup script for Ramses Extras development."""

from setuptools import setup

setup(
    name="ramses_extras",
    version="0.3.0",
    packages=[
        "custom_components.ramses_extras",
        "custom_components.ramses_extras.helpers",
    ],
    package_dir={
        "custom_components.ramses_extras": "custom_components/ramses_extras",
        "custom_components.ramses_extras.helpers":
            "custom_components/ramses_extras/helpers",
    },
    install_requires=[
        "homeassistant==2025.10.1",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-asyncio>=0.24.0",
            "mypy>=1.11.0",
            "black>=24.0.0",
            "isort>=5.13.0",
            "flake8>=7.0.0",
            "pre-commit>=3.8.0",
            "typing-extensions>=4.15.0",
        ],
    },
    python_requires=">=3.13",
)
