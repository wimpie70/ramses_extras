/**
 * Card Footer Template
 * Contains scripts and closing HTML tags
 */

export function createCardFooter() {
  return `
      <script>
        // Update UI
        document.getElementById('fanMode').textContent = mode;

        // Update active state for all button types
        document.querySelectorAll('.control-button').forEach(btn => {
          const label = btn.querySelector('.control-label').textContent;

          // Handle mode buttons (away, auto, active)
          if (['Away', 'Auto', 'Active', 'Dehumidify'].includes(label)) {
            if (label.toLowerCase() === mode) {
              btn.classList.add('active');
            } else {
              btn.classList.remove('active');
            }
          }

          // Handle speed buttons (low, medium, high)
          else if (['Low', 'Medium', 'High'].includes(label)) {
            if (label.toLowerCase() === mode) {
              btn.classList.add('active');
            } else {
              btn.classList.remove('active');
            }
          }

          // Timer and bypass buttons are handled by their respective functions
        });
      </script>

      <script>
        function updateTimerUI(minutes) {
          console.log('Updating timer UI to:', minutes, 'minutes');
          document.getElementById('timer').textContent = minutes + ' min';

          // Update active state
          document.querySelectorAll('.control-button').forEach(btn => {
            const label = btn.querySelector('.control-label').textContent;
            if (label === minutes + 'm') {
              btn.classList.add('active');
            } else if (['15m', '30m', '60m'].includes(label)) {
              btn.classList.remove('active');
            }
          });
        }

        // Handle bypass button clicks with UI update and command sending
        async function setBypassMode(mode) {
          console.log('Setting bypass to:', mode);
          try {
            // Update UI using the card instance
            if (window.orconFanCardInstance) {
              window.orconFanCardInstance.updateBypassUI(mode);
              // Send command to device
              await window.orconFanCardInstance.sendBypassCommand(mode);
            } else {
              console.error('Card instance not available for bypass mode');
            }
          } catch (error) {
            console.error('Error setting bypass mode to ' + mode + ':', error);
            // Optionally show user feedback
            console.warn('Bypass command may have failed - check Home Assistant logs');
          }
        }
      </script>
    </body>
    </html>
  `;
}
