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
import { copyToClipboard } from '../../helpers/clipboard.js';
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
 * Return the HGI that heard this device best: argmax over the fresh
 * per-HGI RSSI map, falling back to the last-known map.  Returns the
 * HGI id (with '~' prefix when only last-known data exists), or ''.
 *
 * @param {Object} d - Device row
 * @returns {string} HGI device id or ''
 */
function bestHgi(d) {
  const fresh =
    d.rssi_per_hgi &&
    typeof d.rssi_per_hgi === 'object' &&
    Object.keys(d.rssi_per_hgi).length
      ? d.rssi_per_hgi
      : null;
  const stale =
    !fresh &&
    d.last_known_rssi_per_hgi &&
    typeof d.last_known_rssi_per_hgi === 'object' &&
    Object.keys(d.last_known_rssi_per_hgi).length
      ? d.last_known_rssi_per_hgi
      : null;
  const map = fresh || stale;
  if (!map) return '';
  let bestId = null;
  let bestVal = -Infinity;
  for (const [hgi, r] of Object.entries(map)) {
    if (Number(r) > bestVal) {
      bestVal = Number(r);
      bestId = hgi;
    }
  }
  return bestId ? `${stale ? '~' : ''}${bestId}` : '';
}

/**
 * Format the "last seen" cell: prefer staleness_seconds, fall back to
 * the pool child's last_pkt_time for transport (HGI) rows.
 *
 * @param {Object} d - Device row
 * @returns {string} Human-readable age
 */
