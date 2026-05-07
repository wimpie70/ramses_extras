/**
 * Profiles tab — profile loader card, profile list, device status banner.
 */

import {
  SCENARIO_LOAD_PROFILE,
  SCENARIO_PROFILE_EMISSIONS,
} from "../constants.js";

export function buildProfileDevicesStatus(card) {
  if (!card._activeProfile) {
    return "";
  }

  const stateMeta = card._profileDeviceStateMeta();
  if (stateMeta.state === "active") {
    const runningMeta =
      (card._runningMetadata || {})[SCENARIO_PROFILE_EMISSIONS] || {};
    const deviceCount =
      runningMeta.devices?.length || stateMeta.profileCount || 0;
    const label = deviceCount
      ? `${deviceCount} devices emitting`
      : stateMeta.description;
    return `
      <div style="margin-top:8px; padding:8px 12px; border-radius:8px; background:var(--primary-color, #3f51b5); color:var(--text-primary-color,#fff); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <span>🔥 ${label}</span>
        <button class="btn btn-secondary" data-action="stop-profile-devices">Stop all profile devices</button>
      </div>`;
  }

  if (stateMeta.state === "reply") {
    return `
      <div style="margin-top:8px; padding:8px 12px; border-radius:8px; background:var(--info-color-light, rgba(2,136,209,0.15)); color:var(--primary-text-color); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <span>🛰️ ${stateMeta.description}</span>
      </div>`;
  }

  if (stateMeta.knownCount) {
    return `
      <div style="margin-top:8px; padding:8px 12px; border-radius:8px; background:var(--secondary-background-color); color:var(--secondary-text-color); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <span>⏸️ ${stateMeta.description}</span>
      </div>`;
  }

  return "";
}

export function buildProfileLoaderCard(card) {
  const conflicts = card._scenarioConflicts(SCENARIO_LOAD_PROFILE).filter((id) => ![SCENARIO_LOAD_PROFILE, SCENARIO_PROFILE_EMISSIONS].includes(id));
  const conflictWarn = conflicts.length
    ? `<div style="font-size: 0.75em; color: var(--warning-color, #ff9800); margin-top: 4px;">⚠️ Conflicts with: ${conflicts.join(", ")}</div>`
    : "";
  const params = card._scenarioParams[SCENARIO_LOAD_PROFILE] || {};
  const nameField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "profile_name");
  const yamlField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "profile_yaml");
  const reloadField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "reload_ramses");
  const preloadField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "preload_schema");
  const resetField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "reset_rf_cache");
  const eavesdropField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "enable_eavesdrop");
  const skipHydrateField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "remove_database");
  const clearLogField = card._getScenarioFieldMeta(SCENARIO_LOAD_PROFILE, "clear_message_log");

  const profileName = (params.profile_name ?? card._activeProfile ?? nameField?.default ?? "").trim();
  const yamlValue = params.profile_yaml ?? card._activeProfileYaml ?? "";
  const hasYaml = Boolean((yamlValue || "").trim());
  const reloadValue = params.reload_ramses ?? reloadField?.default ?? true;
  const preloadValue = params.preload_schema ?? preloadField?.default ?? true;
  const resetValue = params.reset_rf_cache ?? resetField?.default ?? false;
  const eavesdropValue = params.enable_eavesdrop ?? eavesdropField?.default ?? false;
  const skipHydrateValue = params.remove_database ?? skipHydrateField?.default ?? false;
  const clearLogValue = params.clear_message_log ?? clearLogField?.default ?? false;

  const profileNameInput = `
    <div class="scenario-field">
      <label for="loader-profile-name">${nameField?.label || "Profile name"}</label>
      <input id="loader-profile-name" type="text" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="profile_name" value="${profileName}" placeholder="${nameField?.placeholder || "imported_profile"}" />
    </div>`;

  const yamlInput = `
    <div class="scenario-field">
      <label for="loader-profile-yaml">${yamlField?.label || "Profile YAML"} <span style="color:var(--error-color);">*</span></label>
      <textarea id="loader-profile-yaml" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="profile_yaml" placeholder="${yamlField?.placeholder || "known_list:\n  32:150000:\n    class: FAN"}">${yamlValue}</textarea>
    </div>`;

  const reloadToggle = `
    <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;">
      <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="reload_ramses" data-type="checkbox" ${reloadValue ? "checked" : ""} />
      ${reloadField?.label || "Reload RF"}
    </label>`;

  const preloadToggle = `
    <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;">
      <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="preload_schema" data-type="checkbox" ${preloadValue ? "checked" : ""} />
      ${preloadField?.label || "Preload schema"}
    </label>`;

  const resetToggle = `
    <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;">
      <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="reset_rf_cache" data-type="checkbox" ${resetValue ? "checked" : ""} />
      ${resetField?.label || "Reset RF cache"}
    </label>`;

  const eavesdropToggle = `
    <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;" title="Enable ramses_rf eavesdrop so HVAC devices are promoted (FAN/REM/CO2/HUM) from observed traffic.">
      <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="enable_eavesdrop" data-type="checkbox" ${eavesdropValue ? "checked" : ""} />
      ${eavesdropField?.label || "Enable eavesdrop"}
    </label>`;

  const skipHydrateToggle = `
    <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;">
      <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="remove_database" data-type="checkbox" ${skipHydrateValue ? "checked" : ""} />
      ${skipHydrateField?.label || "Remove database file"}
    </label>`;

  const clearLogToggle = clearLogField
    ? `
      <label style="font-size: 0.8em; display:flex; align-items:center; gap:4px; cursor:pointer;">
        <input type="checkbox" data-action="scenario-param" data-scenario-id="${SCENARIO_LOAD_PROFILE}" data-field="clear_message_log" data-type="checkbox" ${clearLogValue ? "checked" : ""} />
        ${clearLogField.label || "Clear message log"}
      </label>
      <div style="font-size:0.7em; color:var(--secondary-text-color); margin-top:-4px;">
        ${clearLogField.description || "Clear the device simulator UI log before applying the profile."}
      </div>`
    : "";

  return `
    <div class="card" style="margin-bottom: 16px;" data-card="profile-loader">
      <div style="display:flex; justify-content: space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <strong>Load Ramses RF profile (YAML)</strong>
        <span class="chip ${hasYaml ? "profile" : "muted"}" data-loader-chip>${hasYaml ? "Ready" : "Awaiting YAML"}</span>
      </div>
      <div style="font-size:0.85em; color: var(--secondary-text-color); margin-top:4px;">
        Paste a known_devices YAML snippet to import a simulator profile and activate its devices.
      </div>
      ${card._activeProfile ? `<div style="font-size:0.8em; color: var(--secondary-text-color); margin-top:6px;">Active profile: <strong>${card._activeProfile}</strong>${card._activeProfileZones?.length ? ` · ${card._activeProfileZones.length} zones detected` : ""}</div>` : ""}
      ${conflictWarn}
      ${buildProfileDevicesStatus(card)}
      ${profileNameInput}
      ${yamlInput}
      <div style="display:flex; flex-direction:column; gap:6px; font-size:0.8em;">
        ${reloadToggle}
        ${preloadToggle}
        ${resetToggle}
        ${eavesdropToggle}
        ${skipHydrateToggle}
        ${clearLogToggle}
      </div>
      <div style="margin-top: 8px; display:flex; gap:8px; flex-wrap:wrap;">
        <button class="btn btn-primary" data-action="start-scenario" data-scenario-id="${SCENARIO_LOAD_PROFILE}" ${!hasYaml || conflicts.length ? "disabled" : ""}>Load</button>
        <button class="btn btn-secondary" data-action="reset-loader" ${hasYaml ? "" : "disabled"}>Clear form</button>
      </div>
    </div>`;
}

