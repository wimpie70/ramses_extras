/**
 * Ramses Editor Embed card
 *
 * Mounts a plan editor's own webcomponent inside a Lovelace card so a
 * panel-style editor (e.g. ha-floorplan-studio's floorplan-studio-panel)
 * can live on the same dashboard view as the actions card instead of a
 * separate sidebar page.
 *
 * The element/module come from the resolved editor adapter's
 * capabilities (panel_element / panel_module via get_config), so the
 * same card works for any editor whose UI is a webcomponent taking
 * `.hass` — including card-shaped editors (studio), which are mounted
 * through the normal setConfig(hass) card lifecycle.
 *
 * Config (all optional):
 *   editor: hfs | studio — which adapter's panel to embed; absent →
 *     the backend resolves the configured/default editor
 *   element — custom element to mount (overrides the adapter's)
 *   module — JS module URL imported once before mounting
 *   card_config — forwarded to setConfig() when the embedded element
 *     is itself a Lovelace card
 *   height — embed height (default 72vh)
 */

const FP_CONFIG_WS = 'ramses_extras/floorplan_helper/get_config';

const EMBED_STYLE = `
  :host { display: block; }
  ha-card { padding: 0; overflow: hidden; }
  .frame { width: 100%; }
  .err { padding: 16px; font-size: 13px;
         color: var(--error-color, #db4437); }
`;

class RamsesEditorEmbed extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this._el = null; // mounted editor element
    this._mounting = false;
    this._error = '';
    this._narrowMql = window.matchMedia('(max-width: 870px)');
    this._onNarrow = () => this._applyNarrow();
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._el) this._el.hass = hass;
    if (hass && !this._el && !this._mounting && !this._error) {
      this._mount();
    }
  }

  connectedCallback() {
    this._narrowMql.addEventListener?.('change', this._onNarrow);
  }

  disconnectedCallback() {
    this._narrowMql.removeEventListener?.('change', this._onNarrow);
    // keep this._el — lovelace re-parents cards on layout reflows and
    // _render() re-appends it, so the editor survives the move
  }

  getCardSize() {
    return 12;
  }

  static getConfigElement() {
    return document.createElement('div'); // no visual editor
  }

  static getStubConfig() {
    return {};
  }

  async _resolveTarget() {
    // Manual overrides win — lets the card embed an editor the backend
    // does not know (a future adapter-less panel, say).
    if (this._config.element) {
      return {
        element: this._config.element,
        module: this._config.module || '',
      };
    }
    const cfg = await this._hass.callWS({
      type: FP_CONFIG_WS,
      ...(this._config.editor ? { editor: this._config.editor } : {}),
    });
    const caps = cfg.editor_caps || {};
    return {
      element: this._config.element || caps.panel_element || '',
      module: this._config.module || caps.panel_module || '',
    };
  }

  async _mount() {
    this._mounting = true;
    try {
      const target = await this._resolveTarget();
      if (!target.element) {
        throw new Error(
          `editor '${this._config.editor || 'auto'}' has no embeddable element`
        );
      }
      if (target.module) {
        // same-origin only — a yaml `module:` field must not become a
        // way to import a script from another origin
        const url = new window.URL(target.module, window.location.origin);
        if (url.origin !== window.location.origin) {
          throw new Error(`module must be same-origin, got ${target.module}`);
        }
        await import(url.href);
      }
      if (!customElements.get(target.element)) {
        throw new Error(`<${target.element}> is not defined`);
      }
      const el = document.createElement(target.element);
      // panel_custom-style props first (hfs's panel reads hass/narrow);
      // harmless on plain card elements
      el.hass = this._hass;
      el.narrow = this._narrowMql.matches;
      el.panel = { config: {} };
      el.route = window.location.pathname;
      // card-shaped editors (studio) take the Lovelace card lifecycle
      if (typeof el.setConfig === 'function') {
        el.setConfig({
          type: `custom:${target.element}`,
          ...(this._config.card_config || {}),
        });
      }
      this._el = el;
      this._error = '';
    } catch (err) {
      this._error = `ramses-editor-embed: ${err.message || err}`;
    } finally {
      this._mounting = false;
      this._render();
    }
  }

  _applyNarrow() {
    if (this._el) this._el.narrow = this._narrowMql.matches;
  }

  _render() {
    const height = this._config.height || '72vh';
    this.shadowRoot.innerHTML = `
      <style>${EMBED_STYLE}</style>
      <ha-card>
        ${this._error
          ? `<div class="err">${this._error}</div>`
          : '<div class="frame"></div>'}
      </ha-card>`;
    if (this._el && !this._error) {
      const frame = this.shadowRoot.querySelector('.frame');
      frame.style.height = height;
      this._el.style.height = '100%';
      this._el.style.display = 'block';
      // hfs's panels size themselves to --fp-editor-height (fallback
      // calc(100vh - 150px) assumes a full page); bound it to the card
      // minus their toolbar so the side panel's own scrollbar engages
      this._el.style.setProperty(
        '--fp-editor-height',
        `calc(${height} - 64px)`
      );
      frame.appendChild(this._el);
    }
  }
}

customElements.define('ramses-editor-embed', RamsesEditorEmbed);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ramses-editor-embed',
  name: 'Ramses Editor Embed',
  description: 'Embed a panel-style plan editor (e.g. ha-floorplan-studio) on a dashboard',
});
