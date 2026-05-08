/**
 * Devices tab — manual injection, profile emitters, resume, playback,
 * autonomous speed, and the active devices grid with message previews.
 */

import {
  SCENARIO_MANUAL_DEVICE,
  SCENARIO_PROFILE_EMISSIONS,
  SCENARIO_DEVICE_PLAYBACK,
} from "../constants.js";

// ---------- Pure helpers ----------

function fmtHex(hex) {
  if (!hex) return "";
  return hex.match(/.{1,2}/g)?.join(" ") || hex;
}

function fmtDecoded(decoded) {
  if (decoded == null) return null;
  if (typeof decoded === "string") return decoded;
  if (typeof decoded === "number" || typeof decoded === "boolean") return String(decoded);
  try {
    return JSON.stringify(decoded);
  } catch {
    return String(decoded);
  }
}

export function formatAutonomousSpeedLabel(speed) {
  const value = Number(speed) || 1;
  if (Math.abs(value - 1) < 0.01) {
    return "1× normal";
  }
  if (value > 1) {
    const magnitude = value >= 10 ? value.toFixed(0) : value.toFixed(1);
    return `${magnitude}× faster`;
  }
  const slower = 1 / value;
  const text = slower >= 10 ? slower.toFixed(0) : slower.toFixed(1);
  return `${text}× slower`;
}

function renderDeviceZones(device) {
  const zones = device?.zones || [];
  if (!zones.length) {
    return "";
  }

  const items = zones.map((zone) => {
    const label = zone.label || `Zone ${zone.zone_id || "?"}`;
    const controller = zone.controller ? `CTL ${zone.controller}` : null;
    const roleLabel = (zone.roles || [])
      .map((role) => (role === "devices" ? "device" : role))
      .join(", ");
    const badge = roleLabel ? `<span class="chip muted">${roleLabel}</span>` : "";
    const sensor = zone.sensor ? `<span class="chip sensor">sensor ${zone.sensor}</span>` : "";

    let members = "";
    if ((zone.roles || []).includes("controller") && Array.isArray(zone.members)) {
      const formattedMembers = zone.members
        .map((member) => {
          const memberRoles = member.roles?.includes("sensor")
            ? "(sensor)"
            : member.roles?.includes("actuator")
              ? "(actuator)"
              : "";
          return `${member.id}${memberRoles ? ` ${memberRoles}` : ""}`;
        })
        .join(", ");
      if (formattedMembers) {
        members = `<div class="device-zone-members">Members: ${formattedMembers}</div>`;
      }
    }

    return `
      <div class="device-zone-row">
        <div>
          <strong>${label}</strong>${controller ? ` · ${controller}` : ""}
        </div>
        <div style="display:flex; gap:4px; flex-wrap:wrap; font-size:0.75em;">${badge}${sensor}</div>
        ${members}
      </div>`;
  }).join("");

  return `
    <div class="device-zones" style="margin-top:12px;">
      <div style="font-size:0.8em; color:var(--secondary-text-color); margin-bottom:4px;">Zone relationships</div>
      <div class="device-zone-list" style="display:flex; flex-direction:column; gap:6px;">${items}</div>
    </div>`;
}

// ---------- Card builders ----------

