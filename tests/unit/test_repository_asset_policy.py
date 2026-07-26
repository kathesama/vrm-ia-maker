from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _policy_lines(relative_path: str) -> set[str]:
    return {
        line.strip()
        for line in (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_generated_and_scratch_roots_are_ignored_without_hiding_required_archive() -> None:
    ignore_lines = _policy_lines(".gitignore")

    assert {
        "build/",
        "output/",
        "/.superpowers/brainstorm/",
        "/.pytest-tmp*/",
        "/.pytest_tmp/",
        "/.tmp_pytest*/",
        "/.t3*/",
        "/.tmp/",
        "/artifacts/debug/*",
        "!/artifacts/debug/invalid-donor-overlay.blend",
    } <= ignore_lines


def test_required_binary_evidence_uses_path_scoped_lfs_rules() -> None:
    attribute_lines = _policy_lines(".gitattributes")

    assert (
        "/artifacts/debug/invalid-donor-overlay.blend "
        "filter=lfs diff=lfs merge=lfs -text"
    ) in attribute_lines
    assert (
        "/tools/juana_bust/assets/*.glb filter=lfs diff=lfs merge=lfs -text"
    ) in attribute_lines
    assert (
        "/packages/juana-pixel-runtime/v2/runtime/**/*.png "
        "filter=lfs diff=lfs merge=lfs -text"
    ) in attribute_lines
    assert not any(
        line.startswith(pattern)
        for line in attribute_lines
        for pattern in ("*.blend filter=lfs", "*.glb filter=lfs", "*.png filter=lfs")
    )


def test_asset_policy_defines_the_four_repository_storage_classes() -> None:
    policy = (REPOSITORY_ROOT / "ASSET_POLICY.md").read_text(encoding="utf-8")
    normalized_policy = " ".join(policy.split())

    for heading in (
        "### Ordinary Git",
        "### Git LFS",
        "### Ignored local build roots",
        "### Release artifacts",
    ):
        assert heading in policy

    assert "`build/`" in policy
    assert "`output/`" in policy
    assert "must not be used as a dependency cache" in normalized_policy
