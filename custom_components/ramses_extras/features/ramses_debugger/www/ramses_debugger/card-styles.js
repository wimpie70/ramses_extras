/**
 * Common base styles shared across all debugger cards.
 */
function getBaseCardStyles() {
  return `
    :host { display: block; width: 100%; min-width: 0; max-width: 100%; }
    ha-card {
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    button { cursor: pointer; }
    dialog {
      width: 90vw;
      max-width: 90vw;
      height: 80vh;
      max-height: 80vh;
      resize: both;
      overflow: auto;
    }
    dialog pre {
      white-space: pre-wrap;
      word-break: break-word;
      overflow: auto;
      max-height: 70vh;
      user-select: text;
      -webkit-user-select: text;
    }
  `;
}

export function logExplorerCardStyle({ wrapCss }) {
  const gridCols = '1fr';

  return `
    ${getBaseCardStyles()}
    :host { height: 700px; }

    .r-xtrs-log-xp-card-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      padding: 16px;
    }

    .r-xtrs-log-xp-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .r-xtrs-log-xp-row input[type="text"] { min-width: 220px; }
    .r-xtrs-log-xp-row input.small { width: 70px; }
    .r-xtrs-log-xp-row select { min-width: 260px; flex: 1; }

    .r-xtrs-log-xp-muted { font-size: var(--ha-font-size-xs); opacity: 0.8; }
    .r-xtrs-log-xp-error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

    .r-xtrs-log-xp-grid { display: grid; grid-template-columns: ${gridCols}; gap: 12px; margin-top: 12px; }
    .r-xtrs-log-xp-grid > div { min-width: 0; }

    .r-xtrs-log-xp-scrollable-section {
      flex: 1;
      overflow: auto;
      min-height: 0;
    }

    pre {
      margin: 0;
      padding: 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      overflow: auto;
      max-width: 100%;
      white-space: ${wrapCss};
      user-select: text;
      -webkit-user-select: text;
    }

    dialog { width: 98vw; max-width: 98vw; height: 90vh; max-height: 90vh; overflow: hidden; }
    dialog form { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
    dialog pre { max-height: 70vh; flex-shrink: 0; }
    #zoomResults { flex: 1; overflow: auto; min-height: 0; }

    .r-xtrs-log-xp-hl-line { display: inline; }

    .r-xtrs-log-xp-result-block { margin-bottom: 16px; }
    .r-xtrs-log-xp-result-header {
      padding: 4px 8px;
      background: var(--secondary-background-color, rgba(0,0,0,0.02));
      border-radius: 4px 4px 0 0;
      border: 1px solid var(--divider-color);
      border-bottom: none;
    }
    .r-xtrs-log-xp-result-controls button {
      font-size: var(--ha-font-size-xs, 12px);
      padding: 4px 8px;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      background: var(--primary-background-color);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .r-xtrs-log-xp-result-controls button:hover {
      background: var(--secondary-background-color);
    }
    .r-xtrs-log-xp-result-block .r-xtrs-log-xp-result-pre {
      border-radius: 0 0 4px 4px;
      border-top: none;
      margin: 0;
      position: relative;
    }
    .r-xtrs-log-xp-line-numbers {
      padding-left: 60px;
    }
    .r-xtrs-log-xp-line-numbers .r-xtrs-log-xp-line {
      position: relative;
      white-space: pre;
    }
    .r-xtrs-log-xp-line-numbers .r-xtrs-log-xp-line::before {
      content: attr(data-line);
      position: absolute;
      left: -60px;
      width: 50px;
      text-align: right;
      color: var(--secondary-text-color);
      font-family: var(--code-font-family, monospace);
      font-size: var(--ha-font-size-xs);
      user-select: none;
    }
    .r-xtrs-log-xp-hl-match { background: rgba(255, 235, 59, 0.35); border-radius: 3px; padding: 0 1px; }
    .r-xtrs-log-xp-hl-warning { color: var(--warning-color, #c77f00); }
    .r-xtrs-log-xp-hl-error { color: var(--error-color); }
    .r-xtrs-log-xp-hl-source { color: #1f7a1f; font-weight: 600; }
    .r-xtrs-log-xp-hl-id { background: var(--dev-bg, rgba(33, 150, 243, 0.18)); border-radius: 4px; padding: 0 2px; }
    .r-xtrs-log-xp-hl-traceback { background: rgba(244, 67, 54, 0.08); }
    .r-xtrs-log-xp-hl-traceback-header { font-weight: 700; }
    .r-xtrs-log-xp-hl-traceback-file { text-decoration: underline; text-decoration-style: dotted; }
    .r-xtrs-log-xp-separator {
      height: 2px;
      width: 100%;
      background: var(--divider-color, #9e9e9e);
      opacity: 0.7;
      border-radius: 1px;
      margin: 12px 0;

    }
  `;
}

