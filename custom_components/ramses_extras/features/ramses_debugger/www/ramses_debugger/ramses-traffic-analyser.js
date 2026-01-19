/* global setInterval */
/* global clearInterval */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocket } from '../../helpers/card-services.js';

import './ramses-log-explorer.js';

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
  }

  getCardSize() {
    return 12;
  }

  render() {
    if (this._dialogOpen) {
      this._pendingRender = true;
      return;
    }

    super.render();
  }

  static getTagName() {
    return 'ramses-traffic-analyser';
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

    if (this._config.enable_polling === true) {
      this._startPolling();
      return;
    }

    this._startSubscription();
  }

  _buildFiltersFromConfig() {
    const filters = {
      limit: this._config?.limit || 200,
    };

    const deviceId = this._config?.device_id;
    if (deviceId) {
      filters.device_id = deviceId;
    }

    return filters;
  }

  _startPolling() {
    const pollInterval = Number(this._config?.poll_interval || 5000);
    const safeInterval = Number.isFinite(pollInterval) ? Math.max(1000, pollInterval) : 5000;

    const doPoll = async () => {
      try {
        this._lastError = null;
        const result = await callWebSocket(this._hass, {
          type: 'ramses_extras/ramses_debugger/traffic/get_stats',
          ...this._buildFiltersFromConfig(),
        });
        this._stats = result;
      } catch (error) {
        this._lastError = error;
      }
      this.render();
    };

    void doPoll();
    this._pollInterval = setInterval(() => {
      void doPoll();
    }, safeInterval);
  }

  _startSubscription() {
    if (!this._hass?.connection) {
      return;
    }

    const throttleMs = Number(this._config?.throttle_ms || 1000);
    const safeThrottleMs = Number.isFinite(throttleMs) ? Math.max(0, throttleMs) : 1000;

    const payload = {
      type: 'ramses_extras/ramses_debugger/traffic/subscribe_stats',
      ...this._buildFiltersFromConfig(),
      throttle_ms: safeThrottleMs,
    };

    this._wsUnsubPromise = this._hass.connection
      .subscribeMessage((msg) => {
        const eventPayload = msg?.event || msg;
        this._stats = eventPayload;
        this._lastError = null;
        this.render();
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
      const devices = await callWebSocket(this._hass, { type: 'config/device_registry/list' });
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

    // Make the base color strongly dependent on the xx: prefix,
    // with smaller variations per :xxxxxx suffix.
    const baseHue = (typeInt * 67) % 360;
    const hue = (baseHue + (slugVar % 24) - 12 + 360) % 360;

    const baseLightness = typeInt === 0x32 ? 88 : 84;
    const lightness = Math.max(74, Math.min(92, baseLightness + ((slugVar % 8) - 4)));

    return `hsla(${hue}, 82%, ${lightness}%, 0.28)`;
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

    try {
      await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/traffic/reset_stats',
      });
    } catch (error) {
      this._lastError = error;
    }

    this.render();
  }

  _renderContent() {
    const title = this._config?.name || 'Ramses Traffic Analyser';
    const deviceDisplay = this._config?.device_id ? this.getDeviceDisplayName() : '-';

    const width = this.offsetWidth || 0;
    const compact = width > 0 && width < 900;

    const stats = this._stats;
    const flows = Array.isArray(stats?.flows) ? stats.flows : [];
    const totalCount = stats?.total_count;
    const startedAt = stats?.started_at;

    const errorText = this._lastError ? String(this._lastError?.message || this._lastError) : '';

    const sortArrow = (key) => {
      if (this._sortKey !== key) return '';
      return this._sortDir === 'asc' ? ' ▲' : ' ▼';
    };

    const sortedFlows = this._sortFlows([...flows]);

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

        const srcSlug = this._deviceSlug(src);
        const dstSlug = this._deviceSlug(dst);

        return `
          <tr class="flow-row" data-flow="${data}">
            <td class="device-cell" style="--dev-bg: ${srcBg};" title="Source device">
              <div class="dev">
                <span class="id">${src}</span>
                ${srcAlias ? `<span class="alias">${srcAlias}</span>` : ''}
                <span class="slug">${srcSlug}</span>
              </div>
            </td>
            <td class="device-cell" style="--dev-bg: ${dstBg};" title="Destination device">
              <div class="dev">
                <span class="id">${dst}</span>
                ${dstAlias ? `<span class="alias">${dstAlias}</span>` : ''}
                <span class="slug">${dstSlug}</span>
              </div>
            </td>
            <td class="verbs" title="Verbs observed for this flow">${verbs}</td>
            <td class="codes" title="Codes observed for this flow">${codes}</td>
            <td style="text-align: right;">${count}</td>
            <td>${lastSeen}</td>
            <td class="actions" title="Actions">
              <button class="action-log" title="Open Log Explorer for this flow">Logs</button>
              <button class="action-details" title="Show flow details">Details</button>
              <button class="action-messages" title="List raw messages for this flow (coming soon)">Messages</button>
            </td>
          </tr>
        `;
      })
      .join('');

    this.shadowRoot.innerHTML = `
      <style>
        ${trafficAnalyserCardStyle({ compact })}
      </style>
      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div class="meta">
            <div><strong>Device</strong>: ${deviceDisplay}</div>
            <div><strong>Total</strong>: ${typeof totalCount === 'number' ? totalCount : '-'}</div>
            <div><strong>Since</strong>: ${startedAt || '-'}</div>
            <div style="margin-left:auto;">
              <button id="resetStats" title="Reset the traffic counters">Reset</button>
            </div>
          </div>

          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="sortable" data-sort="src" title="Sort by source">src${sortArrow('src')}</th>
                  <th class="sortable" data-sort="dst" title="Sort by destination">dst${sortArrow('dst')}</th>
                  <th title="Verbs observed for this flow">verbs</th>
                  <th title="Codes observed for this flow">codes</th>
                  <th class="sortable" data-sort="count_total" title="Sort by total count" style="text-align: right;">count${sortArrow('count_total')}</th>
                  <th class="sortable" data-sort="last_seen" title="Sort by last seen">last_seen${sortArrow('last_seen')}</th>
                  <th title="Actions">actions</th>
                </tr>
              </thead>
              <tbody>
                ${rowsHtml || '<tr><td colspan="7">No data</td></tr>'}
              </tbody>
            </table>
          </div>

          <dialog id="detailsDialog">
            <form method="dialog">
              <h3>Flow details</h3>
              <pre id="detailsPre"></pre>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeDialog" title="Close this dialog">Close</button>
              </div>
            </form>
          </dialog>

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
              <h3>Messages (coming soon)</h3>
              <div class="muted" style="margin-top: 6px;">
                This will list the actual ramses_cc messages for the selected flow (src/dst),
                with a later drill-down to parsed fields.
              </div>
              <pre id="messagesPre"></pre>
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

  _attachEventListeners() {
    if (!this.shadowRoot) {
      return;
    }
    const resetBtn = this.shadowRoot.getElementById('resetStats');
    const closeBtn = this.shadowRoot.getElementById('closeDialog');
    const closeLogBtn = this.shadowRoot.getElementById('closeLogDialog');
    const closeMessagesBtn = this.shadowRoot.getElementById('closeMessagesDialog');

    const thead = this.shadowRoot.querySelector('thead');

    if (!this._boundOnReset) {
      this._boundOnReset = () => {
        void this._resetStats();
      };
    }
    if (!this._boundOnActionClick) {
      this._boundOnActionClick = (ev) => {
        const target = ev?.target;
        const btn = target?.closest?.('button');
        if (!btn) {
          return;
        }

        const row = btn.closest?.('tr.flow-row');
        if (!row) {
          return;
        }

        const encoded = row.getAttribute('data-flow');
        if (!encoded) {
          return;
        }

        try {
          const flow = JSON.parse(decodeURIComponent(encoded));
          const isLog = btn.classList.contains('action-log');
          const isDetails = btn.classList.contains('action-details');

          if (isLog) {
            const logDialog = this.shadowRoot?.getElementById('logDialog');
            const src = flow?.src || '';
            const dst = flow?.dst || '';
            const query = src && dst ? `${src} ${dst}` : src || dst;

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
            return;
          }

          if (isDetails) {
            const detailsDialog = this.shadowRoot?.getElementById('detailsDialog');
            const pre = this.shadowRoot?.getElementById('detailsPre');
            if (pre) {
              pre.textContent = JSON.stringify(flow, null, 2);
            }
            if (detailsDialog && typeof detailsDialog.showModal === 'function') {
              this._dialogOpen = true;
              detailsDialog.showModal();
            }
          }

          if (btn.classList.contains('action-messages')) {
            const messagesDialog = this.shadowRoot?.getElementById('messagesDialog');
            const pre = this.shadowRoot?.getElementById('messagesPre');
            if (pre) {
              pre.textContent = JSON.stringify(
                {
                  src: flow?.src,
                  dst: flow?.dst,
                  note: 'TODO: implement message listing backend + UI',
                },
                null,
                2,
              );
            }
            if (messagesDialog && typeof messagesDialog.showModal === 'function') {
              this._dialogOpen = true;
              messagesDialog.showModal();
            }
          }
        } catch (error) {
          logger.warn('Failed to handle row action:', error);
        }
      };
    }
    if (!this._boundOnDialogClose) {
      this._boundOnDialogClose = () => {
        try {
          const detailsDialog = this.shadowRoot?.getElementById('detailsDialog');
          const logDialog = this.shadowRoot?.getElementById('logDialog');
          const messagesDialog = this.shadowRoot?.getElementById('messagesDialog');

          if (detailsDialog && detailsDialog.open) {
            detailsDialog.close();
          }
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
    if (closeBtn) {
      closeBtn.onclick = this._boundOnDialogClose;
    }
    if (closeLogBtn) {
      closeLogBtn.onclick = this._boundOnDialogClose;
    }
    if (closeMessagesBtn) {
      closeMessagesBtn.onclick = this._boundOnDialogClose;
    }

    if (thead) {
      thead.onclick = this._boundOnSortClick;
    }

    const tbody = this.shadowRoot.querySelector('tbody');
    if (tbody) {
      tbody.onclick = this._boundOnActionClick;
    }

    const detailsDialog = this.shadowRoot.getElementById('detailsDialog');
    if (detailsDialog) {
      detailsDialog.onclose = this._boundOnDialogClosed;
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
