/* global navigator */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocket } from '../../helpers/card-services.js';

class RamsesLogExplorerCard extends RamsesBaseCard {
  constructor() {
    super();

    this._files = [];
    this._basePath = null;
    this._selectedFileId = null;

    this._tailText = '';
    this._searchResult = null;

    this._wrap = true;
    this._loading = false;
    this._lastError = null;
  }

  getCardSize() {
    return 4;
  }

  static getTagName() {
    return 'ramses-log-explorer';
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
      name: 'Ramses Log Explorer',
      max_tail_lines: 200,
      max_tail_chars: 200000,
      before: 3,
      after: 3,
      max_matches: 200,
      max_chars: 400000,
      case_sensitive: false,
    };
  }

  getFeatureName() {
    return 'ramses_debugger';
  }

  _onConnected() {
    void this._refreshFilesAndTail();
  }

  async _refreshFilesAndTail() {
    if (!this._hass) {
      return;
    }

    this._loading = true;
    this._lastError = null;
    this.render();

    try {
      const res = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/list_files',
      });

      this._basePath = typeof res?.base === 'string' ? res.base : null;
      this._files = Array.isArray(res?.files) ? res.files : [];

      const available = new Set(this._files.map((f) => f?.file_id).filter(Boolean));
      if (!this._selectedFileId || !available.has(this._selectedFileId)) {
        this._selectedFileId = this._files?.[0]?.file_id || null;
      }

      await this._refreshTail();
    } catch (error) {
      this._lastError = error;
    } finally {
      this._loading = false;
      this.render();
    }
  }

  async _refreshTail() {
    if (!this._hass || !this._selectedFileId) {
      return;
    }

    try {
      const res = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/get_tail',
        file_id: this._selectedFileId,
        max_lines: Number(this._config?.max_tail_lines || 200),
        max_chars: Number(this._config?.max_tail_chars || 200000),
      });

      this._tailText = typeof res?.text === 'string' ? res.text : '';
    } catch (error) {
      this._lastError = error;
    }
  }

  async _runSearch() {
    if (!this._hass || !this._selectedFileId || !this.shadowRoot) {
      return;
    }

    const qEl = this.shadowRoot.getElementById('searchQuery');
    const query = qEl && typeof qEl.value === 'string' ? qEl.value.trim() : '';
    if (!query) {
      this._searchResult = null;
      this.render();
      return;
    }

    this._loading = true;
    this._lastError = null;
    this.render();

    try {
      const res = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/search',
        file_id: this._selectedFileId,
        query,
        before: Number(this._config?.before || 3),
        after: Number(this._config?.after || 3),
        max_matches: Number(this._config?.max_matches || 200),
        max_chars: Number(this._config?.max_chars || 400000),
        case_sensitive: Boolean(this._config?.case_sensitive),
      });

      this._searchResult = res;
    } catch (error) {
      this._lastError = error;
    } finally {
      this._loading = false;
      this.render();
    }
  }

  async _copyToClipboard(text) {
    try {
      if (!text) {
        return;
      }
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      }
    } catch (error) {
      logger.warn('Copy to clipboard failed:', error);
    }
  }

  _openDialog(title, text) {
    const dialog = this.shadowRoot?.getElementById('zoomDialog');
    const dialogTitle = this.shadowRoot?.getElementById('zoomTitle');
    const pre = this.shadowRoot?.getElementById('zoomPre');
    if (!dialog || !pre || !dialogTitle) {
      return;
    }

    dialogTitle.textContent = title;
    pre.textContent = text || '';

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
      void this._refreshFilesAndTail();
    });
    bind('refreshTail', 'click', () => {
      void this._refreshTail().then(() => this.render());
    });
    bind('runSearch', 'click', () => {
      void this._runSearch();
    });
    bind('wrapToggle', 'change', (ev) => {
      this._wrap = Boolean(ev?.target?.checked);
      this.render();
    });

    bind('fileSelect', 'change', (ev) => {
      const val = ev?.target?.value;
      this._selectedFileId = typeof val === 'string' && val ? val : null;
      void this._refreshTail().then(() => this.render());
    });

    bind('copyPlain', 'click', () => {
      void this._copyToClipboard(this._searchResult?.plain || '');
    });
    bind('copyMarkdown', 'click', () => {
      void this._copyToClipboard(this._searchResult?.markdown || '');
    });
    bind('zoomTail', 'click', () => {
      this._openDialog('Tail', this._tailText);
    });
    bind('zoomResult', 'click', () => {
      this._openDialog('Search result', this._searchResult?.plain || '');
    });
    bind('closeDialog', 'click', () => {
      const dialog = this.shadowRoot?.getElementById('zoomDialog');
      if (dialog?.open) {
        dialog.close();
      }
    });
  }

  _renderContent() {
    const title = this._config?.name || 'Ramses Log Explorer';
    const files = Array.isArray(this._files) ? this._files : [];

    const fileOptions = files
      .map((f) => {
        const id = f?.file_id || '';
        const selected = id && id === this._selectedFileId ? 'selected' : '';
        const size = typeof f?.size === 'number' ? ` (${f.size})` : '';
        return `<option value="${id}" ${selected}>${id}${size}</option>`;
      })
      .join('');

    const errorText = this._lastError
      ? String(this._lastError?.message || this._lastError)
      : '';

    const wrapCss = this._wrap ? 'pre-wrap' : 'pre';
    const resultPlain = this._searchResult?.plain || '';
    const matches = this._searchResult?.matches;
    const truncated = Boolean(this._searchResult?.truncated);

    this.shadowRoot.innerHTML = `
      <style>
        .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .row input[type="text"] { min-width: 220px; }
        .row input.small { width: 70px; }
        .row select { min-width: 260px; }
        .muted { font-size: 12px; opacity: 0.8; }
        .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }
        pre { margin: 0; padding: 10px; border: 1px solid var(--divider-color); border-radius: 6px; overflow: auto; white-space: ${wrapCss}; }
        dialog { width: min(1100px, 92vw); }
        dialog pre { max-height: 70vh; }
        button { cursor: pointer; }
      </style>
      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div class="row">
            <label>${this.t('card.log.files') || 'files'}:</label>
            <select id="fileSelect">${fileOptions}</select>
            <button id="refreshFiles">${this.t('card.log.actions.refresh') || 'Refresh'}</button>
            <button id="refreshTail">${this.t('card.log.actions.tail') || 'Tail'}</button>
            <button id="zoomTail">${this.t('card.log.actions.zoom') || 'Zoom'}</button>
            <label style="display:flex; gap:6px; align-items:center;">
              <input id="wrapToggle" type="checkbox" ${this._wrap ? 'checked' : ''} />
              ${this.t('card.log.actions.wrap') || 'Wrap'}
            </label>
          </div>
          <div class="muted" style="margin-top: 6px;">
            ${this._basePath ? `${this.t('card.log.base') || 'base'}: ${this._basePath}` : ''}
          </div>

          <div class="row" style="margin-top: 12px;">
            <label>${this.t('card.log.search.query') || 'query'}:</label>
            <input id="searchQuery" type="text" placeholder="ERROR" />
            <label>${this.t('card.log.search.before') || 'before'}:</label>
            <input class="small" type="number" value="${Number(this._config?.before || 3)}" disabled />
            <label>${this.t('card.log.search.after') || 'after'}:</label>
            <input class="small" type="number" value="${Number(this._config?.after || 3)}" disabled />
            <button id="runSearch">${this.t('card.log.actions.search') || 'Search'}</button>
            <button id="zoomResult">${this.t('card.log.actions.zoom') || 'Zoom'}</button>
            <button id="copyPlain">${this.t('card.log.actions.copy_plain') || 'Copy plain'}</button>
            <button id="copyMarkdown">${this.t('card.log.actions.copy_markdown') || 'Copy markdown'}</button>
          </div>

          ${this._loading ? `<div class="muted" style="margin-top: 8px;">${this.t('card.log.loading') || 'Loading...'}</div>` : ''}
          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <div class="grid">
            <div>
              <div class="muted">${this.t('card.log.tail.title') || 'tail'}</div>
              <pre>${this._tailText || ''}</pre>
            </div>
            <div>
              <div class="muted">
                ${this.t('card.log.search.title') || 'search'}
                ${typeof matches === 'number' ? ` • ${matches} ${this.t('card.log.search.matches') || 'matches'}` : ''}
                ${truncated ? ` • ${this.t('card.log.search.truncated') || 'truncated'}` : ''}
              </div>
              <pre>${resultPlain}</pre>
            </div>
          </div>

          <dialog id="zoomDialog">
            <form method="dialog">
              <h3 id="zoomTitle"></h3>
              <pre id="zoomPre"></pre>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeDialog">${this.t('card.actions.close') || 'Close'}</button>
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
      type: 'ramses-log-explorer',
      name: 'Ramses Log Explorer',
      description: 'Filter and extract context from the HA log file',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }
}

RamsesLogExplorerCard.register();
