# AYON addon constitution — extension layer (seed template)

<!--
SEED TEMPLATE — copied by `agentic_setup.py` into each consumer addon
repository as `.specify/memory/ayon-addon-constitution.md`, where it becomes
that repository's own, version-controlled extension constitution.

Amendment rules for this file (enforced by the mandatory
`after_constitution` hook → `speckit.ayon-constitution.verify`):
- `/speckit.constitution` in an addon repository writes ONLY here.
- It MUST NOT modify `constitution.md`, `ayon-constitution.md`, or
  `ayon-constitution-evidence.md` (all three are shared, symlinked files).
- This extension may only TIGHTEN the shared constitution — never weaken,
  reinterpret, or contradict it (pointer stub "Extension layer" rule).
- Cite the shared article each extension rule extends (e.g. "extends
  Article 3").
- Bump this file's own version on change; record the change in the Sync
  Impact Report below.
-->

## Extension principles

### [EXTENSION_PRINCIPLE_1_NAME]

[EXTENSION_PRINCIPLE_1_DESCRIPTION — must cite the shared article it
extends and only add stricter requirements]

## Additional constraints

[ADDON_SPECIFIC_CONSTRAINTS — repository-specific rules that do not map to
a shared article; keep them declarative and testable]

## Governance

- This extension constitution is owned and version-controlled by this
  addon repository; the shared constitution remains in
  `ayon-agentic-instructions` and is read through `.agents-main`.
- Amendments require the same evidence discipline as the shared
  constitution: every principle MUST be pointable at an existing file in
  this repository.
- On conflict: the shared constitution wins unless this file is strictly
  stricter; document any such precedence explicitly per rule.

**Version**: 0.1.0 (seed) | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]

<!--
Sync Impact Report
- Version change: (seed)
- Modified: none
- Added: none
- Removed: none
- Follow-up TODOs: replace [EXTENSION_PRINCIPLE_*] and
  [ADDON_SPECIFIC_CONSTRAINTS] placeholders with real, evidence-backed
  rules for this repository; fill dates.
-->
