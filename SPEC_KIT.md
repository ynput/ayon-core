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

Recommended — run the setup script from the repo root (idempotent,
cross-platform; see `python agentic_setup.py install --help`):

```bash
python agentic_setup.py install
# optional: also install the specify CLI and an agent integration:
python agentic_setup.py install --specify --integration=goose
```

Manual fallback (macOS/Linux):

```bash
# Clone next to this repository's root (sibling directory), e.g.:
git clone \
  https://github.com/ynput/ayon-agentic-instructions ../ayon-agentic-instructions
# ...then symlink it in this repo (gitignored, never committed):
ln -s ../ayon-agentic-instructions .agents-main
```

On Windows, do not use `ln -s` (Git Bash copies instead of linking) —
let `agentic_setup.py` handle the platform-specific linking and the
constitution; see its module docstring for details.

Key files provided by the shared repo:

- `.agents-main/AGENTS.md` — universal AYON instruction entry point.
- `.agents-main/fragments/core.md` — `ayon-core` repo-type detail.
- `.agents-main/.specify/memory/` — the canonical constitution home:
  `ayon-constitution.md` (shared constitution), `constitution.md`
  (pointer stub), `ayon-constitution-evidence.md` (evidence annex),
  `ayon-addon-constitution.md` (seed copied into this repo).
  `agentic_setup.py` symlinks the first three into
  `.specify/memory/` and copies the seed as the addon-owned
  `ayon-addon-constitution.md`.

### 2. Install Spec Kit for your preferred agent

Install the `specify` CLI (version-agnostic — use the current release of
Spec Kit):

```bash
uv tool install specify-cli
```

Then install your integration (or let the setup script do it:
`python agentic_setup.py install --specify [--integration=<agent>]
[<extra args passed verbatim to specify>]`). On a fresh checkout,
initialize; in this existing repo, just install the integration for
your agent:

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
| `.specify/memory/constitution.md`, `ayon-constitution.md`, `ayon-constitution-evidence.md` | `agentic_setup.py` | machine-local symlinks into the shared repository's `.specify/memory/` |
| `.specify/memory/ayon-addon-constitution.md` | `agentic_setup.py` | copied seed — **tracked** extension constitution owned by this repo |
| `.specify/presets/ayon-constitution/`, `.specify/extensions/ayon-constitution/`, `.specify/extensions.yml` | `agentic_setup.py` | governance preset/extension installing the wrapped `/speckit.constitution` and the mandatory `after_constitution` hook |

Everything except `.specify/memory/ayon-addon-constitution.md` is
per-machine, per-harness, and regenerable by the CLI or the setup script,
so the repo's `.gitignore` ignores it and the files are not committed (a
negation exception keeps the addon constitution tracked). The shared
`.specify/.gitignore`
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
- `.specify/memory/constitution.md`, `ayon-constitution.md`,
  `ayon-constitution-evidence.md` — machine-local symlinks to
  `.agents-main/.specify/memory/…`; the actual files come from the shared
  repo, so amendments propagate automatically.
- `.specify/memory/ayon-addon-constitution.md` — copied seed, tracked in
  this repo; this is the only constitution file `/speckit.constitution`
  amends here (extension layer — it may only tighten the shared one).

## Spec & bug records (what gets committed)

Version control keeps the durable decision record, not the working files —
this is what future agents (and reviewers) read to understand past choices:

| File | Produced by | Kept |
| --- | --- | --- |
| `specs/<NNN-feature>/spec.md` | `/speckit.specify` | ✅ what & why (requirements, acceptance criteria) |
| `specs/<NNN-feature>/plan.md` | `/speckit.plan` | ✅ how & why (approach, decisions) |
| `specs/<NNN-feature>/tasks.md` | `/speckit.tasks` | ✅ what was done (task breakdown) |
| `specs/<NNN-feature>/research.md`, `data-model.md`, `quickstart.md`, `contracts/`, `checklists/` | plan phase / checklists | ❌ working artifacts — regenerate with `/speckit.plan` if needed |
| `.specify/bugs/<slug>/assessment.md` | `speckit.bug.assess` | ✅ root cause & remediation decision |
| `.specify/bugs/<slug>/fix.md` | `speckit.bug.fix` | ✅ what changed (+ deviations) |
| `.specify/bugs/<slug>/test.md` | `speckit.bug.test` | ✅ verification report |

Commit the spec files with the feature's code on the feature branch.

## Keep it clean

- Never commit harness output or per-machine state (`.specify/*.json`
  manifests record which agent was installed and are machine-local).
- Never create a hard copy of the constitution — keep the symlink so
  amendments propagate.
- If you add another agent integration, its config directory will be
  ignored by the future-proofed patterns in `.gitignore`; no repo change is
  needed — but do document any agent that writes elsewhere in this file.
