#!/bin/bash
# Activate the virtual environment
echo "Activating Ramses Extras development environment..."
source ~/venvs/extras/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install in development mode for testing
echo "Installing ramses_extras in development mode..."
pip install -e .

echo "Development environment setup complete!"
echo "Virtual environment activated: $(which python)"
echo "Home Assistant version: $(python -c 'import homeassistant; print(homeassistant.__version__)')"
echo ""
echo "Available commands:"
echo "  pytest          - Run tests"
echo "  mypy .          - Type checking"
echo "  black .         - Code formatting"
echo "  isort .         - Import sorting"
echo "  flake8 .        - Linting"
echo "  pre-commit run  - Run pre-commit hooks"
