# Delegated Execution Policy

## Status

Active project policy for autonomous implementation inside
`kathesama/vrm-ia-maker`.

## Purpose

Kathy has granted standing authority for Codex and other approved implementation
agents to advance this repository's mission without requesting approval for every
reversible implementation slice.

The mission is to build a reproducible offline toolchain that turns an approved
`CharacterDesignPackage` and traceable 3D assets into a validated VRM 1.0 avatar,
ultimately producing `dist/juana/juana.vrm` for deterministic Three.js use.

This policy resolves the tension between the SDD plan-approval checkpoint and the
project owner's explicit instruction to continue independently until a genuine
blocker is reached.

## Authorized repository scope

Standing authority applies only to:

```text
https://github.com/kathesama/vrm-ia-maker
```

Within that repository, the agent is authorized to:

- create and update GitHub issues;
- create, update, and delete feature branches;
- create commits on feature, fix, documentation, spike, recovery, or release-preparation branches;
- open, update, mark ready, and merge pull requests;
- address review comments;
- rerun or repair CI;
- add tests, schemas, adapters, tools, documentation, and build workflows;
- make reversible architectural and implementation decisions that advance the
  repository mission;
- continue from one completed slice to the next without waiting for a new user
  message.

`development` is the normal integration branch. `main` remains release-oriented.

## Protected integration branches

This section governs implementation agents. It does not restrict the repository owner
from making direct commits when she intentionally chooses to do so.

Agents must never create or push ordinary work commits directly to `development` or
`main`.

All implementation, documentation, recovery, and CI repair work must occur on a
non-protected branch and enter `development` through a pull request. The only normal
agent-created commit allowed to land on `development` is the commit produced by the
approved GitHub pull-request merge operation.

Partial, experimental, failing, or review-incomplete agent work must remain on its
feature or recovery branch. It must not be used as an integration checkpoint.

When an accidental agent-created direct commit is discovered:

1. preserve its exact commit on a recovery branch;
2. stop further direct pushes;
3. restore a green integration state through a reviewable recovery or revert plan;
4. split the preserved work into the correct issue branches and pull requests;
5. do not hide, amend away, or silently discard the accidental work.

An intentional direct commit authored by Kathy is not an agent-policy violation and
must not be characterized as accidental agent behavior. Agents must treat owner-authored
work as current repository state, inspect it, validate it, and continue from it unless a
real escalation condition applies.

Rewriting shared history remains an escalation condition. Prefer a normal revert or
reviewable recovery flow unless Kathy explicitly authorizes a force update.

## Standing approval and the SDD gate

For in-scope, reversible work, this policy is the explicit approval required by
step 6 of the repository SDD workflow.

A ticket plan must record:

```text
Approval source: standing delegated execution authority (GH-20)
```

The agent must still create and validate the ticket plan, implementation spec,
and changelog. It must not stop merely to ask for `approve`, `change`, or `deny`
when no escalation condition applies.

The normal loop is:

```text
inspect current state
-> select the smallest useful vertical slice
-> create or resolve the GitHub issue
-> create a non-protected branch
-> create and validate SDD artifacts
-> implement with RED -> GREEN -> REFACTOR
-> run local validation
-> open or update the pull request
-> wait for CI and automated review
-> address valid P1 and P2 findings
-> merge when green and review-clean
-> delete the merged branch
-> select the next slice
-> continue
```

Opening an issue, writing a plan, creating a branch, pushing a commit, or opening
a pull request is not a completion condition by itself.

## Safe default rule

When several reasonable implementation choices exist, the agent must choose a
safe, reversible, locally testable default and continue.

The agent must document the choice in an ADR, decision record, ticket plan, or PR
when it affects architecture or future compatibility.

The agent must not ask Kathy to choose among implementation details when all
options:

- remain inside this repository;
- have compatible and verified licensing;
- require no paid service, secret, or external infrastructure mutation;
- are reversible without losing approved source data;
- preserve the product mission and validation contract.

## Closed escalation list

The agent must stop and request Kathy's direct decision only when at least one of
the following conditions is true.

### 1. Visual canon decision

