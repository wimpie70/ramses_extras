/**
 * Card Header Template
 * Contains DOCTYPE, html, head, and style elements
 */

export function createCardHeader(cardStyle) {
  return `
    <!DOCTYPE html>
    <html>
    <head>
      <style>${cardStyle}</style>
    </head>
    <body>
      <script>
        // Store the card instance globally so it can be accessed from inline handlers
        if (!window.orconFanCardInstance) {
          window.orconFanCardInstance = this;
        }
      </script>
  `;
}
