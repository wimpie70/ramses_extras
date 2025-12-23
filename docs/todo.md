- more cleanup on the features, framework, starting with the hello world feature

Do we know what cards are enabled at startup ?
- removing deployed cards from local/www/ramses_extras/* when removing the entry ? or when removing a feature ?
- same for registered resources

todo: create json file in local/www/ramses_extras/config with the card info for card registration (without hass instance)




2025-12-22 07:35:55.149 INFO (MainThread) [custom_components.ramses_extras] 🔧 Exposing feature configuration to frontend...
2025-12-22 07:35:55.150 DEBUG (MainThread) [custom_components.ramses_extras.config_flow] Card path does not exist, nothing to remove: /config/local/ramses_extras/features/humidity_control
2025-12-22 07:35:55.150 WARNING (MainThread) [custom_components.ramses_extras.config_flow] Cannot register hvac_fan_card: /config/custom_components/ramses_extras/www/hvac_fan_card not found
2025-12-22 07:35:55.150 WARNING (MainThread) [custom_components.ramses_extras.config_flow] Cannot register hello_world: /config/custom_components/ramses_extras/www/hello_world not found
2025-12-22 07:35:55.150 WARNING (MainThread) [custom_components.ramses_extras.config_flow] Cannot register sensor_control: /config/custom_components/ramses_extras/www/sensor_control not found
2025-12-22 07:35:55.150 DEBUG (MainThread) [custom_components.ramses_extras.config_flow] Dynamic features found: ['default', 'hvac_fan_card', 'hello_world', 'sensor_control']
2025-12-22 07:35:55.151 INFO (MainThread) [custom_components.ramses_extras] ✅ Feature configuration exposed to frontend: /config/www/ramses_extras/helpers/ramses-extras-features.js



sensor control improvements

- why external calculated abs humid entities:
We may have a few temp/humid sensors for 1 fan. eg. a bathroom and a kitchen....I want to be able to create logic later that if 1 of them goes high we also should ventilate high (but then for eg 15 minutes) to get rid of the local moisture. But this would need extra logic and handshaking with automations that control the speed....
Or, we would create some kind of OR logic for the different abs humid entities -> select the highest one as the one to work with and fall back to internal after 15 minutes...or always use the highest one....The same but upside-down goes for too dry air.