A new or materially changed face, body shape, hairstyle, outfit, color identity,
expression language, or other user-facing character canon requires approval
before it becomes approved production canon.

The agent may create reviewable provisional renders without prior approval when
they are clearly labeled as provisional.

### 2. Unresolved legal or provenance risk

An asset, model, font, texture, dependency, or generated-output license has
unresolved questions involving source, author, commercial use, modification,
redistribution, attribution, territory, or output ownership.

A dependency with a verified compatible license is not automatically an
escalation merely because it is new.

### 3. Secrets, paid services, or external infrastructure

The work requires credentials, private keys, paid usage, cloud provisioning,
account changes, secrets, or mutation of infrastructure outside this repository.

### 4. Destructive or irreversible action

The work would rewrite shared Git history, remove unreplaced source-of-truth
assets, publish a release, publicly distribute a production avatar, delete data,
or perform another action that cannot be safely rolled back.

Ordinary squash merges into `development` are authorized and are not considered
an escalation.

### 5. Material product fork without a safe default

Two or more options would create materially different user-facing products, and
there is no safe reversible implementation that preserves both paths for later
selection.

### 6. Missing design information with no honest provisional path

A required visual or metric input is absent and the missing value cannot be:

- recorded as an explicit gap;
- represented by a reversible provisional assumption;
- isolated behind a configurable adapter;
- deferred without blocking useful validated work.

### 7. Repository boundary

The required action would modify another repository, global GitHub settings,
Juana IA runtime services, or any system outside `kathesama/vrm-ia-maker`.

This list is exhaustive. A reason not listed here is not, by itself, grounds to
stop and request approval.

## Visual reconstruction and assumptions

Approved character sheets are creative canon. They are not automatically
orthographic measurement data.

The agent may use clearly documented provisional assumptions to produce visual
review iterations. Each assumption must be classified as one of:

- `approved_fact`;
- `measured_input`;
- `derived_constraint`;
- `provisional_visual_assumption`;
- `blocking_gap`.

A `provisional_visual_assumption` may drive a preview build, render comparison,
or temporary mesh adjustment. It must not be promoted to `measured_input` or
`approved_fact` without evidence or Kathy's approval.

The correct response to incomplete references is therefore not always to stop.
The preferred sequence is:

```text
record the gap
-> isolate the assumption
-> build a reversible preview
-> compare against approved references
-> continue technical work
-> request visual approval only when a canon checkpoint is ready
```

## External tool and dependency selection

The agent may adopt a new local tool or dependency without asking for approval
when:

- its license and distribution terms are verified and compatible;
- its version and integrity are pinned;
- it does not require secrets or paid infrastructure;
- it is placed behind a port or adapter when it is an infrastructure detail;
- a fallback or migration path is documented;
- tests prove the product contract rather than merely proving tool invocation.

The agent must not present a tool choice as a blocker simply because multiple
compatible tools exist.

## Merge authority

The agent may merge a pull request into `development` when:

- required CI is green;
- no unresolved valid P1 or P2 review thread remains;
- repository language, provenance, and licensing policies are satisfied;
- the PR has a valid GitHub issue and required SDD evidence;
- generated-artifact claims are supported by actual files and reports.

After merge, the agent should delete the merged branch when safe and continue to
the next issue.

## Truthfulness requirements

Autonomy does not relax evidence requirements.

The agent must never:

- claim that a VRM, render, model, report, or test exists when it was not produced;
- describe procedural fixtures as Juana's finished production avatar;
- convert artistic perspective or occluded anatomy into asserted measured fact;
- hide failing tests or unresolved review findings;
- use an asset whose legal provenance is unknown;
- treat visual attractiveness as proof of rigging, morph, VRM, or runtime validity.

## Stop report

When a real escalation condition is reached, the agent must leave the repository
in a clean, reviewable state and report:

- completed issues, commits, pull requests, and merges;
- current branch and exact commit;
- validation evidence;
- the specific escalation condition from this policy;
- the smallest decision, credential, or approved source needed from Kathy;
- the safe work that can continue independently while waiting, when applicable.
