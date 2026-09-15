# client/ayon_core — subsystem map

Directory-scoped guidance for the installed client package. See
`AGENTS.md` at the repository root for repo-wide rules, and
`.agents-main/AGENTS.md` for shared AYON guidance. This file adds only
what applies inside `client/ayon_core/`.

Host-agnostic pipeline library. Subsystems, briefly:

- `addon/` — `AyonAddon`/`ModuleClass` base, addon discovery.
- `host/` — `HostBase`/interfaces every DCC integration implements.
- `pipeline/` — `create/`, `load/`, `publish/`, `farm/`, `anatomy/`,
  `workfile/`, `traits/` — the Pyblish contract surface (see constitution
  Article 2 before touching identifiers, order, or trait shapes here).
- `plugins/` — built-in create/load/publish plugins.
- `tools/` — Qt UI tools (loader, publisher, etc.).
- `lib/` — general utilities, no pipeline semantics.
- `settings/` — client-side settings access helpers (pairs with
  `server/settings/`, constitution Article 3).
- `vendor/` — excluded from Ruff; never reformat.
- `tests/` — core-library unit suite (`testpaths` in root
  `pyproject.toml`). CI's `./tools/manage.sh run-tests` covers only
  `tests/` (UI suite, `-m "not server"`), so run this suite explicitly,
  e.g. `./tools/manage.sh run pytest client/ayon_core/tests -m "not server"`.
