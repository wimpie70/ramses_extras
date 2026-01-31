/* global setTimeout */

/**
 * Ramses Log Explorer Card - Home Assistant log file browser and search tool.
 *
 * This card provides a comprehensive interface for browsing and searching Home Assistant
 * log files, including rotated log variants. It supports:
 * - File selection from available log files
 * - Tail view with configurable line count and offset
 * - Full-text search with context expansion
 * - Line wrapping toggle
 * - Copy to clipboard functionality
 * - Zoom dialog for detailed viewing
 *
 * The card uses WebSocket commands to communicate with the backend debugger feature,
 * with automatic request de-duplication via callWebSocketShared().
 *
 * @module ramses-log-explorer
 * @extends RamsesBaseCard
 */

import * as logger from '../../helpers/logger.js';
import { RamsesBaseCard } from '../../helpers/ramses-base-card.js';
import { callWebSocketShared } from '../../helpers/card-services.js';
import { copyToClipboard } from '../../helpers/clipboard.js';

import { logExplorerCardStyle } from './card-styles.js';

/**
 * Ramses Log Explorer Card component.
 *
 * Provides UI for browsing Home Assistant log files with search and tail functionality.
 * Supports multiple log files (base + rotated), context expansion, and zoom viewing.
 *
 * @class RamsesLogExplorerCard
 * @extends RamsesBaseCard
 */
class RamsesLogExplorerCard extends RamsesBaseCard {
  constructor() {
    super();

    this._files = [];
    this._basePath = null;
    this._selectedFileId = null;

    this._tailText = '';
    this._tailStartLine = null;
    this._tailEndLine = null;
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
    this._domInitialized = false;

    this._zoomMode = null;
  }

  /**
   * Get human-readable label for current tail window position.
   *
   * Generates a label showing the tail window position relative to end-of-file (EOF).
   * Format: "EOF-200 … EOF" for tail at end, or "EOF-250 … EOF-50" for offset tail.
   *
   * @returns {string} Tail window position label
   * @private
   */
  _getTailWindowLabel() {
    const tailLines = Number.isFinite(this._tailLines)
      ? this._tailLines
      : Number(this._config?.max_tail_lines || 200);
    const tailOffset = this._tailOffset || 0;
    return tailOffset
      ? `EOF-${tailLines + tailOffset} … EOF-${tailOffset}`
      : `EOF-${tailLines} … EOF`;
  }

  /**
   * Configure zoom dialog controls based on current mode.
   *
   * Updates button labels and tooltips to match the current zoom mode:
   * - 'tail' mode: Controls for moving tail window (±50 lines)
   * - 'search' mode: Controls for expanding search context (±10 lines)
   *
   * @param {string} mode - Zoom mode: 'tail' or 'search'
   * @private
   */
  _setZoomControlsForMode(mode) {
    const label = this.shadowRoot?.getElementById('zoomControlsLabel');
    const beforeBtn = this.shadowRoot?.getElementById('zoomBeforeMore');
    const afterBtn = this.shadowRoot?.getElementById('zoomAfterMore');
    if (!beforeBtn || !afterBtn) {
      return;
    }

    if (mode === 'tail') {
      if (label) {
        label.textContent = 'Tail controls';
      }
      beforeBtn.textContent = '+50 lines up';
      beforeBtn.title = 'Move window 50 lines earlier';
      afterBtn.textContent = '-50 lines down';
      afterBtn.title = 'Move window 50 lines later';
      return;
    }

    if (label) {
      label.textContent = 'Zoom controls';
    }
    beforeBtn.textContent = '+10 lines up';
    beforeBtn.title = 'Increase context lines before matches by 10';
    afterBtn.textContent = '-10 lines down';
    afterBtn.title = 'Increase context lines after matches by 10';
  }

