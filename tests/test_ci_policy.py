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


def _modular_workflow_job() -> dict[str, Any]:
    workflow = yaml.safe_load(
        (
            PROJECT_ROOT
            / ".github"
            / "workflows"
            / "modular-vrm-output-spike.yml"
        ).read_text(encoding="utf-8")
    )
    return cast(dict[str, Any], workflow["jobs"]["build-modular-vrm"])


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


def test_modular_workflow_retains_spike_and_validates_both_production_variants() -> None:
    job = _modular_workflow_job()

    assert job["env"]["BLENDER_SHA256"] == (
        "4f4fd7646af01f6fee9d420408318381a6e52571268eb7cf9cd5033bd9e7a359"
    )
    blender_download = _named_step(job, "Download and verify pinned Blender")["run"]
    assert (
        'printf \'%s  %s\\n\' "$BLENDER_SHA256" "/tmp/${BLENDER_ARCHIVE}"'
        " | sha256sum --check"
    ) in blender_download

    retained_without = _named_step(
        job,
        "Finalize VRM without accessory in Blender",
    )["run"]
    retained_with = _named_step(
        job,
        "Finalize VRM with accessory in Blender",
    )["run"]
    assert "spikes/modular-asset-composition/finalize_modular_avatar.py" in (
        retained_without
    )
    assert "spikes/modular-asset-composition/finalize_modular_avatar.py" in (
        retained_with
    )

    production = _named_step(
        job,
        "Finalize both production schema 1.1 VRMs through Forge",
    )["run"]
    assert "RetainedBlenderRunnerAdapter" in production
    assert "finalize_compiled_assembly" in production
    assert "production-compiled-without-accessory.json" in production
    assert "production-compiled-with-accessory.json" in production
    assert "production-modular-without-accessory.vrm" in production
    assert "production-modular-with-accessory.vrm" in production
    assert "production-blender-report-without-accessory.json" in production
    assert "production-blender-report-with-accessory.json" in production
    assert "load_forge_build_report" in production

    structural = _named_step(
        job,
        "Validate production modular VRM structures",
    )["run"]
    assert structural.count(
        "spikes/modular-asset-composition/structural_validate.py"
    ) == 2
    assert "production-modular-without-accessory.vrm" in structural
    assert "production-modular-with-accessory.vrm" in structural

    threejs = _named_step(
        job,
        "Validate production modular VRMs through Three.js",
    )["run"]
    assert threejs.count(
        "spikes/modular-asset-composition/three/validate.mjs"
    ) == 2
    assert "production-modular-without-accessory.vrm" in threejs
    assert "production-modular-with-accessory.vrm" in threejs


def test_production_forge_boundary_and_retained_seam_trigger_are_documented() -> None:
    decision = (
        PROJECT_ROOT
        / "docs"
        / "DECISIONS"
        / "D-014-production-blender-forge-boundary.md"
    ).read_text(encoding="utf-8")
    decision_index = (
        PROJECT_ROOT / "docs" / "DECISIONS" / "README.md"
    ).read_text(encoding="utf-8")
    retained_seams = (
        PROJECT_ROOT / "docs" / "migration" / "RETAINED_SEAM_CONTRACTS.md"
    ).read_text(encoding="utf-8")
    pruning = (
        PROJECT_ROOT / "docs" / "migration" / "PRUNING_SEQUENCE.md"
    ).read_text(encoding="utf-8")
    spike = (
        PROJECT_ROOT / "spikes" / "modular-asset-composition" / "README.md"
    ).read_text(encoding="utf-8")

    assert "D-014" in decision_index
    assert "Blender is the final writer" in decision
    assert "VrmBuildSpec is the only source" in decision
    assert "RetainedBlenderRunnerAdapter" in decision
    assert "deletion trigger" in decision
    assert "production schema 1.1" in retained_seams
    assert "must not be deleted" in retained_seams
    assert "CompiledAssemblySpec" in pruning
    assert "production Forge boundary" in pruning
    assert "production-modular-without-accessory.vrm" in spike
    assert "production-modular-with-accessory.vrm" in spike