export function buildDeviceMsgPreview(card, deviceId) {
  const messages = card._deviceMsgPreviews[deviceId];
  if (!messages || !messages.length) {
    return `<div class="msg-log-empty">No traffic yet — refresh to update</div>`;
  }
  const headerRow = `
    <div class="msg-log-header-row">
      <span>Recent traffic</span>
      <button class="btn btn-secondary" data-action="clear-device-log" data-device-id="${deviceId}">Clear</button>
    </div>`;
  const header = `
    <thead>
      <tr>
        <th>Time</th>
        <th>Dir</th>
        <th>Source</th>
        <th>Verb</th>
        <th>Code</th>
        <th>Src</th>
        <th>Dst</th>
        <th>Bcast</th>
        <th>Payload</th>
      </tr>
    </thead>`;
  const originLabels = {
    rf: "RF",
    sim: "SIM",
    auto_answer: "AUTO-RP",
    auto_emit: "AUTO-I",
  };
  const rows = messages.slice().sort((a, b) => b.ts - a.ts).map((m) => {
    const dir = m.direction === "inbound" ? "in" : "out";
    const origin = m.origin || (dir === "in" ? "rf" : "sim");
    const originLabel = originLabels[origin] || origin.toUpperCase();
    const ts = new Date(m.ts * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 });
    const hexPayload = fmtHex(m.payload);
    const decoded = fmtDecoded(m.decoded_payload);
    const payloadDisplay = decoded ?? hexPayload;
    const payloadTitle = decoded ? `${decoded}\n\nraw: ${hexPayload}` : hexPayload;
    const bcast = m.broadcast || "--:------";
    return `<tr class="${dir} origin-${origin}">
      <td class="msg-ts">${ts}</td>
      <td class="msg-dir ${dir}">${dir === "in" ? "RX" : "TX"}</td>
      <td><span class="msg-origin origin-${origin}" title="Frame origin: ${origin}">${originLabel}</span></td>
      <td class="msg-verb">${m.verb}</td>
      <td class="msg-code">${m.code}</td>
      <td class="msg-addr" title="${m.src}">${m.src}</td>
      <td class="msg-addr" title="${m.dst}">${m.dst}</td>
      <td class="msg-addr" title="${bcast}">${bcast}</td>
      <td class="msg-payload" title="${payloadTitle}">${payloadDisplay}</td>
    </tr>`;
  }).join("");
  return `<div class="msg-log">${headerRow}<table class="msg-log-table">${header}<tbody>${rows}</tbody></table></div>`;
}

export function buildManualInjectionCard(card) {
  const manualCount = card._manualDeviceCount();
  const conflicts = card._scenarioConflicts(SCENARIO_MANUAL_DEVICE);
  const conflictWarn = conflicts.length
    ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
    : "";
  const statusChip = manualCount
    ? `<span class="chip manual">${manualCount} active</span>`
    : `<span class="chip muted">Idle</span>`;
  const knownList = card._knownList();
  const templateOptions = Object.entries(knownList).map(([deviceId, meta]) => {
    const slug = (meta?.class || "FAN").toUpperCase();
    const variant = meta?.variant || meta?.variant_id || "default";
    return `<option value="${deviceId}" data-slug="${slug}" data-variant="${variant}">${deviceId} • ${slug}</option>`;
  }).join("");
  const templateSelect = templateOptions
    ? `<label style="font-size: 0.8em; display:flex; flex-direction:column; gap:4px;">
          <span>Preset from profile</span>
          <select data-action="manual-template" style="font-size:0.85em; padding:4px; border:1px solid var(--divider-color); border-radius:4px; background:var(--card-background-color); color:var(--primary-text-color);">
            <option value="">Select device...</option>
            ${templateOptions}
          </select>
       </label>`
    : "";

  return `
    <div class="card">
      <div style="display:flex; justify-content: space-between; align-items:center; flex-wrap: wrap; gap:8px;">
        <strong>Manual Device Injection</strong>
        ${statusChip}
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">Inject an ad-hoc device that emits its periodic frames. Use profile presets to auto-fill slug/device id.</div>
      ${templateSelect}
      ${card._buildScenarioParamsById(SCENARIO_MANUAL_DEVICE)}
      ${conflictWarn}
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${SCENARIO_MANUAL_DEVICE}" ${conflicts.length ? "disabled" : ""}>Inject Device</button>
        <button class="btn btn-secondary" data-action="stop-scenario" data-scenario-id="${SCENARIO_MANUAL_DEVICE}" ${manualCount ? "" : "disabled"}>Stop manual devices</button>
      </div>
    </div>`;
}

