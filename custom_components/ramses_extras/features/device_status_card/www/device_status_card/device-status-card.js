/**
 * Device Status Card - fleet overview of all RAMSES devices.
 *
 * Lists every known RAMSES device with its online status and
 * communication quality (best RSSI, per-HGI breakdown for pooled
 * gateways). Data comes from the feature WebSocket command
 * `ramses_extras/device_status_card/get_device_status`, which reads the
 * ramses_cc per-device status entities (ramses_cc issue 1210) and falls
 * back to the ramses_rf device objects on older ramses_cc versions.
 *
 * This is a global card: it needs no device_id and creates no entities.
 *
 * @module device-status-card
 * @extends RamsesBaseCard
 */

import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocketShared } from '../../helpers/card-services.js';
import { deviceCache } from '../../helpers/device-cache.js';
import { deviceStatusCardStyle } from './card-styles.js';

const WS_GET_DEVICE_STATUS = 'ramses_extras/device_status_card/get_device_status';
const DEFAULT_POLL_INTERVAL_MS = 30000;

/**
 * Format a staleness duration in seconds as a compact age string.
 *
 * @param {number|null|undefined} seconds - Staleness in seconds
 * @returns {string} Human-readable age (e.g. "2m", "3h", "1d")
 */
function formatAge(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return '-';
  }
  const s = Math.max(0, Number(seconds));
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}

/**
 * Map an RSSI quality string to a CSS class.
 *
 * @param {string|null|undefined} quality - RSSI quality label
 * @returns {string} CSS class suffix
 */
function qualityClass(quality) {
  // ramses_rf labels: strong, normal, weak, very_weak, unknown.
  const q = String(quality || '').toLowerCase();
  if (q === 'strong' || q === 'good') return 'strong';
  if (q === 'normal' || q === 'ok' || q === 'medium' || q === 'fair') return 'ok';
  if (q === 'weak' || q === 'very_weak' || q === 'poor') return 'weak';
  return '';
}

/**
 * Escape a string for safe interpolation into HTML.
 *
 * @param {*} value - Value to escape
 * @returns {string} Escaped string
 */
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Device Status Card component.
 *
 * @class DeviceStatusCard
 * @extends RamsesBaseCard
 */
class DeviceStatusCard extends RamsesBaseCard {
  constructor() {
    super();

    this._snapshot = null;
    this._deviceNameMap = null;
    this._deviceNameMapTs = 0;
    this._pollInterval = null;
    this._lastError = null;
    this._sortKey = 'status';
    this._sortDir = 'asc';
    this._boundOnSortClick = null;
  }

  getCardSize() {
    const count = this._snapshot?.devices?.length || 0;
    return Math.min(12, Math.max(3, Math.ceil(count / 5) + 2));
  }

  static getTagName() {
    return 'device-status-card';
  }

  static getStubConfig() {
    return {
      type: `custom:${this.getTagName()}`,
      ...this.prototype.getDefaultConfig(),
    };
  }

