// Ramses Message Broker - Global singleton for handling ramses_cc messages
// Provides real-time message routing for cards and features
//
// Dual delivery path (with automatic fallback):
// 1. Modern: subscribes to state_changed on event.ramses_cc_regex_event
//    (HA Event Entity, available to all users — in SUBSCRIBE_ALLOWLIST)
// 2. Legacy: subscribes to ramses_cc_message bus events
//    (requires admin — not in SUBSCRIBE_ALLOWLIST)
// Deduplication ensures messages from both paths are only processed once.

import * as logger from './logger.js';

const EVENT_ENTITY_ID = 'event.ramses_cc_regex_event';
const DEDUP_TTL_MS = 5000;

class RamsesMessageBroker {
    constructor() {
        this.listeners = new Map(); // device_id -> [[card, handle_codes], ...]
        this._recentMessages = new Map(); // dedup: key -> timestamp
        this._dedupInterval = null;
        this._eventEntityActive = false;
        this._busEventActive = false;
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
                // Try fallback subscribe method
                if (conn && typeof conn.subscribe === 'function') {
                    conn.subscribe('ramses_cc_message', (event) => {
                        this._handleBusEvent(event);
                    });
                }
                return;
            }

            // Path 1 (modern): subscribe to state_changed, filter for event entity
            this._subscribeToEventEntity(conn);

            // Path 2 (legacy): subscribe to ramses_cc_message bus events
            this._subscribeToBusEvents(conn);

            // Start dedup cleanup
            this._startDedupCleanup();
        } catch (error) {
            logger.error('RamsesMessageBroker: Error setting up subscriptions:', error);
        }
    }

    // --- Modern path: Event Entity via state_changed ---

    _subscribeToEventEntity(conn) {
        conn.subscribeEvents(
            (event) => {
                if (
                    event.event_type === 'state_changed' &&
                    event.data?.entity_id === EVENT_ENTITY_ID &&
                    event.data?.new_state
                ) {
                    this._handleEventEntityState(event.data.new_state);
                }
            },
            'state_changed'
        ).then(() => {
            this._eventEntityActive = true;
            logger.debug('RamsesMessageBroker: Subscribed to state_changed for event entity (modern path)');
        }).catch((error) => {
            logger.warn('RamsesMessageBroker: Failed to subscribe to state_changed:', error);
        });
    }

    _handleEventEntityState(newState) {
        const data = newState.attributes?.data;
        if (!data) return;

        const deviceId = data.src || data.device_id;
        const messageCode = data.code;
        if (!deviceId || !messageCode) return;

        // Dedup — skip if already seen via bus events
        const dedupKey = this._makeDedupKey(deviceId, messageCode, data.dtm);
        if (this._isDuplicate(dedupKey)) {
            logger.debug(`RamsesMessageBroker: Dedup (event entity) ${messageCode} from ${deviceId}`);
            return;
        }

        // Normalize to the same format as bus events so card handlers
        // can access messageData.data.payload uniformly
        const normalizedEvent = {
            event_type: 'ramses_cc_message',
            data: data,
        };

        logger.debug(`RamsesMessageBroker: (event entity) ${messageCode} from ${deviceId}`);
        this.routeMessage(deviceId, messageCode, normalizedEvent);
    }

    // --- Legacy path: ramses_cc_message bus events ---

    _subscribeToBusEvents(conn) {
        conn.subscribeEvents(
            (event) => {
                if (event.event_type === 'ramses_cc_message') {
                    this._handleBusEvent(event);
                }
            },
            'ramses_cc_message'
        ).then(() => {
            this._busEventActive = true;
            logger.debug('RamsesMessageBroker: Subscribed to ramses_cc_message bus events (legacy path)');
        }).catch((error) => {
            // Expected for non-admin users when the event entity path is active
            if (this._eventEntityActive) {
                logger.debug('RamsesMessageBroker: Bus event subscription failed (non-admin, event entity active)');
            } else {
                logger.warn('RamsesMessageBroker: Failed to subscribe to bus events:', error);
            }
        });
    }

    _handleBusEvent(event) {
        const data = event.data;
        if (!data) return;

        const deviceId = data.src || data.device_id;
        const messageCode = data.code;
        if (!deviceId || !messageCode) return;

        // Dedup — skip if already seen via event entity
        const dedupKey = this._makeDedupKey(deviceId, messageCode, data.dtm);
        if (this._isDuplicate(dedupKey)) {
            logger.debug(`RamsesMessageBroker: Dedup (bus event) ${messageCode} from ${deviceId}`);
            return;
        }

        logger.debug(`RamsesMessageBroker: (bus event) ${messageCode} from ${deviceId}`);
        this.routeMessage(deviceId, messageCode, event);
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

    // Handle ramses_cc_message events from window/document (legacy dispatch)
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
            event_entity: this._eventEntityActive,
            bus_events: this._busEventActive,
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
