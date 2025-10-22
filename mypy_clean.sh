#!/bin/bash
# Script to run mypy without package conflicts
# This temporarily uninstalls the package to avoid duplicate module detection

echo "🔍 Running mypy without package conflicts..."

# Temporarily uninstall the package
source ~/venvs/extras/bin/activate
pip uninstall ramses_extras -y 2>/dev/null || true

# Run mypy on source files only
mypy custom_components tests

# Reinstall the package in development mode
pip install -e /home/willem/dev/ramses_extras

echo "✅ Mypy completed, package reinstalled"
