/**
 * Scenarios tab — selectable scenarios (including playback + manual injection)
 * + playback import editor.
 *
 * Each scenario renders as a card with inline config params and a "Select"
 * button. Only one scenario can be armed at a time (tracked via
 * `card._selectedScenarioId`, persisted in localStorage). Run/Pause/Stop for
 * the armed scenario happen on the Devices tab.
 */

import {
  SCENARIO_MANUAL_DEVICE,
  SCENARIO_LOAD_PROFILE,
  SCENARIO_PROFILE_EMISSIONS,
  SCENARIO_DEVICE_PLAYBACK,
} from "../constants.js";

// ========== Playback import editor ==========

function buildSavedPlaybacksPanel(card) {
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
             title="Load frames into the editor above">Edit</button>`;
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

function buildPlaybackImportCard(card) {
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
        <strong>Import a conversation playback</strong>
        ${savingState}
      </div>
      <div class="scenario-description">
        Paste a ramses.log and save it as a reusable conversation. It becomes selectable on the <em>Device Playback</em> scenario below.
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

// ========== Scenario cards ==========

function buildSelectChip(card, scenarioId) {
  return card._selectedScenarioId === scenarioId
    ? `<span class="chip profile" title="Armed — run from Devices tab">Selected</span>`
    : "";
}

function buildSelectButton(card, scenarioId, conflicts) {
  const selected = card._selectedScenarioId === scenarioId;
  const isRunning = (card._runningScenarios || []).includes(scenarioId);
  const buttons = [];

  // If this scenario is running, allow stopping it directly from here so
  // conflicts with other scenarios can be cleared.
  if (isRunning) {
    buttons.push(
      `<button class="btn btn-danger" data-action="stop-scenario" data-scenario-id="${scenarioId}" title="Stop this running scenario">⏹ Stop</button>`
    );
  }

  if (selected) {
    buttons.push(
      `<button class="btn btn-secondary" data-action="clear-selected-scenario" title="Unselect this scenario">✕ Unselect</button>`
    );
  } else {
    const disabled = conflicts.length ? " disabled" : "";
    const title = conflicts.length
      ? ` title="Conflicts with: ${conflicts.join(", ")} – stop those first"`
      : "";
    buttons.push(
      `<button class="btn btn-primary" data-action="select-scenario" data-scenario-id="${scenarioId}"${disabled}${title}>Select</button>`
    );
  }

  return buttons.join("");
}

function buildManualInjectionScenarioCard(card) {
  const conflicts = card._scenarioConflicts(SCENARIO_MANUAL_DEVICE);
  const conflictWarn = conflicts.length
    ? `<div style="font-size:0.75em; color: var(--warning-color,#ff9800); margin-top:4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
    : "";

  const knownList = card._knownList();
  const templateOptions = Object.entries(knownList).map(([deviceId, meta]) => {
    const slug = (meta?.class || "FAN").toUpperCase();
    const variant = meta?.variant || meta?.variant_id || "default";
    return `<option value="${deviceId}" data-slug="${slug}" data-variant="${variant}">${deviceId} • ${slug}</option>`;
  }).join("");
  const templateSelect = templateOptions
    ? `<label style="font-size:0.8em; display:flex; flex-direction:column; gap:4px;">
          <span>Preset from profile</span>
          <select data-action="manual-template" style="font-size:0.85em; padding:4px; border:1px solid var(--divider-color); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color);">
            <option value="">Select device...</option>
            ${templateOptions}
          </select>
       </label>`
    : "";

  const isSelected = card._selectedScenarioId === SCENARIO_MANUAL_DEVICE;
  return `
    <div class="card ${isSelected ? "active" : ""}">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>Manual Device Injection</strong>
        ${buildSelectChip(card, SCENARIO_MANUAL_DEVICE)}
      </div>
      <div class="scenario-description">Inject an ad-hoc device that emits its periodic frames. Select this scenario, then press Run on Devices tab.</div>
      ${templateSelect}
      ${card._buildScenarioParamsById(SCENARIO_MANUAL_DEVICE)}
      ${conflictWarn}
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        ${buildSelectButton(card, SCENARIO_MANUAL_DEVICE, conflicts)}
      </div>
    </div>`;
}

