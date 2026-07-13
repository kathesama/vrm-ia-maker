## Ticket
<!-- AUTO-TICKET-START -->
N/A
<!-- AUTO-TICKET-END -->

**Target branch**
- [ ] `development` (feature integration)
- [ ] `main` (release or urgent production fix)

## Summary
<!-- AUTO-SUMMARY-START -->
<!-- AUTO-SUMMARY-END -->

## Change Type
- [ ] Bugfix
- [ ] Feature
- [ ] Refactor
- [ ] Documentation / chore
- [ ] Infrastructure / CI

## Scope
- [ ] Character design package / schema
- [ ] Compiler / base adapter
- [ ] Blender forge / rendering
- [ ] VRM or Three.js compatibility
- [ ] CLI
- [ ] Tests
- [ ] Documentation
- [ ] CI / repository governance

## What Was Done
-
-
-

## Changes

### Files Created
-

### Files Modified
-

### Files Deleted
-

## Testing And Validation

- Tests written or updated:
- Scenarios covered:
- Commands executed:
- CI status:

## Acceptance Criteria Coverage

- [ ] AC:
  - Status:
  - Evidence:

## Generated Artifacts

<!-- For avatar/build changes, list VRM, manifests, reports, and renders. Otherwise write N/A. -->
N/A

## How To Test

```sh
sh tools/setup_sdd_workspace.sh
sh tools/check_sdd_workspace.sh
python -m pytest -m "not requires_blender and not requires_vroid_host"
```

Additional integration commands:

```sh
# Add Blender, VRM, or Three.js validation commands when applicable.
```

## Risks And Mitigations

- Risk:
- Mitigation:

## Asset And License Review

- [ ] No untracked third-party asset was added
- [ ] New assets include source, author, license, redistribution terms, and checksum
- [ ] Generated avatar licensing is documented separately from tool licensing
- [ ] Apache-2.0 notices are preserved for derived source code

## SDD Evidence

- Implementation plan:
- Implementation spec:
- Changelog:
- QA report:
- Code review report:
- PR report:

## Pre-Merge Checklist

- [ ] Scope is small and focused
- [ ] No secrets or credentials are present
- [ ] Submodule pointer is intentional and reviewed
- [ ] SDD validators pass
- [ ] Tests cover the change or the validation gap is documented
- [ ] Documentation is updated where applicable
- [ ] Risks and mitigations are documented
- [ ] Commits follow Conventional Commits
