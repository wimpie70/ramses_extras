This integration is an addition to, and runs on top of Ramses RF

The framework will allow for easy definition of entities, cards, websockets, servicecalls, entities, hooks into ramses_rf or \_cc, or whatever you come up with.
This will allow for faster development and an easy way to share your work. All without the need of special tweaks in ramses RF itself.

I would like to create it as user friendly as possible: just enable a feature and a .js card is added, with entities it requires, and also the servicecalls or websockets.
When disabling the feature, everything gets cleaned up again.

I can imagine this tool will support different cards, or other features for the same devices. A user can choose and enable only the ones he/she requires.

Feel free to create a PR or contact me if you want to contribute to this project.
If you have a card, automation or other that you would like included, please let me know.

regards, Willem

ps. this is a work-in-progress. WIKI pages will come with info on how to contribute, requirements for PR's and examples.

---

## Coding & Development Standards

All contributions (whether written by human contributors or generated via AI coding assistants) must strictly adhere to the following standards:

### 1. Code Style & Conventions

- **Line Constraints**: PEP 8 compliance (code <= 79 characters, docstrings/comments <= 72 characters).
- **EXEMPTION (Raw Data)**: Raw RF packets, hex strings, routing dictionaries, and timestamped packet logs are strictly exempt from line limits to preserve readability and grep-ability.
- **String Literals**: Prefer double quotes (`"`) for all string literals.
- **Deferred Logging**: Always use standard deferred `%`-formatting across all log levels and logger instances (e.g., `_LOGGER.debug(...)`) instead of `f-strings` to prevent string evaluation and interpolation overhead when logging is disabled or filtered.

### 2. Typing & Type Safety

- **Strict Type Safety**: 100% compliance with `mypy`. Do not introduce untyped definitions (`Any`) without strong technical justification.
- **Domain Types**: Prefer domain-specific types (`Address`, `DeviceIdT`, dataclasses, enums) over primitive `str` or `dict`.
- **Python Syntax**: Use modern Python 3.13+ syntax:
  - Use `|` for unions (e.g., `str | int`).
  - Use native collection types (e.g., `list[int]`, `dict[str, Any]`).
  - **Banned Imports**: Do not import `List`, `Dict`, `Set`, `Tuple`, `Optional`, or `Union` from `typing`.

### 3. Code Quality & Modularity

- **Immutability & State**: Treat data objects as immutable where possible. Avoid unnecessary state mutations and return new instances instead.
- **Context Managers**: Avoid nested `with` statements. Use parenthetical multi-context syntax (`with (A(), B()):`).
- **Imports**: Place imports at module level (top of file). Combine imports from the same module onto a single line (`combine-as-imports = true`).

### 4. Documentation & Comments

- **Public APIs**: Require full Sphinx-style docstrings (summary, detailed explanation, `:param:`, `:type:`, `:returns:`, `:rtype:`).
- **Private Helpers**: Concise, single-line summaries are preferred for internal helpers (`_helper`).
- **Preserve Inline Comments**: Treat existing comments, `#TODO`, `#FIXME`, and `#HACK` markers as locked anchors. Multi-line wrap comments rather than truncating text.

### 5. Testing & Verification

- **Test Structure**: Exempt from Sphinx docstrings. Use descriptive test names following the **Arrange, Act, Assert (AAA)** pattern with inline comments.
- **Tooling**: Verify changes locally using `~/venvs/extras/bin/prek run -a`, `~/venv/extras/bin/ruff check .`, `~/venvs/extras/bin/mypy`, and `~/venvs/extras/bin/pytest`.
