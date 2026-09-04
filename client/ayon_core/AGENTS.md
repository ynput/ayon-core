# client/ayon_core — subsystem map

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
- `tests/` — pytest suite (`testpaths` in root `pyproject.toml`).
