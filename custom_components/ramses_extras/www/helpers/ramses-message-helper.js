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
        // Use the fallback listener approach that was working before
        this.setupGlobalListener();
        console.log('✅ RamsesMessageHelper: Using fallback listener approach');
    }

    subscribeToHAEvents(connection) {
        console.log('🎯 RamsesMessageHelper: Attempting to subscribe to ramses_cc_message events');
        console.log('🎯 RamsesMessageHelper: connection object:', connection);
        console.log('🎯 RamsesMessageHelper: connection methods:', Object.getOwnPropertyNames(connection));

        // The connection is a Promise, we need to await it
        connection.then((conn) => {
            console.log('🎯 RamsesMessageHelper: Resolved connection:', conn);
            console.log('🎯 RamsesMessageHelper: Resolved connection methods:', Object.getOwnPropertyNames(conn));
            console.log('🎯 RamsesMessageHelper: conn.conn methods:', conn.conn ? Object.getOwnPropertyNames(conn.conn) : 'no conn.conn');

            // Try the conn.conn object which might have the subscription methods
            const actualConn = conn.conn || conn;

            if (typeof actualConn.subscribeEvents === 'function') {
                console.log('🎯 RamsesMessageHelper: Using actualConn.subscribeEvents');
                actualConn.subscribeEvents(
                    (event) => {
                        console.log('🎯 RamsesMessageHelper: Received HA event:', event);
                        this.handleHAEvent(event);
                    },
                    "ramses_cc_message"
                ).then(() => {
                    console.log('✅ RamsesMessageHelper: Successfully subscribed to ramses_cc_message events');
                }).catch((error) => {
                    console.error('❌ RamsesMessageHelper: Failed to subscribe to ramses_cc_message events:', error);
                });
            } else if (typeof actualConn.subscribe === 'function') {
                console.log('🎯 RamsesMessageHelper: Using actualConn.subscribe');
                actualConn.subscribe("ramses_cc_message", (event) => {
                    console.log('🎯 RamsesMessageHelper: Received HA event via subscribe:', event);
                    this.handleHAEvent(event);
                });
            } else if (typeof actualConn.addEventListener === 'function') {
                console.log('🎯 RamsesMessageHelper: Using actualConn.addEventListener');
                actualConn.addEventListener("ramses_cc_message", (event) => {
                    console.log('🎯 RamsesMessageHelper: Received HA event via addEventListener:', event);
                    this.handleHAEvent(event);
                });
            } else {
                console.log('❌ RamsesMessageHelper: No suitable subscription method found');
                console.log('🎯 RamsesMessageHelper: actualConn object:', actualConn);
            }
        }).catch((error) => {
            console.error('❌ RamsesMessageHelper: Failed to resolve connection promise:', error);
        });
    }

    setupGlobalListener() {
        console.log('🎯 RamsesMessageHelper: Setting up global listener for ramses_cc_message events');
        // Listen for ramses_cc_message events on window
        if (window.addEventListener) {
            window.addEventListener('ramses_cc_message', this.handleRamsesMessage.bind(this));
            console.log('✅ RamsesMessageHelper: Added window event listener');
        } else if (document.addEventListener) {
            document.addEventListener('ramses_cc_message', this.handleRamsesMessage.bind(this));
            console.log('✅ RamsesMessageHelper: Added document event listener');
        } else {
            console.log('❌ RamsesMessageHelper: No addEventListener available');
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
            console.log('🎯 RamsesMessageHelper: Received ramses_cc_message event:', event);

            const messageData = event.detail;
            console.log('🎯 RamsesMessageHelper: Event detail:', messageData);

            if (messageData?.event_type === 'ramses_cc_message') {
                const messageCode = messageData.data?.code;
                const deviceId = messageData.data?.src;

                console.log('🎯 RamsesMessageHelper: Processing message:', { messageCode, deviceId });

                if (messageCode && deviceId) {
                    console.log('🎯 RamsesMessageHelper: Routing message', messageCode, 'for device', deviceId);
                    this.routeMessage(deviceId, messageCode, messageData);
                } else {
                    console.log('⚠️ RamsesMessageHelper: Missing messageCode or deviceId');
                }
            } else {
                console.log('⚠️ RamsesMessageHelper: Not a ramses_cc_message event');
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
