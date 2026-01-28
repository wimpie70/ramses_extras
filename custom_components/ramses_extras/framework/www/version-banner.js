/**
 * Version Mismatch Banner Component
 *
 * Provides a reusable banner to display version mismatch warnings
 * when frontend and backend versions don't match.
 */

/**
 * Get HTML for version mismatch banner
 * @returns {string} HTML for banner or empty string if no mismatch
 */
export function getVersionMismatchBanner() {
  const mismatch = window.ramsesExtras?._versionMismatch;
  if (!mismatch) {
    return '';
  }

  return `
    <div class="version-mismatch-banner" style="background: #ff9800; color: #000; padding: 12px; margin: 8px; border-radius: 4px; display: flex; align-items: center; justify-content: space-between; gap: 12px;">
      <div style="display: flex; align-items: center; gap: 8px; flex: 1;">
        <ha-icon icon="mdi:alert" style="color: #000; --mdc-icon-size: 24px;"></ha-icon>
        <div style="flex: 1;">
          <strong>Version Mismatch Detected</strong><br>
          <span style="font-size: 12px; opacity: 0.9;">
            Frontend: ${mismatch.frontend} | Backend: ${mismatch.backend}
            <br>Please hard refresh to load the latest version.
          </span>
        </div>
      </div>
      <button
        onclick="location.reload(true);"
        style="background: #fff; color: #000; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; white-space: nowrap;">
        Hard Refresh
      </button>
    </div>
  `;
}

/**
 * Check if version mismatch exists
 * @returns {boolean} True if mismatch detected
 */
export function hasVersionMismatch() {
  return Boolean(window.ramsesExtras?._versionMismatch);
}
