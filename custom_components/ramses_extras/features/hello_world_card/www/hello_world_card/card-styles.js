/* global getComputedStyle, module, exports */

// Hello World Card Styles
// Part of the Ramses Extra integration
// See https://github.com/wimpie70/ramses_extras for more information

/**
 * Card-specific styling and theming for Hello World Card
 * Provides consistent visual design and responsive layouts
 */

export class HelloWorldCardStyles {
  /**
   * Get the main card styles
   * @returns {string} CSS styles for the main card
   */
  static getMainStyles() {
    return `
      /* Main Card Container */
      .hello-world-card {
        --hw-primary-color: var(--primary-color, #2196f3);
        --hw-secondary-color: var(--secondary-text-color, #666);
        --hw-success-color: #4caf50;
        --hw-error-color: #f44336;
        --hw-warning-color: #ff9800;
        --hw-card-background: var(--card-background-color, #fff);
        --hw-border-radius: 12px;
        --hw-padding: 16px;
        --hw-gap: 12px;
        --hw-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        --hw-transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        background: var(--hw-card-background);
        border-radius: var(--hw-border-radius);
        padding: var(--hw-padding);
        box-shadow: var(--hw-shadow);
        transition: var(--hw-transition);
        position: relative;
        overflow: hidden;
      }

      .hello-world-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
      }

      /* Card Header */
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: calc(var(--hw-padding) * 0.75);
        padding-bottom: var(--hw-gap);
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }

      .device-info {
        font-size: 1.1em;
        font-weight: 600;
        color: var(--primary-text-color);
        line-height: 1.2;
      }

      .status-indicator {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.9em;
        color: var(--hw-secondary-color);
      }

      .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--hw-secondary-color);
        transition: var(--hw-transition);
      }

      .status-dot.on {
        background: var(--hw-success-color);
        box-shadow: 0 0 8px rgba(76, 175, 80, 0.4);
      }

      .status-dot.off {
        background: var(--hw-error-color);
        box-shadow: 0 0 8px rgba(244, 67, 54, 0.4);
      }

      /* Card Content */
      .card-content {
        display: flex;
        flex-direction: column;
        gap: calc(var(--hw-gap) * 1.5);
      }

      /* Switch Section */
      .switch-section {
        display: flex;
        flex-direction: column;
      }

      .switch-container {
        display: flex;
        align-items: center;
        gap: var(--hw-gap);
        padding: calc(var(--hw-gap) * 0.5);
        background: var(--secondary-background-color, #f5f5f5);
        border-radius: calc(var(--hw-border-radius) * 0.75);
        transition: var(--hw-transition);
      }

      .switch-container:hover {
        background: var(--divider-color, #e0e0e0);
        transform: scale(1.02);
      }

      .hello-world-switch {
        --switch-checked-track-color: var(--hw-primary-color);
        --switch-checked-button-color: var(--hw-primary-color);
        --switch-track-height: 24px;
        --switch-track-width: 48px;
      }

      .switch-labels {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .switch-label {
        font-weight: 600;
        font-size: 1em;
        color: var(--primary-text-color);
        transition: var(--hw-transition);
      }

      .switch-description {
        font-size: 0.8em;
        color: var(--hw-secondary-color);
      }

      /* Sensor Section */
      .sensor-section {
        display: flex;
        align-items: center;
        gap: var(--hw-gap);
        padding: var(--hw-gap);
        background: rgba(33, 150, 243, 0.05);
        border: 1px solid rgba(33, 150, 243, 0.2);
        border-radius: calc(var(--hw-border-radius) * 0.5);
      }

      .sensor-info {
        display: flex;
        align-items: center;
        gap: var(--hw-gap);
        flex: 1;
      }

      .sensor-icon {
        color: var(--hw-primary-color);
        font-size: 1.2em;
      }

      .sensor-details {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .sensor-name {
        font-weight: 500;
        font-size: 0.9em;
        color: var(--primary-text-color);
      }

      .sensor-state {
        font-size: 0.8em;
        color: var(--hw-secondary-color);
      }

      /* Device Panel */
      .device-panel {
        background: var(--secondary-background-color, #fafafa);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: calc(var(--hw-border-radius) * 0.5);
        padding: var(--hw-gap);
      }

      .device-details {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .device-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }

      .device-label {
        font-size: 0.85em;
        color: var(--hw-secondary-color);
        font-weight: 500;
      }

      .device-value {
        font-size: 0.85em;
        color: var(--primary-text-color);
        font-weight: 600;
        font-family: 'Courier New', monospace;
      }

      /* Card Footer */
      .card-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: calc(var(--hw-padding) * 0.5);
        padding-top: var(--hw-gap);
        border-top: 1px solid var(--divider-color, #e0e0e0);
      }

      .footer-info {
        display: flex;
        justify-content: space-between;
        align-items: center;
        width: 100%;
      }

      .last-updated {
        font-size: 0.75em;
        color: var(--hw-secondary-color);
      }

      .power-button {
        --mdc-icon-button-size: 32px;
        --mdc-icon-button-size: 32px;
        --mdc-icon-button-font-size: 18px;
        color: var(--hw-secondary-color);
        transition: var(--hw-transition);
      }

      .power-button.active {
        color: var(--hw-success-color);
      }

      .power-button:hover {
        transform: scale(1.1);
      }

      /* Compact View */
      .hello-world-card.compact {
        --hw-padding: 12px;
        --hw-gap: 8px;
      }

      .hello-world-card.compact .card-header {
        margin-bottom: var(--hw-gap);
        padding-bottom: var(--hw-gap);
      }

      .hello-world-card.compact .device-info {
        font-size: 1em;
      }

      .hello-world-card.compact .switch-container {
        gap: 8px;
        padding: 6px;
      }

      .hello-world-card.compact .switch-label {
        font-size: 0.9em;
      }

      /* Responsive Design */
      @media (max-width: 480px) {
        .hello-world-card {
          --hw-padding: 12px;
          --hw-gap: 8px;
        }

        .card-header {
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
        }

        .status-indicator {
          align-self: flex-end;
        }

        .switch-container {
          flex-direction: column;
          text-align: center;
          gap: 6px;
        }

        .sensor-section {
          flex-direction: column;
          text-align: center;
          gap: 6px;
        }
      }

      /* Dark Theme Adjustments */
      @media (prefers-color-scheme: dark) {
        .hello-world-card {
          --hw-card-background: var(--card-background-color, #1e1e1e);
          --hw-secondary-color: var(--secondary-text-color, #aaa);
        }

        .switch-container {
          background: var(--primary-background-color, #2e2e2e);
        }

        .sensor-section {
          background: rgba(33, 150, 243, 0.1);
        }

        .device-panel {
          background: var(--primary-background-color, #2e2e2e);
        }
      }

      /* Animation Keyframes */
      @keyframes helloWorldPulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
      }

      @keyframes helloWorldSlideIn {
        from {
          opacity: 0;
          transform: translateY(20px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      /* Animation Classes */
      .hello-world-card.animating {
        animation: helloWorldSlideIn 0.3s ease-out;
      }

      .hello-world-card.pulsing .status-dot {
        animation: helloWorldPulse 2s infinite;
      }

      /* Loading State */
      .hello-world-card.loading {
        pointer-events: none;
        opacity: 0.6;
      }

      .hello-world-card.loading::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(
          90deg,
          transparent,
          rgba(255, 255, 255, 0.4),
          transparent
        );
        animation: helloWorldShimmer 1.5s infinite;
      }

      @keyframes helloWorldShimmer {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
      }
    `;
  }