export function trafficAnalyserCardStyle({ compact }) {
  const metaWrap = compact ? 'wrap' : 'nowrap';

  return `
    ${getBaseCardStyles()}
    :host { height: 700px; font-size: var(--ha-font-size-xs); }

    .r-xtrs-traf-nlysr-card-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      padding: 16px;
    }

    .r-xtrs-traf-nlysr-meta { display: flex; gap: 12px; font-size: var(--ha-font-size-xs); opacity: 0.8; flex-wrap: ${metaWrap}; }
    .r-xtrs-traf-nlysr-controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .r-xtrs-traf-nlysr-controls input { width: 110px; }
    .r-xtrs-traf-nlysr-controls input.small { width: 80px; }

    .r-xtrs-traf-nlysr-table-wrap {
      flex: 1;
      overflow: auto;
      margin-top: 12px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      min-height: 0;
    }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
    th { text-align: left; font-weight: 600; }
    th.r-xtrs-msg-viewer-sortable { cursor: pointer; user-select: none; }
    th.r-xtrs-msg-viewer-sortable:hover { text-decoration: underline; }
    tr.r-xtrs-traf-nlysr-flow-row:hover { background: rgba(0,0,0,0.06); }

    td.r-xtrs-traf-nlysr-device-cell { background: var(--dev-bg, transparent); }
    .r-xtrs-traf-nlysr-dev { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
    .r-xtrs-traf-nlysr-dev .r-xtrs-traf-nlysr-id { font-family: var(--code-font-family, monospace); font-size: var(--ha-font-size-xs); }
    .r-xtrs-traf-nlysr-alias { font-size: var(--ha-font-size-xs); opacity: 0.9; }
    .r-xtrs-traf-nlysr-slug { font-size: 11px; opacity: 0.75; }
    .r-xtrs-traf-nlysr-select-cell { text-align: center; width: 40px; }
    .r-xtrs-traf-nlysr-select-cell input[type="checkbox"] { cursor: pointer; }
    .r-xtrs-traf-nlysr-codes { font-family: var(--code-font-family, monospace); font-size: var(--ha-font-size-xs); white-space: normal; word-break: break-word; }
    .r-xtrs-traf-nlysr-actions { white-space: nowrap; }
    .r-xtrs-traf-nlysr-actions button { cursor: pointer; margin-right: 6px; }

    .r-xtrs-traf-nlysr-error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

    dialog { height: 600px; max-height: 600px; }
    dialog form { display: flex; flex-direction: column; height: 100%; }
    #logContainer { width: 100%; flex: 1; min-height: 0; }
    #messagesContainer { width: 100%; flex: 1; min-height: 0; overflow: auto; }
    .r-xtrs-traf-nlysr-messages-list { display: flex; flex-direction: column; height: 100%; }
    .r-xtrs-traf-nlysr-messages-header { padding: 8px 0; border-bottom: 1px solid var(--divider-color); margin-bottom: 8px; }
    .r-xtrs-traf-nlysr-messages-table-wrapper { overflow: auto; flex: 1; }
    .r-xtrs-traf-nlysr-messages-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: var(--ha-font-size-xs); }
    .r-xtrs-traf-nlysr-messages-table th, .r-xtrs-traf-nlysr-messages-table td { padding: 4px 6px; border: 1px solid var(--divider-color); vertical-align: top; white-space: nowrap; }
    .r-xtrs-traf-nlysr-messages-table th { background: var(--secondary-background-color); position: sticky; top: 0; z-index: 1; }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-time { width: 140px; font-size: 11px; }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-verb { width: 40px; text-align: center; }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-code { width: 50px; text-align: center; }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-src { width: 110px; background: var(--dev-bg); color: var(--dev-fg); }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-dst { width: 110px; background: var(--dev-bg); color: var(--dev-fg); }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-bcast { width: 60px; text-align: center; }
    .r-xtrs-traf-nlysr-messages-table .r-xtrs-traf-nlysr-col-payload { width: auto; min-width: 300px; white-space: pre; overflow-x: auto; user-select: text; -webkit-user-select: text; }
    .r-xtrs-traf-nlysr-messages-table td { user-select: text; -webkit-user-select: text; }
    dialog pre { user-select: text; -webkit-user-select: text; }
  `;
}
