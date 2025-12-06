working on ramses_extras/docs/CONFIG_FLOW_EXTENSION_COMPLETE.md. This old doc is way too large, we can keep it as a ref for now. We are working on phase 4
What we need now is a plan to check all flows and problems that we still have and create a new plan for this.  Lets try to address what we have and what we don't have:

config menu:

main menu
- enable/disable features -> Confirm feature removal step works, but will also need to show the entities it will remove/change. Also, check if we actually create/remove cards/automations ?
- configure devices for features /// we don't need this, each feature will do this in its own step
- view current configuration /// we don't need this
- advanced settings /// leave that for now as is
- feature: default /// works, but we need the extra step to confirm what will be created/removed
- feature: humidity control /// works -> confirm feature removal /// we see now what device we have enabled, but we need to see what feature we are dealing with, and what entities will be created. Then on confirm, we need to actually create the entities
- feature: hvac fan card // works, only shows that there are no configs but that is what it should do.
- feature: hello world // correctly shows the devices it can enable. -> confirm feature removal /// the same as for humidity control, we need to see what feature we are dealing with, and what entities will be created. Then on confirm, we need to actually create the entities

startup
- we don't create entities anymore, i'm not sure if we create cards/automations but we should

- run tests like: cd /home/willem/dev/ramses_extras && bash -c "source ~/venvs/extras/bin/activate && python3 tests/managers/test_humidity_automation.py"
- we need unit tests for every phase
- we need to test every phase on docker hass to confirm it's intended workings. add a few logs if needed.
- we want to commit every phase. Therefore we need to pass all mypy, pytest and ruff and pre-commit tests
