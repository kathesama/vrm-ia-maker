"""Deterministic delivery packaging for the Juana pixel portrait runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

_SEAL_FILENAME: Final = "bundle-seal.json"
_MANIFEST_FILENAME: Final = "portrait-manifest.json"
_FIXED_ZIP_TIMESTAMP: Final = (1980, 1, 1, 0, 0, 0)
_COPY_CHUNK_BYTES: Final = 1024 * 1024
_LOCK_SCHEMA_VERSION: Final = "1.0"


class RuntimeReleaseError(ValueError):
    """Raised when a runtime cannot be verified or packaged safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RuntimeInventory:
    """Verified immutable metadata for one runtime directory."""

    package_id: str
    schema_version: str
    files: dict[str, str]
    file_sizes: dict[str, int]
    seal_sha256: str
    total_bytes: int
    png_count: int
    scenario_bytes: dict[str, int]

    @property
    def file_count(self) -> int:
        return len(self.files)

    def as_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "schema_version": self.schema_version,
            "file_count": self.file_count,
            "png_count": self.png_count,
            "bytes": self.total_bytes,
            "seal_sha256": self.seal_sha256,
            "scenarios": {
                scenario_id: {"bytes": byte_count}
                for scenario_id, byte_count in sorted(self.scenario_bytes.items())
            },
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_COPY_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeReleaseError(
            "invalid_json",
            f"The runtime {label} is missing or is not valid UTF-8 JSON.",
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeReleaseError(
            "invalid_json",
            f"The runtime {label} must contain a JSON object.",
        )
    return value


def _validated_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeReleaseError(
            "unsafe_path",
            "Every runtime seal path must be a non-empty string.",
        )
    if "\\" in value:
        raise RuntimeReleaseError(
            "unsafe_path",
            f"Runtime seal path uses a non-portable separator: {value!r}.",
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeReleaseError(
            "unsafe_path",
            f"Runtime seal path is not a normalized relative path: {value!r}.",
        )
    return value


def _actual_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeReleaseError(
                "unsafe_path",
                f"Runtime packages cannot contain symbolic links: {path}.",
            )
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    return files


def verify_runtime(root: Path) -> RuntimeInventory:
    """Verify exact inventory and hashes from a runtime bundle seal."""
    runtime_root = root.resolve()
    if not runtime_root.is_dir():
        raise RuntimeReleaseError(
            "runtime_missing",
            f"Runtime directory does not exist: {runtime_root}.",
        )

    seal_path = runtime_root / _SEAL_FILENAME
    seal = _load_json_object(seal_path, label="bundle seal")
    raw_files = seal.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise RuntimeReleaseError(
            "invalid_seal",
            "The runtime bundle seal must contain a non-empty files object.",
        )

    sealed_files: dict[str, str] = {}
    for raw_path, raw_digest in raw_files.items():
        relative_path = _validated_relative_path(raw_path)
        if (
            not isinstance(raw_digest, str)
            or len(raw_digest) != 64
            or any(character not in "0123456789abcdef" for character in raw_digest)
        ):
            raise RuntimeReleaseError(
                "invalid_seal",
                f"Runtime seal hash is not lowercase SHA-256 for {relative_path}.",
            )
        sealed_files[relative_path] = raw_digest

    expected_files = set(sealed_files) | {_SEAL_FILENAME}
    actual_files = _actual_files(runtime_root)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise RuntimeReleaseError(
            "inventory_mismatch",
            f"Runtime inventory does not match its seal; missing={missing}, extra={extra}.",
        )

    file_sizes: dict[str, int] = {}
    for relative_path, expected_digest in sorted(sealed_files.items()):
        path = runtime_root / PurePosixPath(relative_path)
        actual_digest = _sha256(path)
        if actual_digest != expected_digest:
            raise RuntimeReleaseError(
                "hash_mismatch",
                f"Runtime file hash does not match its seal: {relative_path}.",
            )
        file_sizes[relative_path] = path.stat().st_size

    manifest = _load_json_object(
        runtime_root / _MANIFEST_FILENAME,
        label="portrait manifest",
    )
    package_id = manifest.get("package_id")
    schema_version = manifest.get("schema_version")
    if not isinstance(package_id, str) or not isinstance(schema_version, str):
        raise RuntimeReleaseError(
            "invalid_manifest",
            "The portrait manifest must define string package_id and schema_version values.",
        )

    file_sizes[_SEAL_FILENAME] = seal_path.stat().st_size
    scenario_bytes: dict[str, int] = {}
    scenario_order = manifest.get("scenario_order", [])
    if not isinstance(scenario_order, list) or not all(
        isinstance(item, str) and item for item in scenario_order
    ):
        raise RuntimeReleaseError(
            "invalid_manifest",
            "The portrait manifest scenario_order must contain scenario identifiers.",
        )
    for scenario_id in scenario_order:
        prefix = f"scenarios/{scenario_id}/"
        scenario_bytes[scenario_id] = sum(
            byte_count
            for relative_path, byte_count in file_sizes.items()
            if relative_path.startswith(prefix)
        )

    all_hashes = dict(sorted(sealed_files.items()))
    all_hashes[_SEAL_FILENAME] = _sha256(seal_path)
    return RuntimeInventory(
        package_id=package_id,
        schema_version=schema_version,
        files=dict(sorted(all_hashes.items())),
        file_sizes=dict(sorted(file_sizes.items())),
        seal_sha256=all_hashes[_SEAL_FILENAME],
        total_bytes=sum(file_sizes.values()),
        png_count=sum(path.endswith(".png") for path in file_sizes),
        scenario_bytes=scenario_bytes,
    )


def _ensure_disjoint(source: Path, destination: Path) -> None:
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    if source_resolved == destination_resolved:
        return
    if (
        source_resolved in destination_resolved.parents
        or destination_resolved in source_resolved.parents
    ):
        raise RuntimeReleaseError(
            "overlapping_paths",
            "Runtime source and destination must not contain one another.",
        )


def synchronize_runtime(source: Path, destination: Path) -> RuntimeInventory:
    """Copy a verified runtime through a staging directory and atomic rename."""
    source_root = source.resolve()
    destination_root = destination.resolve()
    _ensure_disjoint(source_root, destination_root)
    source_inventory = verify_runtime(source_root)
    if source_root == destination_root:
        return source_inventory

    destination_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination_root.name}.staging-",
            dir=destination_root.parent,
        )
    )
    backup_root: Path | None = None
    try:
        for relative_path in source_inventory.files:
            source_path = source_root / PurePosixPath(relative_path)
            target_path = staging_root / PurePosixPath(relative_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path)
        staged_inventory = verify_runtime(staging_root)
        if staged_inventory.files != source_inventory.files:
            raise RuntimeReleaseError(
                "copy_mismatch",
                "The staged runtime does not match the verified source.",
            )

        if destination_root.exists():
            backup_root = destination_root.parent / (
                f".{destination_root.name}.backup-{uuid.uuid4().hex}"
            )
            os.replace(destination_root, backup_root)
        try:
            os.replace(staging_root, destination_root)
        except OSError:
            if backup_root is not None and backup_root.exists():
                os.replace(backup_root, destination_root)
                backup_root = None
            raise
        if backup_root is not None:
            shutil.rmtree(backup_root)
            backup_root = None
        return verify_runtime(destination_root)
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        if backup_root is not None and backup_root.exists():
            if not destination_root.exists():
                os.replace(backup_root, destination_root)
            else:
                shutil.rmtree(backup_root)


