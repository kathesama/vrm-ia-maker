"""Filesystem workspace adapter for bounded character-reference authoring."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from pydantic import TypeAdapter, ValidationError

from vrm_ia_maker.design.contracts import (
    ArtifactEvidence,
    AuthoringState,
    CandidateRecord,
    CharacterDesignPackageRevision,
    GapRecord,
    PackageRelativePath,
    ProvenanceRecord,
    SealEvidence,
    SourceClass,
    TaskProgress,
    TaskState,
)
from vrm_ia_maker.design.plan import (
    TALKING_BUST_PLAN,
    AuthoringPlanDefinition,
    AuthoringTaskDefinition,
)
from vrm_ia_maker.design.ports import (
    AuthoringWorkspaceError,
    GeneratedImage,
    WorkspaceInitialization,
)

_PACKAGE_PATH_ADAPTER = TypeAdapter(PackageRelativePath)


class WorkspaceError(AuthoringWorkspaceError):
    """Base error for deterministic authoring workspace failures."""

    error_code = "workspace_failure"

    def __init__(self, message: str) -> None:
        super().__init__(self.error_code, message)


class WorkspaceAlreadyExistsError(WorkspaceError):
    """Raised when a no-clobber workspace or attempt destination exists."""

    error_code = "already_exists"


class WorkspaceLockedError(WorkspaceError):
    """Raised when another writer owns the workspace lock."""

    error_code = "workspace_locked"


class WorkspacePathError(WorkspaceError):
    """Raised when a relative artifact path escapes the workspace."""

    error_code = "unsafe_path"


class CandidateValidationError(WorkspaceError):
    """Raised after preserving malformed provider output for audit."""

    error_code = "invalid_candidate"


class PackageDestinationExistsError(WorkspaceError):
    """Raised when a sealed package destination is not new."""

    error_code = "destination_exists"


class PackageIntegrityError(WorkspaceError):
    """Raised when persisted evidence no longer matches artifact bytes."""

    error_code = "integrity_failure"


class PackageSealError(WorkspaceError):
    """Raised when approved state cannot form a valid sealed package."""

    error_code = "package_invalid"


class FilesystemAuthoringWorkspace:
    """Persist authoring state and candidate images beneath one local root."""

    STATE_FILE = "authoring-state.json"
    PLAN_FILE = "authoring-plan.json"
    LOCK_FILE = ".authoring.lock"

    def __init__(
        self,
        root: Path,
        plan: AuthoringPlanDefinition = TALKING_BUST_PLAN,
    ) -> None:
        self.root = Path(root)
        self._plan = plan

    def initialize(self, command: WorkspaceInitialization) -> AuthoringState:
        """Create a new workspace around an immutable copy of the master PNG."""
        if self.root.exists() or os.path.lexists(self.root):
            raise WorkspaceAlreadyExistsError(
                f"Authoring workspace already exists: {self.root}"
            )
        master_data = self._read_source(command.master_source)
        width, height = self._png_dimensions(master_data)
        self.root.parent.mkdir(parents=True, exist_ok=True)
        staging = self.root.with_name(f".{self.root.name}.init-{uuid4().hex}.tmp")
        try:
            staging.mkdir()
            master_relative = "inputs/master.png"
            master_path = staging / master_relative
            master_path.parent.mkdir(parents=True)
            self._write_bytes_exclusive(master_path, master_data)
            master_artifact = self._artifact(
                master_relative,
                master_data,
                width,
                height,
            )
            revision = CharacterDesignPackageRevision(
                package_id=command.package_id,
                character_id=command.character_id,
                display_name=command.display_name,
                revision=command.revision,
                master_reference=master_artifact,
                height_meters=command.height_meters,
            )
            gaps = self._initial_gaps(command)
            state = AuthoringState(
                revision=revision,
                plan_id=self._plan.plan_id,
                plan_version=self._plan.plan_version,
                tasks={task.task_id: TaskState(task_id=task.task_id) for task in self._plan.tasks},
                provenance=(
                    ProvenanceRecord(
                        provenance_id="master-reference",
                        source_class=SourceClass.CREATIVE_CANON,
                        artifact=master_artifact,
                        authoritative_source=command.authoritative_source,
                        rights=command.rights,
                    ),
                ),
                gaps=gaps,
            )
            self._write_json_exclusive(
                staging / self.PLAN_FILE,
                self._plan.model_dump(mode="json"),
            )
            self._write_json_exclusive(
                staging / self.STATE_FILE,
                state.model_dump(mode="json"),
            )
            if self.root.exists() or os.path.lexists(self.root):
                raise WorkspaceAlreadyExistsError(
                    f"Authoring workspace already exists: {self.root}"
                )
            os.rename(staging, self.root)
            return state
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def load_state(self) -> AuthoringState:
        """Load and validate the current state contract."""
        return AuthoringState.model_validate_json(
            (self.root / self.STATE_FILE).read_text(encoding="utf-8")
        )

    def save_state(self, state: AuthoringState) -> None:
        """Atomically replace state while retaining the previous valid file on failure."""
        state_path = self.root / self.STATE_FILE
        temporary = self.root / f".{self.STATE_FILE}.{uuid4().hex}.tmp"
        try:
            self._write_json_exclusive(temporary, state.model_dump(mode="json"))
            os.replace(temporary, state_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def resolve_artifact(self, relative_path: PackageRelativePath | str) -> Path:
        """Resolve a validated path and reject containment or symlink escapes."""
        try:
            normalized = _PACKAGE_PATH_ADAPTER.validate_python(relative_path)
        except ValidationError as exc:
            raise WorkspacePathError("Artifact path is not a safe package-relative path.") from exc
        root = self.root.resolve()
        resolved = (self.root / normalized).resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise WorkspacePathError("Artifact path escapes the authoring workspace.")
        return resolved

    def stage_candidate(
        self,
        *,
        task: AuthoringTaskDefinition,
        attempt: int,
        generated: GeneratedImage,
        input_artifacts: tuple[ArtifactEvidence, ...],
        created_at: Any,
    ) -> CandidateRecord:
        """Validate one provider result and extract deterministic panel previews."""
        attempt_relative = f"candidates/{task.task_id}/attempt-{attempt}"
        attempt_path = self.resolve_artifact(attempt_relative)
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            attempt_path.mkdir()
        except FileExistsError as exc:
            raise WorkspaceAlreadyExistsError(
                f"Candidate attempt already exists: {attempt_relative}"
            ) from exc

        try:
            image = self._load_png(generated.data)
        except CandidateValidationError:
            self._write_bytes_exclusive(attempt_path / "failed-output.bin", generated.data)
            raise
        if image.size != (task.width, task.height):
            self._write_bytes_exclusive(attempt_path / "failed-output.bin", generated.data)
            image.close()
            raise CandidateValidationError(
                f"Candidate PNG must be exactly {task.width}x{task.height} pixels."
            )

        sheet_relative = f"{attempt_relative}/sheet.png"
        sheet_path = attempt_path / "sheet.png"
        self._write_bytes_exclusive(sheet_path, generated.data)
        sheet = self._artifact(
            sheet_relative,
            generated.data,
            task.width,
            task.height,
        )
        previews_path = attempt_path / "previews"
        previews_path.mkdir()
        previews: list[ArtifactEvidence] = []
        try:
            for panel in task.panels:
                relative = f"{attempt_relative}/previews/{panel.panel_id}.png"
                path = previews_path / f"{panel.panel_id}.png"
                preview = image.crop(task.crop_box(panel))
                preview.save(path, format="PNG")
                preview.close()
                data = path.read_bytes()
                previews.append(
                    self._artifact(
                        relative,
                        data,
                        task.width // task.columns,
                        task.height // task.rows,
                    )
                )
        finally:
            image.close()
        return CandidateRecord(
            candidate_id=f"{task.task_id}-attempt-{attempt}",
            task_id=task.task_id,
            attempt=attempt,
            provider=generated.provider,
            model=generated.model,
            prompt_id=task.prompt_id,
            prompt_version=task.prompt_version,
            input_artifacts=input_artifacts,
            sheet=sheet,
            previews=tuple(previews),
            created_at=created_at,
        )

    def seal(
        self,
        state: AuthoringState,
        destination: Path,
        sealed_at: datetime,
    ) -> SealEvidence:
        """Publish approved sheets and crops into a new validated package."""
        destination = Path(destination)
        if destination.exists() or os.path.lexists(destination):
            raise PackageDestinationExistsError(
                f"CharacterDesignPackage destination already exists: {destination}"
            )
        destination_resolved = destination.resolve(strict=False)
        if destination_resolved.is_relative_to(self.root.resolve()):
            raise WorkspacePathError(
                "CharacterDesignPackage destination cannot be inside the authoring workspace."
            )
        if any(task.progress is not TaskProgress.APPROVED for task in state.tasks.values()):
            raise PackageSealError("Every authoring task must be approved before sealing.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(f".{destination.name}.seal-{uuid4().hex}.tmp")
        try:
            staging.mkdir()
            self._create_package_directories(staging)
            provenance: list[ProvenanceRecord] = []
            approval_payloads: list[dict[str, object]] = []
            approval_ids: list[str] = []
            approved_sheets: dict[str, str] = {}

            master_source = state.revision.master_reference
            master_relative = "references/master/master-character-sheet.png"
            master_artifact = self._copy_verified_artifact(
                master_source,
                staging,
                master_relative,
            )
            master_record = self._provenance(state, "master-reference")
            provenance.append(master_record.model_copy(update={"artifact": master_artifact}))

            for task_definition in self._plan.tasks:
                task = state.tasks[task_definition.task_id]
                candidate = next(
                    (
                        item
                        for item in task.candidates
                        if item.candidate_id == task.approved_candidate_id
                    ),
                    None,
                )
                if candidate is None:
                    raise PackageSealError(
                        f"Task {task.task_id} has no approved candidate evidence."
                    )
                decision = next(
                    (
                        item
                        for item in task.decisions
                        if item.candidate_id == candidate.candidate_id
                    ),
                    None,
                )
                if decision is None:
                    raise PackageSealError(
                        f"Task {task.task_id} has no approved human decision."
                    )

                sheet_relative = (
                    f"references/master/approved-sheets/{task_definition.task_id}.png"
                )
                sheet_artifact = self._copy_verified_artifact(
                    candidate.sheet,
                    staging,
                    sheet_relative,
                )
                approved_sheets[task_definition.task_id] = sheet_relative
                candidate_provenance_id = f"candidate-{candidate.candidate_id}"
                candidate_provenance = self._provenance(
                    state,
                    candidate_provenance_id,
                )
                provenance.append(
                    candidate_provenance.model_copy(update={"artifact": sheet_artifact})
                )

                if len(candidate.previews) != len(task_definition.panels):
                    raise PackageSealError(
                        f"Task {task.task_id} preview count does not match its panel map."
                    )
                sealed_review_paths = [sheet_relative]
                for panel, preview in zip(
                    task_definition.panels,
                    candidate.previews,
                    strict=True,
                ):
                    expected_preview = (
                        f"candidates/{task.task_id}/attempt-{candidate.attempt}/"
                        f"previews/{panel.panel_id}.png"
                    )
                    if preview.path != expected_preview:
                        raise PackageSealError(
                            f"Task {task.task_id} preview paths do not match its panel map."
                        )
                    panel_artifact = self._copy_verified_artifact(
                        preview,
                        staging,
                        panel.package_path,
                    )
                    sealed_review_paths.append(panel.package_path)
                    provenance.append(
                        ProvenanceRecord(
                            provenance_id=f"panel-{task.task_id}-{panel.panel_id}",
                            source_class=SourceClass.TECHNICAL_REFERENCE,
                            artifact=panel_artifact,
                            authoritative_source=(
                                "Deterministic crop from an approved generated reference sheet."
                            ),
                            rights_basis_provenance_id=candidate_provenance_id,
                            derived_from_sha256=(candidate.sheet.sha256,),
                            provider=candidate.provider,
                            model=candidate.model,
                            prompt_id=candidate.prompt_id,
                            prompt_version=candidate.prompt_version,
                        )
                    )
                approval_payloads.append(
                    {
                        "decision_record": decision.model_dump(mode="json"),
                        "sealed_artifacts": sealed_review_paths,
                    }
                )
                approval_ids.append(decision.approval_id)

            self._validate_rights_chain(provenance)
            package_payload: dict[str, object] = {
                "schema_version": "1.0",
                "package_id": state.revision.package_id,
                "character_id": state.revision.character_id,
                "display_name": state.revision.display_name,
                "revision": state.revision.revision,
                "created_at": sealed_at.isoformat(),
                "updated_at": sealed_at.isoformat(),
                "profile": "talking-bust-visual-reference",
                "canonical_pose": "a-pose",
                "height_meters": state.revision.height_meters,
                "master_reference": master_artifact.model_dump(mode="json"),
                "approved_reference_sheets": approved_sheets,
                "required_expressions": [
                    "blink",
                    "blinkLeft",
                    "blinkRight",
                    "happy",
                    "sad",
                    "angry",
                    "surprised",
                    "relaxed",
                ],
                "required_visemes": ["aa", "ih", "ou", "ee", "oh"],
                "asset_pack_manifest": None,
                "assembly_manifest": None,
                "base_model_adapter": None,
            }
            self._write_package_metadata(
                staging,
                package_payload=package_payload,
                provenance=provenance,
                approvals=approval_payloads,
                state=state,
            )
            file_hashes = self._package_file_hashes(staging)
            evidence = SealEvidence(
                package_id=state.revision.package_id,
                revision=state.revision.revision,
                sealed_at=sealed_at,
                file_hashes=file_hashes,
                approval_ids=tuple(approval_ids),
                provenance_ids=tuple(record.provenance_id for record in provenance),
                unresolved_gap_ids=tuple(gap.gap_id for gap in state.gaps),
            )
            self._write_json_exclusive(
                staging / "seal.json",
                evidence.model_dump(mode="json"),
            )
            self.validate_sealed_package(staging)
            if destination.exists() or os.path.lexists(destination):
                raise PackageDestinationExistsError(
                    f"CharacterDesignPackage destination already exists: {destination}"
                )
            os.rename(staging, destination)
            return evidence
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def validate_artifacts(self, state: AuthoringState) -> None:
        """Verify every master, candidate sheet, and preview recorded in state."""
        artifacts = [state.revision.master_reference]
        for task in state.tasks.values():
            for candidate in task.candidates:
                artifacts.append(candidate.sheet)
                artifacts.extend(candidate.previews)
        checked: set[str] = set()
        for artifact in artifacts:
            if artifact.path in checked:
                continue
            self._verified_artifact_data(artifact)
            checked.add(artifact.path)

    @classmethod
    def validate_sealed_package(cls, package_root: Path) -> SealEvidence:
        """Validate seal evidence and every recorded file digest without network access."""
        package_root = Path(package_root)
        try:
            evidence = SealEvidence.model_validate_json(
                (package_root / "seal.json").read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise PackageIntegrityError("Sealed package evidence is missing or invalid.") from exc
        root = package_root.resolve()
        for relative_path, expected_digest in evidence.file_hashes.items():
            path = (package_root / relative_path).resolve(strict=False)
            if not path.is_relative_to(root) or not path.is_file():
                raise PackageIntegrityError(
                    f"Sealed package file is missing or unsafe: {relative_path}"
                )
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_digest:
                raise PackageIntegrityError(
                    f"Sealed package digest mismatch: {relative_path}"
                )
        required_files = (
            "package.json",
            "provenance.json",
            "approvals.json",
            "gaps.json",
        )
        if any(not (package_root / name).is_file() for name in required_files):
            raise PackageIntegrityError("Sealed package is missing required metadata files.")
        required_directories = (
            "references/master",
            "references/body",
            "references/face",
            "references/expressions",
            "references/visemes",
            "references/hair",
            "references/outfit",
            "references/materials",
            "measurements",
            "landmarks",
            "palette",
            "materials",
            "expressions",
            "visemes",
            "hair",
            "outfit",
            "assets/base",
            "assets/hair",
            "assets/outfit",
            "assets/accessories",
            "adapters",
        )
        if any(not (package_root / name).is_dir() for name in required_directories):
            raise PackageIntegrityError("Sealed package is missing required directories.")
        return evidence

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Hold a process-owned lock that the operating system releases on exit."""
        lock_path = self.root / self.LOCK_FILE
        if lock_path.is_symlink():
            raise WorkspacePathError("Authoring workspace lock cannot be a symlink.")
        try:
            lock_file = lock_path.open("a+b")
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\x00")
                lock_file.flush()
                os.fsync(lock_file.fileno())
            lock_file.seek(0)
            self._acquire_file_lock(lock_file)
        except OSError as exc:
            if "lock_file" in locals():
                lock_file.close()
            raise WorkspaceLockedError("Authoring workspace is already locked.") from exc
        try:
            yield
        finally:
            try:
                self._release_file_lock(lock_file)
            finally:
                lock_file.close()

    @staticmethod
    def _acquire_file_lock(lock_file: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import importlib

            fcntl = importlib.import_module("fcntl")
            api = vars(fcntl)
            api["flock"](
                lock_file.fileno(),
                api["LOCK_EX"] | api["LOCK_NB"],
            )

    @staticmethod
    def _release_file_lock(lock_file: BinaryIO) -> None:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import importlib

            fcntl = importlib.import_module("fcntl")
            api = vars(fcntl)
            api["flock"](lock_file.fileno(), api["LOCK_UN"])

    @staticmethod
    def _create_package_directories(staging: Path) -> None:
        directories = (
            "references/master/approved-sheets",
            "references/body",
            "references/face",
            "references/expressions",
            "references/visemes",
            "references/hair",
            "references/outfit",
            "references/materials",
            "measurements",
            "landmarks",
            "palette",
            "materials",
            "expressions",
            "visemes",
            "hair",
            "outfit",
            "assets/base",
            "assets/hair",
            "assets/outfit",
            "assets/accessories",
            "adapters",
        )
        for relative_path in directories:
            (staging / relative_path).mkdir(parents=True, exist_ok=False)

    def _copy_verified_artifact(
        self,
        source: ArtifactEvidence,
        staging: Path,
        destination_relative: str,
    ) -> ArtifactEvidence:
        data = self._verified_artifact_data(source)
        try:
            normalized = _PACKAGE_PATH_ADAPTER.validate_python(destination_relative)
        except ValidationError as exc:
            raise PackageSealError("Package artifact path is invalid.") from exc
        destination = staging / normalized
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._write_bytes_exclusive(destination, data)
        except FileExistsError as exc:
            raise PackageSealError(
                f"Package artifact destination would be overwritten: {normalized}"
            ) from exc
        return self._artifact(
            normalized,
            data,
            source.width,
            source.height,
        )

    def _verified_artifact_data(self, artifact: ArtifactEvidence) -> bytes:
        path = self.resolve_artifact(artifact.path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PackageIntegrityError(
                f"Approved artifact is unavailable: {artifact.path}"
            ) from exc
        if len(data) != artifact.byte_length:
            raise PackageIntegrityError(
                f"Approved artifact byte length changed: {artifact.path}"
            )
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise PackageIntegrityError(
                f"Approved artifact digest changed: {artifact.path}"
            )
        try:
            dimensions = self._png_dimensions(data)
        except CandidateValidationError as exc:
            raise PackageIntegrityError(
                f"Approved artifact is no longer a valid PNG: {artifact.path}"
            ) from exc
        if dimensions != (artifact.width, artifact.height):
            raise PackageIntegrityError(
                f"Approved artifact dimensions changed: {artifact.path}"
            )
        return data

    @staticmethod
    def _provenance(state: AuthoringState, provenance_id: str) -> ProvenanceRecord:
        record = next(
            (
                item
                for item in state.provenance
                if item.provenance_id == provenance_id
            ),
            None,
        )
        if record is None:
            raise PackageSealError(f"Missing provenance record: {provenance_id}")
        return record

    @staticmethod
    def _validate_rights_chain(records: list[ProvenanceRecord]) -> None:
        by_id = {record.provenance_id: record for record in records}

        def has_complete_rights(provenance_id: str, visiting: set[str]) -> bool:
            if provenance_id in visiting:
                return False
            record = by_id.get(provenance_id)
            if record is None:
                return False
            if record.rights is not None:
                return record.rights.is_complete
            if record.rights_basis_provenance_id is None:
                return False
            return has_complete_rights(
                record.rights_basis_provenance_id,
                {*visiting, provenance_id},
            )

        incomplete = [
            record.provenance_id
            for record in records
            if not has_complete_rights(record.provenance_id, set())
        ]
        if incomplete:
            raise PackageSealError(
                "Incomplete provenance rights chain: " + ", ".join(incomplete)
            )

    def _write_package_metadata(
        self,
        staging: Path,
        *,
        package_payload: dict[str, object],
        provenance: list[ProvenanceRecord],
        approvals: list[dict[str, object]],
        state: AuthoringState,
    ) -> None:
        def write(relative_path: str, payload: object) -> None:
            path = staging / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_json_exclusive(path, payload)

        write("package.json", package_payload)
        write(
            "provenance.json",
            {
                "schema_version": "1.0",
                "records": [record.model_dump(mode="json") for record in provenance],
            },
        )
        write(
            "approvals.json",
            {"schema_version": "1.0", "approvals": approvals},
        )
        write(
            "gaps.json",
            {
                "schema_version": "1.0",
                "gaps": [gap.model_dump(mode="json") for gap in state.gaps],
            },
        )
        gap_payloads = {
            "measurements/body.json": ["measurements-missing"],
            "measurements/face.json": ["measurements-missing"],
            "landmarks/body.json": ["landmarks-missing"],
            "landmarks/face.json": ["landmarks-missing"],
            "palette/palette.json": ["numeric-materials-missing"],
            "materials/materials.json": ["numeric-materials-missing"],
        }
        for relative_path, gap_ids in gap_payloads.items():
            write(
                relative_path,
                {
                    "schema_version": "1.0",
                    "status": "gap",
                    "gap_ids": gap_ids,
                },
            )
        expression_task = self._plan.task("expressions")
        viseme_task = self._plan.task("visemes")
        hair_task = self._plan.task("hair-construction")
        outfit_task = self._plan.task("outfit-construction")
        write(
            "expressions/expressions.json",
            {
                "schema_version": "1.0",
                "references": {
                    panel.panel_id: panel.package_path for panel in expression_task.panels
                },
            },
        )
        write(
            "visemes/visemes.json",
            {
                "schema_version": "1.0",
                "references": {
                    panel.panel_id: panel.package_path for panel in viseme_task.panels
                },
            },
        )
        write(
            "hair/hair.json",
            {
                "schema_version": "1.0",
                "references": {
                    panel.panel_id: panel.package_path for panel in hair_task.panels
                },
                "production_asset_gap": "production-assets-missing",
            },
        )
        write(
            "outfit/outfit.json",
            {
                "schema_version": "1.0",
                "references": {
                    panel.panel_id: panel.package_path for panel in outfit_task.panels
                },
                "production_asset_gap": "production-assets-missing",
            },
        )

    @staticmethod
    def _package_file_hashes(staging: Path) -> dict[str, str]:
        files = sorted(
            (path for path in staging.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(staging).as_posix(),
        )
        return {
            path.relative_to(staging).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        }

    @staticmethod
    def _read_source(path: Path) -> bytes:
        try:
            return Path(path).read_bytes()
        except OSError as exc:
            raise WorkspaceError("Master source image is unavailable.") from exc

    @staticmethod
    def _load_png(data: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format != "PNG":
                    raise CandidateValidationError("Candidate output must be a valid PNG image.")
                source.load()
                return source.convert("RGB")
        except CandidateValidationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise CandidateValidationError(
                "Candidate output must be a valid PNG image."
            ) from exc

    @classmethod
    def _png_dimensions(cls, data: bytes) -> tuple[int, int]:
        image = cls._load_png(data)
        try:
            return image.size
        finally:
            image.close()

    @staticmethod
    def _artifact(
        relative_path: str,
        data: bytes,
        width: int,
        height: int,
    ) -> ArtifactEvidence:
        return ArtifactEvidence(
            path=relative_path,
            sha256=hashlib.sha256(data).hexdigest(),
            byte_length=len(data),
            width=width,
            height=height,
        )

    @staticmethod
    def _write_bytes_exclusive(path: Path, data: bytes) -> None:
        with path.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())

    @classmethod
    def _write_json_exclusive(cls, path: Path, payload: object) -> None:
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        cls._write_bytes_exclusive(path, encoded)

    @staticmethod
    def _initial_gaps(command: WorkspaceInitialization) -> tuple[GapRecord, ...]:
        gaps = [
            GapRecord(
                gap_id="measurements-missing",
                area="measurements",
                description="Metric measurements require a later approved source.",
                blocks_visual_seal=False,
            ),
            GapRecord(
                gap_id="landmarks-missing",
                area="landmarks",
                description="Body and face landmarks require a later approved source.",
                blocks_visual_seal=False,
            ),
            GapRecord(
                gap_id="numeric-materials-missing",
                area="materials",
                description="Numeric palette and material values require later authoring.",
                blocks_visual_seal=False,
            ),
            GapRecord(
                gap_id="production-assets-missing",
                area="assets",
                description="Traceable production 3D assets have not been selected.",
                blocks_visual_seal=False,
            ),
            GapRecord(
                gap_id="base-adapter-missing",
                area="adapters",
                description="A base-model adapter belongs to a later 3D build stage.",
                blocks_visual_seal=False,
            ),
        ]
        if command.rights is None or not command.rights.is_complete:
            gaps.append(
                GapRecord(
                    gap_id="source-rights-incomplete",
                    area="provenance",
                    description=(
                        "Master source rights must be completed before visual package sealing."
                    ),
                    blocks_visual_seal=True,
                )
            )
        return tuple(gaps)
