"""Verify pinned inputs and orchestrate the provisional GH-22 Juana bust build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
REQUIRED_VIEW_IDS = (
    "front",
    "left-profile",
    "right-profile",
    "left-three-quarter",
    "right-three-quarter",
)


class IntegrityError(RuntimeError):
    """Raised when a pinned local input differs from its recorded evidence."""


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return data


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> tuple[str, int]:
    """Hash a directory by stable relative paths and file contents."""
    if not path.is_dir():
        raise IntegrityError(f"Required artifact tree is missing: {path}.")
    files = sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
        and "__pycache__" not in candidate.parts
        and candidate.suffix not in {".pyc", ".pyo"}
    )
    digest = hashlib.sha256()
    for candidate in files:
        digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with candidate.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest(), len(files)


def verify_file(
    path: Path,
    *,
    artifact_id: str,
    expected_sha256: str,
    expected_byte_length: int,
) -> dict[str, str | int]:
    """Fail closed unless a local artifact matches its pinned size and digest."""
    if not path.is_file():
        raise IntegrityError(f"Required artifact {artifact_id} is missing: {path}.")
    actual_byte_length = path.stat().st_size
    actual_sha256 = sha256_file(path)
    if actual_byte_length != expected_byte_length or actual_sha256 != expected_sha256:
        raise IntegrityError(
            f"Integrity mismatch for {artifact_id} at {path}: "
            f"expected sha256={expected_sha256}, bytes={expected_byte_length}; "
            f"actual sha256={actual_sha256}, bytes={actual_byte_length}."
        )
    return {
        "id": artifact_id,
        "path": str(path),
        "sha256": actual_sha256,
        "byte_length": actual_byte_length,
    }


def verify_tree(
    path: Path,
    *,
    artifact_id: str,
    expected_sha256: str,
    expected_file_count: int,
) -> dict[str, str | int]:
    """Fail closed unless an installed tool tree matches its pinned extraction."""
    actual_sha256, actual_file_count = sha256_tree(path)
    if actual_sha256 != expected_sha256 or actual_file_count != expected_file_count:
        raise IntegrityError(
            f"Integrity mismatch for {artifact_id} at {path}: "
            f"expected sha256={expected_sha256}, files={expected_file_count}; "
            f"actual sha256={actual_sha256}, files={actual_file_count}."
        )
    return {
        "id": artifact_id,
        "path": str(path),
        "sha256": actual_sha256,
        "file_count": actual_file_count,
    }


def verify_locked_inputs(
    repository_root: Path = REPOSITORY_ROOT,
    lock_path: Path = TOOL_ROOT / "toolchain-lock.json",
) -> list[dict[str, str | int]]:
    """Verify every local artifact declared by the GH-22 toolchain lock."""
    lock = load_json_object(lock_path)
    verified = []
    for artifact in lock["artifacts"]:
        if artifact.get("kind", "file") == "tree":
            verified.append(
                verify_tree(
                    repository_root / artifact["relative_path"],
                    artifact_id=artifact["id"],
                    expected_sha256=artifact["sha256"],
                    expected_file_count=artifact["file_count"],
                )
            )
        else:
            verified.append(
                verify_file(
                    repository_root / artifact["relative_path"],
                    artifact_id=artifact["id"],
                    expected_sha256=artifact["sha256"],
                    expected_byte_length=artifact["byte_length"],
                )
            )
    return verified


def _verify_digest_only(
    path: Path,
    *,
    artifact_id: str,
    expected_sha256: str,
) -> dict[str, str | int]:
    if not path.is_file():
        raise IntegrityError(f"Required source image {artifact_id} is missing: {path}.")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise IntegrityError(
            f"Integrity mismatch for {artifact_id} at {path}: "
            f"expected sha256={expected_sha256}; actual sha256={actual_sha256}."
        )
    return {
        "id": artifact_id,
        "path": str(path),
        "sha256": actual_sha256,
        "byte_length": path.stat().st_size,
    }


def verify_source_inputs(
    repository_root: Path = REPOSITORY_ROOT,
    evidence_path: Path = TOOL_ROOT / "source-evidence.json",
) -> list[dict[str, str | int]]:
    """Verify the approved Juana master and every view used by the checkpoint."""
    evidence = load_json_object(evidence_path)
    master = evidence["master_reference"]
    verified = [
        verify_file(
            repository_root / master["path"],
            artifact_id=master["id"],
            expected_sha256=master["sha256"],
            expected_byte_length=master["byte_length"],
        )
    ]
    package_root = repository_root / evidence["approved_package"]["path"]
    for reference in evidence["face_references"]:
        verified.append(
            _verify_digest_only(
                package_root / reference["path"],
                artifact_id=f"face-{reference['view']}",
                expected_sha256=reference["sha256"],
            )
        )
    for family in ("hair", "outfit"):
        family_evidence = evidence[family]
        for view in ("front", "left", "right", "back"):
            verified.append(
                _verify_digest_only(
                    package_root / "references" / family / f"{view}.png",
                    artifact_id=f"{family}-{view}",
                    expected_sha256=family_evidence[f"approved_{view}_sha256"]
                    if family == "hair"
                    else family_evidence[f"{view}_sha256"],
                )
            )
    return verified


def validate_render_manifest(manifest: dict[str, Any]) -> None:
    """Validate the fixed GH-22 camera and render contract."""
    render = manifest.get("render")
    views = manifest.get("views")
    if not isinstance(render, dict) or render.get("resolution") != [1024, 1024]:
        raise ValueError("Render manifest must declare a fixed 1024x1024 resolution.")
    if not isinstance(views, list):
        raise ValueError("Render manifest views must be a list.")
    canonicalization = render.get("canonicalization")
    if canonicalization != {
        "strip_metadata": True,
        "rgb_lsb_bits_cleared": 2,
    }:
        raise ValueError("Render manifest must declare the fixed GH-22 PNG canonicalization.")
    view_ids = tuple(view.get("id") for view in views if isinstance(view, dict))
    if view_ids != REQUIRED_VIEW_IDS:
        raise ValueError(
            f"Render manifest views must be ordered exactly as {REQUIRED_VIEW_IDS}; got {view_ids}."
        )
    for view in views:
        if (
            not isinstance(view.get("camera_location"), list)
            or len(view["camera_location"]) != 3
            or not isinstance(view.get("target"), list)
            or len(view["target"]) != 3
            or not isinstance(view.get("reference"), str)
        ):
            raise ValueError(f"Render view {view.get('id')} is incomplete.")


def canonicalize_render(path: Path, *, rgb_lsb_bits_cleared: int = 2) -> None:
    """Remove volatile PNG metadata and insignificant Eevee rounding noise."""
    if rgb_lsb_bits_cleared not in range(0, 5):
        raise ValueError("RGB canonicalization must clear between zero and four bits.")
    mask = (0xFF << rgb_lsb_bits_cleared) & 0xFF
    with Image.open(path) as source:
        red, green, blue, alpha = source.convert("RGBA").split()
    normalized = Image.merge(
        "RGBA",
        (
            red.point(lambda value: value & mask),
            green.point(lambda value: value & mask),
            blue.point(lambda value: value & mask),
            alpha,
        ),
    )
    normalized.save(path, format="PNG", optimize=False, compress_level=9)


def canonicalize_renders(
    renders_root: Path,
    *,
    rgb_lsb_bits_cleared: int,
) -> None:
    """Canonicalize every required render before validation and comparison."""
    for view_id in REQUIRED_VIEW_IDS:
        canonicalize_render(
            renders_root / f"{view_id}.png",
            rgb_lsb_bits_cleared=rgb_lsb_bits_cleared,
        )


def _comparison_image(
    path: Path,
    *,
    require_render_dimensions: bool = False,
) -> Image.Image:
    with Image.open(path) as source:
        if source.width != source.height:
            raise ValueError(f"Comparison input must be square: {path} is {source.size}.")
        if require_render_dimensions and source.size != (1024, 1024):
            raise ValueError(f"Render input must be 1024x1024: {path} is {source.size}.")
        normalized = source.convert("RGB")
    if normalized.size != (1024, 1024):
        normalized = normalized.resize((1024, 1024), Image.Resampling.LANCZOS)
    return normalized


def create_comparison_sheets(
    manifest: dict[str, Any],
    *,
    references_root: Path,
    renders_root: Path,
    comparisons_root: Path,
) -> dict[str, Path]:
    """Create fixed side-by-side sheets and a compact human-review board."""
    comparisons_root.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    board = Image.new("RGB", (1536, 1152), (14, 15, 18))
    board_draw = ImageDraw.Draw(board)

    for index, view in enumerate(manifest["views"]):
        view_id = view["id"]
        reference = _comparison_image(references_root / view["reference"])
        render = _comparison_image(
            renders_root / f"{view_id}.png",
            require_render_dimensions=True,
        )

        comparison = Image.new("RGB", (2048, 1072), (14, 15, 18))
        comparison.paste(reference, (0, 48))
        comparison.paste(render, (1024, 48))
        draw = ImageDraw.Draw(comparison)
        draw.text((16, 16), f"{view_id} | approved reference", fill=(238, 240, 244))
        draw.text((1040, 16), "provisional 3D render", fill=(238, 240, 244))
        output = comparisons_root / f"{view_id}-comparison.png"
        comparison.save(output, format="PNG", optimize=False)
        outputs[view_id] = output

        column = index % 2
        row = index // 2
        cell_x = column * 768
        cell_y = row * 384
        board_draw.text(
            (cell_x + 16, cell_y + 5),
            f"{view_id}: reference | provisional 3D",
            fill=(238, 240, 244),
        )
        board.paste(
            reference.resize((360, 360), Image.Resampling.LANCZOS),
            (cell_x + 16, cell_y + 24),
        )
        board.paste(
            render.resize((360, 360), Image.Resampling.LANCZOS),
            (cell_x + 392, cell_y + 24),
        )

    board_output = comparisons_root / "review-board.png"
    board.save(board_output, format="PNG", optimize=False)
    outputs["review-board"] = board_output
    return outputs


def provisional_output_paths(repository_root: Path = REPOSITORY_ROOT) -> dict[str, Path]:
    """Return all primary outputs, intentionally outside the final distribution path."""
    root = repository_root / "build" / "juana-bust-preview"
    return {
        "root": root,
        "blend": root / "juana-bust-provisional.blend",
        "glb": root / "juana-bust-provisional.glb",
        "scene_report": root / "scene-report.json",
        "blender_validation": root / "blender-validation.json",
        "inspection_report": root / "three-inspection.json",
        "build_report": root / "build-report.json",
        "renders": root / "renders",
        "comparisons": root / "comparisons",
    }


def _run(command: list[str], *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
    )


def _blender_environment(repository_root: Path) -> dict[str, str]:
    profile = repository_root / "build" / "local-toolchain" / "mpfb-2.0.16" / "blender-profile"
    environment = os.environ.copy()
    environment.update(
        {
            "BLENDER_USER_CONFIG": str(profile / "config"),
            "BLENDER_USER_SCRIPTS": str(profile / "scripts"),
            "BLENDER_USER_DATAFILES": str(profile / "datafiles"),
            "BLENDER_USER_EXTENSIONS": str(profile / "extensions"),
        }
    )
    return environment


def _output_record(path: Path, *, repository_root: Path) -> dict[str, str | int]:
    return {
        "path": path.relative_to(repository_root).as_posix(),
        "sha256": sha256_file(path),
        "byte_length": path.stat().st_size,
    }


def _write_build_report(
    paths: dict[str, Path],
    *,
    repository_root: Path,
    verified_toolchain: list[dict[str, str | int]],
    verified_sources: list[dict[str, str | int]],
    comparisons: dict[str, Path],
    render_manifest: dict[str, Any],
) -> None:
    primary_outputs = [
        paths["blend"],
        paths["glb"],
        paths["scene_report"],
        paths["blender_validation"],
        paths["inspection_report"],
        *(paths["renders"] / f"{view_id}.png" for view_id in REQUIRED_VIEW_IDS),
        *comparisons.values(),
    ]
    report = {
        "schema_version": "1.0",
        "status": "ready_for_human_visual_review",
        "ticket": "GH-22",
        "character_id": "juana",
        "toolchain_inputs_verified": len(verified_toolchain),
        "approved_source_images_verified": len(verified_sources),
        "render_contract": {
            "view_ids": list(REQUIRED_VIEW_IDS),
            "resolution": render_manifest["render"]["resolution"],
            "canonicalization": render_manifest["render"]["canonicalization"],
        },
        "outputs": [
            _output_record(path, repository_root=repository_root) for path in primary_outputs
        ],
        "provisional_boundary": {
            "visual_canon_approved": False,
            "final_vrm": False,
            "distribution_path": None,
            "next_gate": "Kathy visual review",
        },
    }
    paths["build_report"].write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and validate the provisional GH-22 Juana bust."
    )
    parser.add_argument(
        "--skip-authoring",
        action="store_true",
        help="Reuse an existing provisional blend, GLB, and render set.",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    repository_root = REPOSITORY_ROOT
    paths = provisional_output_paths(repository_root)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["renders"].mkdir(parents=True, exist_ok=True)
    paths["comparisons"].mkdir(parents=True, exist_ok=True)

    verified_toolchain = verify_locked_inputs(repository_root)
    verified_sources = verify_source_inputs(repository_root)
    render_manifest = load_json_object(TOOL_ROOT / "render-manifest.json")
    validate_render_manifest(render_manifest)

    blender = (
        repository_root / "build" / "local-toolchain" / "blender-4.2.0-windows-x64" / "blender.exe"
    )
    toolchain_root = repository_root / "build" / "local-toolchain" / "mpfb-2.0.16"
    references_root = (
        repository_root
        / load_json_object(TOOL_ROOT / "source-evidence.json")["approved_package"]["path"]
    )
    blender_environment = _blender_environment(repository_root)

    if not args.skip_authoring:
        _run(
            [
                str(blender),
                "--background",
                "--python-exit-code",
                "1",
                "--python",
                str(TOOL_ROOT / "blender_author_preview.py"),
                "--",
                "--repo-root",
                str(repository_root),
                "--output-root",
                str(paths["root"]),
                "--toolchain-root",
                str(toolchain_root),
                "--references-root",
                str(references_root),
                "--render-manifest",
                str(TOOL_ROOT / "render-manifest.json"),
            ],
            environment=blender_environment,
        )

    canonicalize_renders(
        paths["renders"],
        rgb_lsb_bits_cleared=render_manifest["render"]["canonicalization"]["rgb_lsb_bits_cleared"],
    )
    _run(
        [
            str(blender),
            "--background",
            str(paths["blend"]),
            "--python-exit-code",
            "1",
            "--python",
            str(TOOL_ROOT / "blender_validate_preview.py"),
            "--",
            "--report",
            str(paths["blender_validation"]),
            "--glb",
            str(paths["glb"]),
            "--renders",
            str(paths["renders"]),
            "--adapter",
            str(repository_root / "examples" / "juana-bust" / "base-adapter.json"),
            "--repo-root",
            str(repository_root),
        ],
        environment=blender_environment,
    )
    _run(
        [
            "node",
            str(TOOL_ROOT / "inspect_glb.mjs"),
            str(paths["glb"]),
            str(paths["inspection_report"]),
            str(repository_root / "examples" / "juana-bust" / "base-adapter.json"),
            str(repository_root),
        ]
    )
    comparisons = create_comparison_sheets(
        render_manifest,
        references_root=references_root,
        renders_root=paths["renders"],
        comparisons_root=paths["comparisons"],
    )
    _write_build_report(
        paths,
        repository_root=repository_root,
        verified_toolchain=verified_toolchain,
        verified_sources=verified_sources,
        comparisons=comparisons,
        render_manifest=render_manifest,
    )
    print(f"GH-22 preview ready for visual review: {comparisons['review-board']}")


if __name__ == "__main__":
    main()
