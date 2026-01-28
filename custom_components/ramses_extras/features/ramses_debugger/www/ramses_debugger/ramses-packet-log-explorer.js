/**
 * Ramses Packet Log Explorer card.
 *
 * This card explores ramses_cc packet logs (ramses_log) via debugger WebSocket
 * endpoints. It is primarily for browsing / debugging and does not poll by
 * default.
 *
 * Performance:
 * - Uses `callWebSocketShared()` so multiple explorers can share in-flight
 *   requests and short-lived cached results.
 */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocketShared } from '../../helpers/card-services.js';

import './ramses-messages-viewer.js';

class RamsesPacketLogExplorerCard extends RamsesBaseCard {
  constructor() {
    super();

    this._files = [];
    this._basePath = null;
    this._selectedFileId = null;

    this._limit = 200;

    this._loadMode = 'manual';
    this._autoLoadedFileId = null;

    this._loading = false;
    this._lastError = null;
    this._autoLoaded = false;
    this._domInitialized = false;
  }

  set hass(hass) {
    super.hass = hass;

    if (this._autoLoaded) {
      return;
    }
    if (!this._hass || !this._config) {
      return;
    }

    this._autoLoaded = true;
    void this._refreshFiles();
  }

  getCardSize() {
    return 12;
  }

