export function logExplorerCardStyle({ wrapCss }) {
  const gridCols = '1fr';

  return `
    :host { display: block; width: 100%; min-width: 1200px; max-width: none; }
    ha-card { width: 100%; }

    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .row input[type="text"] { min-width: 220px; }
    .row input.small { width: 70px; }
    .row select { min-width: 260px; flex: 1; }

    .muted { font-size: 12px; opacity: 0.8; }
    .error { color: var(--error-color); margin-top: 8px; white-space: pre-wrap; }

    .grid { display: grid; grid-template-columns: ${gridCols}; gap: 12px; margin-top: 12px; }

    pre {
      margin: 0;
      padding: 10px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      overflow: auto;
      white-space: ${wrapCss};
      max-height: 320px;
    }

    dialog { width: 98vw; max-width: 98vw; height: 90vh; max-height: 90vh; resize: both; overflow: auto; }
    dialog pre { max-height: 70vh; }

    button { cursor: pointer; }

    .hl-line { display: inline; }
    .hl-match { background: rgba(255, 235, 59, 0.35); border-radius: 3px; padding: 0 1px; }
    .hl-warning { color: var(--warning-color, #c77f00); }
    .hl-error { color: var(--error-color); }
  `;
}

export function trafficAnalyserCardStyle({ compact }) {
  const metaWrap = compact ? 'wrap' : 'nowrap';

  return `
    :host { display: block; width: 100%; min-width: 1200px; max-width: none; }
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
    .verbs { font-family: var(--code-font-family, monospace); font-size: 12px; white-space: normal; word-break: break-word; }
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
    .messages-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .messages-table th, .messages-table td { padding: 4px 6px; border: 1px solid var(--divider-color); vertical-align: top; }
    .messages-table th { background: var(--secondary-background-color); position: sticky; top: 0; z-index: 1; }
    .payload-cell { font-family: monospace; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .source-cell { font-weight: bold; }
  `;
}