  /**
   * Update tail zoom dialog content with current tail data.
   *
   * Refreshes the zoom dialog when in tail mode, updating the title with
   * current window position and re-rendering the tail content with line numbers.
   * Only updates if dialog is open and in tail mode.
   *
   * @private
   */
  _updateTailZoomDialog() {
    const dialog = this.shadowRoot?.getElementById('zoomDialog');
    const dialogTitle = this.shadowRoot?.getElementById('zoomTitle');
    if (!dialog?.open) {
      return;
    }
    if (this._zoomMode !== 'tail') {
      return;
    }
    if (dialogTitle) {
      dialogTitle.textContent = `Tail (${this._getTailWindowLabel()})`;
    }
    const pre = this.shadowRoot?.getElementById('zoomPre');
    if (pre) {
      pre.innerHTML = this._renderTailHtml(this._tailText, this._tailStartLine, this._searchQuery) || '';
      pre.style.display = '';
    }
  }

  /**
   * Open zoom dialog in tail mode.
   *
   * Opens the zoom dialog displaying the current tail content with line numbers.
   * Configures controls for tail mode (±50 line navigation) and sets the dialog
   * title to show current window position.
   *
   * @private
   */
  _openTailDialog() {
    const dialog = this.shadowRoot?.getElementById('zoomDialog');
    const dialogTitle = this.shadowRoot?.getElementById('zoomTitle');
    const pre = this.shadowRoot?.getElementById('zoomPre');
    const zoomResults = this.shadowRoot?.getElementById('zoomResults');
    if (!dialog || !dialogTitle) {
      return;
    }

    this._zoomMode = 'tail';
    this._setZoomControlsForMode('tail');

    dialogTitle.textContent = `Tail (${this._getTailWindowLabel()})`;

    if (pre) {
      pre.innerHTML = this._renderTailHtml(this._tailText, this._tailStartLine, this._searchQuery) || '';
      pre.style.display = '';
    }
    if (zoomResults) {
      zoomResults.innerHTML = '';
      zoomResults.style.display = 'none';
    }

    try {
      if (typeof dialog.showModal === 'function') {
        dialog.showModal();
      }
    } catch (error) {
      logger.warn('Failed to open dialog:', error);
    }
  }

  _renderTailHtml(text, startLine, query) {
    if (startLine !== null && text) {
      const tailLines = String(text).split('\n');
      const tailHtml = tailLines
        .map((line, idx) => {
          const lineNumber = startLine + idx;
          const highlightedLine = this._renderHighlightedLog(line, query);
          return `<div class="r-xtrs-log-xp-line" data-line="${lineNumber}">${highlightedLine}</div>`;
        })
        .join('');
      return `<div class="r-xtrs-log-xp-line-numbers">${tailHtml}</div>`;
    }
    return this._renderHighlightedLog(text, query);
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

    const isLogHeader = (line) => /^\d{4}-\d{2}-\d{2}[ T]/.test(String(line || ''));
    const isTracebackHeader = (line) => String(line || '').startsWith('Traceback (most recent call last):');
    const isBlockingCallWarning = (line) => String(line || '').includes('Detected blocking call');

    const tbFlags = new Array(lines.length).fill(false);
    let tbActive = false;
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      if (isTracebackHeader(line)) {
        tbActive = true;
      } else if (tbActive && isLogHeader(line)) {
        tbActive = false;
      }
      tbFlags[i] = tbActive;
    }
    for (let i = 0; i < lines.length; i += 1) {
      if (isTracebackHeader(lines[i]) && i > 0 && isBlockingCallWarning(lines[i - 1])) {
        tbFlags[i - 1] = true;
      }
    }

