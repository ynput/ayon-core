# Spec Kit — Spec-Driven Development setup (harness-agnostic)

This repository is deliberately **agent-harness agnostic**: no agent-specific
scaffolding (`.agents/`, `.goose/`, `.github/skills/`, `.kilo/`, `.zed/`,
`.specify/` output, ...) is committed. Every team member installs their own
AI-coding-agent integration and links the shared AYON instructions
(`.agents-main`) themselves. This document is the pointer — it stays
version-agnostic on purpose, so it does not pin a Spec Kit release.

Spec Kit (<https://github.com/github/spec-kit>) is an open-source,
harness-agnostic Spec-Driven Development toolkit. It works with 30+ AI
coding agents (Claude, Copilot, Gemini, Cursor, Codex, Goose, Grok, Kilo,
Zed, ...): you pick the agent, install the integration, and use the
`/speckit-*` workflows in the repo.

## One-time setup

### 1. Link the shared AYON instructions (`.agents-main`)

`AGENTS.md` and the SpeckIt workflow read shared AYON guidance from a
symlink `.agents-main -> ../ayon-agentic-instructions` at the repo root.
The link is expected to be created by tooling/CI, but can be set up
manually:

```bash
# Clone next to this repository's root (sibling directory), e.g.:
git clone \
  https://github.com/ynput/ayon-agentic-instructions ../ayon-agentic-instructions
# ...then symlink it in this repo (gitignored, never committed):
ln -s ../ayon-agentic-instructions .agents-main
```

Key files provided by the shared repo:

- `.agents-main/AGENTS.md` — universal AYON instruction entry point.
- `.agents-main/fragments/core.md` — `ayon-core` repo-type detail.
- `.agents-main/memory/ayon-constitution.md` — the active SDD constitution
  (`.specify/memory/constitution.md` is a tracked symlink to it).

### 2. Install Spec Kit for your preferred agent

Install the `specify` CLI (version-agnostic — use the current release of
Spec Kit):

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
```

Then install your integration. On a fresh checkout, initialize; in this
existing repo, just install the integration for your agent:

```bash
specify integration install <your-agent>
# where supported, agent skills instead of slash-command prompts:
specify integration install <your-agent> --integration-options="--skills"
```

Run `specify integration list` for all available agents and
`specify integration install --help` for options.

## What the install creates, and why it is ignored

| Path | Created by | Content |
| --- | --- | --- |
| `.agents/` | skills-mode integrations (e.g. Zed) | shared skills, e.g. `speckit-*/SKILL.md` |
| `.github/skills/` | GitHub Copilot integration | Copilot agent skills |
| `.goose/` | Goose integration | `speckit.*.yaml` recipes |
| `.kilo/` | Kilo integration | `speckit.*.md` commands |
| `.zed/` | Zed integration | tasks/agent config |
| `.specify/` | Spec Kit core | scripts, templates, workflows, install manifests |
| `.specify/memory/constitution.md` | Spec Kit core | **tracked** symlink to the shared constitution (see above) |

Everything except `.specify/memory/constitution.md` is per-machine,
per-harness, and regenerable by the CLI, so the repo's `.gitignore` ignores
it and the files are not committed. The shared `.specify/.gitignore`
(managed by the CLI) additionally keeps `feature.json` and
`extensions/*/local-config.yml` out of version control.

> `.agents/skills/` is the closest thing to a cross-harness skills location
> and is a reasonable spot for team-authored skills. It is still not
> committed: skills installed here are generated artifacts of a specific
> integration/version, and the repo stays agnostic.

## Where the instructions live

- `AGENTS.md` (root) — committed, self-sufficient repo guidance; read it
  regardless of harness.
- `client/ayon_core/AGENTS.md` — committed, scoped subsystem guidance.
- `.agents-main/` — linked shared guidance (enrichment; never commit it).
- `.specify/memory/constitution.md` — tracked symlink to
  `.agents-main/memory/ayon-constitution.md`; the actual file comes from
  the shared repo, so amendments propagate automatically.

## Keep it clean

- Never commit harness output or per-machine state (`.specify/*.json`
  manifests record which agent was installed and are machine-local).
- Never create a hard copy of the constitution — keep the symlink so
  amendments propagate.
- If you add another agent integration, its config directory will be
  ignored by the future-proofed patterns in `.gitignore`; no repo change is
  needed — but do document any agent that writes elsewhere in this file.