function lastSeenLabel(d) {
  if (d.staleness_seconds !== null && d.staleness_seconds !== undefined) {
    return formatAge(d.staleness_seconds);
  }
  if (d.last_pkt_time) {
    const t = Date.parse(d.last_pkt_time);
    if (!Number.isNaN(t)) {
      return formatAge((Date.now() - t) / 1000);
    }
  }
  return '-';
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
    this._showForeign = false;
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
      name: 'Ramses Device Status Card',
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
      name: 'Ramses Device Status',
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
        case 'by':
          return bestHgi(d);
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

  /**
   * Devices visible under the current foreign/unowned filter.  Devices
   * without owner info (older ramses_cc without schema, or no schema)
   * are always shown; HGI rows are pool infrastructure and always
   * shown regardless of ownership.
   *
   * @returns {Array<Object>} Filtered device rows
   */
  _visibleDevices() {
    const devices = this._snapshot?.devices;
    if (!Array.isArray(devices)) {
      return [];
    }
    if (this._showForeign) {
      return devices;
    }
    return devices.filter(
      (d) =>
        d.group === 'hgi' || d.owner === undefined || d.owner === 'owned'
    );
  }

  /**
   * Order a group's rows so children follow their parent device.
   *
   * @param {Array<Object>} devices - Rows of one group
   * @returns {Array<Object>} Ordered rows (children flagged _child)
   */
  _organizeGroup(devices) {
    const sorted = this._sortDevices(devices);
    const byParent = new Map();
    const tops = [];
    for (const d of sorted) {
      if (d.parent) {
        if (!byParent.has(d.parent)) byParent.set(d.parent, []);
        byParent.get(d.parent).push(d);
      } else {
        tops.push(d);
      }
    }
    const out = [];
    const emitted = new Set();
    for (const d of tops) {
      out.push(d);
      for (const c of byParent.get(d.id) || []) {
        out.push({ ...c, _child: true });
        emitted.add(c);
      }
    }
    for (const children of byParent.values()) {
      for (const c of children) {
        if (!emitted.has(c)) {
          out.push({ ...c, _child: true });
        }
      }
    }
    return out;
  }

  _renderDeviceRows() {
    const devices = this._visibleDevices();
    if (devices.length === 0) {
      return `<div class="r-xtrs-devstat-empty">No RAMSES devices found</div>`;
    }

    const groups = [
      ['hgi', 'HGIs'],
      ['hvac', 'HVAC'],
      ['heat', 'Heat'],
      ['orphan', 'Orphans'],
    ];
    const byGroup = new Map();
    for (const d of devices) {
      const g = groups.some(([k]) => k === d.group) ? d.group : 'orphan';
      if (!byGroup.has(g)) byGroup.set(g, []);
      byGroup.get(g).push(d);
    }

    const sections = [];
    for (const [key, label] of groups) {
      const rows = byGroup.get(key);
      if (!rows || rows.length === 0) continue;
      sections.push(
        `<tr class="r-xtrs-devstat-group"><td colspan="8">${label}</td></tr>` +
          this._organizeGroup(rows)
            .map((d) => this._renderDeviceRow(d))
            .join('')
      );
    }
    return sections.join('');
  }

  _renderDeviceRow(d) {
    const online = d.status === 'on';
    const name =
      (this._deviceNameMap && this._deviceNameMap.get
        ? this._deviceNameMap.get(d.id)
        : undefined) ||
      d.name ||
      '';
    const dotClass = online ? 'on' : d.status === 'off' ? 'off' : 'unknown';
    const qClass = qualityClass(d.rssi_quality);

    // Fresh RSSI wins; fall back to the entity's last-known value
    // (pool per-HGI readings expire after 5 min, all readings are
    // lost on restart) with the age shown in the tooltip.
    const hasFresh = d.best_rssi !== null && d.best_rssi !== undefined;
    const hasLast = d.last_known_rssi !== null && d.last_known_rssi !== undefined;
    let rssi = '-';
    let rssiTitle = '';
    let rssiClass = '';
    if (hasFresh) {
      rssi = `${d.best_rssi} dBm`;
      rssiTitle =
        d.rssi_per_hgi && typeof d.rssi_per_hgi === 'object'
          ? Object.entries(d.rssi_per_hgi)
              .map(([hgi, r]) => `${hgi}: ${r}`)
              .join('\n')
          : '';
    } else if (hasLast) {
      rssi = `${d.last_known_rssi} dBm`;
      rssiClass = ' r-xtrs-devstat-stale';
      const parts = [];
      if (
        d.last_known_rssi_per_hgi &&
        typeof d.last_known_rssi_per_hgi === 'object'
      ) {
        parts.push(
          Object.entries(d.last_known_rssi_per_hgi)
            .map(([hgi, r]) => `${hgi}: ${r}`)
            .join('\n')
        );
      }
      const age = formatAge(d.last_rssi_age_seconds);
      parts.push(`last known${age !== '-' ? `, ${age} ago` : ''}`);
      rssiTitle = parts.join('\n');
    }

    const missed =
      d.consecutive_missed_polls !== undefined &&
      d.consecutive_missed_polls !== null &&
      d.consecutive_missed_polls > 0
        ? String(d.consecutive_missed_polls)
        : '';
    const ownerMark =
      d.owner && d.owner !== 'owned' ? ` (${d.owner})` : '';

    return `
      <tr class="${online ? '' : 'offline'}${d._child ? ' r-xtrs-devstat-child' : ''}">
        <td>
          <div>${d._child ? '↳ ' : ''}${escapeHtml(name || d.id)}${escapeHtml(ownerMark)}</div>
          <div class="r-xtrs-devstat-hgi">${escapeHtml(d.id)}</div>
        </td>
        <td>${escapeHtml(d.class || '')}</td>
        <td>
          <span class="r-xtrs-devstat-status">
            <span class="r-xtrs-devstat-dot ${dotClass}"></span>
            ${online ? 'online' : d.status === 'off' ? 'offline' : 'unknown'}
          </span>
        </td>
        <td class="${rssiClass.trim()}" title="${escapeHtml(rssiTitle)}">${escapeHtml(rssi)}</td>
        <td class="r-xtrs-devstat-hgi">${escapeHtml(bestHgi(d))}</td>
        <td>
          ${d.rssi_quality ? `<span class="r-xtrs-devstat-quality ${qClass}">${escapeHtml(d.rssi_quality)}</span>` : '-'}
        </td>
        <td>${escapeHtml(lastSeenLabel(d))}</td>
        <td>${escapeHtml(missed)}</td>
      </tr>`;
  }

  /**
   * Build a markdown-table export of the current snapshot for
   * copy/paste into GitHub issues or debugging notes.
   *
   * @returns {string} Markdown text
   */
  _buildClipboardText() {
    const lines = [];
    const pool = this._snapshot?.pool;

    if (pool) {
      const hgis = Array.isArray(pool.hgis) ? pool.hgis : [];
      const total = pool.children_total ?? hgis.length;
      const online =
        pool.children_online ?? hgis.filter((h) => h.online === true).length;
      lines.push(`Pool: ${pool.status === 'on' ? 'online' : 'offline'} (${online}/${total} HGIs)`);
      for (const hgi of hgis) {
        lines.push(
          `- ${hgi.hgi_id}: ${hgi.online === true ? 'online' : hgi.online === false ? 'offline' : 'unknown'}` +
            (hgi.availability ? ` (${hgi.availability})` : '') +
            (hgi.pkts_received !== undefined ? `, ${hgi.pkts_received} pkts` : '')
        );
      }
      lines.push('');
    }

    const devices = this._visibleDevices();
    if (devices.length) {
      lines.push('| Device | Type | Status | RSSI | By | Quality | Last seen | Missed |');
      lines.push('|---|---|---|---|---|---|---|---|');
      for (const d of devices) {
        const name =
          (this._deviceNameMap && this._deviceNameMap.get
            ? this._deviceNameMap.get(d.id)
            : undefined) || '';
        const label = name ? `${name} (${d.id})` : d.id;
        const hasFresh =
          d.best_rssi !== null && d.best_rssi !== undefined;
        const hasLast =
          d.last_known_rssi !== null && d.last_known_rssi !== undefined;
        let rssi = '-';
        if (hasFresh) {
          rssi = `${d.best_rssi} dBm`;
          if (d.rssi_per_hgi && typeof d.rssi_per_hgi === 'object') {
            rssi += ` (${Object.entries(d.rssi_per_hgi)
              .map(([h, r]) => `${h}:${r}`)
              .join(', ')})`;
          }
        } else if (hasLast) {
          rssi = `${d.last_known_rssi} dBm (last ${formatAge(d.last_rssi_age_seconds)} ago)`;
          if (
            d.last_known_rssi_per_hgi &&
            typeof d.last_known_rssi_per_hgi === 'object'
          ) {
            rssi += ` (${Object.entries(d.last_known_rssi_per_hgi)
              .map(([h, r]) => `${h}:${r}`)
              .join(', ')})`;
          }
        }
        const owner =
          d.owner && d.owner !== 'owned' ? ` [${d.owner}]` : '';
        const group =
          d.group && d.group !== 'orphan' ? `${d.group}: ` : '';
        lines.push(
          `| ${group}${label}${owner} | ${d.class || ''} | ${d.status === 'on' ? 'online' : d.status === 'off' ? 'offline' : 'unknown'} |` +
            ` ${rssi} | ${bestHgi(d) || '-'} | ${d.rssi_quality || '-'} |` +
            ` ${lastSeenLabel(d)} |` +
            ` ${d.consecutive_missed_polls > 0 ? d.consecutive_missed_polls : ''} |`
        );
      }
    }

    lines.push('');
    lines.push(`_Exported ${new Date().toISOString()}_`);
    return lines.join('\n');
  }

  async _copyToClipboard(btn) {
    const flash = (label) => {
      if (!btn) return;
      btn.textContent = label;
      setTimeout(() => {
        btn.textContent = 'Copy';
      }, 2000);
    };
    try {
      await copyToClipboard(this._buildClipboardText());
      flash('Copied');
    } catch {
      flash('Failed');
    }
  }

  _renderContent() {
    const title = this._config?.name || 'Ramses Device Status';
    const error = this._lastError;
    const sortArrow = (key) =>
      this._sortKey === key ? (this._sortDir === 'asc' ? ' ▲' : ' ▼') : '';

    this.shadowRoot.innerHTML = `
      <style>${deviceStatusCardStyle}</style>
      <ha-card>
        <div class="r-xtrs-devstat-content">
          <div class="r-xtrs-devstat-header">
            <div class="card-header">${escapeHtml(title)}</div>
            <label
              class="r-xtrs-devstat-toggle"
              title="Show foreign-owned and unowned devices"
            >
              <input
                type="checkbox"
                id="r-xtrs-devstat-foreign"
                ${this._showForeign ? 'checked' : ''}
              >
              non-owned
            </label>
            <button
              id="r-xtrs-devstat-copy"
              class="r-xtrs-devstat-refresh"
              title="Copy status table to clipboard"
            >Copy</button>
          </div>
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
                  <th data-sort="by" title="HGI with the best signal for this device">By${sortArrow('by')}</th>
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

    const copyBtn = this.shadowRoot?.getElementById('r-xtrs-devstat-copy');
    if (copyBtn) {
      copyBtn.onclick = () => {
        void this._copyToClipboard(copyBtn);
      };
    }

    const foreignToggle = this.shadowRoot?.getElementById(
      'r-xtrs-devstat-foreign'
    );
    if (foreignToggle) {
      foreignToggle.onchange = (e) => {
        this._showForeign = Boolean(e.target?.checked);
        this.render();
      };
    }
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
