# AGENTS.md — ayon-core

## Project Overview

AYON core addon — the base building block for the AYON pipeline. Provides CLI handlers, publishing plugins, pipeline API, loaders, and Qt graphical tools. Successor to OpenPype.

## Two pyproject.toml Files (Critical)

| File | Purpose |
|------|---------|
| `pyproject.toml` (root) | **Development only** — defines the dev venv used for linting, testing, and tooling. Uses `uv`. Dependencies must be synced manually. |
| `client/pyproject.toml` | **Addon deployment** — defines runtime dependencies processed by [ayon-dependencies-tool](https://github.com/ynput/ayon-dependencies-tool). Uses Poetry format. |

**Never** add a runtime dependency only to the root `pyproject.toml`. It must go in `client/pyproject.toml`.

## Developer Commands

Use `./tools/manage.sh` for all common tasks:

```
./tools/manage.sh create-env   # Create/update venv via uv, install pre-commit hooks
./tools/manage.sh run-tests    # Run pytest (excludes 'server' marker)
./tools/manage.sh ruff-check   # Run ruff linter
./tools/manage.sh ruff-fix     # Run ruff linter with --fix
./tools/manage.sh codespell    # Run codespell
./tools/manage.sh run <cmd>    # Run any command via uv run
```

**Requires Python 3.9.x only.** The script will reject 3.10+.

## Testing

- Tests live in `tests/` (not `client/ayon_core/tests/` despite the pyproject.toml `testpaths` setting — the actual path is `tests/` at repo root).
- `conftest.py` adds `client/` to `sys.path` so `ayon_core` is importable.
- Run a single test: `./tools/manage.sh run pytest <path> -v`
- Markers: `unit`, `integration`, `api`, `cli`, `slow`, `server`
- Default test run excludes `server` marker (requires a running AYON server).

## Linting / Formatting

- **Ruff** is the linter and formatter. Pre-commit runs `ruff check` (not `ruff-format`).
- **Codespell** for spelling. Ignore list in `pyproject.toml` `[tool.codespell]`.
- CI runs `ruff-action@v3` on PRs against `develop`.
- Pre-commit enforces branch naming: must match `(release|enhancement|feature|bugfix|documentation|tests|local|chore)/<name>`.

## Code Style (from coding_standards.md)

- PEP-8, max line length **79 characters**.
- Docstrings in **Google format**.
- Use `qtpy` (never PySide6 directly) for Qt portability.
- Use `logging` module, never `print`.
- Always use type hints with `from __future__ import annotations`.
- Favor **dataclasses** over dicts.
- Compatible with **Python 3.9.6**.

## Architecture Notes

- Entry point: `client/ayon_core/cli.py` (CLI) and `client/ayon_core/__main__.py`.
- Main package: `client/ayon_core/` — contains `addon/`, `pipeline/`, `plugins/`, `lib/`, `hooks/`, `host/`, `style/`, `settings/`.
- Pipeline modules: `pipeline/create/`, `pipeline/publish/`, `pipeline/load/`, `pipeline/traits/`.
- Vendor code lives in `client/ayon_core/vendor/`.
- Tests are at repo root `tests/`, mirroring the `client/ayon_core/` structure.

## CI/CD

- Target branch: `develop`.
- PRs trigger: ruff lint, unit tests, label validation.
- Release via `release_trigger.yml` workflow.
- PR labels validated by `validate_pr_labels.yml`.

## Dependency Management

- Root `pyproject.toml` uses **uv** (`uv venv`, `uv sync`).
- `client/pyproject.toml` uses **Poetry** format (processed externally).
- The root `pyproject.toml` has a `pytest-ayon` dependency from a git URL — ensure network access when running `uv sync`.
