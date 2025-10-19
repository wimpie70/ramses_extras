/**
 * Card Footer Template
 * Contains scripts and closing HTML tags
 */

export function createCardFooter() {
  return `
      <script>
        console.log('🔧 Card HTML generated, running inline scripts');

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

        function triggerRefresh() {
          console.log('🔄 Manual refresh requested by user (html)');

          // Get the card instance from the global reference
          if (window.orconFanCardInstance) {
            window.orconFanCardInstance.forceRefresh().then(success => {
              if (success) {
                console.log('✅ Manual refresh completed');
                // Show a brief success indicator (optional)
                const refreshBtn = document.querySelector('.refresh-button');
                if (refreshBtn) {
                  refreshBtn.style.background = 'rgba(76, 175, 80, 0.3)';
                  setTimeout(() => {
                    refreshBtn.style.background = 'rgba(255, 255, 255, 0.2)';
                  }, 500);
                }
              } else {
                console.error('❌ Manual refresh failed');
                // Show error indicator (optional)
                const refreshBtn = document.querySelector('.refresh-button');
                if (refreshBtn) {
                  refreshBtn.style.background = 'rgba(244, 67, 54, 0.3)';
                  setTimeout(() => {
                    refreshBtn.style.background = 'rgba(255, 255, 255, 0.2)';
                  }, 1000);
                }
              }
            });
          } else {
            console.error('Card instance not found for refresh');
          }
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

        // Handle refresh button clicks
        async function forceRefresh() {
          console.log('🔄 Manual refresh requested by user');
          if (window.orconFanCardInstance) {
            const success = await window.orconFanCardInstance.forceRefresh();
            if (success) {
              console.log('✅ Manual refresh completed');
              // Show a brief success indicator (optional)
              const refreshBtn = document.querySelector('.refresh-button');
              if (refreshBtn) {
                refreshBtn.style.background = 'rgba(76, 175, 80, 0.3)';
                setTimeout(() => {
                  refreshBtn.style.background = 'rgba(255, 255, 255, 0.2)';
                }, 500);
              }
            } else {
              console.error('❌ Manual refresh failed');
              // Show error indicator (optional)
              const refreshBtn = document.querySelector('.refresh-button');
              if (refreshBtn) {
                refreshBtn.style.background = 'rgba(244, 67, 54, 0.3)';
                setTimeout(() => {
                  refreshBtn.style.background = 'rgba(255, 255, 255, 0.2)';
                }, 1000);
              }
            }
          } else {
            console.error('Card instance not found for refresh');
          }
        }
      </script>
    </body>
    </html>
  `;
}
