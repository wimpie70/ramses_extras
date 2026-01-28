/* global setInterval */
/* global clearInterval */
/* global navigator */

/**
 * Ramses Traffic Analyser card.
 *
 * A "flow" is a unique (src, dst) pair observed in ramses_cc message events.
 * This card can show live flows via subscription, or log-backed flows by
 * polling packet_log / ha_log sources.
 *
 * Performance:
 * - Uses `callWebSocketShared()` to de-duplicate in-flight requests across
 *   multiple cards on the same dashboard.
 * - When using the default poll interval, it prefers the integration option
 *   `ramses_debugger_default_poll_ms` so all cards stay in sync.
 */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocketShared } from '../../helpers/card-services.js';

import './ramses-log-explorer.js';
import './ramses-messages-viewer.js';

import { trafficAnalyserCardStyle } from './card-styles.js';

class RamsesTrafficAnalyserCard extends RamsesBaseCard {
  constructor() {
    super();

    this._stats = null;
    this._wsUnsubPromise = null;
    this._wsUnsub = null;
    this._pollInterval = null;
    this._lastError = null;

    this._detailsDialogOpen = false;
    this._detailsFlow = null;

    this._dialogOpen = false;
    this._pendingRender = false;

    this._boundOnReset = null;
    this._boundOnActionClick = null;
    this._boundOnDialogClose = null;
    this._boundOnDialogClosed = null;

    this._sortKey = 'count_total';
    this._sortDir = 'desc';
    this._boundOnSortClick = null;

    this._deviceNameMap = null;
    this._deviceNameMapTs = 0;

    this._deviceSlugMap = null;
    this._deviceSlugMapTs = 0;

    this._checkedRows = new Map(); // src|dst -> checked
    this._flows = []; // Initialize to avoid undefined errors

    this._trafficSource = 'live';
    this._boundOnTrafficSourceChange = null;

    this._messagesSortKey = 'dtm';
    this._messagesSortDir = 'asc';
    this._messagesDecode = false;
    this._boundOnMessagesSortClick = null;
    this._boundOnMessagesDecodeToggle = null;
  }

  getCardSize() {
    return 12;
  }

  static getTagName() {
    return 'ramses-traffic-analyser';
  }

