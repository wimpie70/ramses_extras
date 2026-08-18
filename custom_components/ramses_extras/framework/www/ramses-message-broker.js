// Ramses Message Broker - Global singleton for handling ramses_cc messages
// Provides real-time message routing for cards and features
//
// Subscribes to the ramses_extras/subscribe_messages WebSocket command,
// which bridges the in-process RamsesMessageStream (add_msg_handler)
// directly to the browser.  No HA bus events or EventEntity configuration
// required.

import * as logger from './logger.js';

const WS_SUBSCRIBE_TYPE = 'ramses_extras/subscribe_messages';
const DEDUP_TTL_MS = 5000;

class RamsesMessageBroker {
    constructor() {
        this.listeners = new Map(); // device_id -> [[card, handle_codes], ...]
        this._recentMessages = new Map(); // dedup: key -> timestamp
        this._dedupInterval = null;
        this._wsActive = false;
        this.setupHAConnection();
    }

    static get instance() {
        if (!window._RamsesMessageBrokerInstance) {
            window._RamsesMessageBrokerInstance = new RamsesMessageBroker();
        }
        return window._RamsesMessageBrokerInstance;
    }

    setupHAConnection() {
        this.subscribeToHAEvents();
    }

    async subscribeToHAEvents() {
        try {
            if (!window.hassConnection) {
                logger.warn('RamsesMessageBroker: No hassConnection, will retry');
                setTimeout(() => this.subscribeToHAEvents(), 2000);
                return;
            }

            const connection = await window.hassConnection;
            const conn = connection.conn || connection;

            if (!conn || typeof conn.subscribeEvents !== 'function') {
                logger.warn('RamsesMessageBroker: No subscribeEvents method available');
                return;
            }

            // Subscribe to ramses_extras/subscribe_messages WebSocket command
            this._subscribeToMessages(conn);

            // Start dedup cleanup
            this._startDedupCleanup();
        } catch (error) {
            logger.error('RamsesMessageBroker: Error setting up subscriptions:', error);
        }
    }

    // --- WebSocket subscription: RamsesMessageStream → browser ---

    _subscribeToMessages(conn) {
        conn.subscribeMessage(
            (event) => {
                if (event?.event_type !== 'ramses_message') return;
                const data = event?.data;
                if (!data) return;
                this._handleMessage(data);
            },
            { type: WS_SUBSCRIBE_TYPE }
        ).then(() => {
            this._wsActive = true;
            logger.debug('RamsesMessageBroker: Subscribed to ramses_extras/subscribe_messages (WS path)');
        }).catch((error) => {
            logger.warn('RamsesMessageBroker: Failed to subscribe to messages WS:', error);
        });
    }

    _handleMessage(data) {
        const deviceId = data.src || data.device_id;
        const messageCode = data.code;
        if (!deviceId || !messageCode) return;

        // Dedup — skip if already seen
        const dedupKey = this._makeDedupKey(deviceId, messageCode, data.dtm);
        if (this._isDuplicate(dedupKey)) {
            logger.debug(`RamsesMessageBroker: Dedup (WS) ${messageCode} from ${deviceId}`);
            return;
        }

        // Normalize so card handlers can access messageData.data.payload uniformly
        const normalizedEvent = {
            event_type: 'ramses_message',
            data: data,
        };

        logger.debug(`RamsesMessageBroker: (WS) ${messageCode} from ${deviceId}`);
        this.routeMessage(deviceId, messageCode, normalizedEvent);
    }

    // --- Deduplication ---

    _makeDedupKey(deviceId, code, dtm) {
        return `${deviceId}|${code}|${dtm || Date.now()}`;
    }

    _isDuplicate(key) {
        const now = Date.now();
        if (this._recentMessages.has(key)) {
            return true;
        }
        this._recentMessages.set(key, now);
        return false;
    }

    _startDedupCleanup() {
        if (this._dedupInterval) return;
        this._dedupInterval = setInterval(() => {
            const now = Date.now();
            for (const [key, ts] of this._recentMessages) {
                if (now - ts > DEDUP_TTL_MS) {
                    this._recentMessages.delete(key);
                }
            }
        }, DEDUP_TTL_MS);
    }

    // --- Message routing ---

    // Handle messages from window/document (legacy dispatch)
    handleRamsesMessage(event) {
        try {
            const messageData = event.detail;

            if (messageData?.event_type === 'ramses_message' ||
                messageData?.event_type === 'ramses_cc_message') {
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
            logger.debug(`RamsesMessageBroker: No listeners for device ${deviceId}`);
            return;
        }

        logger.debug(`RamsesMessageBroker: Routing ${messageCode} to ${listeners.length} listener(s)`);

        // Check if this message code is handled by any listener
        for (const [card, handleCodes] of listeners) {
            if (handleCodes.includes(messageCode)) {
                const handlerMethod = `handle_${messageCode}`;

                if (typeof card[handlerMethod] === 'function') {
                    try {
                        logger.debug(`RamsesMessageBroker: Calling ${handlerMethod} on ${card.constructor.name}`);
                        card[handlerMethod](messageData);
                    } catch (error) {
                        logger.error(`Error calling ${handlerMethod} on card:`, error);
                    }
                } else {
                    logger.warn(`RamsesMessageBroker: ${card.constructor.name} missing ${handlerMethod} method`);
                }
            }
        }
    }

    // --- Listener management ---

    addListener(card, deviceId, handleCodes) {
        const normalizedDeviceId = deviceId.replace(/_/g, ':');

        logger.debug(`RamsesMessageBroker: Registering ${card.constructor.name} for device ${normalizedDeviceId}, codes: ${handleCodes.join(', ')}`);

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
                handle_codes: handleCodes,
            }));
        }
        return info;
    }

    getDeliveryInfo() {
        return {
            ws_subscription: this._wsActive,
        };
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