export function buildProfileEmissionsCard(card) {
  const running = (card._runningScenarios || []).includes(SCENARIO_PROFILE_EMISSIONS);
  const conflicts = card._scenarioConflicts(SCENARIO_PROFILE_EMISSIONS);
  const conflictWarn = conflicts.length
    ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
    : "";
  const knownList = card._knownList();
  const summary = card._profileDeviceSummary || [];
  const counts = card._profileDeviceCounts || null;
  const knownCount = counts?.known ?? (summary.length || Object.keys(knownList).length);
  const profileCount = counts?.active ?? card._profileDeviceCount();
  const stateMeta = card._profileDeviceStateMeta(profileCount, knownCount);
  const statusChip = `<span class="${stateMeta.chipClass}">${stateMeta.label}</span>`;
  const disableStart = !card._activeProfile || !knownCount || conflicts.length;
  const startDisabled = disableStart || running;
  const stopDisabled = profileCount === 0;
  const summaryText = stateMeta.description;

  const startButton = `<button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${SCENARIO_PROFILE_EMISSIONS}" ${startDisabled ? "disabled" : ""}>Start profile emitters</button>`;
  const stopButton = `<button class="btn btn-secondary" data-action="stop-profile-devices" ${stopDisabled ? "disabled" : ""}>Stop profile emitters</button>`;
  const buttonRow = `${startButton}${stopButton}`;

  const missingDevices = summary.filter((entry) => !entry.active);
  const missingMarkup = missingDevices.length
    ? `
      <div class="profile-missing">
        <strong>${missingDevices.length === 1 ? "1 device" : `${missingDevices.length} devices`} not emitting</strong>
        ${missingDevices
          .map(
            (entry) => `
              <div class="profile-missing-entry">
                <span>${entry.id}${entry.class ? ` • ${entry.class}` : ""}</span>
                <button class="btn btn-secondary" data-action="activate-profile-device" data-device-id="${entry.id}">
                  Activate
                </button>
              </div>`,
          )
          .join("")}
      </div>`
    : "";

  return `
    <div class="card">
      <div style="display:flex; justify-content: space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <strong>Profile emitters</strong>
        ${statusChip}
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">${summaryText} These devices emit their periodic "random" frames directly from the active profile.</div>
      ${conflictWarn}
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">${buttonRow}</div>
      ${missingMarkup}
    </div>`;
}

