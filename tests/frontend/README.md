# Frontend Testing

This directory contains tests for the JavaScript, CSS, and HTML components of the Ramses Extras integration.

## Test Structure

```
tests/frontend/
├── setup.js                    # Jest setup and mocks
├── test-template-helpers.js   # Unit tests for template functions
├── test-hvac-fan-card.js      # Unit tests for main card logic
└── test-integration.js        # Integration tests for card rendering
```

## Running Tests

### Prerequisites

Install frontend testing dependencies:

```bash
npm install
```

Or using Python (for development):

```bash
pip install -r requirements_dev.txt
```

### Test Commands

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Lint JavaScript
npm run lint

# Fix JavaScript linting issues
npm run lint:fix

# Lint CSS
npm run stylelint

# Fix CSS linting issues
npm run stylelint:fix
```

### Python-based Testing

For development environments, you can also run tests using Python:

```bash
# Install test dependencies
pip install jest jsdom

# Run Jest tests
python -m jest --config jest.config.js
```

## Test Coverage

The tests cover:

### JavaScript Unit Tests

- **Template Helpers**: `calculateEfficiency`, `createTemplateData` functions
- **Card Logic**: Entity validation, state management, event handling
- **Error Handling**: Missing entities, invalid configurations

### Integration Tests

- **DOM Rendering**: Complete card HTML generation
- **Event Handling**: Button clicks, state updates
- **Entity State Changes**: Real-time updates from Home Assistant

### CSS Tests

- **Style Validation**: CSS syntax, selectors, properties
- **Responsive Design**: Media queries, layout rules
- **Best Practices**: Color usage, spacing, naming conventions

## Configuration Files

- **`.eslintrc.json`**: ESLint configuration for JavaScript code quality
- **`.stylelintrc.json`**: Stylelint configuration for CSS code quality
- **`jest.config.js`**: Jest configuration for JavaScript testing
- **`package.json`**: Node.js dependencies and scripts

## Pre-commit Hooks

Frontend linting is integrated into pre-commit hooks:

```bash
# Run all pre-commit checks (including frontend)
pre-commit run --all-files

# Run only frontend linting
pre-commit run eslint --all-files
pre-commit run stylelint --all-files
```

## GitHub Actions

Frontend tests run automatically on:

- **Push** to `master` or `develop` branches
- **Pull requests** targeting these branches
- **Manual dispatch** via GitHub UI

The workflow includes:

- Multi-browser testing (Node.js 18, 20)
- Coverage reporting to Codecov
- Linting and style checking
- Test status reporting

## Writing Tests

### JavaScript Tests

```javascript
describe('ComponentName', () => {
  test('should handle specific case', () => {
    // Arrange
    const mockData = {
      /* test data */
    };

    // Act
    const result = functionUnderTest(mockData);

    // Assert
    expect(result).toBe(expectedValue);
  });
});
```

### Mock Setup

The test environment includes mocks for:

- **Home Assistant API**: `hass` object with states and services
- **DOM Elements**: Shadow DOM, event handling
- **Browser APIs**: ResizeObserver, IntersectionObserver
- **Console**: Suppressed logging during tests

## Debugging

Enable console output in tests by removing the console mock in `setup.js`:

```javascript
// In setup.js, comment out or modify:
global.console = {
  log: jest.fn(), // Change to: log: (...args) => console.log(...args),
  // ... etc
};
```
