- more cleanup on the features, framework, starting with the hello world feature

Do we know what cards are enabled at startup ?
- removing deployed cards from local/www/ramses_extras/* when removing the entry ? or when removing a feature ?
- same for registered resources
- we can instead show a placeholder card for each feature that is disabled, with a message to enable it in the config flow
- we can create small 'main-card.js' files for each card, that will be registered. It will redirect to the real card if enabled, or show a 'this card is disabled, you can enabled it's feature from the Ramses Extras configuration'
- add update parameters button
- sensor control improvements not working ?

- hvac fan card editor: it never had a followup step for mapping entities (only device dropdown). good idea for future dev.

- why external calculated abs humid entities:
We may have a few temp/humid sensors for 1 fan. eg. a bathroom and a kitchen....I want to be able to create logic later that if 1 of them goes high we also should ventilate high (but then for eg 15 minutes) to get rid of the local moisture. But this would need extra logic and handshaking with automations that control the speed....
Or, we would create some kind of OR logic for the different abs humid entities -> select the highest one as the one to work with and fall back to internal after 15 minutes...or always use the highest one....The same but upside-down goes for too dry air.



check humid control devices not saved
