# SDD Workflow

This repository consumes `kathesama/kathy-sdd-kit` as a pinned Git submodule.
The kit provides the reusable planning, approval, QA, review, and PR-evidence
workflow. This repository owns its architecture, product constraints, build
commands, asset policy, ticket policy, and delegated execution policy.

## Pinned Kit Revision

| Field | Value |
|---|---|
| Repository | `kathesama/kathy-sdd-kit` |
| Mount point | `.sdd-kit/` |
| Version | `0.6.0` |
| Commit | `2164c5e83a70d88fbb7933a433193a019d8e4cf2` |

The gitlink in this repository is the authoritative pin. Do not use
`git submodule update --remote` as a routine setup command: a kit upgrade is a
reviewed repository change with its own ticket and commit.

## Fresh Clone

```sh
git clone --branch img-set-to-vrm-pipeline --recurse-submodules \
  https://github.com/kathesama/vrm-ia-maker.git
git -C vrm-ia-maker submodule status
cd vrm-ia-maker
sh tools/setup_sdd_workspace.sh
```

## Existing Checkout

```sh
git submodule sync -- .sdd-kit
git submodule update --init --recursive .sdd-kit
sh tools/setup_sdd_workspace.sh
```

The setup script verifies the expected kit version and commit, then exposes the
canonical skills into local tool-specific directories:

```text
.agents/skills/
.claude/skills/
.cursor/skills/
```

Those directories are generated local links and are ignored by Git. Their
editable source remains `.sdd-kit/ai-specs/skills/`.

## Ticket Policy

The canonical key is `GH-{number}` from a GitHub issue in this repository.
Examples: `GH-12`, `GH-108`.

At the time of initial kit adoption, GitHub Issues were disabled and the API
could not create the planned issue. Repository-governance bootstrap may use a
clearly documented `BOOTSTRAP-{number}` key until Issues are enabled. Product or
pipeline implementation must not start under a provisional key.

## Planning And Approval Gate

For each ticket:

1. Resolve the ticket and inspect linked work items.
2. Resolve the workspace:

   ```sh
   sh .sdd-kit/tools/resolve-ticket-workspace.sh {TICKET}
   ```

3. Create:

   ```text
   .ai-specs/changes/{TICKET}/{TICKET}-impl-backend.md
   .ai-specs/changes/{TICKET}/{TICKET}-implementation-spec.md
   .ai-specs/changes/{TICKET}/{TICKET}-CHANGELOG.md
   ```

4. Record the kit version from `.sdd-kit/VERSION`.
5. Map every acceptance criterion to implementation and validation evidence.
6. Validate the plan:

   ```sh
   sh .sdd-kit/tools/validate-impl-spec.sh {TICKET}
   ```

7. Apply the repository approval rule:
   - When a closed escalation condition in
     `docs/DELEGATED_EXECUTION_POLICY.md` applies, present the plan and stop. Only
     an explicit `approve` authorizes execution.
   - Otherwise, record
     `Approval source: standing delegated execution authority (GH-20)` and
     continue without another approval prompt.
8. Implement with RED -> GREEN -> REFACTOR.
9. Run QA and code review as separate gates.
10. Address every valid P0, P1, and P2 finding.
11. Validate execution evidence and PR content:

    ```sh
    sh .sdd-kit/tools/validate-changelog.sh {TICKET}
    sh .sdd-kit/tools/validate-pr-content.sh {TICKET}
    ```

12. Continue through CI, review repair, merge, branch cleanup, and the next safe
    vertical slice unless a closed escalation condition is reached.

The project-local delegated execution policy takes precedence over a generic
per-ticket approval stop from the reusable kit for work performed inside this
repository. It does not waive planning, evidence, CI, review, provenance,
licensing, or truthfulness requirements.

## Repository Validation

```sh
sh tools/check_sdd_workspace.sh
python -m pytest -m "not requires_blender and not requires_vroid_host"
```

Blender and live VRoid-host tests remain separate integration suites.

## Windows

The kit tools are POSIX shell scripts. Use Git Bash, or invoke the `sh.exe`
installed with Git for Windows. Keep shell scripts checked out with LF line
endings; `.gitattributes` enforces this.

## Updating The Kit

Use an explicit reviewed revision:

```sh
git -C .sdd-kit fetch origin
git -C .sdd-kit checkout <approved-commit>
git status --short
git diff --submodule
sh tools/setup_sdd_workspace.sh
sh tools/check_sdd_workspace.sh
```

Commit the updated gitlink in this repository. Durable edits to the kit itself
must be made in `kathesama/kathy-sdd-kit`, not inside the consuming checkout.
