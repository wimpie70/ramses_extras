/* global navigator */

/**
 * Clipboard utilities for Ramses Extras cards.
 *
 * Provides cross-browser clipboard copy functionality with fallback
 * for older browsers that don't support the Clipboard API.
 *
 * @module clipboard
 */

import * as logger from './logger.js';

/**
 * Copy text to clipboard with cross-browser support.
 *
 * This function attempts to use the modern Clipboard API (navigator.clipboard.writeText)
 * when available. For older browsers that don't support the Clipboard API, it falls
 * back to the legacy document.execCommand('copy') method.
 *
 * @param {string} text - Text content to copy to clipboard
 * @returns {Promise<void>} Resolves when copy succeeds, rejects on failure
 * @throws {Error} If clipboard copy fails (logged as warning, not thrown)
 *
 * @example
 * // Copy search results to clipboard
 * await copyToClipboard(searchResult.plain);
 *
 * @example
 * // Copy with error handling
 * try {
 *   await copyToClipboard('Hello World');
 *   console.log('Copied successfully');
 * } catch (error) {
 *   console.error('Copy failed:', error);
 * }
 */
export async function copyToClipboard(text) {
  if (!text) {
    return;
  }

  try {
    // Modern Clipboard API (preferred)
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }

    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = String(text);
    textarea.setAttribute('readonly', '');
    textarea.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  } catch (error) {
    logger.warn('Copy to clipboard failed:', error);
    throw error;
  }
}
