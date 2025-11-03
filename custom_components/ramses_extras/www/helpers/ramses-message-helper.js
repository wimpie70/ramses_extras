/* global customElements */
/* global HTMLElement */
/* global setTimeout */

// Ramses Message Helper - Global singleton for handling ramses_cc_message events
// Provides real-time message routing for cards and features

class RamsesMessageHelper {
    constructor() {
        this.listeners = new Map(); // device_id -> {card, handle_codes}
        this.setupHAConnection();
    }

    static get instance() {
        if (!window._RamsesMessageHelperInstance) {
            window._RamsesMessageHelperInstance = new RamsesMessageHelper();
        }
        return window._RamsesMessageHelperInstance;
    }

    setupHAConnection() {
        console.log('🎯 RamsesMessageHelper: Setting up HA connection...');
        // Subscribe to HA events via WebSocket
        this.setupGlobalListener();
        console.log('✅ RamsesMessageHelper: Using WebSocket subscription approach');
    }



    setupGlobalListener() {
        console.log('🎯 RamsesMessageHelper: Setting up HA bus event listener');
        // Subscribe to HA events via WebSocket connection
        this.subscribeToHAEvents();
    }

    async subscribeToHAEvents() {
        console.log('🎯 RamsesMessageHelper: Attempting to subscribe to HA bus events');

        try {
            if (window.hassConnection) {
                const connection = await window.hassConnection;
                console.log('🎯 RamsesMessageHelper: Resolved HA connection:', connection);

                // Use the connection.conn object which has the actual methods
                const actualConn = connection.conn || connection;
                console.log('🎯 RamsesMessageHelper: actualConn object:', actualConn);
                console.log('🎯 RamsesMessageHelper: actualConn methods:', Object.getOwnPropertyNames(actualConn));

                if (actualConn && typeof actualConn.subscribeEvents === 'function') {
                    console.log('✅ RamsesMessageHelper: Subscribing to ramses_cc_message events');

                    actualConn.subscribeEvents(
                        (event) => {
                            console.log('🎯 RamsesMessageHelper: Received HA event:', event);
                            if (event.event_type === 'ramses_cc_message') {
                                this.handleHAEvent(event);
                            }
                        },
                        "ramses_cc_message"
                    ).then(() => {
                        console.log('✅ RamsesMessageHelper: Successfully subscribed to ramses_cc_message events');
                    }).catch((error) => {
                        console.error('❌ RamsesMessageHelper: Failed to subscribe:', error);
                    });
                } else {
                    console.log('❌ RamsesMessageHelper: No subscribeEvents method available');
                    console.log('🎯 RamsesMessageHelper: Trying fallback subscription methods...');

                    // Try alternative subscription approaches
                    if (typeof actualConn.subscribe === 'function') {
                        console.log('🎯 RamsesMessageHelper: Trying subscribe method');
                        actualConn.subscribe("ramses_cc_message", (event) => {
                            console.log('🎯 RamsesMessageHelper: Received HA event via subscribe:', event);
                            this.handleHAEvent(event);
                        });
                    }
                }
            } else {
                console.log('❌ RamsesMessageHelper: No hassConnection available, will retry later');
                // Try again later
                setTimeout(() => this.subscribeToHAEvents(), 2000);
            }
        } catch (error) {
            console.error('❌ RamsesMessageHelper: Error setting up HA event subscription:', error);
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

    // Handle HA event subscription messages
    handleHAEvent(event) {
        const data = event.data;
        const deviceId = data.src || data.device_id;
        const messageCode = data.code;

        // Route the message to registered listeners
        this.routeMessage(deviceId, messageCode, event);
    }

    // Handle ramses_cc_message events from window/document
    handleRamsesMessage(event) {
        try {
            const messageData = event.detail;

            if (messageData?.event_type === 'ramses_cc_message') {
                const messageCode = messageData.data?.code;
                const deviceId = messageData.data?.src;

                if (messageCode && deviceId) {
                    this.routeMessage(deviceId, messageCode, messageData);
                }
            }
        } catch (error) {
            console.error('Error in RamsesMessageHelper event handler:', error);
        }
    }

    routeMessage(deviceId, messageCode, messageData) {
        console.log('🎯 RamsesMessageHelper: Routing message', messageCode, 'for device', deviceId);

        // Find listeners for this device
        const listeners = this.listeners.get(deviceId);

        if (!listeners) {
            console.log('⚠️ RamsesMessageHelper: No listeners found for device', deviceId);
            return; // No listeners for this device
        }

        console.log('✅ RamsesMessageHelper: Found', listeners.length, 'listeners for device', deviceId);

        // Check if this message code is handled by any listener
        for (const [card, handleCodes] of listeners) {
            console.log('🎯 RamsesMessageHelper: Checking card', card.constructor.name, 'with codes:', handleCodes);

            if (handleCodes.includes(messageCode)) {
                // Call the appropriate handler method on the card
                const handlerMethod = `handle_${messageCode}`;
                console.log('🎯 RamsesMessageHelper: Calling method', handlerMethod, 'on card');

                if (typeof card[handlerMethod] === 'function') {
                    try {
                        card[handlerMethod](messageData);
                        console.log('✅ RamsesMessageHelper: Successfully called', handlerMethod);
                    } catch (error) {
                        console.error(`Error calling ${handlerMethod} on card:`, error);
                    }
                } else {
                    console.log('⚠️ RamsesMessageHelper: Method', handlerMethod, 'not found on card');
                }
            } else {
                console.log('⚠️ RamsesMessageHelper: Card does not handle code', messageCode);
            }
        }
    }

    addListener(card, deviceId, handleCodes) {
        // Normalize device ID format
        const normalizedDeviceId = deviceId.replace(/_/g, ':');

        console.log('🎯 RamsesMessageHelper: Adding listener for device', normalizedDeviceId, 'with codes:', handleCodes);

        // Store listener
        if (!this.listeners.has(normalizedDeviceId)) {
            this.listeners.set(normalizedDeviceId, []);
        }

        const listeners = this.listeners.get(normalizedDeviceId);
        listeners.push([card, handleCodes]);

        console.log('✅ RamsesMessageHelper: Listener added. Total listeners for', normalizedDeviceId, ':', listeners.length);
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