export function buildResumeEmittersCard(card) {
  const devices = card._devices || [];
  const resumeCandidates = devices.filter((d) => !d.emitting);
  const silencedCount = devices.filter((d) => d.suppress_autonomous).length;
  const chipClass = resumeCandidates.length
    ? "chip reply"
    : devices.length
      ? "chip emitting"
      : "chip muted";
  const chipLabel = resumeCandidates.length
    ? `${resumeCandidates.length} idle`
    : devices.length
      ? "All emitting"
      : "No active devices";
  const desc = resumeCandidates.length
    ? "Start autonomous emissions for the devices you just activated via playback or discovery."
    : devices.length
      ? "Every active device already has its emitter running."
      : "Activate devices first (via playback, manual injection, or profiles) to resume their emitters.";
  const sampleList = resumeCandidates.slice(0, 4)
    .map((d) => `<span class="chip muted">${d.id}</span>`)
    .join("");
  const extraCount = resumeCandidates.length > 4
    ? `<span class="chip muted">+${resumeCandidates.length - 4} more</span>`
    : "";
  const silencedNote = silencedCount
    ? `<div class="profile-missing" style="margin-top:8px;">
        <strong>${silencedCount} device${silencedCount === 1 ? " is" : "s are"} silenced</strong>
        <span>Use the per-device "Unsilence & resume" button to re-enable them.</span>
      </div>`
    : "";
  return `
    <div class="card">
      <div style="display:flex; justify-content: space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <strong>Resume emitters for active devices</strong>
        <span class="${chipClass}">${chipLabel}</span>
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">${desc}</div>
      <div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="btn btn-secondary" data-action="resume-all-devices" ${resumeCandidates.length ? "" : "disabled"}>Start emitters for active devices</button>
        <button class="btn btn-secondary" data-action="silence-all-devices" ${resumeCandidates.some(d => d.enabled && !d.suppress_autonomous) ? "" : "disabled"}>Stop emitters for active devices</button>
      </div>
      ${resumeCandidates.length ? `<div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">${sampleList}${extraCount}</div>` : ""}
      ${silencedNote}
    </div>`;
}

export function buildRunConsoleCard(card) {
  // Combined Playback + Autonomous Speed control card.
  const playbacks = card._savedPlaybacks || [];
  const runMeta = (card._runningMetadata || {})[SCENARIO_DEVICE_PLAYBACK] || null;
  const isRunning = Boolean(runMeta);
  const isPaused = Boolean(runMeta && runMeta.paused);
  const selection = card._playbackSelection || (playbacks[0] && playbacks[0].id) || "";
  const params = card._scenarioParams?.[SCENARIO_DEVICE_PLAYBACK] || {};
  const loopsValue = params.loops ?? 1;

  const optionList = playbacks.length
    ? playbacks.map((p) => `<option value="${p.id}"${p.id === selection ? " selected" : ""}>${p.id} (${p.frames} frames)</option>`).join("")
    : `<option value="" disabled selected>No saved playbacks</option>`;

  const playbackBadge = isRunning
    ? `<span class="chip" style="background:${isPaused ? "var(--warning-color,#ff9800)" : "var(--success-color,#4caf50)"}; color:white;">
        ${isPaused ? "Paused" : "Playing"}${runMeta?.conversation ? ` · ${runMeta.conversation}` : ""}
      </span>`
    : `<span class="chip muted" title="No playback is running">Idle</span>`;

  const playDisabled = !selection || isRunning ? " disabled" : "";
  const pauseDisabled = !isRunning || isPaused ? " disabled" : "";
  const resumeDisabled = !isRunning || !isPaused ? " disabled" : "";
  const stopDisabled = !isRunning ? " disabled" : "";

  // Speed sub-block
  const currentSpeed = Number(card._autonomousSpeed) || 1;
  const pendingSpeed = Number.isFinite(card._pendingSpeed) ? card._pendingSpeed : currentSpeed;
  const sliderValue = Math.min(1, Math.max(0.01, pendingSpeed || 1));
  const presetValues = [2, 1, 0.5, 0.25, 0.1, 0.05, 0.02];
  const speedBadge = card._speedSaving
    ? '<span class="chip muted">Saving…</span>'
    : `<span class="chip profile">${formatAutonomousSpeedLabel(currentSpeed)}</span>`;
  const presetButtons = presetValues
    .map((value) => {
      const active = Math.abs(currentSpeed - value) < 0.001 ? "btn-primary" : "btn-secondary";
      return `<button class="btn ${active}" data-action="speed-preset" data-speed="${value}">${formatAutonomousSpeedLabel(value)}</button>`;
    })
    .join("");

  return `
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>Run Console</strong>
        ${playbackBadge}
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">
        Replay a saved conversation and tune emitter speed. Configure defaults on <em>Scenarios</em>.
      </div>

      <div style="margin-top:10px; padding-top:8px; border-top:1px dashed var(--divider-color);">
        <div style="font-size:0.78em; font-weight:600; color:var(--secondary-text-color); margin-bottom:6px;">Conversation playback</div>
        <div style="display:flex; flex-direction:column; gap:6px;">
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
        <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px;">
          <button class="btn btn-primary" data-action="start-saved-playback" data-identifier="${selection}"${playDisabled}>▶ Play</button>
          <button class="btn btn-secondary" data-action="pause-scenario" data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"${pauseDisabled}>⏸ Pause</button>
          <button class="btn btn-secondary" data-action="resume-scenario" data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"${resumeDisabled}>▶ Resume</button>
          <button class="btn btn-danger" data-action="stop-scenario" data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"${stopDisabled}>⏹ Stop</button>
        </div>
      </div>

      <div style="margin-top:12px; padding-top:8px; border-top:1px dashed var(--divider-color);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
          <div style="font-size:0.78em; font-weight:600; color:var(--secondary-text-color);">Autonomous emission speed</div>
          ${speedBadge}
        </div>
        <div class="speed-controls">
          <label style="display:flex; flex-direction:column; gap:4px; font-size:0.75em;">
            <span>Slowdown (0.01–1×)</span>
            <input type="range" min="0.01" max="1" step="0.01" value="${sliderValue}" data-action="speed-slider" />
          </label>
          <label style="display:flex; flex-direction:column; gap:4px; font-size:0.75em;">
            <span>Exact multiplier</span>
            <input type="number" min="0.01" max="100" step="0.01" value="${pendingSpeed}" data-action="speed-input" />
          </label>
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:6px;">
          ${presetButtons}
        </div>
      </div>
    </div>`;
}

// Kept for backward compatibility with any external imports.
export function buildPlaybackConversationCard(card) {
  const playbacks = card._savedPlaybacks || [];
  const runMeta = (card._runningMetadata || {})[SCENARIO_DEVICE_PLAYBACK] || null;
  const isRunning = Boolean(runMeta);
  const isPaused = Boolean(runMeta && runMeta.paused);
  const selection = card._playbackSelection || (playbacks[0] && playbacks[0].id) || "";
  const params = card._scenarioParams?.[SCENARIO_DEVICE_PLAYBACK] || {};
  const loopsValue = params.loops ?? 1;

  const optionList = playbacks.length
    ? playbacks.map((p) => `<option value="${p.id}"${p.id === selection ? " selected" : ""}>${p.id} (${p.frames} frames)</option>`).join("")
    : `<option value="" disabled selected>No saved playbacks</option>`;

  const statusBadge = isRunning
    ? `<span class="chip" style="background:${isPaused ? "var(--warning-color,#ff9800)" : "var(--success-color,#4caf50)"}; color:white;">
        ${isPaused ? "Paused" : "Playing"}${runMeta?.conversation ? ` · ${runMeta.conversation}` : ""}
      </span>`
    : `<span class="chip muted" title="No playback is running">Idle</span>`;

  const playDisabled = !selection || isRunning ? " disabled" : "";
  const pauseDisabled = !isRunning || isPaused ? " disabled" : "";
  const resumeDisabled = !isRunning || !isPaused ? " disabled" : "";
  const stopDisabled = !isRunning ? " disabled" : "";

  return `
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <strong>Playback conversation</strong>
        ${statusBadge}
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">
        Replay a saved conversation. Speed follows the slider below (live).
      </div>
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
      <div style="display:flex; gap:6px; flex-wrap:wrap; margin-top:8px;">
        <button class="btn btn-primary" data-action="start-saved-playback" data-identifier="${selection}"${playDisabled}>▶ Play</button>
        <button class="btn btn-secondary" data-action="pause-scenario" data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"${pauseDisabled}>⏸ Pause</button>
        <button class="btn btn-secondary" data-action="resume-scenario" data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"${resumeDisabled}>▶ Resume</button>
        <button class="btn btn-danger" data-action="stop-scenario" data-scenario-id="${SCENARIO_DEVICE_PLAYBACK}"${stopDisabled}>⏹ Stop</button>
      </div>
    </div>`;
}

export function buildAutonomousSpeedCard(card) {
  const current = Number(card._autonomousSpeed) || 1;
  const pending = Number.isFinite(card._pendingSpeed) ? card._pendingSpeed : current;
  const sliderValue = Math.min(1, Math.max(0.01, pending || 1));
  const presetValues = [2, 1, 0.5, 0.25, 0.1, 0.05, 0.02];

  const badge = card._speedSaving
    ? '<span class="chip muted">Saving…</span>'
    : `<span class="chip profile">${formatAutonomousSpeedLabel(current)}</span>`;

  const presetButtons = presetValues
    .map((value) => {
      const active = Math.abs(current - value) < 0.001 ? "btn-primary" : "btn-secondary";
      return `<button class="btn ${active}" data-action="speed-preset" data-speed="${value}">${formatAutonomousSpeedLabel(value)}</button>`;
    })
    .join("");

  return `
    <div class="card speed-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <strong>Autonomous Emission Speed</strong>
        ${badge}
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color);">
        Lower than 1× slows emitters down, higher than 1× speeds them up. The slider covers 0.01–1×; use the number field or presets for faster modes.
      </div>
      <div class="speed-controls">
        <label style="display:flex; flex-direction:column; gap:4px; font-size:0.75em;">
          <span>Slowdown (0.01–1×)</span>
          <input type="range" min="0.01" max="1" step="0.01" value="${sliderValue}" data-action="speed-slider" />
        </label>
        <label style="display:flex; flex-direction:column; gap:4px; font-size:0.75em;">
          <span>Exact multiplier</span>
          <input type="number" min="0.01" max="100" step="0.01" value="${pending}" data-action="speed-input" />
        </label>
      </div>
      <div style="display:flex; flex-wrap:wrap; gap:6px;">
        ${presetButtons}
      </div>
    </div>`;
}

function buildSelectedScenarioConsole(card) {
  const id = card._selectedScenarioId;
  const meta = id ? card._scenarioRegistry[id] : null;
  const isRunning = id ? (card._runningScenarios || []).includes(id) : false;
  const runMeta = id ? (card._runningMetadata || {})[id] : null;
  const isPaused = Boolean(runMeta && runMeta.paused);

  if (!id) {
    return `
      <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
          <strong>Run Console</strong>
          <span class="chip muted">No scenario armed</span>
        </div>
        <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">
          Pick a scenario on the <em>Scenarios</em> tab, then run it from here. Global options live on the <em>Options</em> tab.
        </div>
        <div style="margin-top:8px; font-size:0.85em; color:var(--secondary-text-color);">
          Active devices below continue to emit their periodic frames automatically (random emitters).
          Use the toolbar to pause or resume them.
        </div>
      </div>`;
  }

  const stateChip = isRunning
    ? `<span class="chip" style="background:${isPaused ? "var(--warning-color,#ff9800)" : "var(--success-color,#4caf50)"}; color:white;">${isPaused ? "Paused" : "Running"}</span>`
    : `<span class="chip profile">Armed</span>`;

  let extraInfo = "";
  if (id === SCENARIO_DEVICE_PLAYBACK) {
    const conv = card._playbackSelection
      || (card._savedPlaybacks && card._savedPlaybacks[0] && card._savedPlaybacks[0].id)
      || "(none)";
    extraInfo = `<div style="font-size:0.8em; color:var(--secondary-text-color); margin-top:4px;">Conversation: <strong>${conv}</strong></div>`;
  }

  const runDisabled = isRunning ? " disabled" : "";
  const pauseDisabled = !isRunning || isPaused ? " disabled" : "";
  const resumeDisabled = !isRunning || !isPaused ? " disabled" : "";
  const stopDisabled = !isRunning ? " disabled" : "";

  return `
    <div class="card active">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>Run Console — ${meta?.label || id}</strong>
        ${stateChip}
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">${meta?.description || ""}</div>
      ${extraInfo}
      <div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">
        <button class="btn btn-primary" data-action="run-selected"${runDisabled}>▶ Run</button>
        <button class="btn btn-secondary" data-action="pause-selected"${pauseDisabled}>⏸ Pause</button>
        <button class="btn btn-secondary" data-action="resume-selected"${resumeDisabled}>▶ Resume</button>
        <button class="btn btn-danger" data-action="stop-selected"${stopDisabled}>⏹ Stop</button>
      </div>
    </div>`;
}

export function buildDevices(card) {
  const runConsole = buildSelectedScenarioConsole(card);

  if (card._devices.length === 0) {
    return `${runConsole}<div class="device-list-empty">No active devices. Load a profile or select <em>Manual Device Injection</em> on Scenarios to populate the simulator.</div>`;
  }

  // Random-emitters toolbar
  const devices = card._devices;

  // Debug: log all device sources and IDs to understand the structure (only in dev mode)
  if (window.location.search.includes("debug")) {
    // eslint-disable-next-line no-console
    console.log("All devices:", devices.map(d => ({
      id: d.id,
      device_id: d.device_id,
      source: d.source,
      emitting: d.emitting,
      type: d.type
    })));
  }

  // Try multiple approaches to find discovered devices
  const discoveredDevices = devices.filter((d) => {
    // Try different possible properties that might indicate discovered devices
    return d.source === "scenario" ||
           d.owned_by_profile === true ||
           (d.id && d.id.includes(":")) ||  // Devices with valid RAMSES IDs
           (d.device_id && d.device_id.includes(":"));
  });
  const idleCount = devices.filter((d) => !d.emitting).length;
  const discoveredIdleCount = discoveredDevices.filter((d) => !d.emitting).length;
  const emittingCount = devices.filter((d) => d.emitting).length;
  const silencedCount = devices.filter((d) => d.suppress_autonomous).length;

  if (window.location.search.includes("debug")) {
    // eslint-disable-next-line no-console
    console.log(`Discovered devices: ${discoveredDevices.length}, idle: ${discoveredIdleCount}`);
  }
  // Enable silence all if there are devices that could emit (active and not silenced)
  const canSilence = devices.some((d) => d.enabled && !d.suppress_autonomous);
  const toolbar = `
    <div class="device-grid-toolbar"
         style="display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:12px 0 8px; padding:8px 12px; border:1px solid var(--divider-color); border-radius:6px; background:var(--secondary-background-color);">
      <span style="font-size:0.8em; color:var(--secondary-text-color);">
        Random emitters: <strong>${devices.length}</strong> active · ${emittingCount} emitting · ${idleCount} idle${silencedCount ? ` · ${silencedCount} silenced` : ""}
      </span>
      <span style="flex:1;"></span>
      <button class="btn btn-primary" data-action="resume-discovered-devices" ${discoveredIdleCount ? "" : "disabled"}>Resume discovered (${discoveredIdleCount})</button>
      <button class="btn btn-secondary" data-action="resume-all-devices">Resume All (full dbase)</button>
      <button class="btn btn-secondary" data-action="silence-all-devices" ${canSilence ? "" : "disabled"}>Silence all</button>
    </div>`;

  const knownList = card._knownList();
  const deviceCards = card._devices.map((d) => {
    const isEmitting = d.emitting === true;
    const isSilenced = d.suppress_autonomous;
    const emitterLabel = isEmitting
      ? "Emitter running"
      : isSilenced
        ? "Silenced"
        : "Emitter idle";
    const emitterChipClass = isEmitting
      ? "chip emitting"
      : isSilenced
        ? "chip silenced"
        : "chip idle";
    const ownershipChip = d.owned_by_profile
      ? `<span class="chip profile" title="Defined by the active profile">Profile</span>`
      : `<span class="chip manual" title="Manually injected device">Manual</span>`;
    const knownBadge = knownList[d.id]
      ? `<span class="chip known" title="Device appears in profile known list">Known</span>`
      : "";
    const extraSource = d.source && !["manual", "profile"].includes(d.source)
      ? `<span class="chip source" title="Origin scenario">${d.source}</span>`
      : "";
    const chipsMarkup = (d.excluded_codes || []).map((code) =>
      `<span class="code-chip">${code}<button data-action="remove-code" data-device-id="${d.id}" data-code="${code}" title="Remove">✕</button></span>`
    ).join("");
    const checkedAttr = d.enabled ? " checked" : "";
    const zoneMarkup = renderDeviceZones(d);
    const emitterButton = isEmitting
      ? `<button class="btn btn-secondary" data-action="silence-device" data-device-id="${d.id}">Stop emission</button>`
      : `<button class="btn btn-secondary" data-action="resume-device" data-device-id="${d.id}">${isSilenced ? "Unsilence & resume" : "Resume emission"}</button>`;
    return `
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
          <div><strong>${d.id}</strong> <span style="color: var(--secondary-text-color); font-size: 0.85em;">${d.type}</span></div>
          <div style="display:flex; gap:4px; flex-wrap: wrap;">${ownershipChip}${knownBadge}${extraSource}</div>
        </div>
        <div class="device-actions">
          <label class="toggle">
            <ha-switch data-action="toggle-device" data-device-id="${d.id}"${checkedAttr}></ha-switch>
            <span>${d.enabled ? "Enabled" : "Disabled"}</span>
          </label>
        </div>
        <div class="device-emitter" title="Autonomous emitter state">
          <span class="${emitterChipClass}">${emitterLabel}</span>
          ${emitterButton}
          <button class="btn btn-secondary" data-action="discover-device" data-device-id="${d.id}">Discover capabilities</button>
        </div>
        <div style="font-size: 0.8em; color: var(--secondary-text-color); margin-top: 8px;">Excluded codes:</div>
        <div class="codes-row">${chipsMarkup || `<span class="chip muted">none</span>`}</div>
        <div class="add-code">
          <input type="text" maxlength="4" placeholder="1FC9"
            data-action="code-input" data-device-id="${d.id}"
            value="${card._newCodeInput[d.id] || ""}" />
          <button class="btn btn-primary" data-action="add-code" data-device-id="${d.id}">+ Exclude</button>
        </div>
        ${zoneMarkup}
        <div style="margin-top:10px;">
          <div style="font-size:0.75em; color:var(--secondary-text-color); margin-bottom:3px; font-weight:600;">Recent traffic</div>
          ${buildDeviceMsgPreview(card, d.id)}
        </div>
      </div>`;
  }).join("");

  return `${runConsole}${toolbar}<div class="grid devices-grid">${deviceCards}</div>`;
}
