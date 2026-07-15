"""CI quality-gate policy tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ci_jobs() -> dict[str, Any]:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    return cast(dict[str, Any], workflow["jobs"])


def _named_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    steps = cast(list[dict[str, Any]], job["steps"])
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(f"CI job does not define the expected step: {name}")


def test_ruff_job_gates_production_and_reports_inherited_baseline() -> None:
    lint_job = cast(dict[str, Any], _ci_jobs()["lint"])

    assert lint_job.get("continue-on-error", False) is False
    assert _named_step(lint_job, "Run production Ruff gate")["run"] == (
        "ruff check src/vrm_ia_maker/ tests/unit/vrm_ia_maker/ tests/test_ci_policy.py"
    )

    inherited_step = _named_step(lint_job, "Report inherited Ruff baseline")
    assert inherited_step["run"] == "ruff check src/ tests/"
    assert inherited_step["if"] == "${{ always() }}"
    assert inherited_step["continue-on-error"] is True


def test_mypy_job_gates_production_and_reports_inherited_baseline() -> None:
    typecheck_job = cast(dict[str, Any], _ci_jobs()["typecheck"])

    assert typecheck_job.get("continue-on-error", False) is False
    assert _named_step(typecheck_job, "Run production mypy gate")["run"] == (
        "mypy src/vrm_ia_maker/"
    )

    inherited_step = _named_step(typecheck_job, "Report inherited mypy baseline")
    assert inherited_step["run"] == "mypy src/seidr_smidja/"
    assert inherited_step["if"] == "${{ always() }}"
    assert inherited_step["continue-on-error"] is True


def test_node_job_gates_the_production_three_assembly_compiler() -> None:
    node_job = cast(dict[str, Any], _ci_jobs()["three-assembly-compiler"])

    assert node_job.get("continue-on-error", False) is False
    assert _named_step(node_job, "Set up Node.js 22")["with"]["node-version"] == "22"
    assert _named_step(node_job, "Install production compiler dependencies")["run"] == (
        "npm ci --prefix packages/three-assembly-compiler --no-audit --no-fund"
    )
    assert _named_step(node_job, "Run production compiler syntax gate")["run"] == (
        "npm run check --prefix packages/three-assembly-compiler"
    )
    assert _named_step(node_job, "Run production compiler tests")["run"] == (
        "npm test --prefix packages/three-assembly-compiler"
    )
