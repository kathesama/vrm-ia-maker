"""Repository identity, licensing, and attribution contract tests."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

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


def test_asset_and_third_party_policies_are_present() -> None:
    asset_policy = (PROJECT_ROOT / "ASSET_POLICY.md").read_text(encoding="utf-8")
    third_party_notices = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )

    assert "Required asset record" in asset_policy
    assert "sha256" in asset_policy
    assert "redistribution_allowed" in asset_policy
    assert "Seiðr-Smiðja" in third_party_notices
