# AI Agent Instructions for ramses_extras

The canonical coding standards, guardrails, and behavioural rules for
AI/LLM contributors live in the repo itself. **You MUST read both of
these files before working on ramses_extras:**

- **`LLM_INSTRUCTIONS.md`** (repo root) — behavioural rules, guardrails,
  identity/tone, no-advertising, wait-for-approval, PR framing,
  architecture, backward compatibility.
- **`CONTRIBUTING.md`** (repo root) — coding standards, typing,
  docstrings, testing, tooling.

## Test Environments (Home Assistant instances)

- **`hass` (port 8123)**: the normal dev HA instance, used for day-to-day
  development and debugging.
- **`ha-sim` (port 8124)**: a dedicated simulation HA instance running in
  Docker. The `tools/ha_sim_test` tool makes use of the device simulator
  feature and runs against this instance.
- **Production HA**: runs on a separate server. Do not point dev tools or
  tests at it.
