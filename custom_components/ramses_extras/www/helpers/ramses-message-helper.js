/* global customElements */
/* global HTMLElement */

// Ramses Message Helper - Global singleton for handling ramses_cc_message events
// Provides real-time message routing for cards and features

class RamsesMessageHelper {
    constructor() {
        // Singleton pattern - return existing instance if already created
        if (window.RamsesMessageHelper) {
            return window.RamsesMessageHelper;
        }

        this.listeners = new Map(); // device_id -> {card, handle_codes}
        this.setupGlobalListener();

        // Make globally available
        window.RamsesMessageHelper = this;
        console.log('✅ RamsesMessageHelper singleton initialized');
    }

    static get instance() {
        if (!window.RamsesMessageHelper) {
            new RamsesMessageHelper();
        }
        return window.RamsesMessageHelper;
    }

    setupGlobalListener() {
        // Set up global listener for ramses_cc_message events
        if (window.addEventListener) {
            window.addEventListener('hass-message', this.handleHassMessage.bind(this));
            console.log('✅ RamsesMessageHelper global listener setup for hass-message events');
        } else {
            // Fallback for environments without addEventListener
            document.addEventListener('hass-message', this.handleHassMessage.bind(this));
            console.log('✅ RamsesMessageHelper using document listener as fallback');
        }
    }

    handleHassMessage(event) {
        try {
            const messageData = event.detail;

            // Check if this is a ramses_cc_message
            if (messageData?.event_type === 'ramses_cc_message') {
                const messageCode = messageData.data?.code;
                const payload = messageData.data?.payload;

                if (messageCode && payload?.hvac_id) {
                    this.routeMessage(payload.hvac_id, messageCode, messageData);
                }
            }
        } catch (error) {
            console.error('Error in RamsesMessageHelper message handler:', error);
        }
    }

    routeMessage(deviceId, messageCode, messageData) {
        // Find listeners for this device
        const listeners = this.listeners.get(deviceId);

        if (!listeners) {
            return; // No listeners for this device
        }

        // Check if this message code is handled by any listener
        for (const [card, handleCodes] of listeners) {
            if (handleCodes.includes(messageCode)) {
                // Call the appropriate handler method on the card
                const handlerMethod = `handle_${messageCode}`;

                if (typeof card[handlerMethod] === 'function') {
                    try {
                        card[handlerMethod](messageData);
                        console.log(`✅ Routed ${messageCode} message to ${card.constructor.name}`);
                    } catch (error) {
                        console.error(`Error calling ${handlerMethod} on card:`, error);
                    }
                } else {
                    console.warn(`No handler method ${handlerMethod} found on card`);
                }
            }
        }
    }

    addListener(card, deviceId, handleCodes) {
        // Normalize device ID format
        const normalizedDeviceId = deviceId.replace(/_/g, ':');

        // Store listener
        if (!this.listeners.has(normalizedDeviceId)) {
            this.listeners.set(normalizedDeviceId, []);
        }

        const listeners = this.listeners.get(normalizedDeviceId);
        listeners.push([card, handleCodes]);

        console.log(`✅ Registered listener for device ${normalizedDeviceId}, codes: [${handleCodes.join(', ')}]`);
        console.log(`Total listeners: ${this.listeners.size}`);
    }

    removeListener(card, deviceId) {
        const normalizedDeviceId = deviceId.replace(/_/g, ':');
        const listeners = this.listeners.get(normalizedDeviceId);

        if (listeners) {
            // Remove all entries for this card
            const filteredListeners = listeners.filter(([listenerCard]) => listenerCard !== card);

            if (filteredListeners.length === 0) {
                this.listeners.delete(normalizedDeviceId);
                console.log(`🗑️ Removed all listeners for device ${normalizedDeviceId}`);
            } else {
                this.listeners.set(normalizedDeviceId, filteredListeners);
                console.log(`📋 Updated listeners for device ${normalizedDeviceId}`);
            }
        }
    }

    getListenerInfo() {
        const info = {};
        for (const [deviceId, listeners] of this.listeners) {
            info[deviceId] = listeners.map(([card, handleCodes]) => ({
                card_type: card.constructor.name,
                handle_codes: handleCodes
            }));
        }
        return info;
    }

    debugListeners() {
        console.log('🔍 RamsesMessageHelper - Current listeners:');
        for (const [deviceId, listeners] of this.listeners) {
            console.log(`  Device ${deviceId}:`);
            listeners.forEach(([card, handleCodes], index) => {
                console.log(`    [${index}] ${card.constructor.name} -> [${handleCodes.join(', ')}]`);
            });
        }
    }
}

// Make the helper globally available as both class and instance
window.RamsesMessageHelper = RamsesMessageHelper;
window.RamsesMessageHelperInstance = RamsesMessageHelper.instance;

// Also provide a convenience method for easy importing
export function getRamsesMessageHelper() {
    return RamsesMessageHelper.instance;
}

export { RamsesMessageHelper };
