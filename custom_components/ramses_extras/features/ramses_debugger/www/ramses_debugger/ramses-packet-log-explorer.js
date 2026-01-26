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

    bind('refreshFiles', 'click', () => {
      void this._refreshFiles();
    });

    bind('fileSelect', 'change', (ev) => {
      const val = ev?.target?.value;
      this._selectedFileId = typeof val === 'string' && val ? val : null;
      this._autoLoadedFileId = null;
      this.render();

      if (this._loadMode === 'auto') {
        const viewer = this.shadowRoot.getElementById('messagesViewer');
        if (viewer && typeof viewer.refresh === 'function') {
          void viewer.refresh();
        }
      }
    });

    bind('loadMessages', 'click', () => {
      const viewer = this.shadowRoot.getElementById('messagesViewer');
      if (viewer && typeof viewer.refresh === 'function') {
        void viewer.refresh();
      }
    });

    bind('loadMode', 'change', (ev) => {
      const val = ev?.target?.value;
      this._loadMode = typeof val === 'string' && val ? val : 'manual';
      this._autoLoadedFileId = null;
      this.render();

      if (this._loadMode === 'auto') {
        const viewer = this.shadowRoot.getElementById('messagesViewer');
        if (viewer && typeof viewer.refresh === 'function') {
          void viewer.refresh();
        }
      }
    });

    bind('limitFilter', 'change', (ev) => {
      const val = Number(ev?.target?.value || 200);
      this._limit = Number.isFinite(val) ? val : 200;
      const viewer = this.shadowRoot.getElementById('messagesViewer');
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
    this._renderContentImpl();
  }

  _renderContentImpl() {
    const title = this._config?.name || 'Ramses Packet Log Explorer';
    const files = Array.isArray(this._files) ? this._files : [];

    const fileOptions = files
      .map((f) => {
        const id = f?.file_id || '';
        const selected = id && id === this._selectedFileId ? 'selected' : '';
        const size = typeof f?.size === 'number' ? ` (${f.size})` : '';
        return `<option value="${id}" ${selected}>${id}${size}</option>`;
      })
      .join('');

    const errorText = this._lastError ? String(this._lastError?.message || this._lastError) : '';
    const mode = String(this._loadMode || 'manual');
    const showLoadBtn = mode === 'manual';

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

        .card-content {
          flex: 1;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          padding: 16px;
        }

        .messages-container {
          flex: 1;
          overflow: auto;
          min-height: 0;
        }

        .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .row input[type="text"], .row input[type="number"] { min-width: 120px; }
        .row input.small { width: 70px; }
        .row select { min-width: 260px; flex: 1; }

        .muted { font-size: var(--ha-font-size-s); opacity: 0.8; }
        .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

        button { cursor: pointer; }
      </style>

      <ha-card header="${title}">
        <div class="card-content">
          <div class="row">
            <label>files:</label>
            <select id="fileSelect" title="Select which packet log file to view">${fileOptions}</select>
            <button id="refreshFiles" title="Reload the list of available packet log files">Refresh</button>
            <label>mode:</label>
            <select id="loadMode" title="Auto-load refreshes when the file changes">
              <option value="manual" ${mode === 'manual' ? 'selected' : ''}>manual</option>
              <option value="auto" ${mode === 'auto' ? 'selected' : ''}>auto</option>
            </select>
            ${showLoadBtn ? '<button id="loadMessages" title="Load messages from selected file">Load</button>' : ''}
          </div>

          <div class="muted" style="margin-top: 6px;">
            ${this._basePath ? `base: ${this._basePath}` : ''}
          </div>

          <div class="row" style="margin-top: 12px;">
            <label>limit:</label>
            <input id="limitFilter" class="small" type="number" value="${Number(this._limit || 200)}" />
          </div>

          ${this._loading ? `<div class="muted" style="margin-top: 8px;">Loading...</div>` : ''}
          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <div class="messages-container">
            <ramses-messages-viewer id="messagesViewer"></ramses-messages-viewer>
          </div>
        </div>
      </ha-card>
    `;

    const viewer = this.shadowRoot.getElementById('messagesViewer');
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
