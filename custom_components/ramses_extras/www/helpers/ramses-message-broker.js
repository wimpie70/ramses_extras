/* global customElements */
/* global HTMLElement */
/* global setTimeout */

// Ramses Message Broker - Global singleton for handling ramses_cc_message events
// Provides real-time message routing for cards and features

class RamsesMessageBroker {
    constructor() {
        this.listeners = new Map(); // device_id -> {card, handle_codes}
        this.setupHAConnection();
    }

    static get instance() {
        if (!window._RamsesMessageBrokerInstance) {
            window._RamsesMessageBrokerInstance = new RamsesMessageBroker();
        }
        return window._RamsesMessageBrokerInstance;
    }

    setupHAConnection() {
        console.log('🎯 RamsesMessageBroker: Setting up HA connection...');
        // Subscribe to HA events via WebSocket
        this.setupGlobalListener();
        console.log('✅ RamsesMessageBroker: Using WebSocket subscription approach');
    }

    async subscribeToHAEvents() {
        console.log('🎯 RamsesMessageBroker: Attempting to subscribe to HA bus events');

        try {
            if (window.hassConnection) {
                const connection = await window.hassConnection;
                console.log('🎯 RamsesMessageBroker: Resolved HA connection:', connection);

                // Use the connection.conn object which has the actual methods
                const actualConn = connection.conn || connection;
                console.log('🎯 RamsesMessageBroker: actualConn object:', actualConn);
                console.log('🎯 RamsesMessageBroker: actualConn methods:', Object.getOwnPropertyNames(actualConn));

                if (actualConn && typeof actualConn.subscribeEvents === 'function') {
                    console.log('✅ RamsesMessageBroker: Subscribing to ramses_cc_message events');

                    actualConn.subscribeEvents(
                        (event) => {
                            console.log('🎯 RamsesMessageBroker: Received HA event:', event);
                            if (event.event_type === 'ramses_cc_message') {
                                this.handleHAEvent(event);
                            }
                        },
                        "ramses_cc_message"
                    ).then(() => {
                        console.log('✅ RamsesMessageBroker: Successfully subscribed to ramses_cc_message events');
                    }).catch((error) => {
                        console.error('❌ RamsesMessageBroker: Failed to subscribe:', error);
                    });
                } else {
                    console.log('❌ RamsesMessageBroker: No subscribeEvents method available');
                    console.log('🎯 RamsesMessageBroker: Trying fallback subscription methods...');

                    // Try alternative subscription approaches
                    if (typeof actualConn.subscribe === 'function') {
                        console.log('🎯 RamsesMessageBroker: Trying subscribe method');
                        actualConn.subscribe("ramses_cc_message", (event) => {
                            console.log('🎯 RamsesMessageBroker: Received HA event via subscribe:', event);
                            this.handleHAEvent(event);
                        });
                    }
                }
            } else {
                console.log('❌ RamsesMessageBroker: No hassConnection available, will retry later');
                // Try again later
                setTimeout(() => this.subscribeToHAEvents(), 2000);
            }
        } catch (error) {
            console.error('❌ RamsesMessageBroker: Error setting up HA event subscription:', error);
        }
    }

    setupGlobalListener() {
        console.log('🎯 RamsesMessageBroker: Setting up HA bus event listener');
        // Subscribe to HA events via WebSocket connection
        this.subscribeToHAEvents();
    }

    // Check if events are being received by monitoring events
    checkEventReception() {
        console.log('🧪 RamsesMessageBroker: Basic event reception check...');
        // Keep minimal monitoring for debugging
    }

    // Force re-registration of event listeners (for debugging)
    forceReRegisterListeners() {
        console.log('🔧 RamsesMessageBroker: Re-registering basic event listeners...');
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
            console.error('Error in RamsesMessageBroker event handler:', error);
        }
    }

    routeMessage(deviceId, messageCode, messageData) {
        console.log('🎯 RamsesMessageBroker: Routing message', messageCode, 'for device', deviceId);

        // Find listeners for this device
        const listeners = this.listeners.get(deviceId);

        if (!listeners) {
            console.log('⚠️ RamsesMessageBroker: No listeners found for device', deviceId);
            return; // No listeners for this device
        }

        console.log('✅ RamsesMessageBroker: Found', listeners.length, 'listeners for device', deviceId);

        // Check if this message code is handled by any listener
        for (const [card, handleCodes] of listeners) {
            console.log('🎯 RamsesMessageBroker: Checking card', card.constructor.name, 'with codes:', handleCodes);

            if (handleCodes.includes(messageCode)) {
                // Call the appropriate handler method on the card
                const handlerMethod = `handle_${messageCode}`;
                console.log('🎯 RamsesMessageBroker: Calling method', handlerMethod, 'on card');

                if (typeof card[handlerMethod] === 'function') {
                    try {
                        card[handlerMethod](messageData);
                        console.log('✅ RamsesMessageBroker: Successfully called', handlerMethod);
                    } catch (error) {
                        console.error(`Error calling ${handlerMethod} on card:`, error);
                    }
                } else {
                    console.log('⚠️ RamsesMessageBroker: Method', handlerMethod, 'not found on card');
                }
            } else {
                console.log('⚠️ RamsesMessageBroker: Card does not handle code', messageCode);
            }
        }
    }

    addListener(card, deviceId, handleCodes) {
        // Normalize device ID format
        const normalizedDeviceId = deviceId.replace(/_/g, ':');

        console.log('🎯 RamsesMessageBroker: Adding listener for device', normalizedDeviceId, 'with codes:', handleCodes);

        // Store listener
        if (!this.listeners.has(normalizedDeviceId)) {
            this.listeners.set(normalizedDeviceId, []);
        }

        const listeners = this.listeners.get(normalizedDeviceId);
        listeners.push([card, handleCodes]);

        console.log('✅ RamsesMessageBroker: Listener added. Total listeners for', normalizedDeviceId, ':', listeners.length);
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

// Make the broker globally available as both class and instance
window.RamsesMessageBroker = RamsesMessageBroker;
window.RamsesMessageBrokerInstance = RamsesMessageBroker.instance;

// Also provide a convenience method for easy importing
export function getRamsesMessageBroker() {
    return RamsesMessageBroker.instance;
}

export { RamsesMessageBroker };