  static getStubConfig() {
    return {
      type: `custom:${this.getTagName()}`,
      ...this.prototype.getDefaultConfig(),
      layout_options: {
        grid_columns: 200,
      },
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

  _checkAndLoadInitialState() {
    if (this._hass && this._config && !this._initialStateLoaded) {
      this._loadInitialState();
      this._initialStateLoaded = true;
    }
  }

  async _copyToClipboard(text) {
    try {
      if (!text) {
        return;
      }
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
      }

      const textarea = document.createElement('textarea');
      textarea.value = String(text);
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '0';
      textarea.style.left = '0';
      textarea.style.width = '1px';
      textarea.style.height = '1px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      textarea.remove();
    } catch (error) {
      logger.warn('Copy to clipboard failed:', error);
    }
  }

  async _loadDeviceSlugMap() {
    if (!this._hass) {
      return;
    }

    const now = Date.now();
    if (this._deviceSlugMap && (now - this._deviceSlugMapTs) < 30_000) {
      return;
    }

    try {
      const res = await callWebSocketShared(
        this._hass,
        { type: 'ramses_extras/get_available_devices' },
        { cacheMs: 30_000 }
      );
      const devices = Array.isArray(res?.devices) ? res.devices : [];
      const map = new Map();

      for (const dev of devices) {
        const id = String(dev?.device_id ?? '');
        if (!id) {
          continue;
        }
        const slugLabel = String(dev?.slug_label ?? '').trim();
        const slugs = Array.isArray(dev?.slugs) ? dev.slugs.map((s) => String(s)).filter(Boolean) : [];
        const label = slugLabel || (slugs.length ? slugs.join(', ') : '');
        if (label) {
          map.set(id, label);
        }
      }

      this._deviceSlugMap = map;
      this._deviceSlugMapTs = now;
      this.render();
    } catch {
      // Ignore - this call depends on Ramses Extras integration state.
    }
  }

  getDefaultConfig() {
    return {
      name: 'Ramses Traffic Analyser',
      show_device_id_only: false,
      show_name_only: false,
      show_both: true,

      enable_polling: false,
      poll_interval: 5000,
      throttle_ms: 1000,
      limit: 200,
    };
  }

  getFeatureName() {
    return 'ramses_debugger';
  }

  _onConnected() {
    void this._loadDeviceNameMap();
    void this._loadDeviceSlugMap();
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

    if (typeof this._wsUnsub === 'function') {
      try {
        this._wsUnsub();
      } catch (error) {
        logger.warn('Failed to unsubscribe traffic stats:', error);
      }
    }

    this._wsUnsub = null;
    this._wsUnsubPromise = null;
  }

  _startUpdates() {
    if (!this._hass || !this._config) {
      return;
    }

    this._stopUpdates();

    if (this._trafficSource !== 'live') {
      this._startPolling();
      return;
    }

    if (this._config.enable_polling === true) {
      this._startPolling();
      return;
    }

    this._startSubscription();
  }

  _buildFiltersFromConfig({ includeTrafficSource = true } = {}) {
    const filters = {
      limit: this._config?.limit || 200,
    };

    if (includeTrafficSource && this._trafficSource) {
      filters.traffic_source = this._trafficSource;
    }

    const deviceId = this._config?.device_id;
    if (deviceId) {
      filters.device_id = deviceId;
    }

    return filters;
  }

  _startPolling() {
    // Polling is used for log-backed traffic sources and for users that prefer
    // predictable periodic updates over WebSocket subscriptions.
    let pollInterval = Number(this._config?.poll_interval || 5000);
    const globalDefault = Number(window?.ramsesExtras?.options?.ramses_debugger_default_poll_ms);
    if (pollInterval === 5000 && Number.isFinite(globalDefault) && globalDefault > 0) {
      pollInterval = globalDefault;
    }
    const safeInterval = Number.isFinite(pollInterval) ? Math.max(1000, pollInterval) : 5000;

    const doPoll = async () => {
      try {
        this._lastError = null;
        const result = await callWebSocketShared(this._hass, {
          type: 'ramses_extras/ramses_debugger/traffic/get_stats',
          ...this._buildFiltersFromConfig({ includeTrafficSource: true }),
        }, { cacheMs: 500 });

        // Only render if stats actually changed to avoid unnecessary scroll jumps
        const statsChanged = JSON.stringify(this._stats) !== JSON.stringify(result);
        this._stats = result;

        if (statsChanged) {
          this.render();
        }
      } catch (error) {
        const errorChanged = JSON.stringify(this._lastError) !== JSON.stringify(error);
        this._lastError = error;

        if (errorChanged) {
          this.render();
        }
      }
    };

    void doPoll();
    this._pollInterval = setInterval(() => {
      void doPoll();
    }, safeInterval);
  }

  _startSubscription() {
    // Subscription is preferred for live traffic to reduce periodic polling
    // overhead. If subscription fails, users can enable polling as a fallback.
    if (!this._hass?.connection) {
      return;
    }

    const throttleMs = Number(this._config?.throttle_ms || 1000);
    const safeThrottleMs = Number.isFinite(throttleMs) ? Math.max(0, throttleMs) : 1000;

    const payload = {
      type: 'ramses_extras/ramses_debugger/traffic/subscribe_stats',
      ...this._buildFiltersFromConfig({ includeTrafficSource: false }),
      throttle_ms: safeThrottleMs,
    };

    this._wsUnsubPromise = this._hass.connection
      .subscribeMessage((msg) => {
        const eventPayload = msg?.event || msg;

        // Only render if stats actually changed to avoid unnecessary scroll jumps
        const statsChanged = JSON.stringify(this._stats) !== JSON.stringify(eventPayload);
        this._stats = eventPayload;
        this._lastError = null;

        if (statsChanged) {
          this.render();
        }
      }, payload)
      .then((unsub) => {
        this._wsUnsub = unsub;
      })
      .catch((error) => {
        this._lastError = error;
        logger.warn('Traffic subscribe failed, consider enabling polling:', error);
        this.render();
      });
  }

  async _loadDeviceNameMap() {
    if (!this._hass) {
      return;
    }

    const now = Date.now();
    if (this._deviceNameMap && (now - this._deviceNameMapTs) < 30_000) {
      return;
    }

    try {
      const devices = await callWebSocketShared(
        this._hass,
        { type: 'config/device_registry/list' },
        { cacheMs: 30_000 }
      );
      const map = new Map();

      if (Array.isArray(devices)) {
        for (const dev of devices) {
          const name = dev?.name_by_user || dev?.name || '';
          const identifiers = dev?.identifiers;
          if (!name || !Array.isArray(identifiers)) {
            continue;
          }

          for (const ident of identifiers) {
            if (!Array.isArray(ident) || ident.length !== 2) {
              continue;
            }
            const domain = String(ident[0] ?? '');
            const id = String(ident[1] ?? '');
            if (!domain || !id) {
              continue;
            }
            map.set(`${domain}:${id}`, name);
          }
        }
      }

      this._deviceNameMap = map;
      this._deviceNameMapTs = now;
      this.render();
    } catch {
      // Ignore - not all HA versions/users allow this call in all contexts.
    }
  }

  _deviceSlug(deviceId) {
    const s = String(deviceId || '');
    const parts = s.split(':');
    if (parts.length !== 2) {
      return s;
    }
    return parts[1];
  }

  _deviceSlugLabel(deviceId) {
    const id = String(deviceId || '');
    const label = this._deviceSlugMap?.get(id);
    if (label) {
      return String(label);
    }

    // Fallback: show a readable default for well-known prefixes.
    const prefix = id.split(':')[0] || '';
    if (prefix === '18') {
      return 'HGI';
    }
    return '';
  }

  _deviceAlias(deviceId) {
    const id = String(deviceId || '');
    const key = `ramses_extras:${id}`;
    const alias = this._deviceNameMap?.get(key);
    return alias ? String(alias) : '';
  }

  _deviceBg(deviceId) {
    const s = String(deviceId || '');
    const typeHex = s.split(':')[0] || '';
    const typeInt = Number.parseInt(typeHex, 16);
    if (!Number.isFinite(typeInt)) {
      return 'transparent';
    }

    if (typeInt === 0x18) {
      return 'transparent';
    }

    const slugHex = this._deviceSlug(s);
    const slugInt = Number.parseInt(slugHex, 16);
    const slugVar = Number.isFinite(slugInt) ? slugInt : 0;

    // Map xx: to hue (0–360)
    const hue = (typeInt * 137) % 360;

    // Map :xxxxxx to saturation (15–85)
    const satMin = 15;
    const satMax = 85;
    const saturation = satMin + ((slugVar % 256) / 255) * (satMax - satMin);

    // Map :xxxxxx to lightness (20–75)
    const lightMin = 20;
    const lightMax = 75;
    const lightness = lightMin + ((slugVar % 256) / 255) * (lightMax - lightMin);

    // Map :xxxxxx to alpha (0.35–0.85)
    const alphaMin = 0.35;
    const alphaMax = 0.85;
    const alpha = alphaMin + ((slugVar % 256) / 255) * (alphaMax - alphaMin);

    return `hsla(${hue}, ${saturation}%, ${lightness}%, ${alpha})`;
  }

  _formatCounter(counterObj) {
    if (!counterObj || typeof counterObj !== 'object') {
      return '';
    }

    const items = Object.entries(counterObj)
      .filter(([, v]) => typeof v === 'number' && v > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k}:${v}`);
    return items.join(' ');
  }

  _sortFlows(flows) {
    const key = this._sortKey;
    const dir = this._sortDir;
    const mul = dir === 'asc' ? 1 : -1;

    return flows.sort((a, b) => {
      const av = a?.[key];
      const bv = b?.[key];

      if (typeof av === 'number' && typeof bv === 'number') {
        return (av - bv) * mul;
      }

      const as = String(av ?? '');
      const bs = String(bv ?? '');
      return as.localeCompare(bs) * mul;
    });
  }

  _toggleSort(key) {
    if (this._sortKey === key) {
      this._sortDir = this._sortDir === 'asc' ? 'desc' : 'asc';
      return;
    }
    this._sortKey = key;
    this._sortDir = key === 'count_total' ? 'desc' : 'asc';
  }

  async _resetStats() {
    if (!this._hass) {
      return;
    }

    if (this._trafficSource !== 'live') {
      return;
    }

    // Clear UI immediately so reset feels responsive.
    this._lastError = null;
    this._stats = {
      flows: [],
      total_count: 0,
      started_at: '',
    };
    this._checkedRows.clear();
    this.render();

    try {
      await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/traffic/reset_stats',
      });

      // Refresh after reset so the "since" timestamp reflects the new window.
      this._stats = await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/traffic/get_stats',
        ...this._buildFiltersFromConfig(),
      }, { cacheMs: 500 });
    } catch (error) {
      this._lastError = error;
    }

    this.render();
  }

  _renderContent() {
    if (this._dialogOpen) {
      this._pendingRender = true;
      return;
    }

    this._renderContentImpl();
  }

  _renderContentImpl() {
    const title = this._config?.name || 'Ramses Traffic Analyser';
    const deviceDisplay = this._config?.device_id ? this.getDeviceDisplayName() : '-';

    const trafficSource = this._trafficSource || 'live';

    const width = this.offsetWidth || 0;
    const compact = width > 0 && width < 900;

    const stats = this._stats;
    const flows = Array.isArray(stats?.flows) ? stats.flows : [];
    const totalCount = stats?.total_count;
    const startedAt = stats?.started_at;

    const resetDisabled = trafficSource !== 'live';

    const errorText = this._lastError ? String(this._lastError?.message || this._lastError) : '';

    const sortArrow = (key) => {
      if (this._sortKey !== key) return '';
      return this._sortDir === 'asc' ? ' ▲' : ' ▼';
    };

    const sortedFlows = this._sortFlows([...flows]);

    this._flows = sortedFlows;

    const rowsHtml = sortedFlows
      .map((flow) => {
        const src = flow?.src || '';
        const dst = flow?.dst || '';
        const count = flow?.count_total ?? '';
        const lastSeen = flow?.last_seen || '';
        const verbs = this._formatCounter(flow?.verbs);
        const codes = this._formatCounter(flow?.codes);
        const data = encodeURIComponent(JSON.stringify(flow));

        const srcBg = this._deviceBg(src);
        const dstBg = this._deviceBg(dst);

        const srcAlias = this._deviceAlias(src);
        const dstAlias = this._deviceAlias(dst);

        const srcSlugLabel = this._deviceSlugLabel(src);
        const dstSlugLabel = this._deviceSlugLabel(dst);

        return `
          <tr class="r-xtrs-traf-nlysr-flow-row" data-flow="${data}">
            <td class="r-xtrs-traf-nlysr-select-cell">
              <input type="checkbox" class="r-xtrs-traf-nlysr-row-select" data-src="${src}" data-dst="${dst}" ${this._checkedRows.get(`${src}|${dst}`) ? 'checked' : ''}>
            </td>
            <td class="r-xtrs-traf-nlysr-device-cell" style="--dev-bg: ${srcBg};" title="Source device">
              <div class="r-xtrs-traf-nlysr-dev">
                <span class="r-xtrs-traf-nlysr-id">${src}</span>
                ${srcAlias ? `<span class="r-xtrs-traf-nlysr-alias">${srcAlias}</span>` : ''}
                ${srcSlugLabel ? `<span class="r-xtrs-traf-nlysr-slug">${srcSlugLabel}</span>` : ''}
              </div>
            </td>
            <td class="r-xtrs-traf-nlysr-device-cell" style="--dev-bg: ${dstBg};" title="Destination device">
              <div class="r-xtrs-traf-nlysr-dev">
                <span class="r-xtrs-traf-nlysr-id">${dst}</span>
                ${dstAlias ? `<span class="r-xtrs-traf-nlysr-alias">${dstAlias}</span>` : ''}
                ${dstSlugLabel ? `<span class="r-xtrs-traf-nlysr-slug">${dstSlugLabel}</span>` : ''}
              </div>
            </td>
            <td class="r-xtrs-traf-nlysr-verbs" title="Verbs observed for this flow">${verbs}</td>
            <td class="r-xtrs-traf-nlysr-codes" title="Codes observed for this flow">${codes}</td>
            <td style="text-align: right;">${count}</td>
            <td>${lastSeen}</td>
          </tr>
        `;
      })
      .join('');

    this.shadowRoot.innerHTML = `
      <style>
        ${trafficAnalyserCardStyle({ compact })}
      </style>
      <ha-card header="${title}">
        <div class="r-xtrs-traf-nlysr-card-content">
          <div class="r-xtrs-traf-nlysr-meta">
            <div><strong>Device</strong>: ${deviceDisplay}</div>
            <div>
              <strong>Source</strong>:
              <select id="trafficSource" title="Select traffic source">
                <option value="live" ${trafficSource === 'live' ? 'selected' : ''}>live</option>
                <option value="packet_log" ${trafficSource === 'packet_log' ? 'selected' : ''}>packet_log</option>
                <option value="ha_log" ${trafficSource === 'ha_log' ? 'selected' : ''}>ha_log</option>
              </select>
            </div>
            <div><strong>Total</strong>: ${typeof totalCount === 'number' ? totalCount : '-'}</div>
            <div><strong>Flows</strong>: ${flows.length}</div>
            <div><strong>Since</strong>: ${startedAt || '-'}</div>
            <div style="margin-left:auto; display: flex; gap: 8px;">
              <button id="bulkLogs" title="Copy selected flows to clipboard">Copy selection</button>
              <button id="bulkMessages" title="List raw messages for selected flows">Messages</button>
              <button id="resetStats" title="Reset the traffic counters" ${resetDisabled ? 'disabled' : ''}>Reset</button>
            </div>
          </div>

          ${errorText ? `<div class="r-xtrs-traf-nlysr-error">${errorText}</div>` : ''}

          <div class="r-xtrs-traf-nlysr-table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="r-xtrs-traf-nlysr-select-cell"><input type="checkbox" id="selectAll" title="Select all flows" ${this._flows && this._flows.length && this._checkedRows.size === this._flows.length ? 'checked' : ''}></th>
                  <th class="sortable" data-sort="src" title="Sort by source">src${sortArrow('src')}</th>
                  <th class="sortable" data-sort="dst" title="Sort by destination">dst${sortArrow('dst')}</th>
                  <th title="Verbs observed for this flow">verbs</th>
                  <th title="Codes observed for this flow">codes</th>
                  <th class="sortable" data-sort="count_total" title="Sort by total count" style="text-align: right;">count${sortArrow('count_total')}</th>
                  <th class="sortable" data-sort="last_seen" title="Sort by last seen">last_seen${sortArrow('last_seen')}</th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml || '<tr><td colspan="7">No data</td></tr>'}
              </tbody>
            </table>
          </div>

          <dialog id="logDialog">
            <form method="dialog">
              <h3>Log Explorer</h3>
              <div id="logContainer"></div>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeLogDialog" title="Close this dialog">Close</button>
              </div>
            </form>
          </dialog>

          <dialog id="messagesDialog">
            <form method="dialog">
              <h3>Messages</h3>
              <div id="messagesContainer"></div>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeMessagesDialog" title="Close this dialog">Close</button>
              </div>
            </form>
          </dialog>
        </div>
      </ha-card>
    `;

    this._attachEventListeners();
  }

  _getSelectedFlows() {
    const checkboxes = this.shadowRoot.querySelectorAll('.r-xtrs-traf-nlysr-row-select:checked');
    return Array.from(checkboxes).map((cb) => ({
      src: cb.getAttribute('data-src'),
      dst: cb.getAttribute('data-dst'),
    }));
  }

  _openLogDialog(query) {
    const logDialog = this.shadowRoot?.getElementById('logDialog');
    const container = this.shadowRoot?.getElementById('logContainer');
    if (container) {
      container.innerHTML = '';
      const el = document.createElement('ramses-log-explorer');
      container.appendChild(el);

      try {
        el.setConfig({
          name: 'Ramses Log Explorer',
          prefill_query: query,
          auto_search: true,
        });

        if (this._hass) {
          el.hass = this._hass;
        }
      } catch (error) {
        logger.warn('Failed to init embedded log explorer:', error);
      }
    }

    if (logDialog && typeof logDialog.showModal === 'function') {
      this._dialogOpen = true;
      logDialog.showModal();
    }
  }

  _openMessagesDialog(selected) {
    const messagesDialog = this.shadowRoot?.getElementById('messagesDialog');
    const container = this.shadowRoot?.getElementById('messagesContainer');
    if (container) {
      container.innerHTML = '';
      const viewer = document.createElement('ramses-messages-viewer');
      container.appendChild(viewer);

      const filters = {};
      const srcList = [];
      const dstList = [];
      for (const { src, dst } of selected) {
        if (src) srcList.push(src);
        if (dst) dstList.push(dst);
      }
      if (srcList.length === 1) filters.src = srcList[0];
      if (dstList.length === 1) filters.dst = dstList[0];

      let sources = ['traffic_buffer'];
      if (this._trafficSource === 'packet_log') {
        sources = ['packet_log'];
      } else if (this._trafficSource === 'ha_log') {
        sources = ['ha_log'];
      }

      viewer.fetchMessages = ({ hass, decode, limit }) => hass?.callWS({
        type: 'ramses_extras/ramses_debugger/messages/get_messages',
        sources,
        limit: Number(limit || 200),
        dedupe: true,
        decode: Boolean(decode),
        ...filters,
      });

      try {
        viewer.setConfig({
          pairs: selected,
          pair_mode: 'selected',
          limit: 200,
          sort_key: 'dtm',
          sort_dir: 'desc',
        });
        if (this._hass) {
          viewer.hass = this._hass;
        }
        void viewer.refresh();
      } catch (error) {
        logger.warn('Failed to init embedded messages viewer:', error);
      }
    }
    if (messagesDialog && typeof messagesDialog.showModal === 'function') {
      this._dialogOpen = true;
      messagesDialog.showModal();
    }
  }

  _attachEventListeners() {
    if (!this.shadowRoot) {
      return;
    }
    const resetBtn = this.shadowRoot.getElementById('resetStats');
    const trafficSourceSel = this.shadowRoot.getElementById('trafficSource');
    const closeLogBtn = this.shadowRoot.getElementById('closeLogDialog');
    const closeMessagesBtn = this.shadowRoot.getElementById('closeMessagesDialog');
    const selectAllCb = this.shadowRoot.getElementById('selectAll');
    const bulkLogsBtn = this.shadowRoot.getElementById('bulkLogs');
    const bulkMessagesBtn = this.shadowRoot.getElementById('bulkMessages');

    const thead = this.shadowRoot.querySelector('thead');

    if (!this._boundOnReset) {
      this._boundOnReset = () => {
        void this._resetStats();
      };
    }
    if (!this._boundOnDialogClose) {
      this._boundOnDialogClose = () => {
        try {
          const logDialog = this.shadowRoot?.getElementById('logDialog');
          const messagesDialog = this.shadowRoot?.getElementById('messagesDialog');
          if (logDialog && logDialog.open) {
            logDialog.close();
          }
          if (messagesDialog && messagesDialog.open) {
            messagesDialog.close();
          }

          this._dialogOpen = false;

          if (this._pendingRender) {
            this._pendingRender = false;
            this.render();
          }
        } catch (error) {
          logger.warn('Failed to close dialog:', error);
        }
      };
    }

    if (!this._boundOnDialogClosed) {
      this._boundOnDialogClosed = () => {
        this._dialogOpen = false;
        if (this._pendingRender) {
          this._pendingRender = false;
          this.render();
        }
      };
    }

    if (!this._boundOnSortClick) {
      this._boundOnSortClick = (ev) => {
        const th = ev.target?.closest?.('th');
        const key = th?.getAttribute?.('data-sort');
        if (!key) {
          return;
        }
        this._toggleSort(key);
        this.render();
      };
    }

    if (resetBtn) {
      resetBtn.onclick = this._boundOnReset;
    }

    if (!this._boundOnTrafficSourceChange) {
      this._boundOnTrafficSourceChange = (ev) => {
        const val = ev?.target?.value;
        if (typeof val !== 'string' || !val) {
          return;
        }

        this._trafficSource = val;
        this._checkedRows.clear();
        this._lastError = null;
        this._stats = null;
        this.render();

        this._startUpdates();
      };
    }
    if (trafficSourceSel) {
      trafficSourceSel.onchange = this._boundOnTrafficSourceChange;
    }
    if (closeLogBtn) {
      closeLogBtn.onclick = this._boundOnDialogClose;
    }
    if (closeMessagesBtn) {
      closeMessagesBtn.onclick = this._boundOnDialogClose;
    }
    if (!this._boundOnSelectAll) {
      this._boundOnSelectAll = (ev) => {
        const checked = Boolean(ev?.target?.checked);

        this._checkedRows.clear();
        if (checked && this._flows) {
          this._flows.forEach(({ src, dst }) => {
            this._checkedRows.set(`${src}|${dst}`, true);
          });
        }

        this.render();
      };
    }
    if (selectAllCb) {
      selectAllCb.onchange = this._boundOnSelectAll;
    }

    // Add per-row checkbox listeners
    const rowCheckboxes = this.shadowRoot.querySelectorAll('.r-xtrs-traf-nlysr-row-select');
    rowCheckboxes.forEach((cb) => {
      const src = cb.getAttribute('data-src');
      const dst = cb.getAttribute('data-dst');
      cb.addEventListener('change', (ev) => {
        if (ev.target.checked) {
          this._checkedRows.set(`${src}|${dst}`, true);
        } else {
          this._checkedRows.delete(`${src}|${dst}`);
        }
        // Update select all checkbox state
        const selectAll = this.shadowRoot.getElementById('selectAll');
        if (selectAll && this._flows) {
          selectAll.checked = this._checkedRows.size === this._flows.length;
        }
      });
    });
    if (bulkLogsBtn) {
      bulkLogsBtn.onclick = this._boundOnBulkLogs || (() => {
        const selected = this._getSelectedFlows();
        if (selected.length === 0) return;
        const lines = selected.map(({ src, dst }) => (src && dst ? `${src} ${dst}` : src || dst)).filter(Boolean);
        void this._copyToClipboard(lines.join('\n'));
      });
    }
    if (bulkMessagesBtn) {
      bulkMessagesBtn.onclick = this._boundOnBulkMessages || (() => {
        const selected = this._getSelectedFlows();
        if (selected.length === 0) return;
        this._openMessagesDialog(selected);
      });
    }

    if (thead) {
      thead.onclick = this._boundOnSortClick;
    }

    const logDialog = this.shadowRoot.getElementById('logDialog');
    if (logDialog) {
      logDialog.onclose = this._boundOnDialogClosed;
    }

    const messagesDialog = this.shadowRoot.getElementById('messagesDialog');
    if (messagesDialog) {
      messagesDialog.onclose = this._boundOnDialogClosed;
    }
  }

  static getCardInfo() {
    return {
      type: 'ramses-traffic-analyser',
      name: 'Ramses Traffic Analyser',
      description:
        'Spreadsheet-like comms matrix for ramses_cc traffic. Best viewed in full-width or 2+ column layouts.',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }
}

RamsesTrafficAnalyserCard.register();