def _replace_file_bytes(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_bytes(content)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _archive_bytes(runtime_root: Path, inventory: RuntimeInventory) -> bytes:
    descriptor, temporary_name = tempfile.mkstemp(suffix=".zip")
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with ZipFile(
            temporary_path,
            mode="w",
            compression=ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for relative_path in sorted(inventory.files):
                info = ZipInfo(relative_path, date_time=_FIXED_ZIP_TIMESTAMP)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(
                    info,
                    (runtime_root / PurePosixPath(relative_path)).read_bytes(),
                    compress_type=ZIP_DEFLATED,
                    compresslevel=9,
                )
        return temporary_path.read_bytes()
    finally:
        temporary_path.unlink(missing_ok=True)


def build_runtime_release(
    runtime_root: Path,
    archive_path: Path,
    lock_path: Path,
    *,
    version: str,
) -> dict[str, Any]:
    """Build a deterministic ZIP and derived JSON lock from a verified runtime."""
    if not version.strip():
        raise RuntimeReleaseError(
            "invalid_version",
            "Runtime release version must not be empty.",
        )
    resolved_archive_path = archive_path.resolve()
    resolved_lock_path = lock_path.resolve()
    if resolved_archive_path == resolved_lock_path:
        raise RuntimeReleaseError(
            "colliding_destinations",
            "Runtime release archive and lock destinations must be distinct.",
        )
    verified_root = runtime_root.resolve()
    inventory = verify_runtime(verified_root)
    archive_bytes = _archive_bytes(verified_root, inventory)
    archive_digest = hashlib.sha256(archive_bytes).hexdigest()

    lock = {
        "archive": {
            "bytes": len(archive_bytes),
            "filename": archive_path.name,
            "sha256": archive_digest,
        },
        "package_id": inventory.package_id,
        "package_version": version,
        "runtime": {
            "bytes": inventory.total_bytes,
            "file_count": inventory.file_count,
            "png_count": inventory.png_count,
            "scenarios": {
                scenario_id: {"bytes": byte_count}
                for scenario_id, byte_count in sorted(inventory.scenario_bytes.items())
            },
            "seal": {
                "path": _SEAL_FILENAME,
                "sha256": inventory.seal_sha256,
            },
        },
        "schema_version": _LOCK_SCHEMA_VERSION,
    }
    lock_bytes = (json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )

    _replace_file_bytes(resolved_archive_path, archive_bytes)
    _replace_file_bytes(resolved_lock_path, lock_bytes)
    return lock
