#!/bin/bash
set -e

# Activate the Python virtual environment
source ~/venvs/extras/bin/activate

echo "🔍 Running ESLint..."

# Run ESLint with the new configuration
./node_modules/.bin/eslint . --no-error-on-unmatched-pattern

echo -e "\n✅ Linting completed successfully!"
echo "   To fix auto-fixable issues, run: ./node_modules/.bin/eslint . --fix"
