# VRM IA Maker Project Context

VRM IA Maker is being evolved from the Seiðr-Smiðja baseline into a focused,
build-time CLI that compiles a canonical multiview character design package into
a validated VRM 1.0 avatar for deterministic use from Three.js.

## Product Boundary

- The tool runs during avatar creation and release; it is not a Juana runtime
  service.
- Three.js controls the avatar at runtime without AI in the avatar layer.
- The character design package is the source of truth. Compiled specs, Blender
  scenes, renders, manifests, and VRM files are generated artifacts.
- Blender-specific operations remain isolated behind infrastructure adapters.
- Third-party assets require explicit provenance and licensing before use.

## Delivery Rules

- Use `GH-{issue_number}` as the canonical ticket key.
- During bootstrap only, when GitHub Issues are unavailable, a documented
  `BOOTSTRAP-{number}` key may be used for repository-governance work.
- Keep local ticket artifacts in `.ai-specs/changes/{TICKET}/`; do not commit
  them and never place them under `.sdd-kit/`.
- Complete and validate the SDD planning gate, then stop for explicit approval
  before implementation.
- Use TDD and Conventional Commits. Keep PRs focused.

## Repository Language Policy

All new or modified comments, docstrings, tests, logs, exception messages,
documentation, commit messages, pull request content, and review comments must be
written in English. Do not translate untouched legacy text solely for consistency.

## Local Setup

```sh
sh tools/setup_sdd_workspace.sh
sh tools/check_sdd_workspace.sh
```

See `docs/development/sdd-workflow.md` for the full operator workflow.

## SDD Kit

@.sdd-kit/CLAUDE.md