  static getTagName() {
    return 'ramses-packet-log-explorer';
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

  getDefaultConfig() {
    return {
      name: 'Ramses Packet Log Explorer',
    };
  }

  getFeatureName() {
    return 'ramses_debugger';
  }

  _onConnected() {
    void this._refreshFiles();
  }

  async _refreshFiles() {
    if (!this._hass) {
      return;
    }

    // File listing is cached briefly to reduce duplicated requests when
    // multiple instances are present.

    this._loading = true;
    this._lastError = null;
    this.render();

    try {
      const res = await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/packet_log/list_files',
      }, { cacheMs: 1000 });

      this._basePath = typeof res?.base === 'string' ? res.base : null;
      this._files = Array.isArray(res?.files) ? res.files : [];

      const available = new Set(this._files.map((f) => f?.file_id).filter(Boolean));
      if (!this._selectedFileId || !available.has(this._selectedFileId)) {
        this._selectedFileId = this._files?.[0]?.file_id || null;
      }
    } catch (error) {
      this._lastError = error;
    } finally {
      this._loading = false;
      this.render();
    }
  }

  _attachEventListeners() {
    if (!this.shadowRoot) {
      return;
    }

    const bind = (id, event, fn) => {
      const el = this.shadowRoot.getElementById(id);
      if (!el) {
        return;
      }
      el.addEventListener(event, fn);
    };

    bind('r-xtrs-pack-log-refreshFiles', 'click', () => {
      void this._refreshFiles();
    });

    bind('r-xtrs-pack-log-fileSelect', 'change', (ev) => {
      const val = ev?.target?.value;
      this._selectedFileId = typeof val === 'string' && val ? val : null;
      this._autoLoadedFileId = null;
      this.render();

      if (this._loadMode === 'auto') {
        const viewer = this.shadowRoot.getElementById('r-xtrs-pack-log-messagesViewer');
        if (viewer && typeof viewer.refresh === 'function') {
          void viewer.refresh();
        }
      }
    });

    bind('r-xtrs-pack-log-loadMessages', 'click', () => {
      const viewer = this.shadowRoot.getElementById('r-xtrs-pack-log-messagesViewer');
      if (viewer && typeof viewer.refresh === 'function') {
        void viewer.refresh();
      }
    });

    bind('r-xtrs-pack-log-loadMode', 'change', (ev) => {
      const val = ev?.target?.value;
      this._loadMode = typeof val === 'string' && val ? val : 'manual';
      this._autoLoadedFileId = null;
      this.render();

      if (this._loadMode === 'auto') {
        const viewer = this.shadowRoot.getElementById('r-xtrs-pack-log-messagesViewer');
        if (viewer && typeof viewer.refresh === 'function') {
          void viewer.refresh();
        }
      }
    });

    bind('r-xtrs-pack-log-limitFilter', 'change', (ev) => {
      const val = Number(ev?.target?.value || 200);
      this._limit = Number.isFinite(val) ? val : 200;
      const viewer = this.shadowRoot.getElementById('r-xtrs-pack-log-messagesViewer');
      if (viewer && typeof viewer.setConfig === 'function') {
        viewer.setConfig({ limit: this._limit });
      }
      if (this._loadMode === 'auto') {
        if (viewer && typeof viewer.refresh === 'function') {
          void viewer.refresh();
        }
      }
    });
  }

  _renderContent() {
    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }
    this._updateDOM();
  }

  _initializeDOM() {
    const title = this._config?.name || 'Ramses Packet Log Explorer';

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; width: 100%; min-width: 0; max-width: 100%; height: 700px; }
        ha-card {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .r-xtrs-pack-log-card-content {
          flex: 1;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          padding: 16px;
        }

        .r-xtrs-pack-log-messages-container {
          flex: 1;
          // overflow: auto;
          min-height: 0;
        }

        .r-xtrs-pack-log-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .r-xtrs-pack-log-row input[type="text"], .r-xtrs-pack-log-row input[type="number"] { min-width: 120px; }
        .r-xtrs-pack-log-row input.small { width: 70px; }
        .r-xtrs-pack-log-row select { min-width: 260px; flex: 1; }

        .r-xtrs-pack-log-muted { font-size: var(--ha-font-size-s); opacity: 0.8; }
        .r-xtrs-pack-log-error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

        button { cursor: pointer; }
      </style>

      <ha-card header="${title}">
        <div class="r-xtrs-pack-log-card-content">
          <div class="r-xtrs-pack-log-row">
            <label>files:</label>
            <select id="r-xtrs-pack-log-fileSelect" title="Select which packet log file to view"></select>
            <button id="r-xtrs-pack-log-refreshFiles" title="Reload the list of available packet log files">Refresh</button>
            <label>mode:</label>
            <select id="r-xtrs-pack-log-loadMode" title="Auto-load refreshes when the file changes">
              <option value="manual">manual</option>
              <option value="auto">auto</option>
            </select>
            <button id="r-xtrs-pack-log-loadMessages" title="Load messages from selected file" style="display: none;">Load</button>
          </div>

          <div id="r-xtrs-pack-log-basePath" class="r-xtrs-pack-log-muted" style="margin-top: 6px;"></div>

          <div class="r-xtrs-pack-log-row" style="margin-top: 12px;">
            <label>limit:</label>
            <input id="r-xtrs-pack-log-limitFilter" class="small" type="number" value="200" />
          </div>

          <div id="r-xtrs-pack-log-loadingMsg" class="r-xtrs-pack-log-muted" style="margin-top: 8px; display: none;">Loading...</div>
          <div id="r-xtrs-pack-log-errorMsg" class="r-xtrs-pack-log-error" style="display: none;"></div>

          <div class="r-xtrs-pack-log-messages-container">
            <ramses-messages-viewer id="r-xtrs-pack-log-messagesViewer"></ramses-messages-viewer>
          </div>
        </div>
      </ha-card>
    `;

    // Initialize the messages viewer
    const viewer = this.shadowRoot.getElementById('r-xtrs-pack-log-messagesViewer');
    if (viewer) {
      viewer.fetchMessages = ({ hass, decode, limit }) => {
        if (!this._selectedFileId) {
          return { messages: [] };
        }
        return callWebSocketShared(hass, {
          type: 'ramses_extras/ramses_debugger/packet_log/get_messages',
          file_id: this._selectedFileId,
          limit: Number(limit || this._limit || 200),
          decode: Boolean(decode),
        }, { cacheMs: 500 });
      };

      try {
        viewer.setConfig({
          pair_mode: 'derived',
          limit: Number(this._limit || 200),
          sort_key: 'dtm',
          sort_dir: 'desc',
        });
        if (this._hass) {
          viewer.hass = this._hass;
        }
      } catch (error) {
        logger.warn('Failed to init embedded messages viewer:', error);
      }

      if (this._loadMode === 'auto'
        && this._selectedFileId
        && this._selectedFileId !== this._autoLoadedFileId) {
        this._autoLoadedFileId = this._selectedFileId;
        void viewer.refresh();
      }
    }

    this._attachEventListeners();
  }

  _updateDOM() {
    // Update file select options
    const fileSelect = this.shadowRoot.getElementById('r-xtrs-pack-log-fileSelect');
    if (fileSelect) {
      const files = Array.isArray(this._files) ? this._files : [];
      fileSelect.innerHTML = files
        .map((f) => {
          const id = f?.file_id || '';
          const selected = id && id === this._selectedFileId ? 'selected' : '';
          const size = typeof f?.size === 'number' ? ` (${f.size})` : '';
          return `<option value="${id}" ${selected}>${id}${size}</option>`;
        })
        .join('');
    }

    // Update mode select
    const modeSelect = this.shadowRoot.getElementById('r-xtrs-pack-log-loadMode');
    if (modeSelect) {
      modeSelect.value = String(this._loadMode || 'manual');
    }

    // Update Load button visibility
    const loadBtn = this.shadowRoot.getElementById('r-xtrs-pack-log-loadMessages');
    if (loadBtn) {
      loadBtn.style.display = this._loadMode === 'manual' ? '' : 'none';
    }

    // Update base path
    const basePathDiv = this.shadowRoot.getElementById('r-xtrs-pack-log-basePath');
    if (basePathDiv) {
      basePathDiv.textContent = this._basePath ? `base: ${this._basePath}` : '';
    }

    // Update limit input
    const limitInput = this.shadowRoot.getElementById('r-xtrs-pack-log-limitFilter');
    if (limitInput && limitInput.value !== String(this._limit)) {
      limitInput.value = String(this._limit || 200);
    }

    // Update loading message
    const loadingMsg = this.shadowRoot.getElementById('r-xtrs-pack-log-loadingMsg');
    if (loadingMsg) {
      loadingMsg.style.display = this._loading ? '' : 'none';
    }

    // Update error message
    const errorMsg = this.shadowRoot.getElementById('r-xtrs-pack-log-errorMsg');
    if (errorMsg) {
      if (this._lastError) {
        errorMsg.textContent = String(this._lastError?.message || this._lastError);
        errorMsg.style.display = '';
      } else {
        errorMsg.style.display = 'none';
      }
    }
  }

  static getCardInfo() {
    return {
      type: 'ramses-packet-log-explorer',
      name: 'Ramses Packet Log Explorer',
      description:
        'Explore packet log files (ramses_log) with basic filters and message details. Best viewed in full-width layouts.',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }
}

RamsesPacketLogExplorerCard.register();
