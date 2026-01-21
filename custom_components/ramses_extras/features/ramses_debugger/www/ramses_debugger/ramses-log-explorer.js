/* global navigator */
/* global setTimeout */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocket } from '../../helpers/card-services.js';

import { logExplorerCardStyle } from './card-styles.js';

class RamsesLogExplorerCard extends RamsesBaseCard {
  constructor() {
    super();

    this._files = [];
    this._basePath = null;
    this._selectedFileId = null;

    this._tailText = '';
    this._searchResult = null;
    this._searchQuery = '';
    this._autoLoaded = false;

    this._wrap = true;
    this._loading = false;
    this._lastError = null;
    this._before = null;
    this._after = null;
    this._tailLines = null;
    this._tailOffset = 0;
  }

  _escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  _escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  _deviceSlug(deviceId) {
    const s = String(deviceId || '');
    const parts = s.split(':');
    if (parts.length !== 2) {
      return s;
    }
    return parts[1];
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

    const hue = (typeInt * 137) % 360;

    const satMin = 15;
    const satMax = 85;
    const saturation = satMin + ((slugVar % 256) / 255) * (satMax - satMin);

    const lightMin = 20;
    const lightMax = 75;
    const lightness = lightMin + ((slugVar % 256) / 255) * (lightMax - lightMin);

    const alphaMin = 0.35;
    const alphaMax = 0.85;
    const alpha = alphaMin + ((slugVar % 256) / 255) * (alphaMax - alphaMin);

    return `hsla(${hue}, ${saturation}%, ${lightness}%, ${alpha})`;
  }

  _renderHighlightedLog(text, query) {
    const lines = String(text || '').split('\n');
    const q = String(query || '').trim();

    let re = null;
    if (q) {
      try {
        const terms = q
          .split(/\r?\n/)
          .map((t) => String(t).trim())
          .filter(Boolean);
        const pattern = terms.length > 1
          ? terms.map((t) => this._escapeRegExp(t)).join('|')
          : this._escapeRegExp(q);
        re = new RegExp(pattern, 'gi');
      } catch {
        re = null;
      }
    }

    return lines
      .map((line) => {
        let html = this._escapeHtml(line);
        if (re) {
          html = html.replace(re, (m) => `<span class="hl-match">${this._escapeHtml(m)}</span>`);
        }

        html = html.replace(/\[[a-z0-9_.:-]+\]/i, (m) => `<span class="hl-source">${m}</span>`);
        html = html.replace(/\b\d{2}:\d{6}\b/g, (m) => {
          const bg = this._deviceBg(m);
          return `<span class="hl-id" style="--dev-bg: ${bg};">${m}</span>`;
        });

        const level = String(line).match(/\b(error|warning|critical)\b/i);
        const lvl = typeof level?.[1] === 'string' ? level[1].toUpperCase() : '';
        if (lvl === 'ERROR' || lvl === 'CRITICAL') {
          return `<span class="hl-line hl-error">${html}</span>`;
        }
        if (lvl === 'WARNING') {
          return `<span class="hl-line hl-warning">${html}</span>`;
        }
        return html;
      })
      .join('\n');
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
    void this._refreshFilesAndTail().then(() => {
      if (this._config?.auto_search === true && this._searchQuery) {
        void this._runSearch();
      }
    });
  }

  getCardSize() {
    return 12;
  }

