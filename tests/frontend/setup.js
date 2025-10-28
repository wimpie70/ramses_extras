/**
 * Jest setup file for frontend tests
 */

// Mock TextEncoder/TextDecoder for jsdom
const { TextEncoder, TextDecoder } = require('util');
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock Home Assistant WebSocket connection
global.WebSocket = class MockWebSocket {
  constructor() {
    this.readyState = 1; // OPEN
    this.onopen = null;
    this.onclose = null;
    this.onmessage = null;
    this.onerror = null;
  }

  send() {
    // Mock send method
  }

  close() {
    this.readyState = 3; // CLOSED
  }
};

// Mock ResizeObserver
global.ResizeObserver = class MockResizeObserver {
  constructor(callback) {
    this.callback = callback;
  }

  observe() {
    // Mock observe
  }

  unobserve() {
    // Mock unobserve
  }

  disconnect() {
    // Mock disconnect
  }
};

// Mock IntersectionObserver
global.IntersectionObserver = class MockIntersectionObserver {
  constructor(callback) {
    this.callback = callback;
  }

  observe() {
    // Mock observe
  }

  unobserve() {
    // Mock unobserve
  }

  disconnect() {
    // Mock disconnect
  }
};

// Mock HTMLElement for testing
global.HTMLElement = class MockHTMLElement {
  constructor() {
    this.shadowRoot = null;
    this.innerHTML = '';
  }

  attachShadow() {
    this.shadowRoot = {
      innerHTML: '',
      querySelector: () => null,
      querySelectorAll: () => []
    };
    return this.shadowRoot;
  }
};

// Suppress console warnings in tests unless explicitly testing them
const originalWarn = console.warn;
const originalError = console.error;

beforeEach(() => {
  console.warn = jest.fn();
  console.error = jest.fn();
});

afterEach(() => {
  console.warn = originalWarn;
  console.error = originalError;
});
