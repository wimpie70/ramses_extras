export function logExplorerCardStyle({ wrapCss }) {
  const gridCols = '1fr';

  return `
    :host { display: block; width: 100%; min-width: 0; max-width: 100%; }
    ha-card { width: 100%; }

    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .row input[type="text"] { min-width: 220px; }
    .row input.small { width: 70px; }
    .row select { min-width: 260px; flex: 1; }

    .muted { font-size: 12px; opacity: 0.8; }
    .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

    .grid { display: grid; grid-template-columns: ${gridCols}; gap: 12px; margin-top: 12px; }
    .grid > div { min-width: 0; }

    pre {
      margin: 0;
      padding: 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      overflow: auto;
      max-width: 100%;
      white-space: ${wrapCss};
      max-height: 320px;
      user-select: text;
      -webkit-user-select: text;
    }

    dialog { width: 98vw; max-width: 98vw; height: 90vh; max-height: 90vh; resize: both; overflow: auto; }
    dialog pre { max-height: 70vh; white-space: pre-wrap; }

    button { cursor: pointer; }

    .hl-line { display: inline; }
    .hl-match { background: rgba(255, 235, 59, 0.35); border-radius: 3px; padding: 0 1px; }
    .hl-warning { color: var(--warning-color, #c77f00); }
    .hl-error { color: var(--error-color); }
    .hl-source { color: #1f7a1f; font-weight: 600; }
    .hl-id { background: var(--dev-bg, rgba(33, 150, 243, 0.18)); border-radius: 4px; padding: 0 2px; }
    .hl-traceback { background: rgba(244, 67, 54, 0.08); }
    .hl-traceback-header { font-weight: 700; }
    .hl-traceback-file { text-decoration: underline; text-decoration-style: dotted; }
    .separator {
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
    :host { display: block; width: 100%; min-width: 0; max-width: 100%; }
    ha-card { width: 100%; }

    .meta { display: flex; gap: 12px; font-size: 12px; opacity: 0.8; flex-wrap: ${metaWrap}; }
    .controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .controls input { width: 110px; }
    .controls input.small { width: 80px; }
    .controls button { cursor: pointer; }

    .table-wrap { width: 100%; max-height: 420px; overflow: auto; margin-top: 12px; border: 1px solid var(--divider-color); border-radius: 6px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
    th { text-align: left; font-weight: 600; }
    th.sortable { cursor: pointer; user-select: none; }
    th.sortable:hover { text-decoration: underline; }
    tr.flow-row:hover { background: rgba(0,0,0,0.06); }

    td.device-cell { background: var(--dev-bg, transparent); }
    .dev { display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
    .dev .id { font-family: var(--code-font-family, monospace); font-size: 12px; }
    .alias { font-size: 12px; opacity: 0.9; }
    .slug { font-size: 11px; opacity: 0.75; }
    .select-cell { text-align: center; width: 40px; }
    .select-cell input[type="checkbox"] { cursor: pointer; }
    .codes { font-family: var(--code-font-family, monospace); font-size: 12px; white-space: normal; word-break: break-word; }
    .actions { white-space: nowrap; }
    .actions button { cursor: pointer; margin-right: 6px; }

    .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

    dialog { width: 98vw; max-width: 98vw; height: 90vh; max-height: 90vh; resize: both; overflow: auto; }
    dialog form { display: flex; flex-direction: column; height: 100%; }
    dialog pre { white-space: pre-wrap; word-break: break-word; overflow: auto; max-height: 70vh; }
    #logContainer { width: 100%; flex: 1; min-height: 0; }
    #messagesContainer { width: 100%; flex: 1; min-height: 0; overflow: auto; }
    .messages-list { display: flex; flex-direction: column; height: 100%; }
    .messages-header { padding: 8px 0; border-bottom: 1px solid var(--divider-color); margin-bottom: 8px; }
    .messages-table-wrapper { overflow: auto; flex: 1; }
    .messages-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; }
    .messages-table th, .messages-table td { padding: 4px 6px; border: 1px solid var(--divider-color); vertical-align: top; white-space: nowrap; }
    .messages-table th { background: var(--secondary-background-color); position: sticky; top: 0; z-index: 1; }
    .messages-table .col-time { width: 140px; font-size: 11px; }
    .messages-table .col-verb { width: 40px; text-align: center; }
    .messages-table .col-code { width: 50px; text-align: center; }
    .messages-table .col-src { width: 110px; background: var(--dev-bg); color: var(--dev-fg); }
    .messages-table .col-dst { width: 110px; background: var(--dev-bg); color: var(--dev-fg); }
    .messages-table .col-bcast { width: 60px; text-align: center; }
    .messages-table .col-payload { width: auto; min-width: 300px; white-space: pre; overflow-x: auto; user-select: text; -webkit-user-select: text; }
    .messages-table td { user-select: text; -webkit-user-select: text; }
    dialog pre { user-select: text; -webkit-user-select: text; }
  `;
}
