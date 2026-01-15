# Ramses Extras

A collection of **features**: add optional entities, automations, cards, websocket commands, servicecalls to [Ramses RF (ramses_cc)](https://github.com/ramses-rf/ramses_cc). It’s designed to work alongside ramses_cc without getting in the way.
This integration/framework is **built** as a basis for new features and I want to expand it to get a nice collection of handy tools. If you want to contribute, or have an idea for what's missing, **please** contact me (create an issue on my repo).

I started this project to get a better user experience. With a few clicks you can enable a feature, enable the devices it should work with and your card or automation will become available in your dashboard...no more entities that need to be created by hand or other steps that are needed. Even the commands for FAN's are included, so no more need to set them in Ramses RF config flow.
It became quite a big project, just have a look if you're interested.

Have fun, Willem ([wimpie70](https://github.com/wimpie70))

---

## What you get

- **HVAC Fan Card** – A Lovelace card for ventilation/heat-recovery units with airflow diagrams, controls, and parameter editing, add a 'bound' REM to your FAN in Ramses RF to get full control.
- **Humidity Control** – Automates fan speeds based on indoor/outdoor absolute humidity.
- **Sensor Control** – Lets you choose which sensors provide temperature, humidity, CO₂, and absolute humidity for each device.
- **Hello World** – Example/template for building new features.
- **Default** – Shared entities, WebSocket commands, and helpers used by other features.
- **Framework** – Shared base classes and helpers to make adding new features easier.

_More features planned—ideas and contributions welcome!_

<img src="https://github.com/wimpie70/ramses_extras/blob/master/docs/hvac_fan_card_1.png" alt="HVAC Fan Card 1" width="30%"> <img src="https://github.com/wimpie70/ramses_extras/blob/master/docs/hvac_fan_card_2.png" alt="HVAC Fan Card 2" width="30%">

## Install

Install Ramses Extras via HACS or manually, then enable the features you want in the Ramses Extras configuration flow. It will discover your Ramses RF devices and add the extra entities, automations, and Lovelace cards.

- **Repository**: https://github.com/wimpie70/ramses_extras
- **HACS**: Add as a custom repository and install
- **Docs**: See the project README and [wiki](https://github.com/wimpie70/ramses_extras/wiki) for setup and development details

---

Ramses Extras needs Ramses RF to be installed first. It doesn’t replace ramses_cc, it just adds extras on top.
