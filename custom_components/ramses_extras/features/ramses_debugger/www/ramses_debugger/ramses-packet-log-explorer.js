import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocket } from '../../helpers/card-services.js';

class RamsesPacketLogExplorerCard extends RamsesBaseCard {
  constructor() {
    super();

    this._files = [];
    this._basePath = null;
    this._selectedFileId = null;

    this._src = '';
    this._dst = '';
    this._verb = '';
    this._code = '';
    this._since = '';
    this._until = '';
    this._limit = 200;

    this._messages = [];
    this._wrap = false;

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

    this._loading = true;
    this._lastError = null;
    this.render();

    try {
      const res = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/packet_log/list_files',
      });

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

  async _loadMessages() {
    if (!this._hass || !this.shadowRoot || !this._selectedFileId) {
      return;
    }

    const getVal = (id) => {
      const el = this.shadowRoot.getElementById(id);
      return el && typeof el.value === 'string' ? el.value.trim() : '';
    };

    const payload = {
      type: 'ramses_extras/ramses_debugger/packet_log/get_messages',
      file_id: this._selectedFileId,
      src: getVal('srcFilter') || undefined,
      dst: getVal('dstFilter') || undefined,
      verb: getVal('verbFilter') || undefined,
      code: getVal('codeFilter') || undefined,
      since: getVal('sinceFilter') || undefined,
      until: getVal('untilFilter') || undefined,
      limit: Number(getVal('limitFilter') || 200),
    };

    this._loading = true;
    this._lastError = null;
    this.render();

    try {
      const res = await callWebSocket(this._hass, payload);
      const messages = Array.isArray(res?.messages) ? res.messages : [];
      this._messages = messages;
    } catch (error) {
      this._lastError = error;
      this._messages = [];
    } finally {
      this._loading = false;
      this.render();
    }
  }

  _openDetailsDialog(msg) {
    const dialog = this.shadowRoot?.getElementById('detailsDialog');
    const pre = this.shadowRoot?.getElementById('detailsPre');
    if (!dialog || !pre) {
      return;
    }

    const lines = [];
    lines.push(`dtm: ${msg?.dtm || ''}`);
    lines.push(`src: ${msg?.src || ''}`);
    lines.push(`dst: ${msg?.dst || ''}`);
    lines.push(`verb: ${msg?.verb || ''}`);
    lines.push(`code: ${msg?.code || ''}`);
    lines.push(`payload: ${msg?.payload || ''}`);
    lines.push(`packet: ${msg?.packet || ''}`);
    lines.push(`raw_line: ${msg?.raw_line || ''}`);
    if (Array.isArray(msg?.parse_warnings) && msg.parse_warnings.length) {
      lines.push(`parse_warnings: ${msg.parse_warnings.join(', ')}`);
    }

    pre.textContent = lines.join('\n');

    try {
      if (typeof dialog.showModal === 'function') {
        dialog.showModal();
      }
    } catch (error) {
      logger.warn('Failed to open dialog:', error);
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
      this.render();
    });

    bind('loadMessages', 'click', () => {
      void this._loadMessages();
    });

    bind('wrapToggle', 'change', (ev) => {
      this._wrap = Boolean(ev?.target?.checked);
      this.render();
    });

    bind('closeDetails', 'click', () => {
      const dialog = this.shadowRoot?.getElementById('detailsDialog');
      if (dialog?.open) {
        dialog.close();
      }
    });