  static getCardInfo() {
    return {
      type: this.getTagName(),
      name: 'Device Status Card',
      description: 'All RAMSES devices with online status and communication quality',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }

  getRequiredEntities() {
    return {};
  }

  hasValidConfig() {
    return true;
  }

  validateConfig() {
    return {
      valid: true,
      errors: [],
    };
  }

  shouldUpdate() {
    return false;
  }

  getDefaultConfig() {
    return {
      name: 'Device Status',
      poll_interval: DEFAULT_POLL_INTERVAL_MS,
    };
  }

  getFeatureName() {
    return 'device_status_card';
  }

  _onConnected() {
    void this._loadDeviceNameMap();
    this._startUpdates();
  }

  _onDisconnected() {
    this._stopUpdates();
  }

  _stopUpdates() {
    if (this._pollInterval) {
      clearInterval(this._pollInterval);
      this._pollInterval = null;
    }
  }

  _startUpdates() {
    if (!this._hass || !this._config) {
      return;
    }

    this._stopUpdates();

    const doPoll = async () => {
      try {
        this._lastError = null;
        const result = await callWebSocketShared(
          this._hass,
          { type: WS_GET_DEVICE_STATUS },
          { cacheMs: 1000 }
        );

        const changed =
          JSON.stringify(this._snapshot) !== JSON.stringify(result);
        this._snapshot = result;

        if (changed) {
          this.render();
        }
      } catch (error) {
        const errorChanged =
          JSON.stringify(this._lastError) !== JSON.stringify(error);
        this._lastError = error;

        if (errorChanged) {
          this.render();
        }
      }
    };

    void doPoll();

    const interval = Number(this._config?.poll_interval || DEFAULT_POLL_INTERVAL_MS);
    const safeInterval = Number.isFinite(interval)
      ? Math.max(5000, interval)
      : DEFAULT_POLL_INTERVAL_MS;
    this._pollInterval = setInterval(() => {
      void doPoll();
    }, safeInterval);
  }

  async _loadDeviceNameMap() {
    if (!this._hass) {
      return;
    }

    const now = Date.now();
    if (this._deviceNameMap && now - this._deviceNameMapTs < 30_000) {
      return;
    }

    try {
      this._deviceNameMap = await deviceCache.getDeviceNameMap(this._hass, {
        cacheMs: 30_000,
      });
      this._deviceNameMapTs = now;
      this.render();
    } catch {
      // Ignore - depends on ramses_cc integration state.
    }
  }

  _sortDevices(devices) {
    const key = this._sortKey;
    const dir = this._sortDir === 'desc' ? -1 : 1;

    const valueOf = (d) => {
      switch (key) {
        case 'id':
          return String(d.id || '');
        case 'class':
          return String(d.class || '');
        case 'rssi':
          return d.best_rssi === null || d.best_rssi === undefined
            ? -999
            : Number(d.best_rssi);
        case 'last_seen':
          return d.staleness_seconds === null ||
            d.staleness_seconds === undefined
            ? Number.MAX_SAFE_INTEGER
            : Number(d.staleness_seconds);
        case 'status':
        default:
          // Offline first, then unknown, then online.
          if (d.status === 'off') return 0;
          if (d.status === 'on') return 2;
          return 1;
      }
    };

    return [...devices].sort((a, b) => {
      const va = valueOf(a);
      const vb = valueOf(b);
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return String(a.id || '').localeCompare(String(b.id || ''));
    });
  }

  _renderPoolSection() {
    const pool = this._snapshot?.pool;
    if (!pool) {
      return '';
    }

    const hgis = Array.isArray(pool.hgis) ? pool.hgis : [];
    const total = pool.children_total ?? hgis.length;
    const online = pool.children_online ?? hgis.filter((h) => h.online === true).length;

    const hgiItems = hgis
      .map((hgi) => {
        const dotClass =
          hgi.online === true ? 'on' : hgi.online === false ? 'off' : 'unknown';
        const detail = [
          hgi.availability ? String(hgi.availability).toLowerCase() : null,
          hgi.pkts_received !== undefined ? `${hgi.pkts_received} pkts` : null,
        ]
          .filter(Boolean)
          .join(' · ');
        return `
          <div class="r-xtrs-devstat-pool-item" title="${escapeHtml(detail)}">
            <span class="r-xtrs-devstat-dot ${dotClass}"></span>
            <span class="r-xtrs-devstat-hgi">${escapeHtml(hgi.hgi_id)}</span>
          </div>`;
      })
      .join('');

    const poolDot = pool.status === 'on' ? 'on' : 'off';
    return `
      <div class="r-xtrs-devstat-pool">
        <div class="r-xtrs-devstat-pool-item" title="Aggregate pool status">
          <span class="r-xtrs-devstat-dot ${poolDot}"></span>
          <strong>Pool ${escapeHtml(online)}/${escapeHtml(total)}</strong>
        </div>
        ${hgiItems}
      </div>`;
  }

  _renderDeviceRows() {
    const devices = this._snapshot?.devices;
    if (!Array.isArray(devices) || devices.length === 0) {
      return `<div class="r-xtrs-devstat-empty">No RAMSES devices found</div>`;
    }

    const sorted = this._sortDevices(devices);

    return sorted
      .map((d) => {
        const online = d.status === 'on';
        const name =
          (this._deviceNameMap && this._deviceNameMap.get
            ? this._deviceNameMap.get(d.id)
            : undefined) ||
          d.name ||
          '';
        const dotClass = online ? 'on' : d.status === 'off' ? 'off' : 'unknown';
        const qClass = qualityClass(d.rssi_quality);
        const rssi =
          d.best_rssi !== null && d.best_rssi !== undefined
            ? `${d.best_rssi} dBm`
            : '-';
        const perHgi =
          d.rssi_per_hgi && typeof d.rssi_per_hgi === 'object'
            ? Object.entries(d.rssi_per_hgi)
                .map(([hgi, r]) => `${hgi}: ${r}`)
                .join('\n')
            : '';
        const missed =
          d.consecutive_missed_polls !== undefined &&
          d.consecutive_missed_polls !== null &&
          d.consecutive_missed_polls > 0
            ? String(d.consecutive_missed_polls)
            : '';

        return `
          <tr class="${online ? '' : 'offline'}">
            <td>
              <div>${escapeHtml(name || d.id)}</div>
              <div class="r-xtrs-devstat-hgi">${escapeHtml(d.id)}</div>
            </td>
            <td>${escapeHtml(d.class || '')}</td>
            <td>
              <span class="r-xtrs-devstat-status">
                <span class="r-xtrs-devstat-dot ${dotClass}"></span>
                ${online ? 'online' : d.status === 'off' ? 'offline' : 'unknown'}
              </span>
            </td>
            <td title="${escapeHtml(perHgi)}">${escapeHtml(rssi)}</td>
            <td>
              ${d.rssi_quality ? `<span class="r-xtrs-devstat-quality ${qClass}">${escapeHtml(d.rssi_quality)}</span>` : '-'}
            </td>
            <td>${escapeHtml(formatAge(d.staleness_seconds))}</td>
            <td>${escapeHtml(missed)}</td>
          </tr>`;
      })
      .join('');
  }

  _renderContent() {
    const title = this._config?.name || 'Device Status';
    const error = this._lastError;
    const sortArrow = (key) =>
      this._sortKey === key ? (this._sortDir === 'asc' ? ' ▲' : ' ▼') : '';

    this.shadowRoot.innerHTML = `
      <style>${deviceStatusCardStyle}</style>
      <ha-card header="${escapeHtml(title)}">
        <div class="r-xtrs-devstat-content">
          ${
            error
              ? `<div class="r-xtrs-devstat-error">Failed to load device status: ${escapeHtml(
                  error?.message || error
                )}</div>`
              : ''
          }
          ${this._renderPoolSection()}
          <div class="r-xtrs-devstat-table-wrap">
            <table class="r-xtrs-devstat-table">
              <thead>
                <tr>
                  <th data-sort="id">Device${sortArrow('id')}</th>
                  <th data-sort="class">Type${sortArrow('class')}</th>
                  <th data-sort="status">Status${sortArrow('status')}</th>
                  <th data-sort="rssi">RSSI${sortArrow('rssi')}</th>
                  <th>Quality</th>
                  <th data-sort="last_seen">Last seen${sortArrow('last_seen')}</th>
                  <th title="Consecutive missed polls">Missed</th>
                </tr>
              </thead>
              <tbody>
                ${this._renderDeviceRows()}
              </tbody>
            </table>
          </div>
        </div>
      </ha-card>`;

    this._attachSortListeners();
  }

  _attachSortListeners() {
    const headers = this.shadowRoot?.querySelectorAll('th[data-sort]');
    if (!headers) {
      return;
    }
    headers.forEach((th) => {
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-sort');
        if (this._sortKey === key) {
          this._sortDir = this._sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          this._sortKey = key;
          this._sortDir = 'asc';
        }
        this.render();
      });
    });
  }
}

// Register the card using the base class registration
DeviceStatusCard.register();

// Export for testing purposes
export { DeviceStatusCard };
