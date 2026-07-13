# Baseline Test Report

## Execution Identity

| Item | Value |
|---|---|
| Baseline commit | `7b9a2a704e8f8ddc3c7ec7acbd32b9eb1fe0a17d` |
| Diagnostic platform | GitHub-hosted Ubuntu runner |
| Python | 3.11 |
| Diagnostic workflow run | `29261902916` |
| Source capture | `git archive origin/development` |
| Blender tests | Excluded by marker |
| Live VRoid-host tests | Excluded by marker |

The diagnostic workflow was temporary. Its PR was closed without merge and its
branch was reset after evidence capture.

## Commands

```sh
pip install -e ".[dev]"
ruff check src/ tests/ --output-format=json
mypy src/seidr_smidja/ --show-error-codes --no-color-output
pytest --collect-only -q -m "not requires_blender and not requires_vroid_host"
pytest --tb=short -q -m "not requires_blender and not requires_vroid_host"
```

Each command was executed independently so a lint failure could not suppress test
or type-check evidence.

## Result Summary

| Check | Exit | Result |
|---|---:|---|
| Ruff | 1 | 227 findings; 86 reported as autofixable. |
| mypy | 1 | 144 errors in 23 files; 62 source files checked. |
| pytest collection | 0 | 491 tests collected. |
| pytest execution | 0 | 488 passed, 3 skipped, 53 warnings in 4.12s. |
| Standard repository CI | failure | Stops at Ruff; later steps are skipped. |
| SDD validation | success | Repository SDD workspace is healthy. |

## Ruff Findings

### By rule

| Code | Count | Meaning/risk class |
|---|---:|---|
| `E501` | 108 | Line length; mostly mechanical/readability debt. |
| `F401` | 33 | Unused imports; may expose stale integrations. |
| `I001` | 23 | Import ordering; mechanical. |
| `SIM117` | 22 | Nested context-manager simplification. |
| `F841` | 9 | Assigned but unused locals; inspect before autofix. |
| `SIM105` | 8 | Suppressible try/except simplification. |
| `UP017` | 4 | Datetime modernization. |
| `B904` | 3 | Exception chaining. |
| `UP042` | 3 | Enum modernization. |
| Other codes | 14 | Includes two undefined-name findings and smaller style/safety groups. |
| **Total** | **227** | |

The two `F821` undefined-name findings require manual review and must not be swept
into an automatic formatting commit.

### By area

| Area | Findings |
|---|---:|
| `tests/brunhand` | 125 |
| `forge` | 26 |
| `brunhand` source | 25 |
| `oracle_eye` | 12 |
| `bridges` | 8 |
| `hoard` | 7 |
| `annall` | 5 |
| `gate` | 5 |
| Remaining source/tests | 14 |

Most lint debt is either in the out-of-scope Brúarhönd feature or in Blender
scripts that will be adapted. A blanket repository autofix before disposition
would create churn in code scheduled for deletion.

## Mypy Findings

### By area

| Area | Errors |
|---|---:|
| `brunhand` | 49 |
| `bridges` | 46 |
| `forge` | 31 |
| `oracle_eye` | 7 |
| `loom` | 4 |
| `hoard` | 3 |
| `gate` | 2 |
| `annall` | 1 |
| `config.py` | 1 |
| **Total** | **144** |

### By error code

| Code | Count |
|---|---:|
| `unused-ignore` | 64 |
| `misc` | 16 |
| `no-untyped-def` | 15 |
| `type-arg` | 13 |
| `import-untyped` | 10 |
| `no-any-return` | 9 |
| `import-not-found` | 5 |
| Other codes | 12 |

The largest single files are `forge/scripts/build_avatar.py` (29),
`bridges/mjoll/server.py` (21), `brunhand/daemon/runtime.py` (15), and
`bridges/straumur/api.py` (14). This reinforces the proposed order: characterize
and migrate retained seams, then delete out-of-scope bridges instead of polishing
them first.

## Pytest Distribution

| Area | Collected tests |
|---|---:|
| Brúarhönd | 203 |
| Loom | 62 |
| Bridges | 52 |
| Annáll | 48 |
| Root hardening and smoke tests | 45 |
| Hoard | 43 |
| Gate | 33 |
| Blender runner | 5 |
| **Total** | **491** |

The suite gives strong characterization coverage for schemas, catalog/path
security, dispatch behavior, bridge translations, and Brúarhönd. It has only five
direct tests in `_internal`, while Forge and Oracle Eye rely partly on root
hardening tests with mocked Blender execution.

## Warnings

The 53 warnings are concentrated in inherited web/daemon code:

- one Starlette TestClient/HTTPX deprecation warning;
- FastAPI `on_event("startup")` and `on_event("shutdown")` deprecations in
  Brúarhönd daemon tests.

They do not block pytest, but they support removing or isolating those hosted
surfaces rather than carrying them into the CLI.

## CI Interpretation

The repository workflow currently runs:

```text
Ruff -> mypy -> pytest -> coverage
```

without allowing Ruff to fail independently. Because Ruff exits 1, mypy and
pytest are skipped in the normal matrix. Therefore:

- CI is correctly red for lint debt;
- the red status is inherited from the baseline;
- it must not be described as a failing test suite;
- fresh pytest evidence is green;
- no fresh coverage percentage was produced and none is claimed here.

Historical upstream documents mention 82% coverage and smaller Ruff/mypy counts.
Those older figures predate the final Brúarhönd additions and are superseded by
this fresh diagnostic snapshot.

## Characterization To Preserve

Before moving or deleting code, preserve explicit observations for:

1. Blender executable precedence, timeout, process-group termination, and output
   capture.
2. Spec loading and semantic-validation failure modes.
3. Hoard containment, checksum, and catalog validation.
4. Forge temporary-file cleanup and subprocess argument construction.
5. Oracle Eye standard views and soft render failure.
6. Gate parsing of VRM 0.x and 1.0 containers and structured violations.
7. Core stage ordering and partial-failure behavior.
8. CLI JSON output and exit codes selected for compatibility.

## Recommended Follow-Up

Create a separate baseline-quality ticket after disposition is accepted:

- fix Ruff only in retained or immediately adapted code;
- run autofix in small, reviewed groups;
- manually resolve `F821`, `B904`, and unused-value findings;
- reduce mypy scope by removing out-of-scope packages, then make the retained
  namespace strict;
- restructure CI so Ruff, mypy, and pytest report independently while all remain
  required gates for the new namespace.

This inventory intentionally does not modify source or tests.
