// HVAC Fan Card Message Handlers
// Handles real-time 31DA and other ramses_cc messages for the HVAC fan card

import * as logger from '../../helpers/logger.js';

export class HvacFanCardHandlers {

    /**
     * Handle 31DA messages - provides comprehensive HVAC state data
     * Updates the card with real-time temperature, humidity, fan status, etc.
     */
    static handle_31DA(card, messageData) {
        try {
            logger.debug('📨 31DA message received for HVAC fan card');

            const payload = messageData?.data?.payload;
            if (!payload) {
                logger.warn('31DA message missing payload');
                return;
            }

            // Extract HVAC data from 31DA message
            const hvacData = HvacFanCardHandlers.extract31DAData(payload);
            logger.debug('31DA data extracted:', {
                hvac_id: hvacData.hvac_id,
                indoor_temp: hvacData.indoor_temp,
                fan_info: hvacData.fan_info,
                hasTemps: !!(hvacData.indoor_temp || hvacData.outdoor_temp),
                hasHumidity: !!(hvacData.indoor_humidity || hvacData.outdoor_humidity)
            });

            // Update the card with new data
            card.updateFrom31DA(hvacData);
            logger.debug('✅ 31DA data processed and card updated');

        } catch (error) {
            logger.error('Error handling 31DA message:', error);
        }
    }

    /**
     * Handle 10D0 messages - provides filter change and other maintenance info
     */
    static handle_10D0(card, messageData) {
        try {
            logger.debug('📨 10D0 message received for HVAC fan card');

            const payload = messageData?.data?.payload;
            if (!payload) {
                logger.warn('10D0 message missing payload');
                return;
            }

            // Extract 10D0 data
            const filterData = HvacFanCardHandlers.extract10D0Data(payload);
            if (!filterData.hvac_id) {
                filterData.hvac_id = messageData?.data?.src || null;
            }
            logger.debug('10D0 data extracted:', {
                hvac_id: filterData.hvac_id,
                filter_change_required: filterData.filter_change_required,
                days_remaining: filterData.days_remaining,
                payload_type: typeof payload,
            });

            // Update the card with filter information
            card.updateFrom10D0(filterData);
            logger.debug('✅ 10D0 data processed and card updated');

        } catch (error) {
            logger.error('Error handling 10D0 message:', error);
        }
    }

    /**
     * Extract relevant HVAC data from 31DA message payload
     */
    static extract31DAData(payload) {
        const toHumidityPercent = (value) => {
            if (value === null || value === undefined || value === '') {
                return null;
            }
            const humidity = Number(value);
            if (!Number.isFinite(humidity)) {
                return null;
            }
            if (humidity >= 0 && humidity <= 1) {
                return Math.round(humidity * 100);
            }
            if (humidity >= 0 && humidity <= 100) {
                return Math.round(humidity);
            }
            return null;
        };

        const result = {
            // Basic HVAC identification
            hvac_id: payload.hvac_id,

            // Temperature data
            indoor_temp: payload.indoor_temp,
            outdoor_temp: payload.outdoor_temp,
            supply_temp: payload.supply_temp,
            exhaust_temp: payload.exhaust_temp,

            // Humidity data (convert from 0-1 range to percentage)
            indoor_humidity: toHumidityPercent(payload.indoor_humidity),
            outdoor_humidity: toHumidityPercent(payload.outdoor_humidity),

            // Fan data
            fan_info: payload.fan_info,
            exhaust_fan_speed: payload.exhaust_fan_speed,
            supply_fan_speed: payload.supply_fan_speed,

            // Flow data
            supply_flow: payload.supply_flow,
            exhaust_flow: payload.exhaust_flow,

            // System status
            bypass_position: payload.bypass_position,
            remaining_mins: payload.remaining_mins !== undefined ? payload.remaining_mins : null,
            speed_capabilities: payload.speed_capabilities || [],

            // Optional data
            co2_level: payload.co2_level,
            air_quality: payload.air_quality,
            post_heat: payload.post_heat,
            pre_heat: payload.pre_heat,

            // Metadata
            timestamp: payload._timestamp || new Date().toISOString(),
            source: '31DA_message'
        };

        return result;
    }

    /**
     * Extract relevant data from 10D0 message payload
     */
    static extract10D0Data(payload) {
        const payloadObj = (typeof payload === 'object' && payload !== null) ? payload : {};
        const rawPayloadHex = typeof payload === 'string'
            ? payload
            : (
                payloadObj.payload
                || payloadObj.raw_payload
                || payloadObj.hex
                || payloadObj.packet
                || null
            );

        const toNumberOrNull = (value) => {
            if (value === null || value === undefined || value === '') {
                return null;
            }
            const numberValue = Number(value);
            return Number.isFinite(numberValue) ? numberValue : null;
        };

        const firstNumeric = (...values) => {
            for (const value of values) {
                const parsed = toNumberOrNull(value);
                if (parsed !== null) {
                    return parsed;
                }
            }
            return null;
        };

        const parseHexPayload = (value) => {
            if (typeof value !== 'string') {
                return { daysRemaining: null };
            }
            const clean = value.replace(/\s+/g, '').toUpperCase();
            if (clean.length < 4 || clean.length % 2 !== 0 || !/^[0-9A-F]+$/.test(clean)) {
                return { daysRemaining: null };
            }
            const parsedDays = Number.parseInt(clean.slice(0, 4), 16);
            if (!Number.isFinite(parsedDays)) {
                return { daysRemaining: null };
            }
            return { daysRemaining: parsedDays };
        };

        const parsedHex = parseHexPayload(rawPayloadHex);

        return {
            hvac_id: payloadObj.hvac_id || null,

            // Filter information (if available)
            filter_change_required: Boolean(
                payloadObj.filter_change_required ?? payloadObj.filter_replace_required
            ),
            // RF payload field naming varies by version.
            days_remaining: firstNumeric(
                payloadObj.days_remaining,
                payloadObj.filter_remaining,
                payloadObj.filter_days_remaining,
                parsedHex.daysRemaining
            ),
            days_lifetime: firstNumeric(
                payloadObj.days_lifetime,
                payloadObj.filter_days_lifetime,
                payloadObj.filter_lifetime_days
            ),
            percent_remaining: firstNumeric(
                payloadObj.percent_remaining,
                payloadObj.filter_percent_remaining
            ),
            maintenance_required: Boolean(payloadObj.maintenance_required),

            timestamp: new Date().toISOString(),
            source: '10D0_message'
        };
    }

    /**
     * Format temperature display
     */
    static formatTemperature(temp) {
        if (temp === null || temp === undefined) {
            return '?';
        }
        return `${temp.toFixed(1)}°C`;
    }

    /**
     * Format humidity display
     */
    static formatHumidity(humidity) {
        if (humidity === null || humidity === undefined) {
            return '?';
        }
        return `${humidity}%`;
    }

    /**
     * Format fan speed display
     */
    static formatFanSpeed(fanSpeed) {
        if (fanSpeed === null || fanSpeed === undefined) {
            return '?';
        }
        return `${Math.round(fanSpeed * 100)}%`;
    }

    /**
     * Format flow rate display
     */
    static formatFlowRate(flow) {
        if (flow === null || flow === undefined) {
            return '?';
        }
        return `${flow.toFixed(1)} m³/h`;
    }
}

// Make handlers globally available for debugging
window.HvacFanCardHandlers = HvacFanCardHandlers;
