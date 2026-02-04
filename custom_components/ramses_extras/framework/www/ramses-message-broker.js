/* global setTimeout */

// Ramses Message Broker - Global singleton for handling ramses_cc_message events
// Provides real-time message routing for cards and features

import * as logger from './logger.js';

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
        // Subscribe to HA events via WebSocket
        this.setupGlobalListener();
    }

    async subscribeToHAEvents() {
        try {
            if (window.hassConnection) {
                const connection = await window.hassConnection;
                // console.log('🎯 RamsesMessageBroker: Resolved HA connection:', connection);

                // Use the connection.conn object which has the actual methods
                const actualConn = connection.conn || connection;
                // console.log('🎯 RamsesMessageBroker: actualConn object:', actualConn);
                // console.log('🎯 RamsesMessageBroker: actualConn methods:', Object.getOwnPropertyNames(actualConn));

                if (actualConn && typeof actualConn.subscribeEvents === 'function') {
                    // console.log('✅ RamsesMessageBroker: Subscribing to ramses_cc_message events');

                    actualConn.subscribeEvents(
                        (event) => {
                            // console.log('🎯 RamsesMessageBroker: Received HA event:', event);
                            if (event.event_type === 'ramses_cc_message') {
                                this.handleHAEvent(event);
                            }
                        },
                        "ramses_cc_message"
                    ).then(() => {
                        // console.log('✅ RamsesMessageBroker: Successfully subscribed to ramses_cc_message events');
                    }).catch((error) => {
                        logger.error('❌ RamsesMessageBroker: Failed to subscribe:', error);
                    });
                } else {
                    logger.warn('❌ RamsesMessageBroker: No subscribeEvents method available');
                    logger.warn('🎯 RamsesMessageBroker: Trying fallback subscription methods...');

                    // Try alternative subscription approaches
                    if (typeof actualConn.subscribe === 'function') {
                        logger.debug('🎯 RamsesMessageBroker: Trying subscribe method');
                        actualConn.subscribe("ramses_cc_message", (event) => {
                            logger.debug('🎯 RamsesMessageBroker: Received HA event via subscribe:', event);
                            this.handleHAEvent(event);
                        });
                    }
                }
            } else {
                logger.warn('❌ RamsesMessageBroker: No hassConnection available, will retry later');
                // Try again later
                setTimeout(() => this.subscribeToHAEvents(), 2000);
            }
        } catch (error) {
            logger.error('❌ RamsesMessageBroker: Error setting up HA event subscription:', error);
        }
    }

    setupGlobalListener() {
        // Subscribe to HA events via WebSocket connection
        this.subscribeToHAEvents();
    }

    // Handle HA event subscription messages
    handleHAEvent(event) {
        const data = event.data;
        const deviceId = data.src || data.device_id;
        const messageCode = data.code;

        logger.debug(`📡 RamsesMessageBroker: Received ${messageCode} from ${deviceId}`);

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
            logger.error('Error in RamsesMessageBroker event handler:', error);
        }
    }

    routeMessage(deviceId, messageCode, messageData) {
        // Find listeners for this device
        const listeners = this.listeners.get(deviceId);

        if (!listeners) {
            logger.debug(`📡 RamsesMessageBroker: No listeners for device ${deviceId}`);
            return; // No listeners for this device
        }

        logger.debug(`📡 RamsesMessageBroker: Routing ${messageCode} to ${listeners.length} listener(s)`);

        // Check if this message code is handled by any listener
        for (const [card, handleCodes] of listeners) {
            if (handleCodes.includes(messageCode)) {
                // Call the appropriate handler method on the card
                const handlerMethod = `handle_${messageCode}`;

                if (typeof card[handlerMethod] === 'function') {
                    try {
                        logger.debug(`📡 RamsesMessageBroker: Calling ${handlerMethod} on ${card.constructor.name}`);
                        card[handlerMethod](messageData);
                    } catch (error) {
                        logger.error(`Error calling ${handlerMethod} on card:`, error);
                    }
                } else {
                    logger.warn(`📡 RamsesMessageBroker: ${card.constructor.name} missing ${handlerMethod} method`);
                }
            }
        }
    }

    addListener(card, deviceId, handleCodes) {
        // Normalize device ID format
        const normalizedDeviceId = deviceId.replace(/_/g, ':');

        logger.debug(`📡 RamsesMessageBroker: Registering ${card.constructor.name} for device ${normalizedDeviceId}, codes: ${handleCodes.join(', ')}`);

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

// Make the broker globally available as both class and instance
window.RamsesMessageBroker = RamsesMessageBroker;
window.RamsesMessageBrokerInstance = RamsesMessageBroker.instance;

// Also provide a convenience method for easy importing
export function getRamsesMessageBroker() {
    return RamsesMessageBroker.instance;
}

export { RamsesMessageBroker };