  /**
   * Get editor styles
   * @returns {string} CSS styles for the editor
   */
  static getEditorStyles() {
    return `
      /* Editor Container */
      .hello-world-editor {
        --hw-primary-color: var(--primary-color, #2196f3);
        --hw-secondary-color: var(--secondary-text-color, #666);
        --hw-background: var(--card-background-color, #fff);
        --hw-border: var(--divider-color, #e0e0e0);
        --hw-border-radius: 8px;
        --hw-padding: 16px;
        --hw-gap: 12px;

        background: var(--hw-background);
        padding: var(--hw-padding);
        font-family: var(--primary-font-family, inherit);
      }

      /* Section Styling */
      .editor-section {
        margin-bottom: calc(var(--hw-padding) * 1.5);
        padding-bottom: var(--hw-padding);
        border-bottom: 1px solid var(--hw-border);
      }

      .editor-section:last-child {
        border-bottom: none;
        margin-bottom: 0;
      }

      .section-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 1.1em;
        font-weight: 600;
        color: var(--primary-text-color);
        margin: 0 0 var(--hw-gap) 0;
      }

      .subsection-title {
        font-size: 1em;
        font-weight: 500;
        color: var(--primary-text-color);
        margin: 0 0 var(--hw-gap) 0;
      }

      /* Form Elements */
      .form-row {
        margin-bottom: var(--hw-gap);
      }

      .form-label {
        display: block;
        font-weight: 500;
        color: var(--primary-text-color);
        margin-bottom: 4px;
        font-size: 0.9em;
      }

      .form-label.required::after {
        content: '*';
        color: var(--error-color, #f44336);
        margin-left: 2px;
      }

      .form-input,
      .form-select {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid var(--hw-border);
        border-radius: var(--hw-border-radius);
        background: var(--input-background-color, var(--hw-background));
        color: var(--primary-text-color);
        font-size: 14px;
        transition: border-color 0.2s ease;
      }

      .form-input:focus,
      .form-select:focus {
        outline: none;
        border-color: var(--hw-primary-color);
        box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.2);
      }

      .form-help {
        display: block;
        margin-top: 4px;
        font-size: 0.8em;
        color: var(--secondary-text-color);
      }

      /* Checkbox and Radio Groups */
      .checkbox-group,
      .radio-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .checkbox-label,
      .radio-label {
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        transition: background-color 0.2s ease;
      }

      .checkbox-label:hover,
      .radio-label:hover {
        background: var(--secondary-background-color, #f5f5f5);
      }

      .checkbox-text,
      .radio-text {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.9em;
        color: var(--primary-text-color);
      }

      .checkbox-label input[type="checkbox"],
      .radio-label input[type="radio"] {
        margin: 0;
      }

      /* Status Messages */
      .warning-message,
      .error-message,
      .success-message {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: var(--hw-border-radius);
        font-size: 0.85em;
        margin-top: 8px;
      }

      .warning-message {
        background: rgba(255, 152, 0, 0.1);
        color: var(--warning-color, #f57c00);
        border: 1px solid rgba(255, 152, 0, 0.2);
      }

      .error-message {
        background: rgba(244, 67, 54, 0.1);
        color: var(--error-color, #d32f2f);
        border: 1px solid rgba(244, 67, 54, 0.2);
      }

      .success-message {
        background: rgba(76, 175, 80, 0.1);
        color: var(--success-color, #388e3c);
        border: 1px solid rgba(76, 175, 80, 0.2);
      }

      /* Configuration Summary */
      .config-summary {
        background: var(--secondary-background-color, #f9f9f9);
        border: 1px solid var(--hw-border);
        border-radius: var(--hw-border-radius);
        padding: var(--hw-gap);
      }

      .summary-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 0;
        font-size: 0.85em;
        border-bottom: 1px solid var(--hw-border);
      }

      .summary-item:last-child {
        border-bottom: none;
      }

      /* Action Buttons */
      .editor-actions {
        display: flex;
        justify-content: flex-end;
        gap: var(--hw-gap);
        margin-top: calc(var(--hw-padding) * 1.5);
        padding-top: var(--hw-gap);
        border-top: 1px solid var(--hw-border);
      }

      .btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 16px;
        border: none;
        border-radius: var(--hw-border-radius);
        font-size: 0.9em;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s ease;
      }

      .btn-primary {
        background: var(--hw-primary-color);
        color: white;
      }

      .btn-primary:hover {
        background: var(--primary-color-dark, #1976d2);
        transform: translateY(-1px);
      }

      .btn-primary:disabled {
        background: var(--disabled-color, #ccc);
        cursor: not-allowed;
        transform: none;
      }

      .btn-secondary {
        background: transparent;
        color: var(--secondary-text-color);
        border: 1px solid var(--hw-border);
      }

      .btn-secondary:hover {
        background: var(--secondary-background-color, #f5f5f5);
      }

      /* Loading Indicator */
      .loading-indicator {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--secondary-text-color);
        font-style: italic;
      }

      /* Editor Status */
      .editor-status {
        margin-top: var(--hw-gap);
      }

      /* Advanced Section */
      .editor-section.advanced {
        background: var(--secondary-background-color, #fafafa);
        border-radius: var(--hw-border-radius);
        padding: var(--hw-gap);
      }

      /* Responsive Design */
      @media (max-width: 768px) {
        .hello-world-editor {
          --hw-padding: 12px;
          --hw-gap: 10px;
        }

        .editor-actions {
          flex-direction: column;
        }

        .btn {
          justify-content: center;
        }
      }
    `;
  }

