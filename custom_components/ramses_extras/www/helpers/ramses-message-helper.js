/* global customElements */
/* global HTMLElement */

// Ramses Message Helper - Global singleton for handling ramses_cc_message events
// Provides real-time message routing for cards and features

class RamsesMessageHelper {
    constructor() {
        this.listeners = new Map(); // device_id -> {card, handle_codes}
        this.setupGlobalListener();
    }

    static get instance() {
        if (!window._RamsesMessageHelperInstance) {
            window._RamsesMessageHelperInstance = new RamsesMessageHelper();
        }
        return window._RamsesMessageHelperInstance;
    }

    setupGlobalListener() {
        // Keep simple fallback listeners for completeness
        if (window.addEventListener) {
            window.addEventListener('ramses_cc_message', this.handleRamsesMessage.bind(this));
        } else {
            document.addEventListener('ramses_cc_message', this.handleRamsesMessage.bind(this));
        }
    }

    // Check if events are being received by monitoring events
    checkEventReception() {
        console.log('🧪 RamsesMessageHelper: Basic event reception check...');
        // Keep minimal monitoring for debugging
    }

    // Force re-registration of event listeners (for debugging)
    forceReRegisterListeners() {
        console.log('🔧 RamsesMessageHelper: Re-registering basic event listeners...');
        this.setupGlobalListener();
    }

    // Fallback message handler for direct event reception
    handleRamsesMessage(event) {
        try {
            console.log('🎯 RamsesMessageHelper: Fallback ramses_cc_message event received');

            const messageData = event.detail;
            if (messageData?.event_type === 'ramses_cc_message') {
                const messageCode = messageData.data?.code;
                const deviceId = messageData.data?.src;

                if (messageCode && deviceId) {
                    console.log('🎯 RamsesMessageHelper: Fallback routing message', messageCode, 'for device', deviceId);
                    this.routeMessage(deviceId, messageCode, messageData);
                }
            }
        } catch (error) {
            console.error('Error in RamsesMessageHelper fallback handler:', error);
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
                    } catch (error) {
                        console.error(`Error calling ${handlerMethod} on card:`, error);
                    }
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
    }

    removeListener(card, deviceId) {
        const normalizedDeviceId = deviceId.replace(/_/g, ':');
        const listeners = this.listeners.get(normalizedDeviceId);

        if (listeners) {
            // Remove all entries for this card
            const filteredListeners = listeners.filter(([listenerCard]) => listenerCard !== card);

            if (filteredListeners.length === 0) {
                this.listeners.delete(normalizedDeviceId);
            } else {
                this.listeners.set(normalizedDeviceId, filteredListeners);
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
}

// Make the helper globally available as both class and instance
window.RamsesMessageHelper = RamsesMessageHelper;
window.RamsesMessageHelperInstance = RamsesMessageHelper.instance;

// Also provide a convenience method for easy importing
export function getRamsesMessageHelper() {
    return RamsesMessageHelper.instance;
}

export { RamsesMessageHelper };
