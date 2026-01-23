/* global HTMLElement */
/* global customElements */

/**
 * Ramses Messages Viewer.
 *
 * A reusable UI component used by debugger cards to display a list of messages
 * (traffic_buffer / packet_log / ha_log) with sorting and filtering.
 *
 * Data loading is delegated to the parent via `fetchMessages`, which should
 * return either `{ messages: [...] }` or a plain array.
 */
import * as logger from '../../helpers/logger.js';

class RamsesMessagesViewer extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });

    this._hass = null;
    this._messages = [];
    this._lastError = null;
    this._loading = false;

    this._config = {
      pairs: [],
      pair_mode: 'selected',
      limit: 200,
    };

    this._fetchMessages = null;

    this._sortKey = 'dtm';
    this._sortDir = 'asc';
    this._decode = false;

    this._activePairs = new Set();
    this._activeVerbs = new Set();
    this._activeCodes = new Set();

    this._pairFilterTouched = false;
    this._verbFilterTouched = false;
    this._codeFilterTouched = false;

    this._lastPairsKey = '';
    this._lastVerbsKey = '';
    this._lastCodesKey = '';
  }

  set hass(hass) {
    this._hass = hass;
  }

  set fetchMessages(fn) {
    this._fetchMessages = typeof fn === 'function' ? fn : null;
  }

  setConfig(config) {
    const cfg = config && typeof config === 'object' ? config : {};
    this._config = {
      ...this._config,
      ...cfg,
    };

    if (typeof this._config.sort_key === 'string' && this._config.sort_key) {
      this._sortKey = this._config.sort_key;
    }
    if (this._config.sort_dir === 'asc' || this._config.sort_dir === 'desc') {
      this._sortDir = this._config.sort_dir;
    }

    const pairs = Array.isArray(this._config.pairs) ? this._config.pairs : [];
    this._activePairs = new Set(pairs.map((p) => `${p?.src}|${p?.dst}`));

    this.render();
  }

  async refresh() {
    // Explicit refresh is used so parents can control when messages are loaded
    // (e.g. button click, selection change, or auto mode).
    if (!this._fetchMessages) {
      this.render();
      return;
    }

    try {
      this._loading = true;
      this._lastError = null;
      this.render();

      const res = await this._fetchMessages({
        hass: this._hass,
        decode: Boolean(this._decode),
        limit: Number(this._config?.limit || 200),
      });

      const messages = Array.isArray(res?.messages)
        ? res.messages
        : Array.isArray(res)
          ? res
          : [];

      this._messages = messages;
    } catch (error) {
      this._lastError = error;
      this._messages = [];
    } finally {
      this._loading = false;
      this.render();
    }
  }

  connectedCallback() {
    this.render();
  }

  _toggleSort(key) {
    if (this._sortKey === key) {
      this._sortDir = this._sortDir === 'asc' ? 'desc' : 'asc';
      return;
    }
    this._sortKey = key;
    this._sortDir = 'asc';
  }

  render() {
    if (!this.shadowRoot) {
      return;
    }

    const prevWrapper = this.shadowRoot.querySelector('.messages-table-wrapper');
    const prevScrollTop = prevWrapper ? prevWrapper.scrollTop : 0;
    const prevScrollLeft = prevWrapper ? prevWrapper.scrollLeft : 0;

    const deviceBg = (deviceId) => {
      const s = String(deviceId || '');
      if (!s) return 'rgba(0,0,0,0.04)';
      let hash = 0;
      for (let i = 0; i < s.length; i += 1) {
        hash = ((hash << 5) - hash) + s.charCodeAt(i);
        hash |= 0;
      }
      const hue = Math.abs(hash) % 360;
      return `hsla(${hue}, 70%, 50%, 0.22)`;
    };

    const parsePacketAddrs = (pkt) => {
      if (typeof pkt !== 'string' || !pkt) return null;
      const parts = pkt.split(' ');
      const addrs = [];
      for (const p of parts) {
        if (/^\d{2}:\d{6}$|^--:------$/.test(p)) {
          addrs.push(p);
          if (addrs.length >= 3) break;
        }
      }
      if (addrs.length < 2) return null;
      return { src: addrs[0], dstRaw: addrs[1], via: addrs[2] || '' };
    };

    const extractPayloadFromPacket = (pkt) => {
      if (typeof pkt !== 'string' || !pkt) return '';
      const tokens = pkt.split(' ').filter(Boolean);

      const isCode = (t) => /^[0-9A-F]{4}$/.test(t);
      const isLen = (t) => /^\d{3}$/.test(t);

      const codeIdx = tokens.findIndex(isCode);
      if (codeIdx === -1) return '';

      const relLenIdx = tokens.slice(codeIdx + 1).findIndex(isLen);
      if (relLenIdx === -1) return '';

      const lenIdx = codeIdx + 1 + relLenIdx;
      const len = tokens[lenIdx];
      const payload = tokens.slice(lenIdx + 1).join(' ');
      return payload ? `${len} ${payload}` : len;
    };

    const normalizeMessage = (m) => {
      const info = parsePacketAddrs(m?.packet);
      const dstRaw = info?.dstRaw;
      const via = info?.via;

      const dstEffective = (dstRaw && dstRaw !== '--:------')
        ? dstRaw
        : (via && via !== '--:------')
          ? via
          : (m?.dst || '');

      const dstDisplay = dstRaw || m?.dst || '';
      const viaDisplay = (dstRaw === '--:------' && via && via !== '--:------')
        ? via
        : (via && via !== '--:------')
          ? via
          : '';

      const payloadRaw = extractPayloadFromPacket(m?.packet);

      let payloadVal;
      if (this._decode) {
        payloadVal = m?.decoded?.payload != null ? m.decoded.payload : m?.payload;
      } else {
        payloadVal = (typeof m?.payload === 'string' && m.payload)
          ? m.payload
          : (payloadRaw || m?.packet || '');
      }
      if (payloadVal == null) payloadVal = '';
      const payloadStr = (typeof payloadVal === 'string')
        ? payloadVal
        : JSON.stringify(payloadVal);

      return {
        ...m,
        __dstRaw: dstRaw || '',
        __dstDisplay: String(dstDisplay),
        __dstEffective: String(dstEffective),
        __viaDisplay: String(viaDisplay),
        __payloadStr: String(payloadStr),
      };
    };

    let normalized = Array.isArray(this._messages) ? this._messages.map(normalizeMessage) : [];

    let pairGroups = [];
    const mode = String(this._config?.pair_mode || 'selected');
    if (mode === 'derived') {
      const seen = new Set();
      for (const m of normalized) {
        const src = typeof m?.src === 'string' ? m.src : '';
        const dst = typeof m?.__dstEffective === 'string' ? m.__dstEffective : '';
        if (!src || !dst) continue;
        const key = `${src}|${dst}`;
        if (seen.has(key)) continue;
        seen.add(key);
        pairGroups.push({ src, dst, key });
      }
      pairGroups.sort((a, b) => a.key.localeCompare(b.key));
    } else {
      const pairs = Array.isArray(this._config.pairs) ? this._config.pairs : [];
      pairGroups = pairs
        .filter((p) => p && p.src && p.dst)
        .map((p) => ({ src: p.src, dst: p.dst, key: `${p.src}|${p.dst}` }));
    }

    const pairsKey = pairGroups.map((p) => p.key).join('|');
    if (pairsKey !== this._lastPairsKey) {
      if (!this._pairFilterTouched) {
        this._activePairs = new Set(pairGroups.map((p) => p.key));
      } else {
        this._activePairs = new Set([...this._activePairs].filter((k) => pairGroups.some((p) => p.key === k)));
      }
      this._lastPairsKey = pairsKey;
    }

    if (pairGroups.length && this._pairFilterTouched) {
      normalized = normalized.filter((m) => {
        const src = typeof m?.src === 'string' ? m.src : '';
        const dst = typeof m?.__dstEffective === 'string' ? m.__dstEffective : '';
        if (!src || !dst) return false;
        return this._activePairs.has(`${src}|${dst}`);
      });
    }

    const baseFiltered = normalized;

    const availableVerbs = new Set(
      baseFiltered
        .map((m) => (typeof m?.verb === 'string' ? m.verb : ''))
        .filter((v) => v)
    );
    const verbsKey = [...availableVerbs].sort().join('|');
    if (verbsKey !== this._lastVerbsKey) {
      if (!this._verbFilterTouched) {
        this._activeVerbs = new Set(availableVerbs);
      } else {
        this._activeVerbs = new Set([...this._activeVerbs].filter((v) => availableVerbs.has(v)));
      }
      this._lastVerbsKey = verbsKey;
    }
    if (this._verbFilterTouched) {
      normalized = normalized.filter((m) => this._activeVerbs.has(String(m?.verb || '')));
    }

    const availableCodes = new Set(
      normalized
        .map((m) => (typeof m?.code === 'string' ? m.code : ''))
        .filter((c) => c)
    );
    const codesKey = [...availableCodes].sort().join('|');
    if (codesKey !== this._lastCodesKey) {
      if (!this._codeFilterTouched) {
        this._activeCodes = new Set(availableCodes);
      } else {
        this._activeCodes = new Set([...this._activeCodes].filter((c) => availableCodes.has(c)));
      }
      this._lastCodesKey = codesKey;
    }
    if (this._codeFilterTouched) {
      normalized = normalized.filter((m) => this._activeCodes.has(String(m?.code || '')));
    }

    const sortValue = (m, key) => {
      if (key === 'dst') return m?.__dstDisplay ?? '';
      if (key === 'broadcast') return m?.__viaDisplay ?? '';
      if (key === 'payload') return m?.__payloadStr ?? '';
      return m?.[key];
    };

    const mul = this._sortDir === 'desc' ? -1 : 1;
    const sorted = [...normalized].sort((a, b) => {
      const av = sortValue(a, this._sortKey);
      const bv = sortValue(b, this._sortKey);
      return String(av ?? '').localeCompare(String(bv ?? '')) * mul;
    });

    const sortArrow = (key) => {
      if (this._sortKey !== key) return '';
      return this._sortDir === 'asc' ? ' ▲' : ' ▼';
    };

    const errorText = this._lastError
      ? String(this._lastError?.message || this._lastError)
      : '';

    this.shadowRoot.innerHTML = `
      <style>
        .messages-table-wrapper { overflow: auto; max-height: 320px; }
        .messages-table { width: 100%; border-collapse: collapse; }
        .messages-table th, .messages-table td { border: 1px solid var(--divider-color); padding: 4px 6px; vertical-align: top; }
        .messages-table th { background: var(--secondary-background-color); position: sticky; top: 0; z-index: 1; text-align: left; }
        .messages-table td { font-family: monospace; font-size: 12px; user-select: text; -webkit-user-select: text; }
        .messages-table td.col-payload { white-space: nowrap; }
        .messages-table th.sortable { cursor: pointer; user-select: none; }
        .messages-controls { display:flex; align-items:center; gap: 12px; margin-top: 8px; }
        .messages-selected { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
        .messages-chip { display:inline-flex; align-items:center; gap: 6px; padding: 2px 6px; border-radius: 999px; background: rgba(0,0,0,0.04); }
        .dev { padding: 1px 6px; border-radius: 999px; background: var(--dev-bg, rgba(0,0,0,0.04)); }
        .messages-verbs { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
        .messages-verb-chip { display:inline-flex; align-items:center; gap: 6px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); }
        .messages-codes { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
        .messages-code-chip { display:inline-flex; align-items:center; gap: 6px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); }
        .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }
      </style>
      <div class="messages-header">
        <strong>Messages (${sorted.length})</strong>
        ${sorted.length && sorted[0].source ? ` (Source: <code>${sorted[0].source}</code>)` : ''}
      </div>
      ${this._loading ? `<div class="muted" style="margin-top: 8px;">Loading...</div>` : ''}
      ${errorText ? `<div class="error">${errorText}</div>` : ''}
      ${pairGroups.length ? `
        <div class="messages-selected">
          ${pairGroups.map(({ src, dst, key }) => {
            const checked = this._activePairs.has(key);
            return `
              <span class="messages-chip">
                <input type="checkbox" class="pair-toggle" data-pair="${key}" ${checked ? 'checked' : ''} />
                <span class="dev" style="--dev-bg: ${deviceBg(src)};">${src || ''}</span>
                →
                <span class="dev" style="--dev-bg: ${deviceBg(dst)};">${dst || ''}</span>
              </span>
            `;
          }).join('')}
        </div>
      ` : ''}
      ${availableCodes.size ? `
        <div class="messages-codes">
          ${[...availableCodes].sort().map((code) => {
            const checked = this._activeCodes.has(code);
            return `
              <span class="messages-code-chip">
                <input type="checkbox" class="code-toggle" data-code="${code}" ${checked ? 'checked' : ''} />
                <span>${code}</span>
              </span>
            `;
          }).join('')}
        </div>
      ` : ''}
      ${availableVerbs.size ? `
        <div class="messages-verbs">
          ${[...availableVerbs].sort().map((verb) => {
            const checked = this._activeVerbs.has(verb);
            return `
              <span class="messages-verb-chip">
                <input type="checkbox" class="verb-toggle" data-verb="${verb}" ${checked ? 'checked' : ''} />
                <span>${verb}</span>
              </span>
            `;
          }).join('')}
        </div>
      ` : ''}
      <div class="messages-controls">
        <label>
          <input type="checkbox" id="messagesDecode" ${this._decode ? 'checked' : ''} title="Toggle decoded payload values (uses ramses_tx where available)">
          Parsed values
        </label>
      </div>
      <div class="messages-table-wrapper">
        <table class="messages-table">
          <thead>
            <tr>
              <th class="col-time sortable" data-sort="dtm" title="Timestamp (click to sort)">Time${sortArrow('dtm')}</th>
              <th class="col-verb sortable" data-sort="verb" title="Verb (click to sort)">Verb${sortArrow('verb')}</th>
              <th class="col-code sortable" data-sort="code" title="Code (click to sort)">Code${sortArrow('code')}</th>
              <th class="col-src sortable" data-sort="src" title="Source device (click to sort)">Src${sortArrow('src')}</th>
              <th class="col-dst sortable" data-sort="dst" title="Destination device (click to sort)">Dst${sortArrow('dst')}</th>
              <th class="col-bcast sortable" data-sort="broadcast" title="Broadcast/via device (click to sort)">Broadcast${sortArrow('broadcast')}</th>
              <th class="col-payload sortable" data-sort="payload" title="Payload (click to sort)">Payload${sortArrow('payload')}</th>
            </tr>
          </thead>
          <tbody>
            ${sorted.map((msg) => {
              const payload = msg.__payloadStr || '';
              const dstDisplay = msg.__dstDisplay || '';
              const viaDisplay = msg.__viaDisplay || '';
              const srcBg = deviceBg(msg.src);
              const dstBg = (dstDisplay === '--:------') ? 'rgba(0,0,0,0.04)' : deviceBg(dstDisplay);
              const viaBg = viaDisplay ? deviceBg(viaDisplay) : '';
              return `
                <tr>
                  <td class="col-time">${msg.dtm || ''}</td>
                  <td class="col-verb">${msg.verb || ''}</td>
                  <td class="col-code">${msg.code || ''}</td>
                  <td class="col-src"><span class="dev" style="--dev-bg: ${srcBg};">${msg.src || ''}</span></td>
                  <td class="col-dst"><span class="dev" style="--dev-bg: ${dstBg};">${dstDisplay}</span></td>
                  <td class="col-bcast">${viaDisplay ? `<span class="dev" style="--dev-bg: ${viaBg};">${viaDisplay}</span>` : ''}</td>
                  <td class="col-payload">${payload}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;

    const wrapper = this.shadowRoot.querySelector('.messages-table-wrapper');
    if (wrapper) {
      wrapper.scrollTop = prevScrollTop;
      wrapper.scrollLeft = prevScrollLeft;
    }

    const thead = this.shadowRoot.querySelector('thead');
    if (thead) {
      thead.onclick = (ev) => {
        const th = ev.target?.closest?.('th');
        const key = th?.getAttribute?.('data-sort');
        if (!key) return;
        this._toggleSort(key);
        this.render();
      };
    }

    const decodeCb = this.shadowRoot.querySelector('#messagesDecode');
    if (decodeCb) {
      decodeCb.onchange = (ev) => {
        this._decode = Boolean(ev?.target?.checked);
        void this.refresh();
      };
    }

    this.shadowRoot.querySelectorAll('.pair-toggle').forEach((toggle) => {
      toggle.onchange = (ev) => {
        const key = ev?.target?.getAttribute?.('data-pair');
        if (!key) return;
        this._pairFilterTouched = true;
        if (ev?.target?.checked) {
          this._activePairs.add(key);
        } else {
          this._activePairs.delete(key);
        }
        this.render();
      };
    });

    this.shadowRoot.querySelectorAll('.verb-toggle').forEach((toggle) => {
      toggle.onchange = (ev) => {
        const verb = ev?.target?.getAttribute?.('data-verb');
        if (!verb) return;
        this._verbFilterTouched = true;
        if (ev?.target?.checked) {
          this._activeVerbs.add(verb);
        } else {
          this._activeVerbs.delete(verb);
        }
        this.render();
      };
    });

    this.shadowRoot.querySelectorAll('.code-toggle').forEach((toggle) => {
      toggle.onchange = (ev) => {
        const code = ev?.target?.getAttribute?.('data-code');
        if (!code) return;
        this._codeFilterTouched = true;
        if (ev?.target?.checked) {
          this._activeCodes.add(code);
        } else {
          this._activeCodes.delete(code);
        }
        this.render();
      };
    });
  }
}

if (!customElements.get('ramses-messages-viewer')) {
  try {
    customElements.define('ramses-messages-viewer', RamsesMessagesViewer);
  } catch (error) {
    logger.warn('Failed to register ramses-messages-viewer:', error);
  }
}
