from __future__ import annotations

import hashlib
import json
import re
from base64 import b64decode
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from vrm_ia_maker.design.pixel_portrait.cli import main as cli_main
from vrm_ia_maker.design.pixel_portrait.release import (
    RuntimeReleaseError,
    build_runtime_release,
    synchronize_runtime,
    verify_runtime,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
APPROVED_BUILD = (
    REPOSITORY_ROOT
    / "build"
    / "juana-pixel-portrait-runtime"
    / "juana-talking-bust-v2-pixel-ui-ready"
)
CANONICAL_RUNTIME = REPOSITORY_ROOT / "packages" / "juana-pixel-runtime" / "v2" / "runtime"
RUNTIME_GALLERY = REPOSITORY_ROOT / "packages" / "juana-pixel-runtime" / "v2" / "gallery.html"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_fixture_runtime(root: Path) -> Path:
    files = {
        "portrait-manifest.json": json.dumps(
            {
                "package_id": "juana-talking-bust-v2-pixel",
                "schema_version": "2.0",
                "scenario_order": ["juana-diorama-room"],
            },
            sort_keys=True,
        ).encode(),
        "scenarios/juana-diorama-room/provenance.json": b'{"source":"test"}\n',
        "scenarios/juana-diorama-room/states/neutral.png": b"\x89PNG\r\nfixture",
    }
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    seal = {
        "schema_version": "2.0",
        "files": {relative_path: _sha256(root / relative_path) for relative_path in sorted(files)},
    }
    (root / "bundle-seal.json").write_text(
        json.dumps(seal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root


def test_verify_runtime_rejects_missing_extra_and_tampered_files(tmp_path: Path) -> None:
    missing = _write_fixture_runtime(tmp_path / "missing")
    (missing / "scenarios/juana-diorama-room/states/neutral.png").unlink()
    with pytest.raises(RuntimeReleaseError, match="inventory"):
        verify_runtime(missing)

    extra = _write_fixture_runtime(tmp_path / "extra")
    (extra / "unexpected.txt").write_text("not sealed", encoding="utf-8")
    with pytest.raises(RuntimeReleaseError, match="inventory"):
        verify_runtime(extra)

    tampered = _write_fixture_runtime(tmp_path / "tampered")
    (tampered / "portrait-manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeReleaseError, match="hash"):
        verify_runtime(tampered)


def test_invalid_source_does_not_replace_existing_destination(tmp_path: Path) -> None:
    source = _write_fixture_runtime(tmp_path / "source")
    (source / "portrait-manifest.json").write_text("{}", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(RuntimeReleaseError):
        synchronize_runtime(source, destination)

    assert marker.read_text(encoding="utf-8") == "preserve"


def test_synchronize_runtime_preserves_every_sealed_byte(tmp_path: Path) -> None:
    source = _write_fixture_runtime(tmp_path / "source")
    destination = tmp_path / "destination"

    source_inventory = synchronize_runtime(source, destination)
    destination_inventory = verify_runtime(destination)

    assert destination_inventory.files == source_inventory.files
    for relative_path in source_inventory.files:
        assert (destination / relative_path).read_bytes() == (source / relative_path).read_bytes()


def test_release_archive_and_lock_are_deterministic(tmp_path: Path) -> None:
    runtime = _write_fixture_runtime(tmp_path / "runtime")
    first_archive = tmp_path / "first" / "juana-pixel-runtime-v2.zip"
    second_archive = tmp_path / "second" / "juana-pixel-runtime-v2.zip"
    first_lock = tmp_path / "first" / "juana-pixel-runtime-v2.lock.json"
    second_lock = tmp_path / "second" / "juana-pixel-runtime-v2.lock.json"

    first = build_runtime_release(
        runtime,
        first_archive,
        first_lock,
        version="2.0.0",
    )
    second = build_runtime_release(
        runtime,
        second_archive,
        second_lock,
        version="2.0.0",
    )

    assert first_archive.read_bytes() == second_archive.read_bytes()
    assert first_lock.read_bytes() == second_lock.read_bytes()
    assert first == second
    assert first["archive"]["sha256"] == _sha256(first_archive)
    assert first["runtime"]["file_count"] == 4
    assert first["runtime"]["png_count"] == 1
    assert first["runtime"]["scenarios"]["juana-diorama-room"]["bytes"] > 0

    with ZipFile(first_archive) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())


def test_release_rejects_colliding_archive_and_lock_paths(tmp_path: Path) -> None:
    runtime = _write_fixture_runtime(tmp_path / "runtime")
    destination = tmp_path / "release-output"
    destination.write_bytes(b"preserve")

    with pytest.raises(RuntimeReleaseError, match="distinct"):
        build_runtime_release(
            runtime,
            destination,
            destination,
            version="2.0.0",
        )

    assert destination.read_bytes() == b"preserve"


def test_package_runtime_cli_emits_machine_readable_release_identity(
    tmp_path: Path,
) -> None:
    runtime = _write_fixture_runtime(tmp_path / "runtime")
    archive = tmp_path / "juana-pixel-runtime-v2.zip"
    lock = tmp_path / "juana-pixel-runtime-v2.lock.json"
    output = StringIO()
    errors = StringIO()

    exit_code = cli_main(
        [
            "package-runtime",
            "--source",
            str(runtime),
            "--output",
            str(archive),
            "--lock",
            str(lock),
            "--version",
            "2.0.0",
        ],
        stdout=output,
        stderr=errors,
    )

    payload = json.loads(output.getvalue())
    assert exit_code == 0
    assert errors.getvalue() == ""
    assert payload["ok"] is True
    assert payload["command"] == "package-runtime"
    assert payload["result"]["archive"]["sha256"] == _sha256(archive)


@pytest.mark.skipif(
    not APPROVED_BUILD.is_dir(),
    reason="The ignored approved GH-24 build is unavailable in this checkout.",
)
def test_canonical_runtime_matches_the_approved_build_byte_for_byte() -> None:
    approved = verify_runtime(APPROVED_BUILD)
    canonical = verify_runtime(CANONICAL_RUNTIME)

    assert approved.file_count == canonical.file_count == 55
    assert approved.png_count == canonical.png_count == 51
    assert approved.total_bytes == canonical.total_bytes == 36_906_823
    assert approved.files == canonical.files
    for relative_path in approved.files:
        assert (APPROVED_BUILD / relative_path).read_bytes() == (
            CANONICAL_RUNTIME / relative_path
        ).read_bytes()


def test_runtime_gallery_embeds_every_png_thumbnail_for_file_url_viewing() -> None:
    html = RUNTIME_GALLERY.read_text(encoding="utf-8")
    match = re.search(
        r"const thumbnails = (?P<payload>\{.*?\})\n\s+const scenarios =",
        html,
        flags=re.DOTALL,
    )

    assert match is not None
    thumbnails = json.loads(match.group("payload"))
    seal = json.loads((CANONICAL_RUNTIME / "bundle-seal.json").read_text())
    expected_paths = {
        f"runtime/{relative_path}"
        for relative_path in seal["files"]
        if relative_path.endswith(".png")
    }

    assert set(thumbnails) == expected_paths
    assert "image.src = thumbnails[source]" in html
    for data_url in thumbnails.values():
        prefix, encoded = data_url.split(",", maxsplit=1)
        assert prefix == "data:image/webp;base64"
        with Image.open(BytesIO(b64decode(encoded))) as image:
            assert image.format == "WEBP"
            assert image.width <= 384
            assert image.height <= 576
