/**
 * Events tab — renders stats + event log.
 */

export function buildEvents(card) {
  const events = card._events.length === 0
    ? `<div style="padding: 16px; text-align: center; color: var(--secondary-text-color);">No events</div>`
    : card._events.map((e) =>
        `<div class="event ${e.type === "unavailable" ? "unavailable" : ""}">
           <span class="event-type ${e.type}">${e.type}</span>
           <span>${e.message}</span>
         </div>`
      ).join("");
  return `
    <div class="stats">
      <div class="stat"><div class="stat-value">${card._stats.rx}</div><div>RX</div></div>
      <div class="stat"><div class="stat-value">${card._stats.tx}</div><div>TX</div></div>
      <div class="stat"><div class="stat-value">${card._stats.devices}</div><div>Devices</div></div>
      <div class="stat"><div class="stat-value">${card._stats.active}</div><div>Active</div></div>
    </div>
    <div class="event-log">${events}</div>`;
}
