/* eslint-disable no-console */
// HVAC Fan Card Message Handlers
// Handles real-time 31DA and other ramses_cc messages for the HVAC fan card

export class HvacFanCardHandlers {

    /**
     * Handle 31DA messages - provides comprehensive HVAC state data
     * Updates the card with real-time temperature, humidity, fan status, etc.
     */
    static handle_31DA(card, messageData) {
        try {

            const payload = messageData?.data?.payload;
            if (!payload) {
                console.warn('31DA message missing payload');
                return;
            }

            // Extract HVAC data from 31DA message
            const hvacData = HvacFanCardHandlers.extract31DAData(payload);

            // Update the card with new data
            card.updateFrom31DA(hvacData);

            // console.log('✅ 31DA data processed and card updated:', hvacData);

        } catch (error) {
            console.error('Error handling 31DA message:', error);
        }
    }

    /**
     * Handle 10D0 messages - provides filter change and other maintenance info
     */
    static handle_10D0(card, messageData) {
        try {
            // console.log('🎯 10D0 message received for HVAC fan card');

            const payload = messageData?.data?.payload;
            if (!payload) {
                console.warn('10D0 message missing payload');
                return;
            }

            // Extract 10D0 data
            const filterData = HvacFanCardHandlers.extract10D0Data(payload);

            // Update the card with filter information
            card.updateFrom10D0(filterData);

            // console.log('✅ 10D0 data processed and card updated:', filterData);

        } catch (error) {
            console.error('Error handling 10D0 message:', error);
        }
    }

    /**
     * Extract relevant HVAC data from 31DA message payload
     */
    static extract31DAData(payload) {
        const result = {
            // Basic HVAC identification
            hvac_id: payload.hvac_id,

            // Temperature data
            indoor_temp: payload.indoor_temp,
            outdoor_temp: payload.outdoor_temp,
            supply_temp: payload.supply_temp,
            exhaust_temp: payload.exhaust_temp,

            // Humidity data (convert from 0-1 range to percentage)
            indoor_humidity: payload.indoor_humidity !== null ?
                Math.round(payload.indoor_humidity * 100) : null,
            outdoor_humidity: payload.outdoor_humidity !== null ?
                Math.round(payload.outdoor_humidity * 100) : null,

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
        return {
            hvac_id: payload.hvac_id,

            // Filter information (if available)
            filter_change_required: payload.filter_change_required || false,
            days_remaining: payload.days_remaining || null,
            days_lifetime: payload.days_lifetime || null,
            percent_remaining: payload.percent_remaining || null,
            maintenance_required: payload.maintenance_required || false,

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
