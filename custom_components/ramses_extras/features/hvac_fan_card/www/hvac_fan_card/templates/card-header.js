/**
 * Card Header Template
 * Contains ha-card wrapper and styles
 */

export function createCardHeader(cardStyle) {
  return `
    <ha-card>
      <style>${cardStyle}</style>
  `;
}
