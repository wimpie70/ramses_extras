/**
 * Options tab — global simulator preferences + read-only RF/profile status.
 */

import { formatAutonomousSpeedLabel } from "./devices-tab.js";

function speedCard(card) {
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
        Lower than 1× slows emitters down, higher than 1× speeds them up. Slider covers 0.01–1×; use presets or number field for faster modes.
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

function toggleCard({ title, description, checked, action }) {
  return `
    <div class="card ${checked ? "active" : ""}">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
        <div><strong>${title}</strong></div>
        <label class="toggle">
          <ha-switch data-action="${action}"${checked ? " checked" : ""}></ha-switch>
        </label>
      </div>
      <div style="font-size:0.85em; color:var(--secondary-text-color); margin-top:4px;">${description}</div>
    </div>`;
}

function statusCard(card) {
  const rfStatus = card._rfEnforceKnownList
    ? `<span style="color: var(--warning-color); font-weight:600;">ENFORCED</span>`
    : `<span style="color: var(--success-color); font-weight:600;">NOT ENFORCED</span>`;
  const rfDesc = card._rfEnforceKnownList
    ? "RF client only accepts messages from devices in its known_list."
    : "RF client accepts messages from any device.";
  const knownListDesc = card._rfKnownListEnabled
    ? "Known list is configured with entries."
    : "No known list configured.";

  // Eavesdrop is a per-profile option; reflect the active profile's setting.
  const activeProfile = card._activeProfile;
  const eavesdropEnabled = activeProfile
    ? Boolean(card._profileEavesdrop?.[activeProfile])
    : false;
  const eavesdropLabel = activeProfile
    ? (eavesdropEnabled ? "Enabled" : "Disabled")
    : "n/a (no active profile)";

  const profileLabel = activeProfile
    ? `<strong>${activeProfile}</strong>`
    : `<span style="color:var(--secondary-text-color);">none</span>`;

  return `
    <div class="card" style="background: var(--secondary-background-color);">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>RF / profile status</strong>
      </div>
      <div style="display:flex; flex-direction:column; gap:6px; margin-top:6px; font-size:0.85em;">
        <div style="display:flex; justify-content:space-between; gap:8px;">
          <span>Active profile</span><span>${profileLabel}</span>
        </div>
        <div style="display:flex; justify-content:space-between; gap:8px;">
          <span>RF Client: accept only known devices</span>${rfStatus}
        </div>
        <div style="font-size:0.75em; color:var(--secondary-text-color);">${rfDesc} ${knownListDesc}</div>
        <div style="display:flex; justify-content:space-between; gap:8px; margin-top:4px;">
          <span>Eavesdrop (active profile)</span><span><strong>${eavesdropLabel}</strong></span>
        </div>
        <div style="font-size:0.75em; color:var(--secondary-text-color);">Eavesdrop is controlled per profile on the Profiles tab.</div>
      </div>
    </div>`;
}

export function buildOptions(card) {
  const cards = [
    speedCard(card),
    toggleCard({
      title: "Auto Answer (RQ→RP)",
      description: "When off: simulator receives RQ frames but never replies — simulates broken ESP or powered-off device.",
      checked: card._autoAnswer,
      action: "toggle-auto-answer",
    }),
    toggleCard({
      title: "Answer Unknown Devices",
      description: "When on: simulator responds to RQ frames for devices not in the active device list. Uses device DB to infer device type and generate responses.",
      checked: card._answerUnknownDevices,
      action: "toggle-answer-unknown",
    }),
    toggleCard({
      title: "Preserve state on reload",
      description: "When on: simulator state (auto-answer, answer unknown, known list) persists across reloads. When off (Clean restart): state is reset on reload.",
      checked: card._preserveState,
      action: "toggle-preserve-state",
    }),
    statusCard(card),
  ].join("");

  return `<div class="grid">${cards}</div>`;
}