    return lines
      .map((line, idx) => {
        let html = this._escapeHtml(line);
        if (re) {
          html = html.replace(re, (m) => `<span class="r-xtrs-log-xp-hl-match">${this._escapeHtml(m)}</span>`);
        }

        html = html.replace(/\[[a-z0-9_.:-]+\]/i, (m) => `<span class="r-xtrs-log-xp-hl-source">${m}</span>`);
        html = html.replace(/\b\d{2}:\d{6}\b/g, (m) => {
          const bg = this._deviceBg(m);
          return `<span class="r-xtrs-log-xp-hl-id" style="--dev-bg: ${bg};">${m}</span>`;
        });

        const classes = [];
        const level = String(line).match(/\b(error|warning|critical)\b/i);
        const lvl = typeof level?.[1] === 'string' ? level[1].toUpperCase() : '';
        if (lvl === 'ERROR' || lvl === 'CRITICAL') {
          classes.push('r-xtrs-log-xp-hl-error');
        } else if (lvl === 'WARNING') {
          classes.push('r-xtrs-log-xp-hl-warning');
        }

        if (tbFlags[idx]) {
          classes.push('r-xtrs-log-xp-hl-traceback');
          if (isTracebackHeader(line)) {
            classes.push('r-xtrs-log-xp-hl-traceback-header');
          }
          if (String(line || '').startsWith('  File ')) {
            classes.push('r-xtrs-log-xp-hl-traceback-file');
          }
        }

        if (classes.length) {
          return `<span class="r-xtrs-log-xp-hl-line ${classes.join(' ')}">${html}</span>`;
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

    // List files then refresh tail. File listing is cached briefly to reduce
    // duplicate network requests when multiple cards load.

    this._loading = true;
    this._lastError = null;

    try {
      const res = await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/list_files',
      }, { cacheMs: 1000 });

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
      const res = await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/get_tail',
        file_id: this._selectedFileId,
        max_lines: maxLines,
        offset_lines: this._tailOffset,
        max_chars: Number(this._config?.max_tail_chars || 200000),
      }, { cacheMs: 500 });

