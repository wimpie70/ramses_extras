/* global setInterval */
/* global clearInterval */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocket } from '../../helpers/card-services.js';

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

    this._boundOnFilterApply = null;
    this._boundOnReset = null;
    this._boundOnRowClick = null;
    this._boundOnDialogClose = null;
  }

  getCardSize() {
    return 3;
  }

  static getTagName() {
    return 'ramses-traffic-analyser';
  }

  getRequiredEntities() {
    return {};
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

      filter_src: '',
      filter_dst: '',
      filter_code: '',
      filter_verb: '',
      limit: 200,
    };
  }

  getFeatureName() {
    return 'ramses_debugger';
  }

  _onConnected() {
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
    return {
      device_id: this._config?.device_id,
      src: this._config?.filter_src || undefined,
      dst: this._config?.filter_dst || undefined,
      code: this._config?.filter_code || undefined,
      verb: this._config?.filter_verb || undefined,
      limit: this._config?.limit || 200,
    };
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

  _applyFiltersFromForm() {
    if (!this.shadowRoot) {
      return;
    }

    const getValue = (id) => {
      const el = this.shadowRoot.getElementById(id);
      return el && typeof el.value === 'string' ? el.value.trim() : '';
    };

    const getNumber = (id, fallback) => {
      const el = this.shadowRoot.getElementById(id);
      const value = el && typeof el.value === 'string' ? Number(el.value) : fallback;
      return Number.isFinite(value) ? value : fallback;
    };

    this._config = {
      ...this._config,
      filter_src: getValue('filterSrc'),
      filter_dst: getValue('filterDst'),
      filter_code: getValue('filterCode'),
      filter_verb: getValue('filterVerb'),
      limit: getNumber('filterLimit', 200),
    };

    this._startUpdates();
    this.render();
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
    const deviceDisplay = this.getDeviceDisplayName();

    const stats = this._stats;
    const flows = Array.isArray(stats?.flows) ? stats.flows : [];
    const totalCount = stats?.total_count;
    const startedAt = stats?.started_at;

    const errorText = this._lastError ? String(this._lastError?.message || this._lastError) : '';

    const rowsHtml = flows
      .map((flow) => {
        const src = flow?.src || '';
        const dst = flow?.dst || '';
        const count = flow?.count_total ?? '';
        const lastSeen = flow?.last_seen || '';
        const data = encodeURIComponent(JSON.stringify(flow));
        return `
          <tr class="flow-row" data-flow="${data}">
            <td>${src}</td>
            <td>${dst}</td>
            <td style="text-align: right;">${count}</td>
            <td>${lastSeen}</td>
          </tr>
        `;
      })
      .join('');

    this.shadowRoot.innerHTML = `
      <style>
        .meta { display: flex; gap: 12px; font-size: 12px; opacity: 0.8; }
        .controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .controls input { width: 110px; }
        .controls input.small { width: 80px; }
        .controls button { cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
        th { text-align: left; font-weight: 600; }
        tr.flow-row:hover { background: rgba(0,0,0,0.06); }
        .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }
        dialog { width: min(900px, 92vw); }
        dialog pre { white-space: pre-wrap; word-break: break-word; }
      </style>
      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div class="meta">
            <div><strong>Device</strong>: ${deviceDisplay}</div>
            <div><strong>Total</strong>: ${typeof totalCount === 'number' ? totalCount : '-'}</div>
            <div><strong>Since</strong>: ${startedAt || '-'}</div>
          </div>

          <div style="margin-top: 12px;" class="controls">
            <input id="filterSrc" placeholder="src" value="${this._config?.filter_src || ''}" />
            <input id="filterDst" placeholder="dst" value="${this._config?.filter_dst || ''}" />
            <input id="filterCode" class="small" placeholder="code" value="${this._config?.filter_code || ''}" />
            <input id="filterVerb" class="small" placeholder="verb" value="${this._config?.filter_verb || ''}" />
            <input id="filterLimit" class="small" placeholder="limit" value="${this._config?.limit || 200}" />
            <button id="applyFilters">Apply</button>
            <button id="resetStats">Reset</button>
          </div>

          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <table>
            <thead>
              <tr>
                <th>src</th>
                <th>dst</th>
                <th style="text-align: right;">count</th>
                <th>last_seen</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml || '<tr><td colspan="4">No data</td></tr>'}
            </tbody>
          </table>

          <dialog id="detailsDialog">
            <form method="dialog">
              <h3>Flow details</h3>
              <pre id="detailsPre"></pre>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeDialog">Close</button>
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

    const applyBtn = this.shadowRoot.getElementById('applyFilters');
    const resetBtn = this.shadowRoot.getElementById('resetStats');
    const dialog = this.shadowRoot.getElementById('detailsDialog');
    const closeBtn = this.shadowRoot.getElementById('closeDialog');

    if (!this._boundOnFilterApply) {
      this._boundOnFilterApply = () => this._applyFiltersFromForm();
    }
    if (!this._boundOnReset) {
      this._boundOnReset = () => {
        void this._resetStats();
      };
    }
    if (!this._boundOnRowClick) {
      this._boundOnRowClick = (ev) => {
        const row = ev.target?.closest?.('tr.flow-row');
        if (!row) return;

        const encoded = row.getAttribute('data-flow');
        if (!encoded) return;

        try {
          const flow = JSON.parse(decodeURIComponent(encoded));
          const pre = this.shadowRoot.getElementById('detailsPre');
          if (pre) {
            pre.textContent = JSON.stringify(flow, null, 2);
          }
          if (dialog && typeof dialog.showModal === 'function') {
            dialog.showModal();
          }
        } catch (error) {
          logger.warn('Failed to open flow details dialog:', error);
        }
      };
    }
    if (!this._boundOnDialogClose) {
      this._boundOnDialogClose = () => {
        try {
          if (dialog && dialog.open) {
            dialog.close();
          }
        } catch (error) {
          logger.warn('Failed to close dialog:', error);
        }
      };
    }

    if (applyBtn) {
      applyBtn.addEventListener('click', this._boundOnFilterApply);
    }
    if (resetBtn) {
      resetBtn.addEventListener('click', this._boundOnReset);
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', this._boundOnDialogClose);
    }

    const tbody = this.shadowRoot.querySelector('tbody');
    if (tbody) {
      tbody.addEventListener('click', this._boundOnRowClick);
    }
  }

  static getCardInfo() {
    return {
      type: 'ramses-traffic-analyser',
      name: 'Ramses Traffic Analyser',
      description: 'Spreadsheet-like comms matrix for ramses_cc traffic',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }
}

RamsesTrafficAnalyserCard.register();
