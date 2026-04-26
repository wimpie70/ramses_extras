/**
 * Scenarios tab — config toggles, conversation playback settings,
 * stub scenario cards.
 */

import {
  SCENARIO_MANUAL_DEVICE,
  SCENARIO_LOAD_PROFILE,
  SCENARIO_PROFILE_EMISSIONS,
  SCENARIO_DEVICE_PLAYBACK,
} from "../constants.js";

export function buildSavedPlaybacksPanel(card) {
  const list = card._savedPlaybacks || [];
  const query = (card._playbackSearchQuery || "").toLowerCase().trim();
  const filteredList = query
    ? list.filter((p) => p.id.toLowerCase().includes(query))
    : list;
  const builtinCount = list.filter((p) => p.builtin).length;
  const userCount = list.length - builtinCount;
  const header = `
    <div style="margin-top:8px; font-size:0.85em; color:var(--secondary-text-color);">
      <strong>Saved playbacks</strong>
      <span style="margin-left:6px;">(${builtinCount} built-in, ${userCount} imported)</span>
    </div>
    <div style="margin-top:4px;">
      <input type="text"
             placeholder="Search conversations..."
             value="${card._playbackSearchQuery || ""}"
             data-action="playback-search"
             style="width:100%; padding:4px 8px; border:1px solid var(--divider-color,#eee); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color); font-size:0.8em;" />
    </div>`;
  if (!list.length) {
    return `${header}
      <div style="font-size:0.8em; color:var(--secondary-text-color); padding:4px 0;">
        None yet. Paste a log above and click <em>Save</em> to keep it.
      </div>`;
  }
  if (!filteredList.length) {
    return `${header}
      <div style="font-size:0.8em; color:var(--secondary-text-color); padding:4px 0;">
        No matching conversations.
      </div>`;
  }
  const rows = filteredList.map((p) => {
    const builtinTag = p.builtin
      ? `<span class="chip muted" style="font-size:0.65em;">built-in</span>`
      : "";
    const editBtn = `<button class="btn btn-secondary" style="padding:2px 8px; font-size:0.75em;"
             data-action="load-playback-editor" data-identifier="${p.id}"
             title="Load frames into the editor above (${p.builtin ? "saves as a new copy" : "edit and save as new name"})">Edit</button>`;
    const deleteBtn = p.builtin
      ? ""
      : `<button class="btn btn-danger" style="padding:2px 8px; font-size:0.75em;"
                 data-action="delete-saved-playback" data-identifier="${p.id}">Delete</button>`;
    return `
      <div style="display:flex; justify-content:space-between; align-items:center; padding:4px 0; border-top:1px solid var(--divider-color,#eee); gap:6px;">
        <div style="display:flex; flex-direction:column; font-size:0.8em; flex:1;">
          <div style="display:flex; align-items:center; gap:6px;">
            <strong>${p.id}</strong>${builtinTag}
          </div>
          <span style="color:var(--secondary-text-color);">
            ${p.frames} frame${p.frames === 1 ? "" : "s"} · ${(p.peers || []).join(", ") || "no peers"}
          </span>
        </div>
        <div style="display:flex; gap:4px;">${editBtn}${deleteBtn}</div>
      </div>`;
  }).join("");
  return `${header}<div style="margin-top:4px; max-height:300px; overflow-y:auto;">${rows}</div>`;
}

export function buildConversationPlaybackSettingsCard(card) {
  const draft = card._playbackImportDraft || {};
  const logContent = draft.log_content || "";
  const nameValue = draft.name || "";
  const canSave = Boolean(logContent.trim());
  const savingState = card._playbackSaving
    ? `<span class="chip muted" style="margin-left:6px;">Saving…</span>`
    : "";
  return `
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <strong>Conversation Playback</strong>
        ${savingState}
      </div>
      <div class="scenario-description">
        Import a ramses.log and save it as a reusable conversation. Run/pause/stop playback from the <em>Devices</em> tab.
      </div>
      <div class="scenario-field">
        <label for="playback-log-content">Log content (paste ramses.log)</label>
        <textarea id="playback-log-content"
                  data-action="playback-import-field" data-field="log_content"
                  rows="6" placeholder="Paste ramses.log content here...">${logContent}</textarea>
      </div>
      <div class="scenario-field">
        <label for="playback-name">Save as name</label>
        <input id="playback-name" type="text"
               data-action="playback-import-field" data-field="name"
               placeholder="my_playback" value="${nameValue}" />
      </div>
      ${buildSavedPlaybacksPanel(card)}
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="btn btn-primary" data-action="save-playback-import" ${canSave ? "" : "disabled"}>Save</button>
        <button class="btn btn-secondary" data-action="clear-playback-import" ${canSave || nameValue ? "" : "disabled"}>Clear</button>
      </div>
    </div>`;
}

