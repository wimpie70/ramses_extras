# Wiki Re-org Plan (ramses_extras → GitHub Wiki)

## Goal
Split the current single-page documentation (`docs/RAMSES_EXTRAS_ARCHITECTURE.md`) into a small set of **focused wiki pages** kept in-repo under `docs/wiki/`, so they can be copied to the wiki repo.

## Key invariants (must hold)
- **Single source of truth**: content lives in `ramses_extras` under `docs/wiki/`.
- **Wiki gets auto-updated** from `ramses_extras` (sync job / script).
- **Home page is stable** (structure + links stay consistent).
- **Links must work in both repos**:
  - In `ramses_extras` repo: browsing `docs/wiki/*.md`
  - In `ramses_extras.wiki` repo: browsing the wiki pages

## Naming + linking strategy
- **File names**: use simple, stable filenames with dashes.
- **Link style**: use Markdown links with `.md` extensions so links work in the repo.
  - Example: `[Overview](Overview.md)`
  - This should also work in the wiki repo because pages are stored as `.md` files.
- **Images/assets**: place under `docs/wiki/assets/` and link as `assets/<file>`.

## Proposed page set (initial + near-term)
### Initial pages (requested)
- `Home.md`
- `Overview.md`
- `Getting-Started-Users.md`
- `Getting-Started-Devs.md`

### Architecture-derived pages (from `RAMSES_EXTRAS_ARCHITECTURE.md`)
- `System-Architecture.md`
- `Feature-System.md`
- `Framework-Foundation.md`
- `Device-Feature-Management.md`
- `Entity-Management.md`
- `Home-Assistant-Integration.md`
- `Frontend-Architecture.md`
- `Development-Guide.md`
- `Debugging-and-Troubleshooting.md`
- `API-Reference.md`
- `Implementation-Details.md`

### Optional later
- `FAQ.md`
- `Glossary.md`
- `Changelog.md` (or keep changelog elsewhere)

## Content mapping (source → target)
- **Section 2** (Overview & Quick Start)
  - `Overview.md`
  - `Getting-Started-Devs.md` (split out developer quick start)
- **Section 3** (System Architecture)
  - `System-Architecture.md`
- **Section 4** (Feature System)
  - `Feature-System.md`
- **Section 5** (Framework Foundation)
  - `Framework-Foundation.md`
- **Section 6** (Device Feature Management)
  - `Device-Feature-Management.md`
- **Section 7** (Entity Management)
  - `Entity-Management.md`
- **Section 8** (Home Assistant Integration)
  - `Home-Assistant-Integration.md`
- **Section 9** (Frontend Architecture)
  - `Frontend-Architecture.md`
- **Section 10** (Development Guide)
  - `Development-Guide.md`
- **Section 11** (Debugging & Troubleshooting)
  - `Debugging-and-Troubleshooting.md`
- **Section 12** (API Reference)
  - `API-Reference.md`
- **Section 13** (Implementation Details)
  - `Implementation-Details.md`

---

# Progress tracking

## Milestone 1 — Scaffold the wiki folder structure
- [x] Create `docs/wiki/Home.md`
- [x] Create `docs/wiki/Overview.md`
- [x] Create `docs/wiki/Getting-Started-Users.md`
- [x] Create `docs/wiki/Getting-Started-Devs.md`
- [x] Create the additional architecture-derived page stubs listed above
- [x] Create `docs/wiki/assets/` and decide which existing images to copy

## Milestone 2 — Build the Home page (stable TOC)
- [x] Add a short introduction (what Ramses Extras is)
- [x] Add a compact TOC with links to all pages
- [x] Ensure links are relative and include `.md`
- [x] Add a “Where to start” block:
  - [x] Users → `Getting-Started-Users.md`
  - [x] Developers → `Getting-Started-Devs.md`

## Milestone 3 — Extract and split content from RAMSES_EXTRAS_ARCHITECTURE.md
- [x] Populate `Overview.md`
- [x] Populate `Getting-Started-Users.md` -> include the configuration bit about the bound Rem trait I added to README.md
- [x] Populate `Getting-Started-Devs.md`
- [x] Populate `System-Architecture.md`
- [x] Populate `Feature-System.md`
- [x] Populate `Framework-Foundation.md`
- [x] Populate `Device-Feature-Management.md`
- [x] Populate `Entity-Management.md`
- [x] Populate `Home-Assistant-Integration.md`
- [x] Populate `Frontend-Architecture.md`
- [x] Populate `Development-Guide.md`
- [x] Populate `Debugging-and-Troubleshooting.md`
- [x] Populate `API-Reference.md`
- [x] Populate `Implementation-Details.md`
- [x] Add `Feature-Catalog.md`

## Milestone 4 — Cross-linking + consistency
- [x] Add consistent “Next / Previous” navigation at bottom of each page (optional, but nice)
- [x] Ensure terminology is consistent (Feature, Framework, Platforms, Cards)
- [x] Ensure code paths referenced match repo structure
- [x] Move/centralize shared diagrams into `assets/` and fix links

## Milestone 5 — Wiki sync automation
- [x] Decide sync mechanism:
  - [x] Manual updates to the GitHub wiki repo (`ramses_extras.wiki`)
  - [ ] GitHub Action in `ramses_extras` that pushes `docs/wiki/*.md` to `ramses_extras.wiki`
  - [ ] Or: scheduled/manual sync job (fallback)
- [ ] Ensure `Home.md` maps to wiki’s home page (GitHub wiki uses `Home.md`)

## Milestone 6 — Validation
- [x] Verify links work in `ramses_extras` repo browsing
- [ ] Verify links work in wiki repo browsing
- [x] Verify images render in both places
- [ ] Final pass for readability (short sections, stable headings)

---

# Notes / open questions
- [x] Do we want “users” getting started to include YAML examples and UI steps, or only UI steps? -> only UI steps
- [x] Do we want a separate “Feature catalog” page listing each feature and what it provides? -> Yes, Including pictures, Configuration
- [x] Should API reference be trimmed to only stable public interfaces (WebSocket/service calls), and keep internals in the repo docs? -> For now yes, we can later create docs from the sphinx docstrings we already created.
- [x] Don't remove docs/RAMSES_EXTRAS_ARCHITECTURE.md, keep it for now so we can check if we have everything covered