function buildPlaybackScenarioCard(card) {
  const conflicts = card._scenarioConflicts(SCENARIO_DEVICE_PLAYBACK);
  const conflictWarn = conflicts.length
    ? `<div style="font-size:0.75em; color: var(--warning-color,#ff9800); margin-top:4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
    : "";

  const playbacks = card._savedPlaybacks || [];
  const selection = card._playbackSelection || (playbacks[0] && playbacks[0].id) || "";
  const params = card._scenarioParams?.[SCENARIO_DEVICE_PLAYBACK] || {};
  const loopsValue = params.loops ?? 1;

  const optionList = playbacks.length
    ? playbacks.map((p) => `<option value="${p.id}"${p.id === selection ? " selected" : ""}>${p.id} (${p.frames} frames)</option>`).join("")
    : `<option value="" disabled selected>No saved playbacks</option>`;

  const isSelected = card._selectedScenarioId === SCENARIO_DEVICE_PLAYBACK;
  return `
    <div class="card ${isSelected ? "active" : ""}">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>Device Playback</strong>
        ${buildSelectChip(card, SCENARIO_DEVICE_PLAYBACK)}
      </div>
      <div class="scenario-description">Replay a saved conversation. Select the conversation + options, then press Run on Devices tab.</div>
      <div style="display:flex; flex-direction:column; gap:6px; margin-top:8px;">
        <label style="display:flex; flex-direction:column; gap:2px; font-size:0.75em;">
          <span>Conversation</span>
          <select data-action="playback-select">${optionList}</select>
        </label>
        <label style="display:flex; flex-direction:column; gap:2px; font-size:0.75em;">
          <span>Loops</span>
          <input type="number" min="1" step="1" value="${loopsValue}"
                 data-action="scenario-param"
                 data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"
                 data-field="loops"
                 data-type="number" />
        </label>
        <label style="display:flex; flex-direction:column; gap:2px; font-size:0.75em;">
          <span>Fixed gap between frames (s)</span>
          <input type="number" min="0" step="0.01"
                 value="${card._playbackInterMsgDelay ?? ""}"
                 placeholder="Leave blank to use recorded timing"
                 data-action="playback-inter-msg-delay" />
        </label>
        <label style="display:flex; align-items:center; gap:6px; font-size:0.75em; cursor:pointer;"
               title="Skip recorded RP frames so Auto Answer (if enabled) replies instead.">
          <input type="checkbox"
                 data-action="playback-skip-answers"
                 ${card._playbackSkipAnswers ? "checked" : ""} />
          <span>Skip recorded answers (let Auto Answer reply)</span>
        </label>
      </div>
      ${conflictWarn}
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        ${buildSelectButton(card, SCENARIO_DEVICE_PLAYBACK, conflicts)}
      </div>
    </div>`;
}

function buildGenericScenarioCard(card, id) {
  const meta = card._scenarioRegistry[id];
  const conflicts = card._scenarioConflicts(id);
  const conflictWarn = conflicts.length
    ? `<div style="font-size:0.75em; color: var(--warning-color,#ff9800); margin-top:4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
    : "";
  const isRunning = (card._runningScenarios || []).includes(id);
  const runningBadge = isRunning
    ? `<span class="chip" style="background: var(--success-color,#4caf50); color:white;">running</span>`
    : "";
  const isSelected = card._selectedScenarioId === id;
  return `
    <div class="card ${isSelected ? "active" : ""}">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>${meta.label || id}</strong>
        <div style="display:flex; gap:6px;">${runningBadge}${buildSelectChip(card, id)}</div>
      </div>
      <div class="scenario-description">${meta.description || "No description"}</div>
      ${card._buildScenarioParamsById(id)}
      ${conflictWarn}
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        ${buildSelectButton(card, id, conflicts)}
      </div>
    </div>`;
}

export function buildScenarios(card) {
  const registry = card._scenarioRegistry;
  const ids = Object.keys(registry);
  if (!ids.length) {
    return `<div style="color: var(--secondary-text-color); padding: 8px 0;">No scenarios available.</div>`;
  }

  const hint = `
    <div style="margin-bottom:12px; padding:8px 12px; border-radius:6px; background:var(--secondary-background-color); font-size:0.85em;">
      Select a scenario below, then go to the <strong>Devices</strong> tab to run it.
      Global preferences (speed, auto-answer, …) live on the <strong>Options</strong> tab.
    </div>`;

  // Curate order: manual injection, device playback, profile_emissions, then the rest.
  const highlighted = [SCENARIO_MANUAL_DEVICE, SCENARIO_DEVICE_PLAYBACK, SCENARIO_PROFILE_EMISSIONS];
  const hiddenFromList = new Set([SCENARIO_LOAD_PROFILE, "auto_answer", "device_suite"]);
  const restIds = ids.filter((id) => !highlighted.includes(id) && !hiddenFromList.has(id));

  const manualCard = ids.includes(SCENARIO_MANUAL_DEVICE) ? buildManualInjectionScenarioCard(card) : "";
  const playbackCard = ids.includes(SCENARIO_DEVICE_PLAYBACK) ? buildPlaybackScenarioCard(card) : "";
  const profileEmitCard = ids.includes(SCENARIO_PROFILE_EMISSIONS) ? buildGenericScenarioCard(card, SCENARIO_PROFILE_EMISSIONS) : "";
  const restCards = restIds.map((id) => buildGenericScenarioCard(card, id)).join("");

  return `
    ${hint}
    <div class="grid">
      ${manualCard}
      ${playbackCard}
      ${profileEmitCard}
      ${restCards}
      ${buildPlaybackImportCard(card)}
    </div>`;
}