  /**
   * Apply styles to a container element
   * @param {HTMLElement} container - The container to apply styles to
   * @param {string} type - 'main' or 'editor'
   */
  static applyStyles(container, type = 'main') {
    const styleId = `hello-world-${type}-styles`;

    // Remove existing style element if it exists
    const existingStyle = document.getElementById(styleId);
    if (existingStyle) {
      existingStyle.remove();
    }

    // Create new style element
    const styleElement = document.createElement('style');
    styleElement.id = styleId;

    if (type === 'main') {
      styleElement.textContent = this.getMainStyles();
    } else if (type === 'editor') {
      styleElement.textContent = this.getEditorStyles();
    }

    // Add to document head
    document.head.appendChild(styleElement);
  }

  /**
   * Remove styles from document
   * @param {string} type - 'main' or 'editor'
   */
  static removeStyles(type = 'main') {
    const styleId = `hello-world-${type}-styles`;
    const existingStyle = document.getElementById(styleId);
    if (existingStyle) {
      existingStyle.remove();
    }
  }

  /**
   * Create a CSS custom property for theming
   * @param {string} name - Property name
   * @param {string} value - Property value
   */
  static setCustomProperty(name, value) {
    document.documentElement.style.setProperty(name, value);
  }

  /**
   * Get CSS custom property value
   * @param {string} name - Property name
   * @returns {string} Property value
   */
  static getCustomProperty(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name);
  }
}

// Auto-apply styles when module is loaded
if (typeof document !== 'undefined') {
  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      HelloWorldCardStyles.applyStyles(document.body, 'main');
    });
  } else {
    HelloWorldCardStyles.applyStyles(document.body, 'main');
  }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = HelloWorldCardStyles;
}

// Export for ES6 modules
if (typeof exports !== 'undefined') {
  exports.HelloWorldCardStyles = HelloWorldCardStyles;
}
