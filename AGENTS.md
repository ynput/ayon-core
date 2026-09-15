# ayon-core — repo-specific agent guidance

**Read first:** `.agents-main/AGENTS.md` (universal AYON rules, read order)
and `.agents-main/fragments/core.md` (repo-type detail). This file only adds
what is specific to `ayon-core`; don't restate universal rules here.

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

## Verification ladder (stop at first inapplicable step)

This repo has a real CI unit-test gate (`.github/workflows/pr_unittests.yaml`):

1. `ruff check .`
2. `ruff format --check .`
3. `./tools/manage.sh run-tests` — full suite; use `pytest -m unit` (markers:
   `unit`, `integration`, `api`, `cli`, `slow`, `server` — see
   `pyproject.toml`) to scope a targeted run while iterating.
4. `python create_package.py --skip-zip`
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

## Open items (TODO)

- The verification ladder above reflects documented commands, not verified
  CI steps. Before citing exact CI commands in guidance, inspect
  `.github/workflows/pr_unittests.yaml` and `pr_linting.yml` and reconcile
  with `tools/manage.sh run-tests`. Remove this item once verified.

## SDD workflow

`.specify/memory/constitution.md` is authoritative for any `/speckit.*` work
(anatomy, pipeline contracts, settings conventions, style, verification
ladder).
