# Inherited Baseline Inventory

**Ticket:** `BOOTSTRAP-2`  
**Inventory date:** 2026-07-13  
**Observed project baseline:** `7b9a2a704e8f8ddc3c7ec7acbd32b9eb1fe0a17d`  
**Imported upstream baseline:** `16cda2e7e65d383c0022b52b461aa2d86b07ee33`

This directory freezes the technical state inherited from Seiðr-Smiðja before
`vrm-ia-maker` removes, replaces, or migrates any runtime behavior. It is an
observation and migration-planning artifact, not a declaration that the current
architecture is correct or suitable for Juana.

No production source, test, build configuration, model, texture, or generated VRM
was changed as part of this inventory.

## Executive Findings

- The useful build path is identifiable and reasonably separable:
  `Loom -> Hoard -> Forge -> Oracle Eye -> Gate`.
- The shared Blender subprocess runner is a strong reuse candidate.
- The current schema overstates implementation breadth: several declared body,
  face, hair, and outfit parameters are not applied by the Blender builder.
- Brúarhönd is 37.6% of source LOC and 203 of 491 collected tests, but is outside
  the Juana build-time CLI target.
- MCP, REST, remote GUI automation, and agent skill bridges are lateral interfaces;
  they are not required by the deterministic Three.js avatar runtime.
- The inherited test suite is behaviorally valuable: 488 tests pass and 3 skip
  when executed independently of the failing Ruff gate.
- CI is red because Ruff reports 227 findings. Pytest itself is green.
- Software licensing is Apache-2.0 in `LICENSE` and `NOTICE`, while
  `pyproject.toml` incorrectly declares MIT.
- The Hoard catalogs third-party assets whose binaries are not committed; several
  entries have missing checksums or incomplete provenance and cannot be treated as
  product-ready assets.

## Evidence Precedence

When sources disagree, use this order:

1. Fresh diagnostics executed against the pinned baseline.
2. Tracked implementation, tests, configuration, and data files.
3. Current interface documents and accepted upstream decisions.
4. Historical README, devlog, audit, philosophy, and task documents.

Historical documents remain useful context, but they do not override observed
behavior.

## Documents

| Document | Purpose |
|---|---|
| [UPSTREAM_BASELINE.md](UPSTREAM_BASELINE.md) | Provenance, snapshot identity, footprint, and confirmed contradictions. |
| [MODULE_INVENTORY.md](MODULE_INVENTORY.md) | Source domains, support directories, test distribution, and current responsibilities. |
| [INTERFACE_INVENTORY.md](INTERFACE_INVENTORY.md) | CLI, REST, MCP, daemon, file, environment, and output interfaces. |
| [DEPENDENCY_MAP.md](DEPENDENCY_MAP.md) | Observed dependency flow, coupling, external dependencies, and reusable seams. |
| [BASELINE_TEST_REPORT.md](BASELINE_TEST_REPORT.md) | Ruff, mypy, pytest, CI, warnings, and characterization evidence. |
| [DISPOSITION_MATRIX.md](DISPOSITION_MATRIX.md) | Proposed `RETAIN`, `ADAPT`, `REPLACE`, and removal decisions by component. |
| [ASSET_AND_LICENSE_INVENTORY.md](ASSET_AND_LICENSE_INVENTORY.md) | Code licensing, tracked media, Hoard assets, provenance gaps, and output policy. |
| [PRUNING_SEQUENCE.md](PRUNING_SEQUENCE.md) | Safe dependency-ordered migration and deletion sequence. |

## Disposition Vocabulary

| Decision | Meaning |
|---|---|
| `RETAIN` | Preserve behavior and migrate with minimal semantic change. |
| `ADAPT` | Reuse the capability behind a new contract or narrower responsibility. |
| `REPLACE` | Build a new source of truth, then retire the inherited implementation. |
| `REMOVE_LATER` | Outside target scope, but remove only after dependents and tests are detached. |
| `OUT_OF_SCOPE` | Not part of the Juana avatar-maker product. |
| `UNKNOWN` | Provenance or behavior must be resolved before a safe decision. |

## Engineering Rule Packs Applied

| Rule pack | Active obligations | How this inventory applies them |
|---|---|---|
| `working-effectively-with-legacy-code.mini.md` | `WELC-01`, `WELC-02`, `WELC-03` | Records behavior to preserve, identifies migration seams, and requires deletion triggers for temporary compatibility paths. |
| `the-pragmatic-programmer.mini.md` | `TPP-01`, `TPP-02`, `TPP-03` | Identifies future sources of truth, orders reversible cutovers, and records fresh diagnostic feedback. |

## Product Boundary Used By This Inventory

`vrm-ia-maker` is a build-time CLI that compiles a canonical multiview character
package into a validated VRM 1.0 artifact. Three.js owns deterministic runtime
behavior such as loading, rendering, blinking, look-at, expression weights,
visemes, lip-sync, and animation. No LLM, autonomous agent, MCP server, Planner,
or Soul behavior belongs in the avatar runtime.

## Verification

The evidence was captured from the exact `development` tree with `git archive`
and separate Python 3.11 diagnostics. See
[BASELINE_TEST_REPORT.md](BASELINE_TEST_REPORT.md) for commands, exit codes, and
limitations.