      this._tailText = typeof res?.text === 'string' ? res.text : '';
      this._tailStartLine = typeof res?.start_line === 'number' ? res.start_line : null;
      this._tailEndLine = typeof res?.end_line === 'number' ? res.end_line : null;
    } catch (error) {
      this._lastError = error;
    }
  }

  async _runSearch() {
    if (!this._hass || !this._selectedFileId || !this.shadowRoot) {
      return;
    }

    // Search scans the full file server-side and returns both a combined plain
    // string and structured blocks (for better UI rendering).

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

    try {
      const before = Number.isFinite(this._before) ? this._before : Number(this._config?.before || 3);
      const after = Number.isFinite(this._after) ? this._after : Number(this._config?.after || 3);
      const res = await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/search',
        file_id: this._selectedFileId,
        query,
        before,
        after,
        max_matches: Number(this._config?.max_matches || 200),
        max_chars: Number(this._config?.max_chars || 400000),
        case_sensitive: Boolean(this._config?.case_sensitive),
      }, { cacheMs: 500 });

      this._searchResult = res;
    } catch (error) {
      this._lastError = error;
    } finally {
      this._loading = false;
      this.render();
    }
  }


  _openDialog(title, text, { html = false } = {}) {
    const dialog = this.shadowRoot?.getElementById('zoomDialog');
    const dialogTitle = this.shadowRoot?.getElementById('zoomTitle');
    const pre = this.shadowRoot?.getElementById('zoomPre');
    const zoomResults = this.shadowRoot?.getElementById('zoomResults');
    if (!dialog || !dialogTitle) {
      return;
    }

    this._zoomMode = null;
    this._setZoomControlsForMode(null);

    dialogTitle.textContent = title;

    if (pre) {
      if (html) {
        pre.innerHTML = text || '';
      } else {
        pre.textContent = text || '';
      }
      pre.style.display = '';
    }
    if (zoomResults) {
      zoomResults.innerHTML = '';
      zoomResults.style.display = 'none';
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
    bind('searchWarnings', 'click', () => {
      this._searchQuery = 'WARNING';
      const searchInput = this.shadowRoot?.getElementById('searchQuery');
      if (searchInput) {
        searchInput.value = 'WARNING';
      }
      void this._runSearch();
    });
    bind('searchErrors', 'click', () => {
      this._searchQuery = 'ERROR';
      const searchInput = this.shadowRoot?.getElementById('searchQuery');
      if (searchInput) {
        searchInput.value = 'ERROR';
      }
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
      void copyToClipboard(this._searchResult?.plain || '');
    });
    bind('copyMarkdown', 'click', () => {
      void copyToClipboard(this._searchResult?.markdown || '');
    });
    bind('zoomTail', 'click', () => {
      this._openTailDialog();
    });
    bind('zoomResult', 'click', () => {
      this._openSearchResultDialog();
    });
    bind('zoomBeforeMore', 'click', (ev) => {
      ev?.preventDefault?.();
      if (this._zoomMode === 'tail') {
        this._tailOffset = Math.min(100_000, (this._tailOffset || 0) + 50);
        void this._refreshTail().then(() => {
          this._updateTailZoomDialog();
          this.render();
        });
        return;
      }
      if (this._zoomMode === 'search') {
        const beforeVal = Number.isFinite(this._before) ? this._before : Number(this._config?.before || 3);
        this._before = beforeVal + 10;
        void this._runSearch();
      }
    });
    bind('zoomAfterMore', 'click', (ev) => {
      ev?.preventDefault?.();
      if (this._zoomMode === 'tail') {
        this._tailOffset = Math.max(0, (this._tailOffset || 0) - 50);
        void this._refreshTail().then(() => {
          this._updateTailZoomDialog();
          this.render();
        });
        return;
      }
      if (this._zoomMode === 'search') {
        const afterVal = Number.isFinite(this._after) ? this._after : Number(this._config?.after || 3);
        this._after = afterVal + 10;
        void this._runSearch();
      }
    });
    bind('closeDialog', 'click', () => {
      const dialog = this.shadowRoot?.getElementById('zoomDialog');
      if (dialog?.open) {
        dialog.close();
      }
    });

    const zoomDialog = this.shadowRoot?.getElementById('zoomDialog');
    if (zoomDialog) {
      zoomDialog.addEventListener('close', () => {
        this._zoomMode = null;
      });
    }

    // Add event listeners for expand buttons using event delegation
    this.shadowRoot.addEventListener('click', (e) => {
      if (e.target.classList.contains('r-xtrs-log-xp-expand-before')) {
        const blockIndex = parseInt(e.target.dataset.block);
        const blockEl = e.target.closest('.r-xtrs-log-xp-result-block');
        void this._expandBlockContext(blockIndex, 'before', blockEl);
      } else if (e.target.classList.contains('r-xtrs-log-xp-expand-after')) {
        const blockIndex = parseInt(e.target.dataset.block);
        const blockEl = e.target.closest('.r-xtrs-log-xp-result-block');
        void this._expandBlockContext(blockIndex, 'after', blockEl);
      }
    });
  }

  _expandBlockContext(blockIndex, direction, blockElement = null) {
    if (!Array.isArray(this._searchResult?.blocks) || blockIndex >= this._searchResult.blocks.length) {
      return;
    }

    const block = this._searchResult.blocks[blockIndex];
    const el = blockElement || this.shadowRoot.querySelector(`[data-block-index="${blockIndex}"]`);
    if (!el) return;

    // Show loading state
    const button = el.querySelector(direction === 'before' ? '.r-xtrs-log-xp-expand-before' : '.r-xtrs-log-xp-expand-after');
    const originalText = button.textContent;
    button.textContent = 'Loading...';
    button.disabled = true;

    // Calculate the line range to fetch
    let startLine, endLine;
    if (direction === 'before') {
      startLine = Math.max(1, block.start_line - 10);
      endLine = block.start_line - 1;

      // Check if we're already at the start of the file
      if (endLine < 1) {
        button.textContent = 'At start of file';
        setTimeout(() => {
          button.textContent = originalText;
          button.disabled = false;
        }, 2000);
        return;
      }
    } else {
      startLine = block.end_line + 1;
      endLine = block.end_line + 10;
    }

    // Fetch additional lines from the backend
    void this._fetchAdditionalLines(startLine, endLine, blockIndex, direction, button, originalText, el);
  }

  async _fetchAdditionalLines(startLine, endLine, blockIndex, direction, button, originalText, blockElement) {
    try {
      const response = await callWebSocketShared(this._hass, {
        type: 'ramses_extras/ramses_debugger/log/get_lines',
        file_id: this._selectedFileId,
        start_line: startLine,
        end_line: endLine,
      });

      if (response && response.lines && response.lines.length > 0) {
        this._insertLinesIntoBlock(blockIndex, direction, response.lines, startLine, originalText, blockElement);
      } else {
        // No more lines available
        button.textContent = 'No more lines';
        setTimeout(() => {
          button.textContent = originalText;
          button.disabled = false;
        }, 2000);
      }
    } catch (error) {
      logger.error('Failed to fetch additional lines:', error);
      button.textContent = 'Error';
      setTimeout(() => {
        button.textContent = originalText;
        button.disabled = false;
      }, 2000);
    }
  }

  _insertLinesIntoBlock(blockIndex, direction, newLines, startLineNumber, originalText, blockElement) {
    const el = blockElement || this.shadowRoot.querySelector(`[data-block-index="${blockIndex}"]`);
    if (!el) return;

    const preElement = el.querySelector('.r-xtrs-log-xp-result-pre');
    if (!preElement) return;

    // Create new line elements with numbers and highlighting
    const newLineElements = newLines.map((line, idx) => {
      const lineNumber = startLineNumber + idx;
      const highlightedLine = this._renderHighlightedLog(String(line), this._searchQuery);
      return `<div class="r-xtrs-log-xp-line" data-line="${lineNumber}">${highlightedLine}</div>`;
    }).join('');

    if (direction === 'before') {
      // Insert at the beginning
      preElement.insertAdjacentHTML('afterbegin', newLineElements);

      // Update the start line in the header
      const headerSpan = el.querySelector('.r-xtrs-log-xp-result-header .r-xtrs-log-xp-muted');
      const currentEndLine = this._searchResult.blocks[blockIndex].end_line;
      headerSpan.textContent = `Lines ${startLineNumber}-${currentEndLine}`;

      // Update the block data
      this._searchResult.blocks[blockIndex].start_line = startLineNumber;
      this._searchResult.blocks[blockIndex].lines = [...newLines, ...this._searchResult.blocks[blockIndex].lines];
    } else {
      // Insert at the end
      preElement.insertAdjacentHTML('beforeend', newLineElements);

      // Update the end line in the header
      const headerSpan = el.querySelector('.r-xtrs-log-xp-result-header .r-xtrs-log-xp-muted');
      const currentStartLine = this._searchResult.blocks[blockIndex].start_line;
      const newEndLine = startLineNumber + newLines.length - 1;
      headerSpan.textContent = `Lines ${currentStartLine}-${newEndLine}`;

      // Update the block data
      this._searchResult.blocks[blockIndex].end_line = newEndLine;
      this._searchResult.blocks[blockIndex].lines = [...this._searchResult.blocks[blockIndex].lines, ...newLines];
    }

    // Re-enable the button
    const button = el.querySelector(direction === 'before' ? '.r-xtrs-log-xp-expand-before' : '.r-xtrs-log-xp-expand-after');
    button.textContent = originalText;
    button.disabled = false;
  }

  _renderSearchBlocksHtml(blocks) {
    return blocks
      .map((b, idx) => {
        const lines = Array.isArray(b?.lines) ? b.lines : [];
        const startLine = b?.start_line || 0;
        const endLine = b?.end_line || 0;

        const linesWithNumbers = lines.map((line, lineIdx) => {
          const lineNumber = startLine + lineIdx;
          const highlightedLine = this._renderHighlightedLog(String(line), this._searchQuery);
          return `<div class="r-xtrs-log-xp-line" data-line="${lineNumber}">${highlightedLine}</div>`;
        }).join('');

        const sep = idx < blocks.length - 1 ? '<div class="r-xtrs-log-xp-separator"></div>' : '';

        return `
          <div class="r-xtrs-log-xp-result-block" data-block-index="${idx}" data-start-line="${startLine}" data-end-line="${endLine}">
            <div class="r-xtrs-log-xp-result-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span class="r-xtrs-log-xp-muted">Lines ${startLine}-${endLine}</span>
              <div class="r-xtrs-log-xp-result-controls" style="display: flex; gap: 4px;">
                <button class="r-xtrs-log-xp-expand-before" data-block="${idx}" title="Add 10 lines before this block">+10 lines up</button>
                <button class="r-xtrs-log-xp-expand-after" data-block="${idx}" title="Add 10 lines after this block">-10 lines down</button>
              </div>
            </div>
            <pre class="r-xtrs-log-xp-result-pre r-xtrs-log-xp-line-numbers">${linesWithNumbers}</pre>
          </div>${sep}
        `;
      })
      .join('');
  }

  _openSearchResultDialog() {
    const dialog = this.shadowRoot?.getElementById('zoomDialog');
    const dialogTitle = this.shadowRoot?.getElementById('zoomTitle');
    const pre = this.shadowRoot?.getElementById('zoomPre');
    const zoomResults = this.shadowRoot?.getElementById('zoomResults');
    if (!dialog || !dialogTitle || !zoomResults) {
      return;
    }

    this._zoomMode = 'search';
    this._setZoomControlsForMode('search');
    dialogTitle.textContent = 'Search result';
    if (pre) {
      pre.textContent = '';
      pre.style.display = 'none';
    }
    if (zoomResults) {
      zoomResults.style.display = '';
    }

    const blocks = Array.isArray(this._searchResult?.blocks) ? this._searchResult.blocks : [];
    if (blocks.length) {
      zoomResults.innerHTML = this._renderSearchBlocksHtml(blocks);
    } else {
      const resultPlain = this._searchResult?.plain || '';
      const resultHtml = this._renderHighlightedLog(resultPlain, this._searchQuery);
      zoomResults.innerHTML = `<pre class="r-xtrs-log-xp-result-pre">${resultHtml || ''}</pre>`;
    }

    try {
      if (typeof dialog.showModal === 'function') {
        dialog.showModal();
      }
    } catch (error) {
      logger.warn('Failed to open dialog:', error);
    }
  }

  _renderContent() {
    if (!this._domInitialized) {
      this._initializeDOM();
      this._domInitialized = true;
    }
    this._updateDOM();
  }

  _initializeDOM() {
    const title = this._config?.name || 'Ramses Log Explorer';
    const wrapCss = this._wrap ? 'white-space: pre-wrap; word-wrap: break-word;' : 'white-space: pre;';

    this.shadowRoot.innerHTML = `
      <style>
        ${logExplorerCardStyle({ wrapCss })}
      </style>
      <ha-card header="${title}">
        <div class="r-xtrs-log-xp-card-content">
          <div class="r-xtrs-log-xp-row">
            <label>${this.t('card.log.files') || 'files'}:</label>
            <select id="fileSelect" title="Select which log file to view"></select>
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
              />
              ${this.t('card.log.actions.wrap') || 'Wrap'}
            </label>
          </div>
          <div id="basePathDiv" class="r-xtrs-log-xp-muted" style="margin-top: 6px;"></div>

          <div id="loadingMsg" class="r-xtrs-log-xp-muted" style="margin-top: 8px; display: none;"></div>
          <div id="errorMsg" class="r-xtrs-log-xp-error" style="display: none;"></div>

          <div class="r-xtrs-log-xp-scrollable-section" id="tailSection" style="margin-top: 12px;">
            <div class="r-xtrs-log-xp-muted" style="display:flex; align-items:center; justify-content: space-between; gap: 12px;">
              <span id="tailLabel"></span>
              <span style="display:flex; gap: 6px;">
                <button id="tailUp" title="Move window 50 lines earlier">+50 lines up</button>
                <button id="tailDown" title="Move window 50 lines later">-50 lines down</button>
              </span>
            </div>
            <pre id="tailPre"></pre>
          </div>

          <div class="r-xtrs-log-xp-separator"></div>

          <div class="r-xtrs-log-xp-muted" style="margin-top: 6px;">
            Search scans the full file; the tail is shown separately.
          </div>

          <div class="r-xtrs-log-xp-row" style="margin-top: 12px;">
            <label>${this.t('card.log.search.query') || 'query'}:</label>
            <input
              id="searchQuery"
              type="text"
              placeholder="ERROR"
              title="Search query (case-insensitive by default)"
            />
            <button id="runSearch" title="Run search on the selected file" style="color: var(--primary-color, #03a9f4);">
              ${this.t('card.log.actions.search') || 'Search'}
            </button>
            <button id="searchWarnings" title="Search for 'WARNING' in the log" style="color: var(--warning-color, #c77f00);">
              Warnings
            </button>
            <button id="searchErrors" title="Search for 'ERROR' in the log" style="color: var(--error-color);">
              Errors
            </button>
            <label>${this.t('card.log.search.before') || 'before'}:</label>
            <input
              id="beforeInput"
              class="small"
              type="number"
              title="Context lines before each match"
            />
            <label>${this.t('card.log.search.after') || 'after'}:</label>
            <input
              id="afterInput"
              class="small"
              type="number"
              title="Context lines after each match"
            />
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

          <div class="r-xtrs-log-xp-scrollable-section" id="searchSection" style="margin-top: 10px;">
            <div id="searchHeader" class="r-xtrs-log-xp-muted"></div>
            <div id="searchResults"></div>
          </div>

          <dialog id="zoomDialog">
            <form method="dialog">
              <h3 id="zoomTitle"></h3>
              <div style="display:flex; align-items:center; justify-content: space-between; gap: 12px; flex-wrap: wrap;">
                <span id="zoomControlsLabel" class="r-xtrs-log-xp-muted">Zoom controls</span>
                <span style="display:flex; gap: 6px;">
                  <button type="button" id="zoomBeforeMore" title="Increase context lines before matches by 10">+10 lines up</button>
                  <button type="button" id="zoomAfterMore" title="Increase context lines after matches by 10">-10 lines down</button>
                </span>
              </div>
              <pre id="zoomPre"></pre>
              <div id="zoomResults" style="margin-top: 10px;"></div>
              <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 12px;">
                <button type="button" id="closeDialog" title="Close this dialog">${this.t('card.actions.close') || 'Close'}</button>
              </div>
            </form>
          </dialog>
        </div>
      </ha-card>
    `;

    this._attachEventListeners();
  }

  _updateDOM() {
    // Update file select options
    const fileSelect = this.shadowRoot.getElementById('fileSelect');
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

    // Update wrap toggle
    const wrapToggle = this.shadowRoot.getElementById('wrapToggle');
    if (wrapToggle) {
      wrapToggle.checked = this._wrap;
    }

    // Update base path
    const basePathDiv = this.shadowRoot.getElementById('basePathDiv');
    if (basePathDiv) {
      basePathDiv.textContent = this._basePath ? `${this.t('card.log.base') || 'base'}: ${this._basePath}` : '';
    }

    // Update loading message
    const loadingMsg = this.shadowRoot.getElementById('loadingMsg');
    if (loadingMsg) {
      if (this._loading) {
        loadingMsg.textContent = this.t('card.log.loading') || 'Loading...';
        loadingMsg.style.display = '';
      } else {
        loadingMsg.style.display = 'none';
      }
    }

    // Update error message
    const errorMsg = this.shadowRoot.getElementById('errorMsg');
    if (errorMsg) {
      if (this._lastError) {
        errorMsg.textContent = String(this._lastError?.message || this._lastError);
        errorMsg.style.display = '';
      } else {
        errorMsg.style.display = 'none';
      }
    }

    // Update tail label
    const tailLabel = this.shadowRoot.getElementById('tailLabel');
    if (tailLabel) {
      tailLabel.textContent = `${this.t('card.log.tail.title') || 'tail'} (${this._getTailWindowLabel()})`;
    }

    // Update tail content
    const tailPre = this.shadowRoot.getElementById('tailPre');
    if (tailPre) {
      let tailHtml;
      if (this._tailStartLine !== null && this._tailText) {
        const tailLines = this._tailText.split('\n');
        tailHtml = tailLines.map((line, idx) => {
          const lineNumber = this._tailStartLine + idx;
          const highlightedLine = this._renderHighlightedLog(line, this._searchQuery);
          return `<div class="r-xtrs-log-xp-line" data-line="${lineNumber}">${highlightedLine}</div>`;
        }).join('');
        tailHtml = `<div class="r-xtrs-log-xp-line-numbers">${tailHtml}</div>`;
      } else {
        tailHtml = this._renderHighlightedLog(this._tailText, this._searchQuery);
      }
      tailPre.innerHTML = tailHtml || '';
    }

    // Update search query input
    const searchQuery = this.shadowRoot.getElementById('searchQuery');
    if (searchQuery && searchQuery.value !== (this._searchQuery || '')) {
      searchQuery.value = this._searchQuery || '';
    }

    // Update before/after inputs
    const beforeInput = this.shadowRoot.getElementById('beforeInput');
    if (beforeInput) {
      const beforeVal = Number.isFinite(this._before)
        ? this._before
        : Number(this._config?.before || 3);
      if (beforeInput.value !== String(beforeVal)) {
        beforeInput.value = String(beforeVal);
      }
    }

    const afterInput = this.shadowRoot.getElementById('afterInput');
    if (afterInput) {
      const afterVal = Number.isFinite(this._after)
        ? this._after
        : Number(this._config?.after || 3);
      if (afterInput.value !== String(afterVal)) {
        afterInput.value = String(afterVal);
      }
    }

    // Update search header
    const searchHeader = this.shadowRoot.getElementById('searchHeader');
    if (searchHeader) {
      const matches = this._searchResult?.matches;
      const truncated = Boolean(this._searchResult?.truncated);
      let headerText = this.t('card.log.search.title') || 'search';
      if (typeof matches === 'number') {
        headerText += ` • ${matches} ${this.t('card.log.search.matches') || 'matches'}`;
      }
      if (truncated) {
        headerText += ` • ${this.t('card.log.search.truncated') || 'truncated'}`;
      }
      searchHeader.textContent = headerText;
    }

    // Update search results
    const searchResults = this.shadowRoot.getElementById('searchResults');
    if (searchResults) {
      const blocks = Array.isArray(this._searchResult?.blocks)
        ? this._searchResult.blocks
        : [];

      if (blocks.length) {
        searchResults.innerHTML = this._renderSearchBlocksHtml(blocks);
      } else {
        const resultPlain = this._searchResult?.plain || '';
        const resultHtml = this._renderHighlightedLog(resultPlain, this._searchQuery);
        searchResults.innerHTML = `<pre id="resultPre">${resultHtml || ''}</pre>`;
      }
    }

    const zoomDialog = this.shadowRoot.getElementById('zoomDialog');
    const zoomResults = this.shadowRoot.getElementById('zoomResults');
    if (zoomDialog?.open && this._zoomMode === 'search' && zoomResults) {
      const blocks = Array.isArray(this._searchResult?.blocks) ? this._searchResult.blocks : [];
      if (blocks.length) {
        zoomResults.innerHTML = this._renderSearchBlocksHtml(blocks);
      } else {
        const resultPlain = this._searchResult?.plain || '';
        const resultHtml = this._renderHighlightedLog(resultPlain, this._searchQuery);
        zoomResults.innerHTML = `<pre class="r-xtrs-log-xp-result-pre">${resultHtml || ''}</pre>`;
      }
    }
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
