# Architectural Decision Records — Index
**Keeper:** Eirwyn Rúnblóm (Scribe) + Rúnhild Svartdóttir (Architect)
**Last updated:** 2026-07-17

---

## What Is an ADR?

An Architectural Decision Record (ADR) is a short document that preserves one architectural decision — the tension that prompted it, what was decided, and what that decision makes possible or constrains. ADRs are not meeting notes. They are the living memory of why the codebase is shaped the way it is.

Every decision that shapes how the domains are structured, how data flows, or how the system behaves under failure belongs here as an ADR. Tactical implementation choices (which library to use for a helper function) do not need ADRs. Structural choices (where does the Blender runner live, how does Annáll reach every caller) do.

When you encounter something in the codebase that seems strange or over-engineered, there is almost certainly an ADR that explains why. Read the relevant ADR before changing it.

---

## Numbering Convention

Files are named `D-NNN-short-slug.md` where:
- `NNN` is a zero-padded three-digit sequence number (D-001, D-002, ..., D-042, ...)
- `short-slug` is a lowercase-hyphenated summary of the decision topic

Numbers are assigned in the order decisions are ratified — not in order of importance. A higher number is simply more recent. When a decision supersedes an earlier one, both documents are updated: the old ADR gains a `Status: Superseded by D-NNN` line; the new ADR references the superseded document.

---

## Lifecycle

```
Proposed  →  Accepted  →  Superseded (by D-NNN)
                 ↓
             (may also be)
             Rejected (recorded but not implemented)
```

- **Proposed:** The decision has been discussed but not yet ratified by Volmarr.
- **Accepted:** Ratified. The codebase must honor this decision.
- **Superseded:** A later ADR changed this. The old ADR remains for historical reference.
- **Rejected:** The option was considered and declined. The ADR is kept so the reasoning is not lost.

---

## ADR Template

```markdown
# D-NNN — <Title>
**Status:** Accepted
**Date:** YYYY-MM-DD
**Deciders:** Volmarr Wyrd, Runa Gridweaver Freyjasdóttir
**Phase:** <phase name>

## Context
<short — what tension or question prompted this decision>

## Decision
<the actual decision, stated clearly>

## Consequences
<what becomes possible, what becomes constrained, what must be revisited later>

## References
<cross-links to relevant docs>
```

---

## Decision Index

| # | Title | Status | Date | One-Line Summary |
|---|---|---|---|---|
| [D-001](D-001-project-name-and-path-b.md) | Project Name and Path B | Accepted | 2026-05-06 | Project is Seiðr-Smiðja; base mesh strategy is VRoid + Blender headless + VRM Add-on (saturday06) |
| [D-002](D-002-repo-and-branch.md) | Repo and Branch | Accepted | 2026-05-06 | Standalone repo at `hrabanazviking/Seidr-Smidja`; `development` for all work, `main` at release tags only |
| [D-003](D-003-shared-blender-runner-location.md) | Shared Blender Runner Location | Accepted | 2026-05-06 | Shared runner lives at `_internal/blender_runner.py`, not inside Forge or Oracle Eye |
| [D-004](D-004-hoard-v0_1-local-only.md) | Hoard v0.1 Strategy | Accepted | 2026-05-06 | Local-only in v0.1; no remote fetch; `resolve()` interface shaped for future adapter |
| [D-005](D-005-annall-port-injection-pattern.md) | AnnallPort Injection Pattern | Accepted | 2026-05-06 | Port constructed at startup, passed as parameter; no global state; `None` disables logging in unit tests |
| [D-006](D-006-oracle-eye-render-failure-behavior.md) | Oracle Eye Render-Failure Behavior | Accepted | 2026-05-06 | Render failure is soft: `.vrm` + structured warning returned; build not withheld |
| [D-007](D-007-blender-subprocess-pattern-v0_1.md) | Blender Subprocess Pattern v0.1 | Accepted | 2026-05-06 | Two separate subprocess invocations (Forge + Oracle Eye); single-session optimization deferred |
| [D-008](D-008-cli-command-name-inspect.md) | CLI Command Name: `seidr inspect` | Accepted | 2026-05-06 | `seidr inspect` is canonical (not `seidr check`); ratifies AUDIT-003 partial closure; `list-assets` deferred to v0.1.1 |
| [D-009](D-009-list-assets-and-bootstrap-hoard-cli.md) | `seidr list-assets` Implemented + `seidr bootstrap-hoard` Documented | Accepted | 2026-05-06 | Both deferred D-008 sub-items closed; v0.1.1-pending INTERFACE amendment ratified; AUDIT-003 fully closed |
| [D-010](D-010-brunhand-feature-genesis.md) | Brúarhönd Feature Genesis (Cross-Machine VRoid Studio Remote Control) | Accepted | 2026-05-06 | Scope (c) ratified — primitives in v0.1, translation deferred to v0.2; lateral dispatch surface; Tailscale ACL + bearer token defense in depth; Skald-named sub-modules (Horfunarþjónn / Hengilherðir / Gæslumaðr / Sjálfsmöguleiki / Ljósbrú / Tengslastig); httpx promoted to base deps |
| [D-011](D-011-production-threejs-assembly-compiler.md) | Production Three.js Assembly Compiler Boundary | Accepted | 2026-07-15 | Pydantic owns contracts, a versioned adapter owns base mappings, Three.js compiles and inspects, and Blender remains the final VRM writer. |
| [D-013](D-013-bounded-reference-authoring.md) | Bounded Reference Authoring | Accepted | 2026-07-16 | A fixed human-gated build-time workflow may use one optional online image adapter while sealed packages and downstream builds remain provider-free. |
| [D-014](D-014-production-blender-forge-boundary.md) | Production Blender Forge Boundary | Accepted | 2026-07-17 | A port-injected Forge validates staged schema 1.1 outputs while Blender remains the final VRM writer and retained spike evidence stays intact. |

---

*Index maintained by Eirwyn Rúnblóm, Scribe — updated at each new ADR.*
