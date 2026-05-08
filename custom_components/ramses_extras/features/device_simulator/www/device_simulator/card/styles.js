/**
 * Device Simulator Card - shared CSS string.
 */

export const CARD_STYLE = `
  :host { display: block; padding: 16px; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .title { font-size: 1.2em; font-weight: 500; }
  .badge { padding: 4px 12px; border-radius: 12px; font-size: 0.75em; text-transform: uppercase; }
  .badge.active { background: var(--success-color, #4caf50); color: white; }
  .badge.running { background: var(--primary-color, #03a9f4); color: white; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
  .tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--divider-color); }
  .tab { padding: 12px 16px; cursor: pointer; border-bottom: 2px solid transparent; font-size: 0.9em; }
  .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  .content { display: none; }
  .content.active { display: block; }
  .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85em; transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s; }
  .btn:hover { opacity: 0.85; }
  .btn:active { transform: scale(0.95); opacity: 0.7; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); }
  .btn-primary { background: var(--primary-color); color: var(--text-primary-color); }
  .btn-secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
  .btn-danger { background: var(--error-color); color: white; }
  button { cursor: pointer; transition: transform 0.15s, opacity 0.15s; }
  button:hover { opacity: 0.85; }
  button:active { transform: scale(0.95); opacity: 0.7; }
  .grid { display: grid; gap: 12px; }
  .devices-grid { grid-template-columns: repeat(auto-fit, minmax(720px, 1fr)); }
  .card { border: 1px solid var(--divider-color); border-radius: 8px; padding: 16px; }
  .card:hover { border-color: var(--primary-color); }
  .card.active { border-color: var(--success-color); background: var(--success-color-light); }
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
  .stat { background: var(--secondary-background-color); padding: 16px; border-radius: 8px; text-align: center; }
  .stat-value { font-size: 1.5em; font-weight: 600; color: var(--primary-color); }
  .event-log { max-height: 300px; overflow-y: auto; border: 1px solid var(--divider-color); border-radius: 8px; }
  .event { display: flex; gap: 12px; padding: 8px; border-bottom: 1px solid var(--divider-color); font-size: 0.85em; }
  .event.unavailable { background: var(--error-color-light); border-left: 3px solid var(--error-color); }
  .event-type { padding: 2px 6px; border-radius: 4px; font-size: 0.75em; text-transform: uppercase; }
  .event-type.rx { background: var(--success-color-light); color: var(--success-color); }
  .event-type.tx { background: var(--info-color-light); color: var(--info-color); }
  .event-type.unavailable { background: var(--error-color-light); color: var(--error-color); }
  .device-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
  .device-emitter { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 6px; font-size: 0.8em; }
  .toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 0.85em; }
  .codes-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; align-items: center; }
  .code-chip { display: flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
  .code-chip button { background: none; border: none; cursor: pointer; padding: 0; font-size: 0.9em; color: var(--secondary-text-color); line-height: 1; }
  .add-code { display: flex; gap: 4px; margin-top: 4px; }
  .add-code input { padding: 3px 6px; border: 1px solid var(--divider-color); border-radius: 4px; font-size: 0.8em; width: 80px; background: var(--card-background-color); color: var(--primary-text-color); }
  .device-controls { margin-bottom: 16px; }
  .device-list-empty { color: var(--secondary-text-color); padding: 8px 0; }
  .profile-missing { margin-top: 12px; padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); display: flex; flex-direction: column; gap: 8px; }
  .profile-missing strong { font-size: 0.85em; color: var(--secondary-text-color); }
  .profile-missing-entry { display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; font-size: 0.8em; }
  .speed-card { display:flex; flex-direction:column; gap:10px; }
  .speed-card .speed-controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .speed-card input[type='range'] { width:200px; }
  .speed-card input[type='number'] { width:90px; padding:4px; border:1px solid var(--divider-color); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color); }
  .speed-card button { font-size:0.8em; }
  .chip { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 0.7em; font-weight: 600; text-transform: uppercase; }
  .chip.profile { background: var(--primary-color); color: white; }
  .chip.manual { background: var(--info-color, #0288d1); color: white; }
  .chip.known { background: var(--success-color, #388e3c); color: white; }
  .chip.sensor { background: var(--warning-color, #ffa000); color: #000; }
  .chip.reply { background: var(--info-color, #0288d1); color: #fff; }
  .chip.disabled { background: var(--divider-color); color: var(--secondary-text-color); }
  .chip.muted { background: var(--divider-color); color: var(--secondary-text-color); }
  .chip.source { background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .chip.emitting { background: var(--success-color, #388e3c); color: #fff; }
  .chip.idle { background: var(--warning-color, #ffa000); color: #000; }
  .chip.silenced { background: var(--error-color, #f44336); color: #fff; }
  .entity-pill { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 0.7em; font-weight: 600; cursor: pointer; transition: transform 0.1s, opacity 0.1s; }
  .entity-pill:hover { transform: scale(1.05); opacity: 0.8; }
  .btn[disabled] { opacity: 0.6; cursor: not-allowed; }
  .scenario-form { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
  .scenario-field { display: flex; flex-direction: column; gap: 4px; font-size: 0.8em; }
  .scenario-field label { color: var(--secondary-text-color); font-weight: 600; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .scenario-field input[type="text"],
  .scenario-field input[type="search"],
  .scenario-field input[type="number"] { padding: 4px 8px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }
  .scenario-field select { padding: 4px 8px; border: 1px solid var(--divider-color); border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color); font-size: 0.9em; }
  .scenario-field textarea { padding: 8px; border: 1px solid var(--divider-color); border-radius: 6px; min-height: 140px; font-family: var(--code-font-family, 'Fira Code', monospace); font-size: 0.85em; background: var(--card-background-color); color: var(--primary-text-color); resize: vertical; line-height: 1.35; }
  .scenario-field--checkbox { flex-direction: row; align-items: center; gap: 8px; }
  .scenario-field--checkbox label { font-weight: 500; margin: 0; }
  .scenario-description { margin-top: 6px; font-size: 0.8em; color: var(--secondary-text-color); }
  .msg-log {
    font-family: var(--code-font-family, 'Fira Code', monospace);
    font-size: 0.75em;
    max-height: 260px;
    overflow: auto;
    border: 1px solid var(--divider-color);
    border-radius: 6px;
    width: 100%;
    max-width: 100%;
  }
  .msg-log-table { width: max-content; min-width: 100%; border-collapse: collapse; }
  .msg-log-table th,
  .msg-log-table td { padding: 4px 8px; white-space: nowrap; border-bottom: 1px solid var(--divider-color); text-align: left; user-select: text; -webkit-user-select: text; }
  .msg-log-table thead th { font-weight: 600; color: var(--secondary-text-color); font-size: 0.78em; background: var(--secondary-background-color); position: sticky; top: 0; z-index: 1; }
  .msg-log-table tbody tr:last-child td { border-bottom: none; }
  .msg-log-table tbody tr.in td { background: rgba(var(--rgb-success-color, 76,175,80), 0.07); }
  .msg-log-table tbody tr.out td { background: rgba(var(--rgb-info-color, 3,169,244), 0.07); }
  /* Origin-based row tinting (overrides direction tint where applicable). */
  .msg-log-table tbody tr.origin-rf         td { background: rgba(76, 175, 80, 0.10); }
  .msg-log-table tbody tr.origin-sim        td { background: rgba(3, 169, 244, 0.10); }
  .msg-log-table tbody tr.origin-auto_answer td { background: rgba(255, 152, 0, 0.14); }
  .msg-log-table tbody tr.origin-auto_emit  td { background: rgba(156, 39, 176, 0.12); }
  .msg-origin { font-weight: 600; font-size: 0.72em; text-transform: uppercase; padding: 1px 6px; border-radius: 8px; letter-spacing: 0.02em; white-space: nowrap; }
  .msg-origin.origin-rf         { background: rgba(76, 175, 80, 0.20); color: #2e7d32; }
  .msg-origin.origin-sim        { background: rgba(3, 169, 244, 0.20); color: #01579b; }
  .msg-origin.origin-auto_answer { background: rgba(255, 152, 0, 0.25); color: #e65100; }
  .msg-origin.origin-auto_emit  { background: rgba(156, 39, 176, 0.22); color: #6a1b9a; }
  .msg-dir { font-weight: 700; font-size: 0.8em; text-transform: uppercase; }
  .msg-dir.in { color: var(--success-color, #4caf50); }
  .msg-dir.out { color: var(--info-color, #0288d1); }
  .msg-verb { font-weight: 600; color: var(--primary-color); }
  .msg-code { font-weight: 600; }
  .msg-addr { color: var(--secondary-text-color); font-size: 0.9em; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
  .msg-payload { color: var(--secondary-text-color); font-size: 0.9em; overflow: hidden; text-overflow: ellipsis; max-width: 300px; }
  .msg-ts { color: var(--disabled-color, #9e9e9e); font-size: 0.85em; }
  .msg-log-empty { padding: 12px; color: var(--secondary-text-color); font-size: 0.85em; }
  .msg-log-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
  .msg-log-header-row { display:flex; align-items:center; justify-content: space-between; gap:8px; margin-bottom:6px; }
  .msg-log-header-row button { font-size:0.7em; padding:4px 8px; }
`;
