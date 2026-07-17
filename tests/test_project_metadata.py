"""Repository identity, licensing, and attribution contract tests."""

from __future__ import annotations

import hashlib
import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from PIL import Image

from vrm_ia_maker.design.contracts import ProvenanceRecord, SourceClass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_BASELINE = "16cda2e7e65d383c0022b52b461aa2d86b07ee33"


def _project_metadata() -> dict[str, Any]:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        document = tomllib.load(stream)
    return cast(dict[str, Any], document["project"])


def test_distribution_uses_vrm_ia_maker_identity() -> None:
    metadata = _project_metadata()

    assert metadata["name"] == "vrm-ia-maker"
    assert metadata["version"] == "0.1.0.dev0"
    assert metadata["description"].startswith("Build-time CLI")
    assert metadata["requires-python"] == ">=3.11"


def test_installed_distribution_matches_project_version() -> None:
    metadata = _project_metadata()

    assert version("vrm-ia-maker") == metadata["version"]


def test_distribution_declares_apache_2_license() -> None:
    metadata = _project_metadata()

    assert metadata["license"] == {"text": "Apache-2.0"}
    assert "License :: OSI Approved :: Apache Software License" in metadata["classifiers"]


def test_legacy_seidr_command_remains_available_during_migration() -> None:
    metadata = _project_metadata()

    assert metadata["scripts"]["seidr"] == "seidr_smidja.bridges.runstafr.entrypoint:main"
    assert set(metadata["scripts"]) == {"seidr"}


def test_reference_authoring_dependencies_keep_online_provider_optional() -> None:
    metadata = _project_metadata()

    assert "Pillow>=11,<13" in metadata["dependencies"]
    assert metadata["optional-dependencies"]["authoring-openai"] == [
        "openai>=2.30,<3"
    ]


def test_project_urls_preserve_repository_and_upstream_provenance() -> None:
    metadata = _project_metadata()

    assert metadata["urls"]["Repository"] == "https://github.com/kathesama/vrm-ia-maker"
    assert metadata["urls"]["Upstream"] == "https://github.com/hrabanazviking/Seidr-Smidja"


def test_notice_preserves_upstream_attribution() -> None:
    notice = (PROJECT_ROOT / "NOTICE").read_text(encoding="utf-8")

    assert "VRM IA Maker" in notice
    assert "Seiðr-Smiðja" in notice
    assert "Volmarr Wyrd" in notice
    assert UPSTREAM_BASELINE in notice
    assert "Apache License, Version 2.0" in notice


def test_repository_ships_apache_license_text() -> None:
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text


def test_bounded_reference_authoring_decision_and_workflow_are_documented() -> None:
    decision = (
        PROJECT_ROOT / "docs/DECISIONS/D-013-bounded-reference-authoring.md"
    ).read_text(encoding="utf-8")
    decision_index = (PROJECT_ROOT / "docs/DECISIONS/README.md").read_text(
        encoding="utf-8"
    )
    package_guide = (PROJECT_ROOT / "docs/CHARACTER_DESIGN_PACKAGE.md").read_text(
        encoding="utf-8"
    )

    assert "D-013" in decision_index
    assert "build-time-only" in decision
    assert "OPENAI_API_KEY" in decision
    assert "one provider request" in decision
    assert "human approval" in decision
    assert "no provider calls" in decision
    assert "master character sheet" in package_guide
    assert "approved predecessor sheets" in package_guide
    assert "raw and rejected candidates" in package_guide
    assert "python -m vrm_ia_maker.design.cli" in package_guide


def test_asset_and_third_party_policies_are_present() -> None:
    asset_policy = (PROJECT_ROOT / "ASSET_POLICY.md").read_text(encoding="utf-8")
    third_party_notices = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )

    assert "Required asset record" in asset_policy
    assert "sha256" in asset_policy
    assert "redistribution_allowed" in asset_policy
    assert "Pillow" in third_party_notices
    assert "OpenAI Python SDK" in third_party_notices
    assert "Seiðr-Smiðja" in third_party_notices


def test_juana_master_reference_has_verified_first_party_provenance() -> None:
    provenance_path = PROJECT_ROOT / "examples/Juana-full-concept-white.provenance.json"
    record = ProvenanceRecord.model_validate_json(
        provenance_path.read_text(encoding="utf-8")
    )
    asset_path = PROJECT_ROOT / record.artifact.path
    asset_data = asset_path.read_bytes()

    assert record.source_class is SourceClass.CREATIVE_CANON
    assert record.artifact.path == "examples/Juana-full-concept-white.png"
    assert record.artifact.byte_length == len(asset_data)
    assert record.artifact.sha256 == hashlib.sha256(asset_data).hexdigest()
    with Image.open(asset_path) as image:
        assert image.format == "PNG"
        assert image.size == (record.artifact.width, record.artifact.height)

    assert record.rights is not None
    assert record.rights.is_complete
    assert record.rights.rights_holder == "Katherine E. Aguirre"
    assert record.rights.commercial_use is True
    assert record.rights.modification_allowed is True
    assert record.rights.redistribution_allowed is True
