// @ts-check
import js from '@eslint/js';
import prettierConfig from 'eslint-config-prettier';
import prettier from 'eslint-plugin-prettier/recommended';

export default [
  // Base configuration
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      '*.min.js',
      'tests/**',
      'venv/**',
      '__pycache__/**',
      'docs/**',
      'scripts/**',
      'misc/**',
      '.eslintrc.json',
      '.pre-commit-config.yaml',
      '.prettierignore',
      '.prettierrc',
      'mypy.ini',
      'package.json',
      'package-lock.json',
      'Makefile',
      'README.md',
      '.editorconfig',
      '.eslintignore',
      '.eslint.config.js',
      '**/*.py',
      'htmlcov/**',
      '.coverage',
      'MagicMock/**',
    ],
  },

  // Core ESLint recommended rules
  js.configs.recommended,

  // Prettier integration
  prettierConfig,
  prettier,

  // Project-specific rules
  {
    rules: {
      'no-console': 'warn',
      'no-unused-vars': 'warn',
      'no-var': 'error',
      'prefer-const': 'error',
    },
    languageOptions: {
      globals: {
        // Browser globals
        window: 'readonly',
        console: 'readonly',
        document: 'readonly',
        HTMLElement: 'readonly',
        customElements: 'readonly',
        navigator: 'readonly',
        CustomEvent: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        fetch: 'readonly',

        // Home Assistant globals
        hass: 'readonly',
        h: 'readonly',
      },
    },
  },
  // Override for test files
  {
    files: ['**/*-test.js', '**/test-*.js'],
    rules: {
      'no-console': 'off',
      'no-unused-vars': 'off',
    },
  },
];
