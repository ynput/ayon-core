# ayon-core — agent map

`ayon-core` is the AYON pipeline core addon: host-agnostic Pyblish/pipeline
library consumed by every host addon (`ayon-nuke`, `ayon-flame`, etc.).

**SDD constitution** (authoritative for any `/speckit.*` spec/plan/tasks
work): `.specify/memory/constitution.md`. Read it before writing a spec —
it encodes addon anatomy, pipeline contract rules, settings conventions,
Ruff style, and the verification ladder for this repo specifically.

## Repo anatomy
- `client/ayon_core/` — the installed package. See
  `client/ayon_core/AGENTS.md` for its subsystem map.
- `server/` — `ServerAddon` + Pydantic settings models (`server/settings/`).
- `package.py` — addon metadata (name, version, required/compatible addons).
- `create_package.py` — builds the distributable addon package.
- `tools/manage.sh` / `manage.ps1` — dev env + test runner wrapper.
- `tests/`, `client/ayon_core/tests/` — pytest suites.

## Verification ladder (stop at first inapplicable step)
1. `ruff check .`
2. `ruff format --check .`
3. `./tools/manage.sh run-tests` (or `pytest` against
   `pyproject.toml`'s `testpaths`)
4. `python create_package.py --skip-zip`
5. Host-application manual validation — describe steps, don't claim to
   have run them from an agent session.

## SDD workflow
This repo has Spec Kit installed (`.specify/`, `.agents/skills/speckit-*`).
Use `/speckit.specify` → `/speckit.plan` → `/speckit.tasks` →
`/speckit.implement` for non-trivial features; each gate re-checks against
`.specify/memory/constitution.md`.