  static getTagName() {
    return 'ramses-log-explorer';
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

  setConfig(config) {
    super.setConfig(config);

    const prefill = this._config?.prefill_query;
    if (typeof prefill === 'string') {
      this._searchQuery = prefill;
    }

    if (Number.isFinite(this._config?.before)) {
      this._before = Number(this._config?.before);
    }
    if (Number.isFinite(this._config?.after)) {
      this._after = Number(this._config?.after);
    }
  }

  _onConnected() {
    void this._refreshFilesAndTail();

    if (this._config?.auto_search === true && this._searchQuery) {
      setTimeout(() => {
        void this._runSearch();
      }, 0);
    }
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
      const maxLines = Number.isFinite(this._tailLines)
        ? this._tailLines
        : Number(this._config?.max_tail_lines || 200);
      const res = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/get_tail',
        file_id: this._selectedFileId,
        max_lines: maxLines,
        offset_lines: this._tailOffset,
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
    let query = qEl && typeof qEl.value === 'string' ? qEl.value.trim() : '';
    if (!query && this._searchQuery) {
      query = String(this._searchQuery).trim();
    }
    this._searchQuery = query;
    if (!query) {
      this._searchResult = null;
      this.render();
      return;
    }

    this._loading = true;
    this._lastError = null;
    this.render();

    try {
      const before = Number.isFinite(this._before) ? this._before : Number(this._config?.before || 3);
      const after = Number.isFinite(this._after) ? this._after : Number(this._config?.after || 3);
      const res = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/search',
        file_id: this._selectedFileId,
        query,
        before,
        after,
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

  _openDialog(title, text, { html = false } = {}) {
    const dialog = this.shadowRoot?.getElementById('zoomDialog');
    const dialogTitle = this.shadowRoot?.getElementById('zoomTitle');
    const pre = this.shadowRoot?.getElementById('zoomPre');
    if (!dialog || !pre || !dialogTitle) {
      return;
    }

    dialogTitle.textContent = title;
    if (html) {
      pre.innerHTML = text || '';
    } else {
      pre.textContent = text || '';
    }

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
    bind('tailUp', 'click', () => {
      this._tailOffset = Math.min(100_000, this._tailOffset + 50);
      void this._refreshTail().then(() => this.render());
    });
    bind('tailDown', 'click', () => {
      this._tailOffset = Math.max(0, this._tailOffset - 50);
      void this._refreshTail().then(() => this.render());
    });
    bind('runSearch', 'click', () => {
      void this._runSearch();
    });

    bind('searchQuery', 'input', (ev) => {
      const val = ev?.target?.value;
      this._searchQuery = typeof val === 'string' ? val : '';
    });
    bind('beforeInput', 'input', (ev) => {
      const val = Number(ev?.target?.value);
      this._before = Number.isFinite(val) ? val : null;
    });
    bind('afterInput', 'input', (ev) => {
      const val = Number(ev?.target?.value);
      this._after = Number.isFinite(val) ? val : null;
    });
    bind('wrapToggle', 'change', (ev) => {
      this._wrap = Boolean(ev?.target?.checked);
      this.render();
    });

    bind('fileSelect', 'change', (ev) => {
      const val = ev?.target?.value;
      this._selectedFileId = typeof val === 'string' && val ? val : null;
      this._tailOffset = 0;
      void this._refreshTail().then(() => this.render());
    });

    bind('copyPlain', 'click', () => {
      void this._copyToClipboard(this._searchResult?.plain || '');
    });
    bind('copyMarkdown', 'click', () => {
      void this._copyToClipboard(this._searchResult?.markdown || '');
    });
    bind('zoomTail', 'click', () => {
      this._openDialog('Tail', this._renderHighlightedLog(this._tailText, this._searchQuery), { html: true });
    });
    bind('zoomResult', 'click', () => {
      this._openDialog('Search result', this._renderHighlightedLog(this._searchResult?.plain || '', this._searchQuery), { html: true });
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

    const beforeVal = Number.isFinite(this._before)
      ? this._before
      : Number(this._config?.before || 3);
    const afterVal = Number.isFinite(this._after)
      ? this._after
      : Number(this._config?.after || 3);

    const tailHtml = this._renderHighlightedLog(this._tailText, this._searchQuery);
    const resultHtml = this._renderHighlightedLog(resultPlain, this._searchQuery);
    const tailLines = Number.isFinite(this._tailLines)
      ? this._tailLines
      : Number(this._config?.max_tail_lines || 200);
    const tailOffset = this._tailOffset || 0;
    const tailWindowLabel = tailOffset
      ? `EOF-${tailLines + tailOffset} … EOF-${tailOffset}`
      : `EOF-${tailLines} … EOF`;

    this.shadowRoot.innerHTML = `
      <style>
        ${logExplorerCardStyle({ wrapCss })}
      </style>
      <ha-card header="${title}">
        <div style="padding: 16px;">
          <div class="row">
            <label>${this.t('card.log.files') || 'files'}:</label>
            <select id="fileSelect" title="Select which log file to view">${fileOptions}</select>
            <button id="refreshFiles" title="Reload the list of available log files">
              ${this.t('card.log.actions.refresh') || 'Refresh files'}
            </button>
            <button id="refreshTail" title="Fetch the latest tail from the selected file">
              ${this.t('card.log.actions.tail') || 'Tail'}
            </button>
            <button id="zoomTail" title="Open the tail in a large, resizable popup">
              ${this.t('card.log.actions.zoom') || 'Zoom'}
            </button>
            <label style="display:flex; gap:6px; align-items:center;">
              <input
                id="wrapToggle"
                type="checkbox"
                title="Toggle line wrapping in the output"
                ${this._wrap ? 'checked' : ''}
              />
              ${this.t('card.log.actions.wrap') || 'Wrap'}
            </label>
          </div>
          <div class="muted" style="margin-top: 6px;">
            ${this._basePath ? `${this.t('card.log.base') || 'base'}: ${this._basePath}` : ''}
          </div>

          ${this._loading ? `<div class="muted" style="margin-top: 8px;">${this.t('card.log.loading') || 'Loading...'}</div>` : ''}
          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <div class="section" style="margin-top: 12px;">
            <div class="muted" style="display:flex; align-items:center; justify-content: space-between; gap: 12px;">
              <span>${this.t('card.log.tail.title') || 'tail'} (${tailWindowLabel})</span>
              <span style="display:flex; gap: 6px;">
                <button id="tailUp" title="Move window 50 lines earlier">+50 lines up</button>
                <button id="tailDown" title="Move window 50 lines later">-50 lines down</button>
              </span>
            </div>
            <pre>${tailHtml || ''}</pre>
          </div>

          <div class="separator"></div>

          <div class="muted" style="margin-top: 6px;">
            Search scans the full file; the tail is shown separately.
          </div>

          <div class="row" style="margin-top: 12px;">
            <label>${this.t('card.log.search.query') || 'query'}:</label>
            <input
              id="searchQuery"
              type="text"
              placeholder="ERROR"
              value="${this._searchQuery || ''}"
              title="Search query (case-insensitive by default)"
            />
            <label>${this.t('card.log.search.before') || 'before'}:</label>
            <input
              id="beforeInput"
              class="small"
              type="number"
              value="${beforeVal}"
              title="Context lines before each match"
            />
            <label>${this.t('card.log.search.after') || 'after'}:</label>
            <input
              id="afterInput"
              class="small"
              type="number"
              value="${afterVal}"
              title="Context lines after each match"
            />
            <button id="runSearch" title="Run search on the selected file">
              ${this.t('card.log.actions.search') || 'Search'}
            </button>
            <button id="zoomResult" title="Open search results in a large, resizable popup">
              ${this.t('card.log.actions.zoom') || 'Zoom'}
            </button>
            <button id="copyPlain" title="Copy the plain-text search results to clipboard">
              ${this.t('card.log.actions.copy_plain') || 'Copy plain'}
            </button>
            <button id="copyMarkdown" title="Copy the markdown-formatted search results to clipboard">
              ${this.t('card.log.actions.copy_markdown') || 'Copy markdown'}
            </button>
          </div>

          <div class="section" style="margin-top: 10px;">
            <div class="muted">
              ${this.t('card.log.search.title') || 'search'}
              ${typeof matches === 'number' ? ` • ${matches} ${this.t('card.log.search.matches') || 'matches'}` : ''}
              ${truncated ? ` • ${this.t('card.log.search.truncated') || 'truncated'}` : ''}
            </div>
            <pre>${resultHtml || ''}</pre>
          </div>

          <dialog id="zoomDialog">
            <form method="dialog">
              <h3 id="zoomTitle"></h3>
              <pre id="zoomPre"></pre>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button id="closeDialog" title="Close this dialog">${this.t('card.actions.close') || 'Close'}</button>
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
      description:
        'Filter and extract context from the HA log file. Best viewed in full-width or 2+ column layouts.',
      preview: true,
      documentationURL: 'https://github.com/wimpie70/ramses_extras',
    };
  }
}

RamsesLogExplorerCard.register();