    this.shadowRoot.querySelectorAll('[data-action="details"]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        const idx = Number(ev?.currentTarget?.getAttribute('data-idx'));
        const msg = this._messages?.[idx];
        if (msg) {
          this._openDetailsDialog(msg);
        }
      });
    });
  }

  _renderContent() {
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

    const wrapCss = this._wrap ? 'pre-wrap' : 'pre';
    const msgRows = (Array.isArray(this._messages) ? this._messages : [])
      .map((msg, idx) => {
        const src = msg?.src || '';
        const dst = msg?.dst || '';
        const isBroadcast = dst && String(dst).includes('--:------');
        const payload = msg?.payload || '';

        return `
          <tr>
            <td class="col-time">${msg?.dtm || ''}</td>
            <td class="col-verb">${msg?.verb || ''}</td>
            <td class="col-code">${msg?.code || ''}</td>
            <td class="col-src">${src}</td>
            <td class="col-dst">${dst}</td>
            <td class="col-bcast">${isBroadcast ? 'Y' : ''}</td>
            <td class="col-payload" style="white-space:${wrapCss};">${payload}</td>
            <td class="col-actions"><button data-action="details" data-idx="${idx}">Details</button></td>
          </tr>
        `;
      })
      .join('');

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; width: 100%; min-width: 1200px; max-width: none; }
        ha-card { width: 100%; }

        .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .row input[type="text"], .row input[type="number"] { min-width: 120px; }
        .row input.small { width: 70px; }
        .row select { min-width: 260px; flex: 1; }

        .muted { font-size: 12px; opacity: 0.8; }
        .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

        .table-wrap { width: 100%; max-height: 520px; overflow: auto; margin-top: 12px; border: 1px solid var(--divider-color); border-radius: 6px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 4px 6px; border: 1px solid var(--divider-color); vertical-align: top; }
        th { background: var(--secondary-background-color); position: sticky; top: 0; z-index: 1; text-align: left; }
        td { font-family: monospace; font-size: 12px; }

        .col-time { width: 160px; font-size: 11px; }
        .col-verb { width: 40px; text-align: center; }
        .col-code { width: 60px; text-align: center; }
        .col-src { width: 110px; }
        .col-dst { width: 110px; }
        .col-bcast { width: 60px; text-align: center; }
        .col-actions { width: 90px; white-space: nowrap; }
        .col-payload { min-width: 400px; overflow-x: auto; }

        dialog { width: 98vw; max-width: 98vw; height: 90vh; max-height: 90vh; resize: both; overflow: auto; }
        dialog pre { white-space: pre-wrap; word-break: break-word; overflow: auto; max-height: 70vh; }
        button { cursor: pointer; }
      </style>

      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div class="row">
            <label>files:</label>
            <select id="fileSelect" title="Select which packet log file to view">${fileOptions}</select>
            <button id="refreshFiles" title="Reload the list of available packet log files">Refresh</button>
            <button id="loadMessages" title="Load messages from selected file">Load</button>
            <label style="display:flex; gap:6px; align-items:center;">
              <input id="wrapToggle" type="checkbox" ${this._wrap ? 'checked' : ''} />
              Wrap
            </label>
          </div>

          <div class="muted" style="margin-top: 6px;">
            ${this._basePath ? `base: ${this._basePath}` : ''}
          </div>

          <div class="row" style="margin-top: 12px;">
            <label>src:</label>
            <input id="srcFilter" type="text" value="${this._src}" placeholder="32:123456" />
            <label>dst:</label>
            <input id="dstFilter" type="text" value="${this._dst}" placeholder="37:654321" />
            <label>verb:</label>
            <input id="verbFilter" class="small" type="text" value="${this._verb}" placeholder="RQ" />
            <label>code:</label>
            <input id="codeFilter" class="small" type="text" value="${this._code}" placeholder="31DA" />
            <label>since:</label>
            <input id="sinceFilter" type="text" value="${this._since}" placeholder="2026-01-20T09:00:00" />
            <label>until:</label>
            <input id="untilFilter" type="text" value="${this._until}" placeholder="2026-01-20T11:00:00" />
            <label>limit:</label>
            <input id="limitFilter" class="small" type="number" value="${Number(this._limit || 200)}" />
          </div>

          ${this._loading ? `<div class="muted" style="margin-top: 8px;">Loading...</div>` : ''}
          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <div class="muted" style="margin-top: 6px;">Messages: ${Array.isArray(this._messages) ? this._messages.length : 0}</div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="col-time">Time</th>
                  <th class="col-verb">Verb</th>
                  <th class="col-code">Code</th>
                  <th class="col-src">Src</th>
                  <th class="col-dst">Dst</th>
                  <th class="col-bcast">Broadcast</th>
                  <th class="col-payload">Payload</th>
                  <th class="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                ${msgRows}
              </tbody>
            </table>
          </div>

          <dialog id="detailsDialog">
            <form method="dialog">
              <h3>Message details</h3>
              <pre id="detailsPre"></pre>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeDetails">Close</button>
              </div>
            </form>
          </dialog>
        </div>
      </ha-card>
    `;

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
