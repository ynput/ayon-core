# ayon-core — repo-specific agent guidance

**Primary shared guidance:** `.agents-main/AGENTS.md` — universal AYON
rules, read order, and repo-type detail (`fragments/core.md`). This file
adds only confirmed `ayon-core` specifics and extends — never replaces,
overrides, or contradicts — the shared file.

## What this repo is

The shared pipeline core addon (`package.py`: name `core`) consumed by every
host addon via `ayon_required_addons`. A behavior change here can break every
host integration at once — treat it with more caution than a leaf addon, and
don't break compatibility imports / API branches declared in `package.py`
(`ayon_server_version`, `ayon_required_addons`, `ayon_compatible_addons`).

## Layout

- `client/ayon_core/` — installed package; subsystem map in
  `client/ayon_core/AGENTS.md`.
- `server/settings/` — Pydantic settings models (`main.py`, `conversion.py`,
  `publish_plugins.py`, `tools.py`). Settings schema changes need a
  `_convert_*` conversion (see `.agents-main/AGENTS.md`).
- `package.py` — addon metadata and version constraints.
- `create_package.py` — builds the distributable addon package.
- `tools/manage.sh` / `manage.ps1` — dev env + test runner.
- `docs/` — MkDocs site (`mkdocs.yml`); `ui_preview/` — standalone Qt widget
  preview app.

## Verification ladder (CI-verified)

CI gates: lint `.github/workflows/pr_linting.yml`, tests
`.github/workflows/pr_unittests.yaml` (Python 3.11,
`QT_QPA_PLATFORM=offscreen`).

1. `ruff check .` — CI lint (ruff version from `pyproject.toml`).
   `ruff format --check .` is a valid local check but is **not** CI-enforced.
2. `./tools/manage.sh create-env` — installs the uv dev env (CI step).
3. `./tools/manage.sh run-tests` — CI test command; runs
   `uv sync --extra test` then `uv run pytest ./tests -m "not server"`.
   Scope is the `tests/` (UI) suite only — intentional; the
   `client/ayon_core/tests/` suite is not covered by CI, run it explicitly.
   Markers `unit`, `integration`, `api`, `cli`, `slow`, `server`
   (`pyproject.toml`) scope targeted runs, e.g.
   `./tools/manage.sh run pytest -m unit`.
4. `python create_package.py [--skip-zip]` — packaging; not run in CI.
5. Host-application manual validation — describe the steps; don't claim to
   have run them from an agent session.

## Style specifics (authoritative: `ruff.toml`)

- `target-version = "py39"` (runtime compatibility) even though dev env is
  Python 3.11 (`pyproject.toml`).
- Line length 79, Ruff `preview = true`, Google docstring convention.
- Never lint/format `vendor/` or `client/ayon_core/scripts/slates/__init__.py`
  (both excluded in `ruff.toml`).
- `ruff.toml` is the only authoritative style config; `setup.cfg` (flake8/
  isort/pylint) is legacy and may be obsolete — don't follow it.

## Spec Kit

This repo is harness-agnostic — no agent config is committed; each teammate
installs their own Spec Kit integration and links `.agents-main` — run
`python agentic_setup.py install` (cross-platform; uses a junction on
Windows), or manually `ln -s ../ayon-agentic-instructions .agents-main`
(gitignored). See `SPEC_KIT.md` for setup. For any `/speckit.*` work (anatomy, pipeline
contracts, settings conventions, style, verification ladder), the active
constitution is `.agents-main/memory/ayon-constitution.md` — the tracked
`.specify/memory/constitution.md` is a symlink to it.
