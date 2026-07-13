# Local SDD Workspace

The repository uses `kathy-sdd-kit` from `.sdd-kit/` as the framework source.
Ticket-specific planning and execution evidence is local working state and must
be created under:

```text
.ai-specs/changes/{TICKET}/
```

`changes/` is intentionally ignored by Git. Do not place ticket evidence inside
`.sdd-kit/ai-specs/changes/` and do not edit generated skill exposures.

Canonical tickets use `GH-{issue_number}`. `BOOTSTRAP-{number}` is reserved for
repository-governance bootstrap work when the GitHub issue tracker cannot issue
a key; the reason must be recorded in the local plan and PR.

Initialize the submodule and expose agent skills with:

```sh
sh tools/setup_sdd_workspace.sh
```
