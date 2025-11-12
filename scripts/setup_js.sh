#!/bin/bash
set -e

# Clean up environment variables that might interfere with nvm
unset NPM_CONFIG_PREFIX
unset NPM_CONFIG_GLOBALCONFIG
unset NPM_CONFIG_USERCONFIG

# Activate the Python virtual environment
source ~/venvs/extras/bin/activate 2>/dev/null || true

echo "🐍 Using Python: $(python --version)"
echo "🔧 Setting up Node.js environment..."

# Clean up any existing installations
echo "🧹 Cleaning up any existing Node.js installation..."
rm -rf ~/.nodeenvs ~/.npm ~/.npmrc ~/.nvm ~/.nvm-windows ~/venvs/extras/lib/node_modules

# Install nvm (Node Version Manager) if not installed
echo "📥 Setting up nvm (Node Version Manager)..."
export NVM_DIR="$HOME/.nvm"

# Remove any existing nvm installation
if [ -d "$NVM_DIR" ]; then
    rm -rf "$NVM_DIR"
fi

# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Load nvm
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# Install Node.js and npm
echo "📦 Installing Node.js and npm..."
nvm install --lts=hydrogen  # LTS version (18.x)
nvm use --lts

# Verify installations
echo -e "\n🔍 Verifying installations..."
NODE_VERSION=$(node --version)
NPM_VERSION=$(npm --version)

echo "✅ Node.js: $NODE_VERSION"
echo "✅ npm: $NPM_VERSION"

# Configure npm to install packages globally in the virtual environment
echo "⚙️  Configuring npm..."
mkdir -p ~/venvs/extras/bin
mkdir -p ~/venvs/extras/lib/node_modules

export PATH="$HOME/venvs/extras/bin:$PATH"

# Install core packages locally in the project
echo "📦 Installing JavaScript packages locally..."
cd "$(dirname "$0")/.."  # Move to project root

# Create package.json if it doesn't exist
if [ ! -f "config/package.json" ]; then
    echo '{"name": "ramses-extras", "version": "1.0.0", "private": true}' > config/package.json
fi

# Install packages locally
npm install --no-audit --no-fund --save-dev \
    eslint@^8.56.0 \
    @eslint/js@^8.56.0 \
    eslint-config-prettier@^9.1.0 \
    eslint-plugin-prettier@^5.1.3 \
    prettier@^3.2.5 \
    @typescript-eslint/parser@^7.0.1 \
    @typescript-eslint/eslint-plugin@^7.0.1 \
    rimraf@^5.0.5 \
    glob@^10.3.10

# Create npx wrapper scripts
echo "📝 Creating npx wrapper scripts..."
cat > ~/venvs/extras/bin/eslint << 'EOL'
#!/bin/bash
$(command -v node) $(npm root -g)/eslint/bin/eslint.js "$@"
EOL

cat > ~/venvs/extras/bin/prettier << 'EOL'
#!/bin/bash
$(command -v node) $(npm root -g)/prettier/bin-prettier.js "$@"
EOL

chmod +x ~/venvs/extras/bin/{eslint,prettier}

# Verify installations
echo -e "\n🔍 Verifying installations..."
if command -v ./node_modules/.bin/eslint &> /dev/null; then
    echo "✅ ESLint is installed: $(./node_modules/.bin/eslint --version)"
else
    echo "❌ ESLint installation failed"
    exit 1
fi

if command -v ./node_modules/.bin/prettier &> /dev/null; then
    echo "✅ Prettier is installed: $(./node_modules/.bin/prettier --version)"
else
    echo "❌ Prettier installation failed"
    exit 1
fi

echo -e "\n💡 Usage:"
echo "- Run ESLint: npx eslint ."
echo "- Format code: npx prettier --write ."
echo "- Fix all auto-fixable issues: npx eslint . --fix"

echo -e "\n✨ Setup completed successfully!"
exit 0
if [[ "$(npm --version)" != "$NPM_VERSION"* ]]; then
    echo "🔄 Updating npm to version $NPM_VERSION..."
    npm install -g --no-audit --no-fund npm@$NPM_VERSION
    # Verify npm installation
    if [[ "$(npm --version)" != "$NPM_VERSION"* ]]; then
        echo "❌ Failed to update npm to version $NPM_VERSION"
        exit 1
    fi
fi

# Install or update Node.js packages globally in the virtual environment
echo "🚀 Installing/updating JavaScript packages..."

# Clean npm cache and remove potential corrupted cache
echo "🧹 Cleaning npm cache and removing potential corrupted cache..."
npm cache clean --force
rm -rf ~/.npm/_cacache/*
rm -rf ~/.npm/_logs/*

# Function to install packages one by one with retries
install_package() {
    local pkg=$1
    local max_retries=3
    local retry_count=0

    while [ $retry_count -lt $max_retries ]; do
        echo "📦 Installing $pkg (attempt $((retry_count + 1)) of $max_retries)..."
        if npm install -g --no-audit --no-fund "$pkg"; then
            echo "✅ Successfully installed $pkg"
            return 0
        else
            retry_count=$((retry_count + 1))
            echo "⚠️  Failed to install $pkg, retrying..."
            sleep 2
        fi
    done

    echo "❌ Failed to install $pkg after $max_retries attempts"
    return 1
}

# Install core packages one by one
CORE_PACKAGES=(
    "eslint@8.57.0"
    "@eslint/js@8.57.0"
    "eslint-config-prettier@9.1.0"
    "eslint-plugin-prettier@5.1.3"
    "prettier@3.2.5"
    "@typescript-eslint/parser@7.0.1"
    "@typescript-eslint/eslint-plugin@7.0.1"
    "rimraf@5.0.5"
    "glob@10.3.10"
)

for pkg in "${CORE_PACKAGES[@]}"; do
    if ! install_package "$pkg"; then
        echo "❌ Critical error: Failed to install required package: $pkg"
        exit 1
    fi
done

# Verify installations
echo -e "\n🔍 Verifying installations..."

# Function to verify command exists
verify_command() {
    if command -v "$1" &> /dev/null; then
        echo "✅ $1 is installed: $($1 --version 2>/dev/null || echo 'version unknown') "
        return 0
    else
        echo "❌ $1 is not installed or not in PATH"
        return 1
    fi
}

# Verify core tools
verify_command node
verify_command npm
verify_command npx
verify_command eslint
verify_command prettier

# Verify npm packages
NPM_PKGS=(
    "@eslint/js"
    "eslint-config-prettier"
    "eslint-plugin-prettier"
    "@typescript-eslint/parser"
    "@typescript-eslint/eslint-plugin"
)

for pkg in "${NPM_PKGS[@]}"; do
    if npm list -g "$pkg" --depth=0 &> /dev/null; then
        echo "✅ $pkg is installed"
    else
        echo "❌ $pkg is not installed"
        exit 1
    fi
done

echo -e "\n💡 Usage:"
echo "- Run ESLint: npx eslint ."
echo "- Format code: npx prettier --write ."
echo "- Fix all auto-fixable issues: npx eslint . --fix"

echo -e "\n✨ Setup completed successfully!"
