/**
 * Device cache singleton for Ramses Extras cards.
 *
 * Provides centralized caching of device lists from the backend,
 * avoiding duplicate WebSocket calls across multiple cards.
 *
 * This module exports a singleton instance that maintains a cached list
 * of devices with automatic expiry. Multiple cards can share the same
 * cached data, reducing backend load and improving performance.
 *
 * @module device-cache
 */

import { callWebSocketShared } from './card-services.js';

/**
 * Singleton device cache manager.
 *
 * Manages a cached list of devices from the backend with automatic expiry.
 * Provides helper methods to extract specific device information (slugs, names, IDs).
 *
 * @class DeviceCache
 */
class DeviceCache {
  constructor() {
    this._devices = null;
    this._timestamp = 0;
    this._cacheMs = 30000; // 30 seconds default
  }

  /**
   * Get devices from backend with caching.
   *
   * Fetches the device list from the backend via WebSocket. Results are cached
   * for the specified duration to avoid redundant requests. Multiple simultaneous
   * calls are automatically de-duplicated by callWebSocketShared.
   *
   * @param {Object} hass - Home Assistant instance
   * @param {Object} [options={}] - Options for device retrieval
   * @param {number} [options.cacheMs=30000] - Cache duration in milliseconds
   * @param {boolean} [options.forceRefresh=false] - Force refresh even if cached
   * @returns {Promise<Array<Object>>} Array of device objects with properties:
   *   - device_id: Device identifier
   *   - name: Device name
   *   - slug_label: Primary slug label
   *   - slugs: Array of slug strings
   * @throws {Error} If WebSocket call fails
   *
   * @example
   * const devices = await deviceCache.getDevices(hass);
   * console.log(`Found ${devices.length} devices`);
   *
   * @example
   * // Force refresh with custom cache duration
   * const devices = await deviceCache.getDevices(hass, {
   *   forceRefresh: true,
   *   cacheMs: 60000
   * });
   */
  async getDevices(hass, options = {}) {
    const { cacheMs = this._cacheMs, forceRefresh = false } = options;
    const now = Date.now();

    if (!forceRefresh && this._devices && (now - this._timestamp) < cacheMs) {
      return this._devices;
    }

    const res = await callWebSocketShared(
      hass,
      { type: 'ramses_extras/get_available_devices' },
      { cacheMs }
    );

    this._devices = Array.isArray(res?.devices) ? res.devices : [];
    this._timestamp = now;
    return this._devices;
  }

  /**
   * Get device ID to slug label map.
   *
   * Builds a Map from device_id to slug label string. The slug label is either
   * the slug_label property or a comma-separated list of slugs.
   *
   * @param {Object} hass - Home Assistant instance
   * @param {Object} [options={}] - Options (passed to getDevices)
   * @returns {Promise<Map<string, string>>} Map of device_id to slug label
   * @throws {Error} If device fetch fails
   *
   * @example
   * const slugMap = await deviceCache.getDeviceSlugMap(hass);
   * const label = slugMap.get('01:123456');
   * console.log(`Device label: ${label}`);
   */
  async getDeviceSlugMap(hass, options = {}) {
    const devices = await this.getDevices(hass, options);
    const map = new Map();

    for (const dev of devices) {
      const id = String(dev?.device_id ?? '');
      if (!id) {
        continue;
      }

      const slugLabel = String(dev?.slug_label ?? '').trim();
      const slugs = Array.isArray(dev?.slugs)
        ? dev.slugs.map((s) => String(s)).filter(Boolean)
        : [];
      const label = slugLabel || (slugs.length ? slugs.join(', ') : '');

      if (label) {
        map.set(id, label);
      }
    }

    return map;
  }

  /**
   * Get set of known device IDs.
   *
   * Returns a Set containing all known device IDs. Useful for filtering
   * messages or flows to show only known devices.
   *
   * @param {Object} hass - Home Assistant instance
   * @param {Object} [options={}] - Options (passed to getDevices)
   * @returns {Promise<Set<string>>} Set of known device IDs
   * @throws {Error} If device fetch fails
   *
   * @example
   * const knownIds = await deviceCache.getKnownDeviceIds(hass);
   * if (knownIds.has('01:123456')) {
   *   console.log('Device is known');
   * }
   */
  async getKnownDeviceIds(hass, options = {}) {
    const devices = await this.getDevices(hass, options);
    return new Set(
      devices
        .map((d) => String(d?.device_id ?? d?.id ?? ''))
        .filter(Boolean)
    );
  }

  /**
   * Get device ID to name map.
   *
   * Builds a Map from device_id to device name. Only includes devices
   * that have a non-empty name property.
   *
   * @param {Object} hass - Home Assistant instance
   * @param {Object} [options={}] - Options (passed to getDevices)
   * @returns {Promise<Map<string, string>>} Map of device_id to device name
   * @throws {Error} If device fetch fails
   *
   * @example
   * const nameMap = await deviceCache.getDeviceNameMap(hass);
   * const name = nameMap.get('01:123456');
   * console.log(`Device name: ${name}`);
   */
  async getDeviceNameMap(hass, options = {}) {
    const devices = await this.getDevices(hass, options);
    const map = new Map();

    for (const dev of devices) {
      const id = String(dev?.device_id ?? '');
      const name = String(dev?.name ?? '').trim();
      if (id && name) {
        map.set(id, name);
      }
    }

    return map;
  }

  /**
   * Clear the cache.
   *
   * Forces the next getDevices() call to fetch fresh data from the backend.
   * Useful for testing or when you know the device list has changed.
   *
   * @example
   * deviceCache.clear();
   * const freshDevices = await deviceCache.getDevices(hass);
   */
  clear() {
    this._devices = null;
    this._timestamp = 0;
  }

  /**
   * Get cache statistics.
   *
   * Returns information about the current cache state, including whether
   * data is cached, how many devices are cached, cache age, and time until expiry.
   *
   * @returns {Object} Cache statistics object
   * @returns {boolean} returns.cached - Whether devices are currently cached
   * @returns {number} returns.deviceCount - Number of cached devices
   * @returns {number|null} returns.ageMs - Age of cache in milliseconds (null if not cached)
   * @returns {number|null} returns.expiresInMs - Milliseconds until cache expires (null if not cached)
   *
   * @example
   * const stats = deviceCache.getStats();
   * console.log(`Cache has ${stats.deviceCount} devices, expires in ${stats.expiresInMs}ms`);
   */
  getStats() {
    const now = Date.now();
    const age = this._devices ? now - this._timestamp : null;
    return {
      cached: Boolean(this._devices),
      deviceCount: this._devices?.length ?? 0,
      ageMs: age,
      expiresInMs: age !== null ? Math.max(0, this._cacheMs - age) : null,
    };
  }
}

// Export singleton instance
export const deviceCache = new DeviceCache();
