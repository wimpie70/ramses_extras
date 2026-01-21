/* global setInterval */
/* global clearInterval */
/* global navigator */

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
      const res = await callWebSocket(this._hass, { type: 'ramses_extras/get_available_devices' });
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
    const pollInterval = Number(this._config?.poll_interval || 5000);
    const safeInterval = Number.isFinite(pollInterval) ? Math.max(1000, pollInterval) : 5000;

    const doPoll = async () => {
      try {
        this._lastError = null;
        const result = await callWebSocket(this._hass, {
          type: 'ramses_extras/ramses_debugger/traffic/get_stats',
          ...this._buildFiltersFromConfig({ includeTrafficSource: true }),
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
      ...this._buildFiltersFromConfig({ includeTrafficSource: false }),
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
      await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/traffic/reset_stats',
      });

      // Refresh after reset so the "since" timestamp reflects the new window.
      this._stats = await callWebSocket(this._hass, {
        type: 'ramses_extras/ramses_debugger/traffic/get_stats',
        ...this._buildFiltersFromConfig(),
      });
    } catch (error) {
      this._lastError = error;
    }

    this.render();
  }

  _renderContent() {
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
          <tr class="flow-row" data-flow="${data}">
            <td class="select-cell">
              <input type="checkbox" class="row-select" data-src="${src}" data-dst="${dst}" ${this._checkedRows.get(`${src}|${dst}`) ? 'checked' : ''}>
            </td>
            <td class="device-cell" style="--dev-bg: ${srcBg};" title="Source device">
              <div class="dev">
                <span class="id">${src}</span>
                ${srcAlias ? `<span class="alias">${srcAlias}</span>` : ''}
                ${srcSlugLabel ? `<span class="slug">${srcSlugLabel}</span>` : ''}
              </div>
            </td>
            <td class="device-cell" style="--dev-bg: ${dstBg};" title="Destination device">
              <div class="dev">
                <span class="id">${dst}</span>
                ${dstAlias ? `<span class="alias">${dstAlias}</span>` : ''}
                ${dstSlugLabel ? `<span class="slug">${dstSlugLabel}</span>` : ''}
              </div>
            </td>
            <td class="verbs" title="Verbs observed for this flow">${verbs}</td>
            <td class="codes" title="Codes observed for this flow">${codes}</td>
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
        <div style="padding: 16px;">
          <div class="meta">
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

          ${errorText ? `<div class="error">${errorText}</div>` : ''}

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="select-cell"><input type="checkbox" id="selectAll" title="Select all flows" ${this._flows && this._flows.length && this._checkedRows.size === this._flows.length ? 'checked' : ''}></th>
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
    const checkboxes = this.shadowRoot.querySelectorAll('.row-select:checked');
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
      const el = document.createElement('div');
      el.className = 'messages-list';
      container.appendChild(el);

      // Build filters for multiple src/dst pairs
      const filters = {};
      const srcList = [];
      const dstList = [];
      const pairGroups = [];
      for (const { src, dst } of selected) {
        if (src) srcList.push(src);
        if (dst) dstList.push(dst);
        if (src && dst) {
          pairGroups.push({
            src,
            dst,
            key: `${src}|${dst}`,
          });
        }
      }
      // For now, only support single src/dst filters; extend backend later
      if (srcList.length === 1) filters.src = srcList[0];
      if (dstList.length === 1) filters.dst = dstList[0];
      // If multiple, don't filter by src/dst to show all traffic between selected pairs

      let sources = ['traffic_buffer'];
      if (this._trafficSource === 'packet_log') {
        sources = ['packet_log'];
      } else if (this._trafficSource === 'ha_log') {
        sources = ['ha_log'];
      }

      const doFetch = () => this._hass?.callWS({
        type: 'ramses_extras/ramses_debugger/messages/get_messages',
        sources,
        limit: 200,
        dedupe: true,
        decode: Boolean(this._messagesDecode),
        ...filters,
      });

      const activePairs = new Set(pairGroups.map((pair) => pair.key));
      let activeVerbs = new Set();
      let activeCodes = new Set();
      let lastVerbsKey = '';
      let lastCodesKey = '';
      let verbFilterTouched = false;
      let codeFilterTouched = false;
      const renderMessages = (messages) => {
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
          let lenIdx = -1;
          for (let i = 0; i < tokens.length; i += 1) {
            if (/^\d{3}$/.test(tokens[i])) {
              lenIdx = i;
              break;
            }
          }
          if (lenIdx === -1) return '';
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
          let payloadVal = this._messagesDecode && m?.decoded?.payload
            ? m.decoded.payload
            : (!this._messagesDecode && payloadRaw
              ? payloadRaw
              : (!this._messagesDecode && typeof m?.payload === 'string'
                ? m.payload
                : (!this._messagesDecode ? m?.packet : m?.payload)));
          if (payloadVal == null) payloadVal = '';
          const payloadStr = (typeof payloadVal === 'string')
            ? payloadVal
            : JSON.stringify(payloadVal);

          return {
            ...m,
            __dstRaw: dstRaw || '',
            __via: via || '',
            __dstDisplay: String(dstDisplay),
            __dstEffective: String(dstEffective),
            __viaDisplay: String(viaDisplay),
            __payloadStr: String(payloadStr),
          };
        };

        let filtered = Array.isArray(messages) ? messages.map(normalizeMessage) : [];
        if (activePairs.size) {
          filtered = filtered.filter((m) => {
            const src = m?.src;
            const dst = m?.__dstEffective;
            if (typeof src !== 'string' || typeof dst !== 'string') return false;

            for (const pair of pairGroups) {
              if (!activePairs.has(pair.key)) {
                continue;
              }
              if (pair.dst === '--:------') {
                const srcMatch = src === pair.src;
                if (srcMatch && (m?.__dstRaw === '--:------' || m?.dst === '--:------')) {
                  return true;
                }
                continue;
              }
              if (`${src}|${dst}` === pair.key) {
                return true;
              }
            }
            return false;
          });
        }

        const baseFiltered = filtered;
        const availableVerbs = new Set(
          baseFiltered
            .map((m) => (typeof m?.verb === 'string' ? m.verb : ''))
            .filter((v) => v)
        );
        const verbsKey = [...availableVerbs].sort().join('|');
        if (verbsKey !== lastVerbsKey) {
          if (verbFilterTouched) {
            activeVerbs = new Set([...activeVerbs].filter((v) => availableVerbs.has(v)));
          } else {
            activeVerbs = new Set(availableVerbs);
          }
          lastVerbsKey = verbsKey;
        }
        if (verbFilterTouched) {
          filtered = filtered.filter((m) => activeVerbs.has(String(m?.verb || '')));
        }

        const availableCodes = new Set(
          filtered
            .map((m) => (typeof m?.code === 'string' ? m.code : ''))
            .filter((c) => c)
        );
        const codesKey = [...availableCodes].sort().join('|');
        if (codesKey !== lastCodesKey) {
          if (codeFilterTouched) {
            activeCodes = new Set([...activeCodes].filter((c) => availableCodes.has(c)));
          } else {
            activeCodes = new Set(availableCodes);
          }
          lastCodesKey = codesKey;
        }
        if (codeFilterTouched) {
          filtered = filtered.filter((m) => activeCodes.has(String(m?.code || '')));
        }

        const sortKey = this._messagesSortKey || 'dtm';
        const mul = this._messagesSortDir === 'desc' ? -1 : 1;

        const sortValue = (m, key) => {
          if (key === 'dst') return m?.__dstDisplay ?? '';
          if (key === 'broadcast') return m?.__viaDisplay ?? '';
          if (key === 'payload') return m?.__payloadStr ?? '';
          return m?.[key];
        };

        const sorted = [...filtered].sort((a, b) => {
          const av = sortValue(a, sortKey);
          const bv = sortValue(b, sortKey);
          const as = String(av ?? '');
          const bs = String(bv ?? '');
          return as.localeCompare(bs) * mul;
        });

        const sortArrow = (key) => {
          if (this._messagesSortKey !== key) return '';
          return this._messagesSortDir === 'asc' ? ' ▲' : ' ▼';
        };

        el.innerHTML = `
          <style>
            .messages-table-wrapper { overflow-x: auto; }
            .messages-table td.col-payload { white-space: nowrap; font-family: monospace; }
            .messages-table th.sortable { cursor: pointer; }
            .messages-controls { display:flex; align-items:center; gap: 12px; margin-top: 8px; }
            .messages-selected { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
            .messages-chip { display:inline-flex; align-items:center; gap: 6px; padding: 2px 6px; border-radius: 999px; background: rgba(0,0,0,0.04); }
            .messages-chip .dev { padding: 1px 6px; border-radius: 999px; background: var(--dev-bg, transparent); }
            .messages-verbs { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
            .messages-verb-chip { display:inline-flex; align-items:center; gap: 6px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); }
            .messages-codes { display:flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
            .messages-code-chip { display:inline-flex; align-items:center; gap: 6px; padding: 2px 8px; border-radius: 999px; background: rgba(0,0,0,0.04); }
          </style>
          <div class="messages-header">
            <strong>Messages (${sorted.length})</strong>
            ${sorted.length && sorted[0].source ? ` (Source: <code>${sorted[0].source}</code>)` : ''}
          </div>
          ${selected.length ? `
            <div class="messages-selected">
              ${pairGroups.map(({ src, dst, key }) => {
                const pairKey = `${src}|${dst}`;
                const checked = activePairs.has(key);
                const srcBg = src ? this._deviceBg(src) : '';
                const dstBg = dst ? this._deviceBg(dst) : '';
                return `
                  <span class="messages-chip">
                    <input type="checkbox" class="pair-toggle" data-pair="${pairKey}" ${checked ? 'checked' : ''} />
                    <span class="dev" style="--dev-bg: ${srcBg};">${src || ''}</span>
                    →
                    <span class="dev" style="--dev-bg: ${dstBg};">${dst || ''}</span>
                  </span>
                `;
              }).join('')}
            </div>
          ` : ''}
          ${availableCodes.size ? `
            <div class="messages-codes">
              ${[...availableCodes].sort().map((code) => {
                const checked = activeCodes.has(code);
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
                const checked = activeVerbs.has(verb);
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
              <input type="checkbox" id="messagesDecode" ${this._messagesDecode ? 'checked' : ''}>
              Parsed values
            </label>
          </div>
          <div class="messages-table-wrapper">
            <table class="messages-table">
              <thead>
                <tr>
                  <th class="col-time sortable" data-sort="dtm">Time${sortArrow('dtm')}</th>
                  <th class="col-verb sortable" data-sort="verb">Verb${sortArrow('verb')}</th>
                  <th class="col-code sortable" data-sort="code">Code${sortArrow('code')}</th>
                  <th class="col-src sortable" data-sort="src">Src${sortArrow('src')}</th>
                  <th class="col-dst sortable" data-sort="dst">Dst${sortArrow('dst')}</th>
                  <th class="col-bcast sortable" data-sort="broadcast">Broadcast${sortArrow('broadcast')}</th>
                  <th class="col-payload sortable" data-sort="payload">Payload${sortArrow('payload')}</th>
                </tr>
              </thead>
              <tbody>
                ${sorted.map((msg) => {
                  const payload = msg.__payloadStr || '';
                  const dstEffective = msg.__dstEffective || '';
                  const dstDisplay = msg.__dstDisplay || '';
                  const viaDisplay = msg.__viaDisplay || '';
                  const srcBg = msg.src ? this._deviceBg(msg.src) : '';
                  const dstBg = dstEffective ? this._deviceBg(dstEffective) : '';
                  return `
                  <tr>
                    <td class="col-time">${msg.dtm || ''}</td>
                    <td class="col-verb">${msg.verb || ''}</td>
                    <td class="col-code">${msg.code || ''}</td>
                    <td class="col-src" style="--dev-bg: ${srcBg};">${msg.src || ''}</td>
                    <td class="col-dst" style="--dev-bg: ${dstBg};">${dstDisplay}</td>
                    <td class="col-bcast">${viaDisplay}</td>
                    <td class="col-payload">${payload}</td>
                  </tr>
                `;
                }).join('')}
              </tbody>
            </table>
          </div>
        `;

        const thead = el.querySelector('thead');
        if (!this._boundOnMessagesSortClick) {
          this._boundOnMessagesSortClick = (ev) => {
            const th = ev.target?.closest?.('th');
            const key = th?.getAttribute?.('data-sort');
            if (!key) return;
            if (this._messagesSortKey === key) {
              this._messagesSortDir = this._messagesSortDir === 'asc' ? 'desc' : 'asc';
            } else {
              this._messagesSortKey = key;
              this._messagesSortDir = 'asc';
            }
            renderMessages(messages);
          };
        }
        if (thead) {
          thead.onclick = this._boundOnMessagesSortClick;
        }

        const decodeCb = el.querySelector('#messagesDecode');
        if (!this._boundOnMessagesDecodeToggle) {
          this._boundOnMessagesDecodeToggle = (ev) => {
            this._messagesDecode = Boolean(ev?.target?.checked);
            const needsDecode = this._messagesDecode
              && Array.isArray(messages)
              && messages.some((m) => !m?.decoded?.payload);
            if (needsDecode) {
              void fetchAndRender();
              return;
            }
            renderMessages(messages);
          };
        }
        if (decodeCb) {
          decodeCb.onchange = this._boundOnMessagesDecodeToggle;
        }

        const toggles = el.querySelectorAll('.pair-toggle');
        toggles.forEach((toggle) => {
          toggle.onchange = (ev) => {
            const key = ev?.target?.getAttribute?.('data-pair');
            if (!key) return;
            if (ev?.target?.checked) {
              activePairs.add(key);
            } else {
              activePairs.delete(key);
            }
            renderMessages(messages);
          };
        });

        const verbToggles = el.querySelectorAll('.verb-toggle');
        verbToggles.forEach((toggle) => {
          toggle.onchange = (ev) => {
            const verb = ev?.target?.getAttribute?.('data-verb');
            if (!verb) return;
            verbFilterTouched = true;
            if (ev?.target?.checked) {
              activeVerbs.add(verb);
            } else {
              activeVerbs.delete(verb);
            }
            renderMessages(messages);
          };
        });

        const codeToggles = el.querySelectorAll('.code-toggle');
        codeToggles.forEach((toggle) => {
          toggle.onchange = (ev) => {
            const code = ev?.target?.getAttribute?.('data-code');
            if (!code) return;
            codeFilterTouched = true;
            if (ev?.target?.checked) {
              activeCodes.add(code);
            } else {
              activeCodes.delete(code);
            }
            renderMessages(messages);
          };
        });
      };

      const fetchAndRender = async () => {
        try {
          const response = await doFetch();
          renderMessages(response?.messages || []);
        } catch (err) {
          el.innerHTML = `<div class="error">Failed to load messages: ${err.message || err}</div>`;
        }
      };

      void fetchAndRender();
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
    const rowCheckboxes = this.shadowRoot.querySelectorAll('.row-select');
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
