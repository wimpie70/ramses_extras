#!/bin/bash
set -e

# Activate the Python virtual environment
source ~/venvs/extras/bin/activate

echo "🐍 Using Python: $(python --version)"

# Create a local node_modules directory if it doesn't exist
mkdir -p node_modules

# Install ESLint locally in the project
echo "📦 Installing ESLint in the project..."
npm install --save-dev eslint

# Create a basic .eslintrc.json if it doesn't exist
if [ ! -f ".eslintrc.json" ]; then
    echo "📝 Creating .eslintrc.json..."
    cat > .eslintrc.json << 'EOL'
{
  "root": true,
  "env": {
    "browser": true,
    "es2022": true,
    "node": true
  },
  "extends": [
    "eslint:recommended"
  ],
  "parserOptions": {
    "ecmaVersion": "latest",
    "sourceType": "module"
  },
  "rules": {
    "no-console": "warn",
    "no-unused-vars": "warn",
    "no-var": "error",
    "prefer-const": "error"
  },
  "ignorePatterns": [
    "node_modules/",
    "dist/",
    "*.min.js",
    "tests/"
  ]
}
EOL
else
    echo "ℹ️  Using existing .eslintrc.json"
fi

# Create a test script
echo "📝 Creating test script..."
cat > scripts/test-lint.sh << 'EOL'
#!/bin/bash
set -e

# Activate the Python virtual environment
source ~/venvs/extras/bin/activate

# Run ESLint
./node_modules/.bin/eslint .

echo -e "\n✅ Linting completed successfully!"
EOL

chmod +x scripts/test-lint.sh

echo -e "\n✨ ESLint setup complete!"
echo "You can now run './scripts/test-lint.sh' to check your code."
echo "To fix auto-fixable issues, run: ./node_modules/.bin/eslint . --fix"

exit 0