export function buildProfiles(card) {
  const loaderCard = buildProfileLoaderCard(card);
  const profileCards = card._profiles.length === 0
    ? "<div>No profiles available</div>"
    : card._profiles.map((p) => {
        const reloadChecked = (card._profileReload[p.name] ?? true) ? " checked" : "";
        const preloadChecked = (card._profilePreloadSchema[p.name] ?? true) ? " checked" : "";
        const resetCacheChecked = (card._profileResetCache[p.name] ?? true) ? " checked" : "";
        const eavesdropChecked = (card._profileEavesdrop[p.name] ?? true) ? " checked" : "";
        const skipHydrateChecked = (card._profileSkipHydrate[p.name] ?? true) ? " checked" : "";
        const clearLogChecked = (card._profileClearLog[p.name] ?? true) ? " checked" : "";
        const autoAnswerChecked = (p.enable_auto_answer ?? true) ? " checked" : "";
        const deleteButton = p.can_delete
          ? `<button class="btn btn-secondary" data-action="delete-profile" data-profile="${p.name}" style="margin-left:auto;">Delete</button>`
          : "";
        const badges = `
          <div style="display:flex; gap:4px; align-items:center; font-size:0.75em; color:var(--secondary-text-color);">
            ${p.is_active ? "<span class=\"chip profile\">Active</span>" : ""}
            ${p.is_builtin ? "<span class=\"chip source\">Built-in</span>" : ""}
          </div>`;
        return `
          <div class="card ${card._activeProfile === p.name ? "active" : ""}">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              <strong>${p.name}</strong>
              ${badges}
              ${deleteButton}
            </div>
            <div style="font-size: 0.85em; color: var(--secondary-text-color); margin-bottom: 8px;">${p.description || "No description"}</div>
            <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size:0.8em;">
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;">
                <input type="checkbox" data-action="reload-check" data-profile="${p.name}"${reloadChecked} />
                Reload RF
              </label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;">
                <input type="checkbox" data-action="preload-check" data-profile="${p.name}"${preloadChecked} />
                Preload schema
              </label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;">
                <input type="checkbox" data-action="reset-cache-check" data-profile="${p.name}"${resetCacheChecked} />
                Reset cache
              </label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;" title="Enable ramses_rf eavesdrop so HVAC devices are promoted (FAN/REM/CO2/HUM) from observed traffic.">
                <input type="checkbox" data-action="eavesdrop-check" data-profile="${p.name}"${eavesdropChecked} />
                Enable eavesdrop
              </label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;">
                <input type="checkbox" data-action="skip-hydrate-check" data-profile="${p.name}"${skipHydrateChecked} />
                Remove database file
              </label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;">
                <input type="checkbox" data-action="clear-log-check" data-profile="${p.name}"${clearLogChecked} />
                Clear message log
              </label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;" title="Enable auto-answer when this profile is loaded.">
                <input type="checkbox" data-action="auto-answer-check" data-profile="${p.name}"${autoAnswerChecked} />
                Enable auto answer
              </label>
              <button class="btn btn-primary" data-action="load-profile" data-profile="${p.name}">Load</button>
            </div>
          </div>`;
      }).join("");

  const notice = card._profileNotice
    ? `<div style="margin-top: 12px; padding: 8px 12px; background: var(--warning-color, #ff9800); color: white; border-radius: 6px; font-size: 0.85em; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
         <span>⚠️ ${card._profileNotice}</span>
         <button data-action="dismiss-notice" style="background: none; border: none; color: white; cursor: pointer; font-size: 1.1em; line-height: 1; padding: 0 2px;">✕</button>
       </div>`
    : "";

  return `${loaderCard}<div class="grid">${profileCards}</div>${notice}`;
}