export function buildScenarios(card) {
  const registry = card._scenarioRegistry;
  const ids = Object.keys(registry);
  if (!ids.length) return `<div style="color: var(--secondary-text-color); padding: 8px 0;">No scenarios available.</div>`;

  const psChecked = card._preserveState ? " checked" : "";
  const psCard = `
    <div class="card ${card._preserveState ? "active" : ""}">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div><strong>Preserve state on reload / Clean restart</strong></div>
        <label class="toggle">
          <ha-switch data-action="toggle-preserve-state"${psChecked}></ha-switch>
        </label>
      </div>
      <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-top: 4px;">When on: simulator state (auto-answer, answer unknown devices) persists across reloads. When off (Clean restart): state is reset on reload (auto-answer disabled, clean known list).</div>
    </div>`;

  const aaChecked = card._autoAnswer ? " checked" : "";
  const aaCard = `
    <div class="card ${card._autoAnswer ? "active" : ""}">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div><strong>Auto Answer (RQ&#8594;RP)</strong></div>
        <label class="toggle">
          <ha-switch data-action="toggle-auto-answer"${aaChecked}></ha-switch>
        </label>
      </div>
      <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-top: 4px;">When off: simulator receives RQ frames but never replies &#8212; simulates broken ESP or powered-off device.</div>
    </div>`;

  const auChecked = card._answerUnknownDevices ? " checked" : "";
  const auCard = `
    <div class="card ${card._answerUnknownDevices ? "active" : ""}">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div><strong>Answer Unknown Devices</strong></div>
        <label class="toggle">
          <ha-switch data-action="toggle-answer-unknown"${auChecked}></ha-switch>
        </label>
      </div>
      <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-top: 4px;">When on: simulator responds to RQ frames for devices not in the active device list. Uses device DB to infer device type and generate responses.</div>
    </div>`;

  const rfStatus = card._rfEnforceKnownList
    ? `<span style="color: var(--warning-color); font-weight: 600;">ENFORCED</span>`
    : `<span style="color: var(--success-color); font-weight: 600;">NOT ENFORCED</span>`;
  const rfCard = `
    <div class="card" style="background: var(--secondary-background-color);">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <div><strong>RF Client: Accept only known devices</strong></div>
        <div>${rfStatus}</div>
      </div>
      <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-top: 4px;">RF client ${card._rfEnforceKnownList ? "will only accept messages from devices in its known_list" : "accepts messages from any device"}. ${card._rfKnownListEnabled ? `Known list is configured with entries.` : "No known list configured."}</div>
    </div>`;

  const scenarioCards = ids
    .filter(id =>
      id !== "auto_answer"
      && id !== SCENARIO_MANUAL_DEVICE
      && id !== SCENARIO_LOAD_PROFILE
      && id !== SCENARIO_PROFILE_EMISSIONS
      && id !== "device_suite"
      && id !== SCENARIO_DEVICE_PLAYBACK
    )
    .map((id) => {
      const meta = registry[id];
      const isRunning = (card._runningScenarios || []).includes(id);
      const runningMeta = (card._runningMetadata || {})[id] || {};
      const isPaused = Boolean(runningMeta.paused);
      const conflicts = card._scenarioConflicts(id);
      const conflictWarn = conflicts.length
        ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">&#9888; Conflicts with: ${conflicts.join(", ")}</div>`
        : "";
      const disabledAttr = conflicts.length ? " disabled" : "";
      let actionBtns;
      if (meta.toggleable) {
        const checked = isRunning ? " checked" : "";
        const disSwitch = (!isRunning && conflicts.length) ? " disabled" : "";
        actionBtns = `
          <label class="toggle" style="display:flex; align-items:center; gap:6px;">
            <ha-switch data-action="toggle-scenario" data-scenario-id="${id}"${checked}${disSwitch}></ha-switch>
            <span style="font-size:0.75em; color:var(--secondary-text-color);">${isRunning ? "enabled" : "disabled"}</span>
          </label>`;
      } else if (isRunning) {
        actionBtns = `<button class="btn btn-danger" data-action="stop-scenario" data-scenario-id="${id}">Stop</button>`;
      } else {
        actionBtns = `<button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${id}"${disabledAttr}>Run</button>`;
      }
      const runningBadge = isRunning
        ? `<span style="font-size:0.75em; padding:2px 8px; border-radius:10px; background:${isPaused ? "var(--warning-color,#ff9800)" : "var(--success-color,#4caf50)"}; color:white;">${isPaused ? "paused" : "active"}</span>`
        : "";
      return `
        <div class="card ${isRunning ? "active" : ""}">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong>${meta.label || id}</strong>
            ${runningBadge}
          </div>
          <div class="scenario-description">${meta.description || "No description"}</div>
          ${conflictWarn}
          ${card._buildScenarioParamsById(id)}
          <div style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">${actionBtns}</div>
        </div>`;
    }).join("");

  const playbackCard = buildConversationPlaybackSettingsCard(card);
  return `<div class="grid">${psCard}${aaCard}${auCard}${rfCard}${playbackCard}${scenarioCards}</div>`;
}
