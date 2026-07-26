"""No-clobber filesystem adapter for panel-first pixel portrait authoring."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from threading import get_ident
from typing import cast
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from pydantic import TypeAdapter, ValidationError

from ...adapters.filesystem import (
    CandidateValidationError,
    FilesystemAuthoringWorkspace,
    PackageDestinationExistsError,
    PackageIntegrityError,
    PackageSealError,
    WorkspaceAlreadyExistsError,
    WorkspaceError,
    WorkspacePathError,
)
from ...contracts import (
    ApprovalDecision,
    ArtifactEvidence,
    GapRecord,
    PackageRelativePath,
    ProvenanceRecord,
    RightsMetadata,
    SealEvidence,
    SourceClass,
)
from ...ports import GeneratedImage
from ..contracts import (
    PACKAGE_MASTER_PATH,
    CompositeApproval,
    CompositeReviewSheet,
    CompositeScope,
    CompositeStatus,
    PanelProgress,
    PixelPackageRevision,
    PixelPanelApproval,
    PixelPanelCandidate,
    PixelPanelState,
    PixelPortraitAuthoringState,
    PortraitIdentityLock,
)
from ..plan import (
    PIXEL_PORTRAIT_PLAN,
    PixelPanelDefinition,
    PixelPortraitPlanDefinition,
)
from ..ports import BASE_SOURCE_FILENAMES, PixelWorkspaceInitialization

_PACKAGE_PATH_ADAPTER = TypeAdapter(PackageRelativePath)
_PROVENANCE_RECORDS_ADAPTER = TypeAdapter(tuple[ProvenanceRecord, ...])
_PANEL_APPROVALS_ADAPTER = TypeAdapter(tuple[PixelPanelApproval, ...])
_COMPOSITE_APPROVALS_ADAPTER = TypeAdapter(tuple[CompositeApproval, ...])
_GAP_RECORDS_ADAPTER = TypeAdapter(tuple[GapRecord, ...])
_COMPOSITION_VERSION = "pixel-grid-v1"
_COMPOSITE_GAP = 2
_PACKAGE_MASTER_ROWS = 3
_PACKAGE_MASTER_COLUMNS = 3
_PIXEL_PACKAGE_METADATA_FILES = (
    "package.json",
    "provenance.json",
    "approvals.json",
    "gaps.json",
    "authoring/pixel-style.json",
    "authoring/panel-definitions.json",
    "authoring/anchor-profiles.json",
    "authoring/composite-sheets.json",
)
_CANONICAL_PACKAGE_DIRECTORIES = (
    "references/master",
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
_ADDITIVE_PACKAGE_DIRECTORIES = (
    "sources/base-set",
    "sources/talking-bust-v1",
    "authoring",
    "authoring/panel-validation-reports",
    "authoring/composite-slot-maps",
)


class FilesystemPixelPortraitWorkspace:
    """Persist immutable source locks and normalized pixel-panel candidates."""

    STATE_FILE = "authoring-state.json"
    PLAN_FILE = "authoring-plan.json"
    LOCK_FILE = ".authoring.lock"
    TECHNICAL_SOURCE_ROOT = "sources/talking-bust-v1"
    TECHNICAL_PROVENANCE_PREFIX = "talking-bust-v1:"

    def __init__(
        self,
        root: Path,
        plan: PixelPortraitPlanDefinition = PIXEL_PORTRAIT_PLAN,
    ) -> None:
        self.root = Path(root)
        self._plan = plan
        self._exclusive_owner: int | None = None

    def _validate_root_ancestry(self) -> None:
        lexical_root = Path(os.path.abspath(self.root))
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        for path in (lexical_root, *lexical_root.parents):
            if not os.path.lexists(path):
                continue
            try:
                metadata = path.lstat()
                is_junction_method = getattr(path, "is_junction", None)
                is_junction = bool(is_junction_method is not None and is_junction_method())
            except OSError as exc:
                raise WorkspacePathError(
                    "Pixel portrait workspace root ancestry could not be verified."
                ) from exc
            is_reparse_point = bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)
            if stat.S_ISLNK(metadata.st_mode) or is_junction or is_reparse_point:
                raise WorkspacePathError(
                    "Pixel portrait workspace root ancestry cannot contain "
                    "symlinks, junctions, or reparse points."
                )

    def initialize(
        self,
        command: PixelWorkspaceInitialization,
    ) -> PixelPortraitAuthoringState:
        """Create a new workspace after validating and snapshotting every source."""
        self._validate_root_ancestry()
        if self.root.exists() or os.path.lexists(self.root):
            raise WorkspaceAlreadyExistsError(
                f"Pixel portrait workspace already exists: {self.root}"
            )

        technical_package = Path(command.technical_package)
        self._reject_source_symlink(technical_package, "Technical source package")
        technical_seal = FilesystemAuthoringWorkspace.validate_sealed_package(technical_package)
        self._validate_declared_technical_files(technical_package, technical_seal)
        source_technical_provenance = self._read_technical_provenance(
            technical_package,
            technical_seal,
        )
        self._validate_required_technical_provenance(source_technical_provenance)
        locked_technical_provenance = self._remap_technical_provenance(source_technical_provenance)
        technical_directories, technical_files = self._snapshot_source_tree(technical_package)
        base_source_data = self._read_base_sources(command.base_sources)

        self._validate_root_ancestry()
        self.root.parent.mkdir(parents=True, exist_ok=True)
        staging = self.root.with_name(f".{self.root.name}.init-{uuid4().hex}.tmp")
        try:
            self._validate_root_ancestry()
            staging.mkdir()
            base_artifacts: list[ArtifactEvidence] = []
            for filename in BASE_SOURCE_FILENAMES:
                source_path, data, width, height = base_source_data[filename]
                relative_path = f"sources/base-set/{filename}"
                destination = staging / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._write_bytes_exclusive(destination, data)
                base_artifacts.append(self._artifact(relative_path, data, width, height))
                if source_path.read_bytes() != data:
                    raise PackageIntegrityError(
                        f"Base source bytes changed during initialization: {filename}"
                    )

            technical_destination = staging / self.TECHNICAL_SOURCE_ROOT
            technical_destination.mkdir(parents=True)
            for relative_path in technical_directories:
                (technical_destination / relative_path).mkdir(
                    parents=True,
                    exist_ok=True,
                )
            for relative_path, data in technical_files.items():
                destination = technical_destination / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._write_bytes_exclusive(destination, data)
            for record in locked_technical_provenance:
                self._verified_artifact_data_at(staging, record.artifact)

            rights = command.base_rights or RightsMetadata()
            revision = PixelPackageRevision(
                package_id=command.package_id,
                identity=command.identity,
                revision=command.revision,
                base_sources=tuple(base_artifacts),
                base_source_rights=rights,
                technical_source_seal=technical_seal,
            )
            base_provenance = tuple(
                ProvenanceRecord(
                    provenance_id=f"base-set-{Path(filename).stem}",
                    source_class=SourceClass.CREATIVE_CANON,
                    artifact=artifact,
                    authoritative_source=command.authoritative_source,
                    rights=rights,
                )
                for filename, artifact in zip(
                    BASE_SOURCE_FILENAMES,
                    base_artifacts,
                    strict=True,
                )
            )
            state = PixelPortraitAuthoringState(
                revision=revision,
                plan_id=self._plan.plan_id,
                plan_version=self._plan.version,
                panels={
                    panel.panel_id: PixelPanelState(panel_id=panel.panel_id)
                    for panel in self._plan.panels
                },
                provenance=(*base_provenance, *locked_technical_provenance),
                gaps=self._initial_gaps(rights),
            )
            self._write_json_exclusive(
                staging / self.PLAN_FILE,
                self._plan.model_dump(mode="json"),
            )
            self._write_json_exclusive(
                staging / self.STATE_FILE,
                state.model_dump(mode="json"),
            )

            validated_seal = FilesystemAuthoringWorkspace.validate_sealed_package(technical_package)
            self._validate_declared_technical_files(technical_package, validated_seal)
            if validated_seal != technical_seal or self._snapshot_source_tree(
                technical_package
            ) != (technical_directories, technical_files):
                raise PackageIntegrityError(
                    "Technical source package changed during initialization."
                )
            if self.root.exists() or os.path.lexists(self.root):
                raise WorkspaceAlreadyExistsError(
                    f"Pixel portrait workspace already exists: {self.root}"
                )
            self._validate_root_ancestry()
            os.rename(staging, self.root)
            return state
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def load_state(self) -> PixelPortraitAuthoringState:
        """Load the current strict pixel portrait state."""
        self._validate_root_ancestry()
        return PixelPortraitAuthoringState.model_validate_json(
            (self.root / self.STATE_FILE).read_text(encoding="utf-8")
        )

    def save_state(self, state: PixelPortraitAuthoringState) -> None:
        """Atomically replace state through a same-directory temporary file."""
        self._validate_root_ancestry()
        with self._write_guard():
            self._save_state(state)

    def _save_state(self, state: PixelPortraitAuthoringState) -> None:
        self._validate_root_ancestry()
        validated = PixelPortraitAuthoringState.model_validate(state.model_dump(mode="python"))
        state_path = self.root / self.STATE_FILE
        temporary = self.root / f".{self.STATE_FILE}.{uuid4().hex}.tmp"
        try:
            self._write_json_exclusive(
                temporary,
                validated.model_dump(mode="json"),
            )
            os.replace(temporary, state_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def resolve_artifact(self, relative_path: PackageRelativePath | str) -> Path:
        """Resolve a strict relative path and reject containment or symlink escape."""
        self._validate_root_ancestry()
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
        panel: PixelPanelDefinition,
        attempt: int,
        generated: GeneratedImage,
        input_artifacts: tuple[ArtifactEvidence, ...],
        created_at: datetime,
    ) -> PixelPanelCandidate:
        """Preserve one raw provider PNG and normalize it to a bounded pixel grid."""
        self._validate_root_ancestry()
        with self._write_guard():
            return self._stage_candidate(
                panel=panel,
                attempt=attempt,
                generated=generated,
                input_artifacts=input_artifacts,
                created_at=created_at,
            )

    def _stage_candidate(
        self,
        *,
        panel: PixelPanelDefinition,
        attempt: int,
        generated: GeneratedImage,
        input_artifacts: tuple[ArtifactEvidence, ...],
        created_at: datetime,
    ) -> PixelPanelCandidate:
        try:
            canonical_panel = self._plan.panel(panel.panel_id)
        except KeyError as exc:
            raise CandidateValidationError("Pixel panel is not part of the fixed plan.") from exc
        if panel != canonical_panel:
            raise CandidateValidationError(
                "Pixel panel definition does not match the fixed authoring plan."
            )
        if isinstance(attempt, bool) or not isinstance(attempt, int) or not 1 <= attempt <= 3:
            raise CandidateValidationError("Pixel panel attempt must be between 1 and 3.")
        if not input_artifacts:
            raise CandidateValidationError(
                "Pixel panel candidates require at least one locked input artifact."
            )
        for artifact in input_artifacts:
            self._verified_artifact_data(artifact)

        attempt_relative = f"candidates/{panel.panel_id}/attempt-{attempt}"
        attempt_path = self.resolve_artifact(attempt_relative)
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            attempt_path.mkdir()
        except FileExistsError as exc:
            raise WorkspaceAlreadyExistsError(
                f"Pixel panel attempt already exists: {attempt_relative}"
            ) from exc

        raw_relative = f"{attempt_relative}/raw.png"
        raw_path = attempt_path / "raw.png"
        self._write_bytes_exclusive(raw_path, generated.data)
        image = self._load_png(generated.data)
        try:
            if image.size != (panel.request_width, panel.request_height):
                raise CandidateValidationError(
                    "Pixel panel raw PNG must be exactly "
                    f"{panel.request_width}x{panel.request_height} pixels."
                )
            normalized_data, palette = self._normalize_pixel_panel(image, panel)
        finally:
            image.close()

        panel_relative = f"{attempt_relative}/panel.png"
        panel_path = attempt_path / "panel.png"
        self._write_bytes_exclusive(panel_path, normalized_data)
        raw_artifact = self._artifact(
            raw_relative,
            generated.data,
            panel.request_width,
            panel.request_height,
        )
        normalized_artifact = self._artifact(
            panel_relative,
            normalized_data,
            panel.file_width,
            panel.file_height,
        )
        palette_payload = [list(color) for color in palette]
        palette_sha256 = hashlib.sha256(
            json.dumps(
                palette_payload,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        report_payload = {
            "attempt": attempt,
            "normalized_sha256": normalized_artifact.sha256,
            "normalization": {
                "actual_colors": len(palette_payload),
                "dither": "NONE",
                "downsample": "LANCZOS",
                "file_size": [panel.file_width, panel.file_height],
                "logical_pixel_scale": panel.file_width // panel.logical_width,
                "logical_size": [panel.logical_width, panel.logical_height],
                "max_colors": 64,
                "method": "FASTOCTREE",
                "upscale": "NEAREST",
            },
            "palette": palette_payload,
            "palette_sha256": palette_sha256,
            "panel_id": panel.panel_id,
            "raw_sha256": raw_artifact.sha256,
            "schema_version": "1.0",
            "valid": True,
        }
        report_data = self._canonical_json(report_payload)
        report_relative = f"{attempt_relative}/validation-report.json"
        self._write_bytes_exclusive(
            attempt_path / "validation-report.json",
            report_data,
        )
        report_artifact = self._artifact(report_relative, report_data, 1, 1)
        return PixelPanelCandidate(
            candidate_id=f"{panel.panel_id}-attempt-{attempt}",
            panel_id=panel.panel_id,
            attempt=attempt,
            provider=generated.provider,
            model=generated.model,
            prompt_id=panel.prompt_id,
            prompt_version=panel.prompt_version,
            input_artifacts=input_artifacts,
            raw_artifact=raw_artifact,
            normalized_panel=normalized_artifact,
            validation_report=report_artifact,
            created_at=created_at,
        )

    def compose(
        self,
        *,
        state: PixelPortraitAuthoringState,
        scope: CompositeScope,
        family_id: str | None,
        created_at: datetime,
    ) -> CompositeReviewSheet:
        """Compose one immutable deterministic review sheet."""
        self._validate_root_ancestry()
        with self._write_guard():
            return self._compose(
                state=state,
                scope=scope,
                family_id=family_id,
                created_at=created_at,
            )

    def _compose(
        self,
        *,
        state: PixelPortraitAuthoringState,
        scope: CompositeScope,
        family_id: str | None,
        created_at: datetime,
    ) -> CompositeReviewSheet:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise PackageIntegrityError("Composite creation time must include a timezone.")
        state = self._strict_authoring_state(state)
        self.validate(state)
        version = 1 + sum(
            composite.scope is scope and composite.family_id == family_id
            for composite in state.composites
        )
        if scope is CompositeScope.FAMILY:
            if family_id is None:
                raise PackageIntegrityError("Family composition requires a family identifier.")
            try:
                family = self._plan.family(family_id)
            except KeyError as exc:
                raise PackageIntegrityError(
                    "Composite family is not part of the fixed plan."
                ) from exc
            composite_id = f"family-{family_id}-v{version}"
            relative_root = f"composites/family/{composite_id}"
            members = self._current_family_members(state, family_id)
            rows = family.rows
            columns = family.columns
            cell_width = 512
            cell_height = 512
        elif scope is CompositeScope.PACKAGE_MASTER:
            if family_id is not None:
                raise PackageIntegrityError(
                    "Package-master composition cannot declare a family identifier."
                )
            composite_id = f"package-master-v{version}"
            relative_root = f"composites/package-master/{composite_id}"
            members = self._current_package_master_members(state)
            rows = _PACKAGE_MASTER_ROWS
            columns = _PACKAGE_MASTER_COLUMNS
            cell_width = max(member[2].width for member in members)
            cell_height = max(member[2].height for member in members)
        else:
            raise PackageIntegrityError("Composite scope is not supported by the fixed plan.")

        sheet_data, slots, output_width, output_height = self._render_composite(
            members,
            rows=rows,
            columns=columns,
            cell_width=cell_width,
            cell_height=cell_height,
        )
        artifact = self._artifact(
            f"{relative_root}/sheet.png",
            sheet_data,
            output_width,
            output_height,
        )
        composite = CompositeReviewSheet(
            composite_id=composite_id,
            scope=scope,
            family_id=family_id,
            member_ids=tuple(member[0] for member in members),
            member_hashes=tuple(member[1] for member in members),
            member_artifacts=tuple(member[2] for member in members),
            artifact=artifact,
            composition_version=_COMPOSITION_VERSION,
            created_at=created_at,
            status=CompositeStatus.PENDING_REVIEW,
        )
        slot_map = self._slot_map(
            composite,
            rows=rows,
            columns=columns,
            cell_width=cell_width,
            cell_height=cell_height,
            output_width=output_width,
            output_height=output_height,
            slots=slots,
        )
        version_path = self.resolve_artifact(relative_root)
        if version_path.exists() or os.path.lexists(version_path):
            return self._reuse_composite(
                version_path,
                composite,
                sheet_data,
                slot_map,
            )

        version_path.parent.mkdir(parents=True, exist_ok=True)
        staging = version_path.with_name(f".{composite_id}.{uuid4().hex}.tmp")
        try:
            staging.mkdir()
            self._write_bytes_exclusive(staging / "sheet.png", sheet_data)
            self._write_json_exclusive(staging / "slot-map.json", slot_map)
            if version_path.exists() or os.path.lexists(version_path):
                raise PackageIntegrityError(
                    f"Refusing to overwrite an existing composite: {relative_root}"
                )
            os.rename(staging, version_path)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        return composite

    def _current_family_members(
        self,
        state: PixelPortraitAuthoringState,
        family_id: str,
    ) -> tuple[tuple[str, str, ArtifactEvidence, bytes], ...]:
        family = self._plan.family(family_id)
        members: list[tuple[str, str, ArtifactEvidence, bytes]] = []
        for panel_id in family.panel_ids:
            panel_state = state.panels.get(panel_id)
            if panel_state is None or panel_state.progress is not PanelProgress.APPROVED:
                raise PackageIntegrityError(
                    "Family composition requires every ordered member to be actively approved."
                )
            candidate = next(
                (
                    item
                    for item in panel_state.candidates
                    if item.candidate_id == panel_state.approved_candidate_id
                ),
                None,
            )
            if candidate is None:
                raise PackageIntegrityError(
                    "Family composition requires every ordered member to be actively approved."
                )
            artifact = candidate.normalized_panel
            definition = self._plan.panel(panel_id)
            if (artifact.width, artifact.height) != (
                definition.file_width,
                definition.file_height,
            ):
                raise PackageIntegrityError(
                    "Approved family member dimensions do not match the fixed plan."
                )
            members.append(
                (
                    panel_id,
                    artifact.sha256,
                    artifact,
                    self._verified_artifact_data(artifact),
                )
            )
        return tuple(members)

    def _current_package_master_members(
        self,
        state: PixelPortraitAuthoringState,
    ) -> tuple[tuple[str, str, ArtifactEvidence, bytes], ...]:
        composites = {composite.composite_id: composite for composite in state.composites}
        active_families = [
            composites[composite_id]
            for composite_id in state.active_composite_ids
            if composites[composite_id].scope is CompositeScope.FAMILY
        ]
        by_family = {composite.family_id: composite for composite in active_families}
        expected_family_ids = tuple(family.family_id for family in self._plan.families)
        if (
            len(active_families) != len(expected_family_ids)
            or set(by_family) != set(expected_family_ids)
            or any(
                composite.status is not CompositeStatus.APPROVED for composite in active_families
            )
        ):
            raise PackageIntegrityError(
                "Package master requires exactly one current approved composite "
                "for every plan family."
            )
        return tuple(
            (
                by_family[family_id].composite_id,
                by_family[family_id].artifact.sha256,
                by_family[family_id].artifact,
                self._verified_artifact_data(by_family[family_id].artifact),
            )
            for family_id in expected_family_ids
        )

    @classmethod
    def _render_composite(
        cls,
        members: tuple[tuple[str, str, ArtifactEvidence, bytes], ...],
        *,
        rows: int,
        columns: int,
        cell_width: int,
        cell_height: int,
    ) -> tuple[bytes, tuple[dict[str, object], ...], int, int]:
        if len(members) > rows * columns:
            raise PackageIntegrityError("Composite members exceed the fixed grid capacity.")
        output_width = columns * cell_width + (columns - 1) * _COMPOSITE_GAP
        output_height = rows * cell_height + (rows - 1) * _COMPOSITE_GAP
        output = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))
        slots: list[dict[str, object]] = []
        try:
            for index, (member_id, member_hash, artifact, data) in enumerate(members):
                if artifact.width > cell_width or artifact.height > cell_height:
                    raise PackageIntegrityError(
                        "Composite member dimensions exceed the fixed cell."
                    )
                x = (index % columns) * (cell_width + _COMPOSITE_GAP)
                y = (index // columns) * (cell_height + _COMPOSITE_GAP)
                image = cls._load_png(data)
                try:
                    if image.size != (artifact.width, artifact.height):
                        raise PackageIntegrityError(
                            "Composite member dimensions changed during rendering."
                        )
                    output.alpha_composite(image, dest=(x, y))
                finally:
                    image.close()
                slots.append(
                    {
                        "height": artifact.height,
                        "member_id": member_id,
                        "path": artifact.path,
                        "sha256": member_hash,
                        "width": artifact.width,
                        "x": x,
                        "y": y,
                    }
                )
            buffer = io.BytesIO()
            output.save(buffer, format="PNG", optimize=False, compress_level=9)
            return buffer.getvalue(), tuple(slots), output_width, output_height
        finally:
            output.close()

    @staticmethod
    def _slot_map(
        composite: CompositeReviewSheet,
        *,
        rows: int,
        columns: int,
        cell_width: int,
        cell_height: int,
        output_width: int,
        output_height: int,
        slots: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        return {
            "cell": {
                "alignment": "top_left",
                "height": cell_height,
                "width": cell_width,
            },
            "composite_id": composite.composite_id,
            "composition_version": composite.composition_version,
            "created_at": composite.created_at.isoformat(),
            "family_id": composite.family_id,
            "grid": {"columns": columns, "gap": _COMPOSITE_GAP, "rows": rows},
            "members": list(slots),
            "output": {"height": output_height, "width": output_width},
            "schema_version": "1.0",
            "scope": composite.scope.value,
        }

    def _reuse_composite(
        self,
        version_path: Path,
        requested: CompositeReviewSheet,
        expected_sheet: bytes,
        requested_slot_map: dict[str, object],
    ) -> CompositeReviewSheet:
        if version_path.is_symlink() or not version_path.is_dir():
            raise PackageIntegrityError("The existing composite path is not a safe directory.")
        sheet_path = version_path / "sheet.png"
        slot_map_path = version_path / "slot-map.json"
        try:
            entries = {entry.name for entry in version_path.iterdir()}
            if entries != {"sheet.png", "slot-map.json"}:
                raise ValueError("unexpected composite directory entries")
            actual_sheet = sheet_path.read_bytes()
            actual_slot_bytes = slot_map_path.read_bytes()
            actual_slot_map = json.loads(actual_slot_bytes)
            stored_created_at = datetime.fromisoformat(actual_slot_map["created_at"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PackageIntegrityError(
                "The existing composite does not match the deterministic request."
            ) from exc
        try:
            reusable = CompositeReviewSheet.model_validate(
                requested.model_copy(update={"created_at": stored_created_at}).model_dump(
                    mode="python"
                )
            )
        except ValidationError as exc:
            raise PackageIntegrityError(
                "The existing composite does not match the deterministic request."
            ) from exc
        expected_slot_map = dict(requested_slot_map)
        expected_slot_map["created_at"] = stored_created_at.isoformat()
        if (
            actual_sheet != expected_sheet
            or actual_slot_map != expected_slot_map
            or actual_slot_bytes != self._canonical_json(expected_slot_map)
        ):
            raise PackageIntegrityError(
                "The existing composite does not match the deterministic request."
            )
        return reusable

    @staticmethod
    def _strict_authoring_state(
        state: PixelPortraitAuthoringState,
    ) -> PixelPortraitAuthoringState:
        try:
            return PixelPortraitAuthoringState.model_validate(state.model_dump(mode="python"))
        except ValidationError as exc:
            raise PackageIntegrityError("Pixel portrait state is invalid.") from exc

    def seal(
        self,
        state: PixelPortraitAuthoringState,
        destination: Path,
        sealed_at: datetime,
    ) -> SealEvidence:
        """Publish one schema-1.1 package through a validated sibling staging tree."""
        if sealed_at.tzinfo is None or sealed_at.utcoffset() is None:
            raise PackageSealError("Package seal time must include a timezone.")
        self._validate_root_ancestry()
        state = self._strict_authoring_state(state)
        self.validate(state)
        self._validate_seal_state(state)

        destination = Path(destination)
        self._validate_package_destination(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._validate_safe_ancestry(destination.parent, "Package destination")
        staging = destination.with_name(f".{destination.name}.seal-{uuid4().hex}.tmp")
        staging_parent = Path(os.path.abspath(destination.parent))
        try:
            staging.mkdir()
            self._validate_safe_ancestry(staging, "Package staging directory")
            technical_directories = self._create_package_directories(staging)
            (
                panel_artifacts,
                report_artifacts,
                family_artifacts,
                master_artifact,
                slot_map_paths,
            ) = self._publish_package_artifacts(state, staging)
            provenance = self._package_provenance(
                state,
                panel_artifacts=panel_artifacts,
                family_artifacts=family_artifacts,
                master_artifact=master_artifact,
            )
            self._validate_rights_chain(provenance)
            approval_ids = self._write_pixel_package_metadata(
                staging,
                state=state,
                sealed_at=sealed_at,
                technical_directories=technical_directories,
                panel_artifacts=panel_artifacts,
                report_artifacts=report_artifacts,
                family_artifacts=family_artifacts,
                master_artifact=master_artifact,
                slot_map_paths=slot_map_paths,
                provenance=provenance,
            )
            evidence = SealEvidence(
                package_id=state.revision.package_id,
                revision=state.revision.revision,
                sealed_at=sealed_at,
                file_hashes=self._package_file_hashes(staging),
                approval_ids=approval_ids,
                provenance_ids=tuple(record.provenance_id for record in provenance),
                unresolved_gap_ids=tuple(gap.gap_id for gap in state.gaps),
            )
            self._write_json_exclusive(
                staging / "seal.json",
                evidence.model_dump(mode="json"),
            )
            self.validate_sealed_package(staging)
            self._validate_package_destination(destination)
            self._validate_safe_ancestry(destination.parent, "Package destination")
            os.rename(staging, destination)
            return evidence
        except Exception:
            self._cleanup_staging(staging, staging_parent)
            raise

    def _validate_seal_state(self, state: PixelPortraitAuthoringState) -> None:
        if not state.revision.base_source_rights.is_complete:
            raise PackageSealError("Base-set source rights are incomplete.")
        blocking = tuple(gap.gap_id for gap in state.gaps if gap.blocks_visual_seal)
        if blocking:
            raise PackageSealError("Visual package sealing is blocked by: " + ", ".join(blocking))
        if state.identity_lock is None:
            raise PackageSealError("The approved neutral identity lock is missing.")

        for definition in self._plan.panels:
            panel = state.panels[definition.panel_id]
            candidate = self._active_candidate(panel)
            self._active_panel_approval(panel, candidate)
            expected_inputs = self._expected_panel_inputs(state, definition)
            if candidate.input_artifacts != expected_inputs:
                raise PackageSealError(
                    f"Active panel source lineage is not canonical: {definition.panel_id}"
                )

        families, master = self._active_package_composites(state)
        for composite in (*families, master):
            self._active_composite_approval(state, composite)
        expected_master = master.artifact.model_copy(update={"path": PACKAGE_MASTER_PATH})
        if state.revision.master_reference != expected_master:
            raise PackageSealError(
                "The revision master reference does not match the current package master."
            )

    def _expected_panel_inputs(
        self,
        state: PixelPortraitAuthoringState,
        panel: PixelPanelDefinition,
    ) -> tuple[ArtifactEvidence, ...]:
        base_by_name = {
            Path(artifact.path).name: artifact for artifact in state.revision.base_sources
        }
        technical_by_path = {
            record.artifact.path: record.artifact
            for record in state.provenance
            if record.artifact.path.startswith(f"{self.TECHNICAL_SOURCE_ROOT}/")
        }
        if panel.panel_id == "presence-neutral":
            if panel.technical_source_path is None:
                raise PackageSealError("Neutral technical source lineage is missing.")
            return (
                *(base_by_name[filename] for filename in BASE_SOURCE_FILENAMES),
                technical_by_path[f"{self.TECHNICAL_SOURCE_ROOT}/{panel.technical_source_path}"],
            )
        neutral = self._active_candidate(state.panels["presence-neutral"]).normalized_panel
        character_sheet = base_by_name["juana-avatar-character-sheet.png"]
        if panel.family_id == "presence-states":
            if panel.base_source_role is None:
                raise PackageSealError("Presence panel base-state lineage is missing.")
            return (
                character_sheet,
                base_by_name[f"juana-avatar-{panel.base_source_role}.png"],
                neutral,
            )
        if panel.technical_source_path is None:
            raise PackageSealError("Technical panel source lineage is missing.")
        return (
            character_sheet,
            neutral,
            technical_by_path[f"{self.TECHNICAL_SOURCE_ROOT}/{panel.technical_source_path}"],
        )

    @staticmethod
    def _active_candidate(panel: PixelPanelState) -> PixelPanelCandidate:
        if panel.progress is not PanelProgress.APPROVED:
            raise PackageSealError(f"Pixel panel is not actively approved: {panel.panel_id}")
        candidates = tuple(
            candidate
            for candidate in panel.candidates
            if candidate.candidate_id == panel.approved_candidate_id
            and candidate.status.value == "approved"
        )
        if len(candidates) != 1:
            raise PackageSealError(f"Pixel panel has no unique active candidate: {panel.panel_id}")
        return candidates[0]

    @staticmethod
    def _active_panel_approval(
        panel: PixelPanelState,
        candidate: PixelPanelCandidate,
    ) -> PixelPanelApproval:
        approvals = tuple(
            decision
            for decision in panel.decisions
            if decision.candidate_id == candidate.candidate_id
            and decision.decision is ApprovalDecision.APPROVE
        )
        if len(approvals) != 1:
            raise PackageSealError(f"Pixel panel has no unique active approval: {panel.panel_id}")
        return approvals[0]

    def _active_package_composites(
        self,
        state: PixelPortraitAuthoringState,
    ) -> tuple[tuple[CompositeReviewSheet, ...], CompositeReviewSheet]:
        composites = {item.composite_id: item for item in state.composites}
        expected_family_ids = tuple(family.family_id for family in self._plan.families)
        active = tuple(composites[item] for item in state.active_composite_ids)
        families = tuple(item for item in active if item.scope is CompositeScope.FAMILY)
        masters = tuple(item for item in active if item.scope is CompositeScope.PACKAGE_MASTER)
        if (
            tuple(item.family_id for item in families) != expected_family_ids
            or len(masters) != 1
            or state.active_composite_ids
            != (*tuple(item.composite_id for item in families), masters[0].composite_id)
            or any(item.status is not CompositeStatus.APPROVED for item in active)
        ):
            raise PackageSealError(
                "Sealing requires nine current family sheets and one current package master."
            )
        return families, masters[0]

    @staticmethod
    def _active_composite_approval(
        state: PixelPortraitAuthoringState,
        composite: CompositeReviewSheet,
    ) -> CompositeApproval:
        approvals = tuple(
            approval
            for approval in state.composite_approvals
            if approval.composite_id == composite.composite_id
        )
        if len(approvals) != 1:
            raise PackageSealError(
                f"Composite has no unique active approval: {composite.composite_id}"
            )
        return approvals[0]

    def _create_package_directories(self, staging: Path) -> tuple[str, ...]:
        technical_root = self.root / self.TECHNICAL_SOURCE_ROOT
        technical_directories, _ = self._snapshot_source_tree(technical_root)
        planned_parents = {
            str(Path(path).parent).replace("\\", "/")
            for path in (
                *(panel.package_path for panel in self._plan.panels),
                *(family.sheet_package_path for family in self._plan.families),
                PACKAGE_MASTER_PATH,
            )
        }
        directories = {
            *_CANONICAL_PACKAGE_DIRECTORIES,
            *_ADDITIVE_PACKAGE_DIRECTORIES,
            *planned_parents,
            *(f"{self.TECHNICAL_SOURCE_ROOT}/{relative}" for relative in technical_directories),
        }
        for relative in sorted(directories, key=lambda item: (item.count("/"), item)):
            (staging / relative).mkdir(parents=True, exist_ok=True)
        return technical_directories

    def _publish_package_artifacts(
        self,
        state: PixelPortraitAuthoringState,
        staging: Path,
    ) -> tuple[
        dict[str, ArtifactEvidence],
        dict[str, ArtifactEvidence],
        dict[str, ArtifactEvidence],
        ArtifactEvidence,
        dict[str, str],
    ]:
        for source in state.revision.base_sources:
            self._copy_workspace_artifact(source, staging, source.path)

        technical_root = self.root / self.TECHNICAL_SOURCE_ROOT
        technical_directories, technical_files = self._snapshot_source_tree(technical_root)
        for relative in technical_directories:
            (staging / self.TECHNICAL_SOURCE_ROOT / relative).mkdir(
                parents=True,
                exist_ok=True,
            )
        for relative, data in technical_files.items():
            self._copy_bytes_to_package(
                staging,
                f"{self.TECHNICAL_SOURCE_ROOT}/{relative}",
                data,
            )
        copied_technical_root = staging / self.TECHNICAL_SOURCE_ROOT
        copied_seal = FilesystemAuthoringWorkspace.validate_sealed_package(copied_technical_root)
        self._validate_declared_technical_files(copied_technical_root, copied_seal)
        if copied_seal != state.revision.technical_source_seal:
            raise PackageIntegrityError(
                "Copied technical source seal differs from authoring state."
            )

        panel_artifacts: dict[str, ArtifactEvidence] = {}
        report_artifacts: dict[str, ArtifactEvidence] = {}
        for panel_definition in self._plan.panels:
            candidate = self._active_candidate(state.panels[panel_definition.panel_id])
            panel_artifact = self._copy_workspace_artifact(
                candidate.normalized_panel,
                staging,
                panel_definition.package_path,
            )
            panel_data = (staging / panel_definition.package_path).read_bytes()
            self._validate_rgba_png(
                panel_data,
                expected_width=panel_definition.file_width,
                expected_height=panel_definition.file_height,
                label=f"Pixel panel {panel_definition.panel_id}",
            )
            panel_artifacts[panel_definition.panel_id] = panel_artifact
            report_relative = f"authoring/panel-validation-reports/{panel_definition.panel_id}.json"
            report_data = self._verified_artifact_data(candidate.validation_report)
            self._copy_bytes_to_package(staging, report_relative, report_data)
            report_artifacts[panel_definition.panel_id] = self._artifact(
                report_relative,
                report_data,
                1,
                1,
            )

        families, master = self._active_package_composites(state)
        family_artifacts: dict[str, ArtifactEvidence] = {}
        slot_map_paths: dict[str, str] = {}
        for family_definition, composite in zip(
            self._plan.families,
            families,
            strict=True,
        ):
            family_artifact = self._copy_workspace_artifact(
                composite.artifact,
                staging,
                family_definition.sheet_package_path,
            )
            family_data = (staging / family_definition.sheet_package_path).read_bytes()
            self._validate_rgba_png(
                family_data,
                expected_width=composite.artifact.width,
                expected_height=composite.artifact.height,
                label=f"Family sheet {family_definition.family_id}",
            )
            family_artifacts[family_definition.family_id] = family_artifact
            source_slot_map = self.resolve_artifact(
                str(Path(composite.artifact.path).parent / "slot-map.json").replace("\\", "/")
            )
            slot_relative = f"authoring/composite-slot-maps/{family_definition.family_id}.json"
            self._copy_bytes_to_package(
                staging,
                slot_relative,
                source_slot_map.read_bytes(),
            )
            slot_map_paths[composite.composite_id] = slot_relative

        master_artifact = self._copy_workspace_artifact(
            master.artifact,
            staging,
            PACKAGE_MASTER_PATH,
        )
        master_data = (staging / PACKAGE_MASTER_PATH).read_bytes()
        self._validate_rgba_png(
            master_data,
            expected_width=master.artifact.width,
            expected_height=master.artifact.height,
            label="Package master",
        )
        master_slot_source = self.resolve_artifact(
            str(Path(master.artifact.path).parent / "slot-map.json").replace("\\", "/")
        )
        master_slot_relative = "authoring/composite-slot-maps/package-master.json"
        self._copy_bytes_to_package(
            staging,
            master_slot_relative,
            master_slot_source.read_bytes(),
        )
        slot_map_paths[master.composite_id] = master_slot_relative
        return (
            panel_artifacts,
            report_artifacts,
            family_artifacts,
            master_artifact,
            slot_map_paths,
        )

    def _copy_workspace_artifact(
        self,
        source: ArtifactEvidence,
        staging: Path,
        destination_relative: str,
    ) -> ArtifactEvidence:
        data = self._verified_artifact_data(source)
        self._copy_bytes_to_package(staging, destination_relative, data)
        return self._artifact(
            destination_relative,
            data,
            source.width,
            source.height,
        )

    def _copy_bytes_to_package(
        self,
        staging: Path,
        destination_relative: str,
        data: bytes,
    ) -> None:
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

    def _package_provenance(
        self,
        state: PixelPortraitAuthoringState,
        *,
        panel_artifacts: dict[str, ArtifactEvidence],
        family_artifacts: dict[str, ArtifactEvidence],
        master_artifact: ArtifactEvidence,
    ) -> tuple[ProvenanceRecord, ...]:
        source_records = tuple(
            record
            for record in state.provenance
            if record.artifact.path.startswith("sources/base-set/")
            or record.artifact.path.startswith(f"{self.TECHNICAL_SOURCE_ROOT}/")
        )
        base_character_path = "sources/base-set/juana-avatar-character-sheet.png"
        base_rights_records = tuple(
            record
            for record in source_records
            if record.artifact.path == base_character_path
            and record.rights is not None
            and record.rights.is_complete
            and record.rights_basis_provenance_id is None
        )
        if len(base_rights_records) != 1:
            raise PackageSealError(
                "The base character sheet requires one complete direct rights record."
            )
        rights_basis = base_rights_records[0].provenance_id

        panel_records: list[ProvenanceRecord] = []
        for definition in self._plan.panels:
            candidate = self._active_candidate(state.panels[definition.panel_id])
            panel_records.append(
                ProvenanceRecord(
                    provenance_id=f"pixel-panel:{definition.panel_id}",
                    source_class=SourceClass.TECHNICAL_REFERENCE,
                    artifact=panel_artifacts[definition.panel_id],
                    authoritative_source=(
                        "Deterministic pixel normalization of one explicitly approved "
                        "panel candidate."
                    ),
                    rights_basis_provenance_id=rights_basis,
                    derived_from_sha256=(
                        *(artifact.sha256 for artifact in candidate.input_artifacts),
                        candidate.raw_artifact.sha256,
                    ),
                    provider=candidate.provider,
                    model=candidate.model,
                    prompt_id=candidate.prompt_id,
                    prompt_version=candidate.prompt_version,
                )
            )

        family_records = tuple(
            ProvenanceRecord(
                provenance_id=f"pixel-family:{family.family_id}",
                source_class=SourceClass.TECHNICAL_REFERENCE,
                artifact=family_artifacts[family.family_id],
                authoritative_source=(
                    "Deterministic approved family composition from fixed pixel panels."
                ),
                rights_basis_provenance_id=rights_basis,
                derived_from_sha256=tuple(
                    panel_artifacts[panel_id].sha256 for panel_id in family.panel_ids
                ),
            )
            for family in self._plan.families
        )
        master_record = ProvenanceRecord(
            provenance_id="pixel-package-master",
            source_class=SourceClass.CREATIVE_CANON,
            artifact=master_artifact,
            authoritative_source=(
                "Deterministic approved package-master composition from nine family sheets."
            ),
            rights_basis_provenance_id=rights_basis,
            derived_from_sha256=tuple(
                family_artifacts[family.family_id].sha256 for family in self._plan.families
            ),
        )
        return (
            *source_records,
            *panel_records,
            *family_records,
            master_record,
        )

    def _write_pixel_package_metadata(
        self,
        staging: Path,
        *,
        state: PixelPortraitAuthoringState,
        sealed_at: datetime,
        technical_directories: tuple[str, ...],
        panel_artifacts: dict[str, ArtifactEvidence],
        report_artifacts: dict[str, ArtifactEvidence],
        family_artifacts: dict[str, ArtifactEvidence],
        master_artifact: ArtifactEvidence,
        slot_map_paths: dict[str, str],
        provenance: tuple[ProvenanceRecord, ...],
    ) -> tuple[str, ...]:
        families, master = self._active_package_composites(state)
        identity_lock = state.identity_lock
        if identity_lock is None:
            raise PackageSealError("The approved neutral identity lock is missing.")
        panel_approvals: list[PixelPanelApproval] = []
        panel_entries: list[dict[str, object]] = []
        for definition in self._plan.panels:
            panel = state.panels[definition.panel_id]
            candidate = self._active_candidate(panel)
            approval = self._active_panel_approval(panel, candidate)
            panel_approvals.append(approval)
            panel_entries.append(
                {
                    "active_approval_id": approval.approval_id,
                    "active_candidate": candidate.model_dump(mode="json"),
                    "definition": definition.model_dump(mode="json"),
                    "package_artifact": panel_artifacts[definition.panel_id].model_dump(
                        mode="json"
                    ),
                    "validation_report_artifact": report_artifacts[definition.panel_id].model_dump(
                        mode="json"
                    ),
                }
            )

        family_approvals = tuple(
            self._active_composite_approval(state, composite) for composite in families
        )
        master_approval = self._active_composite_approval(state, master)
        active_approval_ids = (
            *(approval.approval_id for approval in panel_approvals),
            *(approval.approval_id for approval in family_approvals),
            master_approval.approval_id,
        )
        package_payload = {
            "approved_reference_sheets": [
                {
                    "family_id": family.family_id,
                    **family_artifacts[family.family_id].model_dump(mode="json"),
                }
                for family in self._plan.families
            ],
            "assembly_manifest": None,
            "asset_pack_manifest": None,
            "base_model_adapter": None,
            "base_sources": [
                source.model_dump(mode="json") for source in state.revision.base_sources
            ],
            "canonical_pose": "portrait-neutral",
            "character_id": state.revision.identity,
            "created_at": sealed_at.isoformat(),
            "display_name": state.revision.identity,
            "height_meters": None,
            "master_reference": master_artifact.model_dump(mode="json"),
            "package_id": state.revision.package_id,
            "profile": state.revision.profile,
            "required_expressions": [
                panel_id.removeprefix("expression-")
                for panel_id in self._plan.family("expressions").panel_ids
            ],
            "required_visemes": [
                panel_id.removeprefix("viseme-")
                for panel_id in self._plan.family("visemes").panel_ids
            ],
            "revision": state.revision.revision,
            "schema_version": state.revision.schema_version,
            "technical_source": {
                "directories": list(technical_directories),
                "root": self.TECHNICAL_SOURCE_ROOT,
                "seal": state.revision.technical_source_seal.model_dump(mode="json"),
            },
            "updated_at": sealed_at.isoformat(),
        }
        approvals_payload = {
            "active_family_approval_ids": [approval.approval_id for approval in family_approvals],
            "active_master_approval_id": master_approval.approval_id,
            "active_panel_approval_ids": [approval.approval_id for approval in panel_approvals],
            "composite_approvals": [
                approval.model_dump(mode="json") for approval in state.composite_approvals
            ],
            "panel_decisions": [
                decision.model_dump(mode="json")
                for definition in self._plan.panels
                for decision in state.panels[definition.panel_id].decisions
            ],
            "schema_version": "1.1",
        }
        pixel_style_payload = {
            "file_canvas": {"height": 512, "width": 512},
            "hair_orientation": identity_lock.hair_orientation.value,
            "logical_canvas": {"height": 256, "width": 256},
            "normalization": {
                "dither": "NONE",
                "downsample": "LANCZOS",
                "logical_pixel_scale": 2,
                "max_colors": 64,
                "method": "FASTOCTREE",
                "upscale": "NEAREST",
            },
            "palette": {
                "max_colors": identity_lock.palette_max_colors,
                "sha256": identity_lock.palette_sha256,
            },
            "profile": state.revision.profile,
            "schema_version": "1.1",
        }
        panel_definitions_payload = {
            "approval_history_sha256": hashlib.sha256(
                self._canonical_json(approvals_payload["panel_decisions"])
            ).hexdigest(),
            "panels": panel_entries,
            "plan_id": self._plan.plan_id,
            "plan_version": self._plan.version,
            "schema_version": "1.1",
        }
        anchor_profiles_payload = {
            "family_anchors": [
                {
                    "family_id": family.family_id,
                    "required_anchors": [
                        item.value for item in family.anchor_contract.required_anchors
                    ],
                }
                for family in self._plan.families
            ],
            "identity_lock": identity_lock.model_dump(mode="json"),
            "schema_version": "1.1",
        }
        composite_payload = {
            "active_composite_ids": list(state.active_composite_ids),
            "active_families": [
                {
                    "active_approval_id": approval.approval_id,
                    "definition": definition.model_dump(mode="json"),
                    "package_artifact": family_artifacts[definition.family_id].model_dump(
                        mode="json"
                    ),
                    "slot_map_path": slot_map_paths[composite.composite_id],
                    "source_composite": composite.model_dump(mode="json"),
                }
                for definition, composite, approval in zip(
                    self._plan.families,
                    families,
                    family_approvals,
                    strict=True,
                )
            ],
            "active_master": {
                "active_approval_id": master_approval.approval_id,
                "package_artifact": master_artifact.model_dump(mode="json"),
                "slot_map_path": slot_map_paths[master.composite_id],
                "source_composite": master.model_dump(mode="json"),
            },
            "approval_history_sha256": hashlib.sha256(
                self._canonical_json(approvals_payload["composite_approvals"])
            ).hexdigest(),
            "composition_version": _COMPOSITION_VERSION,
            "history": [composite.model_dump(mode="json") for composite in state.composites],
            "schema_version": "1.1",
        }
        metadata = {
            "package.json": package_payload,
            "provenance.json": {
                "records": [record.model_dump(mode="json") for record in provenance],
                "schema_version": "1.1",
            },
            "approvals.json": approvals_payload,
            "gaps.json": {
                "gaps": [gap.model_dump(mode="json") for gap in state.gaps],
                "schema_version": "1.1",
            },
            "authoring/pixel-style.json": pixel_style_payload,
            "authoring/panel-definitions.json": panel_definitions_payload,
            "authoring/anchor-profiles.json": anchor_profiles_payload,
            "authoring/composite-sheets.json": composite_payload,
        }
        for relative in _PIXEL_PACKAGE_METADATA_FILES:
            self._write_json_exclusive(staging / relative, metadata[relative])
        return active_approval_ids

    @staticmethod
    def _validate_rights_chain(records: tuple[ProvenanceRecord, ...]) -> None:
        by_id = {record.provenance_id: record for record in records}
        if len(by_id) != len(records):
            raise PackageSealError("Package provenance identifiers must be unique.")

        def complete(provenance_id: str, visiting: set[str]) -> bool:
            if provenance_id in visiting:
                return False
            record = by_id.get(provenance_id)
            if record is None:
                return False
            if record.rights is not None:
                return record.rights.is_complete
            if record.rights_basis_provenance_id is None:
                return False
            return complete(
                record.rights_basis_provenance_id,
                {*visiting, provenance_id},
            )

        incomplete = tuple(
            record.provenance_id for record in records if not complete(record.provenance_id, set())
        )
        if incomplete:
            raise PackageSealError(
                "Incomplete package provenance rights chain: " + ", ".join(incomplete)
            )

    def validate(self, state: PixelPortraitAuthoringState) -> None:
        """Verify source locks and every artifact recorded by the current state."""
        self._validate_root_ancestry()
        state = self._strict_authoring_state(state)
        try:
            plan_data = (self.root / self.PLAN_FILE).read_bytes()
            persisted_plan = PixelPortraitPlanDefinition.model_validate_json(plan_data)
        except (OSError, ValidationError) as exc:
            raise PackageIntegrityError(
                "Pixel portrait workspace plan is missing or invalid."
            ) from exc
        if persisted_plan != self._plan or plan_data != self._canonical_json(
            self._plan.model_dump(mode="json")
        ):
            raise PackageIntegrityError(
                "Pixel portrait workspace plan does not match the fixed plan."
            )
        if state.plan_id != self._plan.plan_id or state.plan_version != self._plan.version:
            raise PackageIntegrityError("Pixel portrait state does not match the workspace plan.")
        expected_base_paths = tuple(
            f"sources/base-set/{filename}" for filename in BASE_SOURCE_FILENAMES
        )
        if tuple(source.path for source in state.revision.base_sources) != (expected_base_paths):
            raise PackageIntegrityError(
                "Pixel portrait state does not contain the exact base-set source locks."
            )
        provenance_by_path = {record.artifact.path: record for record in state.provenance}
        base_sources_by_path = {source.path: source for source in state.revision.base_sources}
        for source in state.revision.base_sources:
            self._verified_artifact_data(source)
            provenance = provenance_by_path.get(source.path)
            if (
                provenance is None
                or provenance.source_class is not SourceClass.CREATIVE_CANON
                or provenance.rights != state.revision.base_source_rights
            ):
                raise PackageIntegrityError(
                    f"Base source provenance is missing or inconsistent: {source.path}"
                )

        technical_root = self.root / self.TECHNICAL_SOURCE_ROOT
        technical_seal = FilesystemAuthoringWorkspace.validate_sealed_package(technical_root)
        self._validate_declared_technical_files(technical_root, technical_seal)
        if technical_seal != state.revision.technical_source_seal:
            raise PackageIntegrityError(
                "Locked technical source seal differs from authoring state."
            )

        technical_provenance = tuple(
            record
            for record in state.provenance
            if record.artifact.path.startswith(f"{self.TECHNICAL_SOURCE_ROOT}/")
        )
        self._validate_required_technical_provenance(
            technical_provenance,
            locked=True,
        )
        technical_provenance_by_path = {
            record.artifact.path: record for record in technical_provenance
        }
        for panel_state in state.panels.values():
            for candidate in panel_state.candidates:
                for artifact in candidate.input_artifacts:
                    if artifact.path.startswith("sources/base-set/"):
                        locked_source = base_sources_by_path.get(artifact.path)
                        if locked_source is None or locked_source != artifact:
                            raise PackageIntegrityError(
                                "Pixel panel candidate base input evidence does not "
                                f"match its locked source: {artifact.path}"
                            )
                    elif artifact.path.startswith(f"{self.TECHNICAL_SOURCE_ROOT}/"):
                        provenance = technical_provenance_by_path.get(artifact.path)
                        if provenance is None or provenance.artifact != artifact:
                            raise PackageIntegrityError(
                                "Pixel panel candidate technical input has no matching "
                                f"state provenance: {artifact.path}"
                            )

        expected_technical_provenance = self._remap_technical_provenance(
            self._read_technical_provenance(technical_root, technical_seal)
        )
        if {record.provenance_id: record for record in technical_provenance} != {
            record.provenance_id: record for record in expected_technical_provenance
        }:
            raise PackageIntegrityError(
                "Imported technical source provenance is missing or inconsistent."
            )
        for record in technical_provenance:
            self._verified_artifact_data(record.artifact)

        checked = {
            *expected_base_paths,
            *(record.artifact.path for record in technical_provenance),
        }
        for panel_state in state.panels.values():
            for candidate in panel_state.candidates:
                for artifact in (
                    *candidate.input_artifacts,
                    candidate.raw_artifact,
                    candidate.normalized_panel,
                    candidate.validation_report,
                ):
                    if artifact.path not in checked:
                        self._verified_artifact_data(artifact)
                        checked.add(artifact.path)
        self._validate_composite_history(state)

    @classmethod
    def validate_sealed_package(cls, package_root: Path) -> SealEvidence:
        """Validate a schema-1.1 pixel package without its authoring workspace."""
        try:
            return cls._validate_sealed_package(Path(package_root))
        except PackageIntegrityError:
            raise
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise PackageIntegrityError(
                "Sealed pixel portrait package metadata is missing or invalid."
            ) from exc

    @classmethod
    def _validate_sealed_package(cls, package_root: Path) -> SealEvidence:
        cls._validate_safe_ancestry(package_root, "Sealed package")
        files, directories = cls._safe_tree_inventory(package_root)
        try:
            seal_data = (package_root / "seal.json").read_bytes()
            evidence = SealEvidence.model_validate_json(seal_data)
        except (OSError, ValidationError) as exc:
            raise PackageIntegrityError(
                "Sealed pixel package evidence is missing or invalid."
            ) from exc
        if seal_data != cls._canonical_json(evidence.model_dump(mode="json")):
            raise PackageIntegrityError("Sealed pixel package evidence is not canonical JSON.")
        if "seal.json" in evidence.file_hashes or tuple(evidence.file_hashes) != tuple(
            sorted(evidence.file_hashes)
        ):
            raise PackageIntegrityError("Sealed pixel package manifest is not canonical.")
        if files != {*evidence.file_hashes, "seal.json"}:
            raise PackageIntegrityError(
                "Sealed pixel package manifest does not match the exact file inventory."
            )
        for relative, expected in evidence.file_hashes.items():
            data = (package_root / relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise PackageIntegrityError(f"Sealed pixel package digest mismatch: {relative}")

        package = cls._read_canonical_json(
            package_root,
            "package.json",
            {
                "approved_reference_sheets",
                "assembly_manifest",
                "asset_pack_manifest",
                "base_model_adapter",
                "base_sources",
                "canonical_pose",
                "character_id",
                "created_at",
                "display_name",
                "height_meters",
                "master_reference",
                "package_id",
                "profile",
                "required_expressions",
                "required_visemes",
                "revision",
                "schema_version",
                "technical_source",
                "updated_at",
            },
        )
        if (
            package["schema_version"] != "1.1"
            or package["profile"] != "pixel-talking-portrait"
            or package["package_id"] != "juana-talking-bust-v2-pixel"
            or package["canonical_pose"] != "portrait-neutral"
            or package["height_meters"] is not None
            or package["character_id"] != package["display_name"]
            or package["created_at"] != package["updated_at"]
            or package["created_at"] != evidence.sealed_at.isoformat()
            or any(
                package[field] is not None
                for field in (
                    "asset_pack_manifest",
                    "assembly_manifest",
                    "base_model_adapter",
                )
            )
        ):
            raise PackageIntegrityError("Pixel package identity or canonical fields are invalid.")
        if evidence.package_id != package["package_id"] or evidence.revision != package["revision"]:
            raise PackageIntegrityError("Pixel package identity does not match seal evidence.")

        base_sources = cls._artifact_list(package["base_sources"], "base source")
        expected_base_paths = tuple(
            f"sources/base-set/{filename}" for filename in BASE_SOURCE_FILENAMES
        )
        if tuple(item.path for item in base_sources) != expected_base_paths:
            raise PackageIntegrityError("Pixel package base-source inventory is not canonical.")
        for artifact in base_sources:
            cls._validate_artifact_at(package_root, artifact, require_alpha=False)

        master_artifact = ArtifactEvidence.model_validate(package["master_reference"])
        if master_artifact.path != PACKAGE_MASTER_PATH:
            raise PackageIntegrityError("Pixel package master reference is not canonical.")
        cls._validate_artifact_at(package_root, master_artifact, require_alpha=True)

        approved_items = package["approved_reference_sheets"]
        if not isinstance(approved_items, list) or len(approved_items) != len(
            PIXEL_PORTRAIT_PLAN.families
        ):
            raise PackageIntegrityError("Pixel package requires nine approved family sheets.")
        family_artifacts: dict[str, ArtifactEvidence] = {}
        artifact_keys = set(ArtifactEvidence.model_fields)
        for family, item in zip(
            PIXEL_PORTRAIT_PLAN.families,
            approved_items,
            strict=True,
        ):
            if not isinstance(item, dict) or set(item) != {"family_id", *artifact_keys}:
                raise PackageIntegrityError("Approved family sheet metadata is invalid.")
            if item["family_id"] != family.family_id:
                raise PackageIntegrityError("Approved family sheet order is not canonical.")
            artifact = ArtifactEvidence.model_validate({key: item[key] for key in artifact_keys})
            if artifact.path != family.sheet_package_path:
                raise PackageIntegrityError("Approved family sheet path is not canonical.")
            cls._validate_artifact_at(package_root, artifact, require_alpha=True)
            family_artifacts[family.family_id] = artifact

        technical = package["technical_source"]
        if not isinstance(technical, dict) or set(technical) != {
            "directories",
            "root",
            "seal",
        }:
            raise PackageIntegrityError("Locked technical source metadata is invalid.")
        if technical["root"] != cls.TECHNICAL_SOURCE_ROOT:
            raise PackageIntegrityError("Locked technical source root is invalid.")
        technical_directories = technical["directories"]
        if (
            not isinstance(technical_directories, list)
            or any(not isinstance(item, str) for item in technical_directories)
            or technical_directories != sorted(set(technical_directories))
        ):
            raise PackageIntegrityError("Locked technical directory inventory is invalid.")
        technical_seal = SealEvidence.model_validate(technical["seal"])
        technical_root = package_root / cls.TECHNICAL_SOURCE_ROOT
        validated_technical_seal = FilesystemAuthoringWorkspace.validate_sealed_package(
            technical_root
        )
        cls._validate_declared_technical_files(technical_root, validated_technical_seal)
        if (
            technical_seal != validated_technical_seal
            or technical_seal.package_id != "juana-talking-bust-v1"
        ):
            raise PackageIntegrityError("Locked technical source seal is inconsistent.")
        actual_technical_directories, technical_files = cls._snapshot_source_tree(technical_root)
        if tuple(technical_directories) != actual_technical_directories:
            raise PackageIntegrityError("Locked technical directory inventory changed.")

        provenance = cls._validate_package_provenance(
            package_root,
            evidence,
            base_sources=base_sources,
            technical_seal=technical_seal,
            family_artifacts=family_artifacts,
            master_artifact=master_artifact,
        )
        (
            candidates,
            panel_artifacts,
            report_artifacts,
            panel_approval_ids,
        ) = cls._validate_published_panels(
            package_root,
            base_sources=base_sources,
            provenance=provenance,
        )
        (
            source_families,
            source_master,
            family_approval_ids,
            master_approval_id,
        ) = cls._validate_published_composites(
            package_root,
            candidates=candidates,
            panel_artifacts=panel_artifacts,
            family_artifacts=family_artifacts,
            master_artifact=master_artifact,
        )
        cls._validate_package_approvals(
            package_root,
            evidence,
            candidates=candidates,
            panel_approval_ids=panel_approval_ids,
            source_families=source_families,
            source_master=source_master,
            family_approval_ids=family_approval_ids,
            master_approval_id=master_approval_id,
        )
        identity_lock = cls._validate_authoring_profiles(
            package_root,
            candidates=candidates,
            panel_artifacts=panel_artifacts,
            report_artifacts=report_artifacts,
        )
        cls._validate_package_gaps(package_root, evidence)
        cls._validate_derived_provenance(
            provenance,
            candidates=candidates,
            panel_artifacts=panel_artifacts,
            family_artifacts=family_artifacts,
            master_artifact=master_artifact,
            source_families=source_families,
            source_master=source_master,
        )
        neutral_approval = cls._active_panel_approval_from_package(
            package_root,
            panel_approval_ids[0],
        )
        if neutral_approval.identity_lock != identity_lock:
            raise PackageIntegrityError(
                "Published identity lock does not match neutral approval evidence."
            )

        expected_files = {
            *_PIXEL_PACKAGE_METADATA_FILES,
            "seal.json",
            *(artifact.path for artifact in base_sources),
            *(f"{cls.TECHNICAL_SOURCE_ROOT}/{relative}" for relative in technical_files),
            *(artifact.path for artifact in panel_artifacts.values()),
            *(artifact.path for artifact in report_artifacts.values()),
            *(artifact.path for artifact in family_artifacts.values()),
            master_artifact.path,
            *(
                f"authoring/composite-slot-maps/{family.family_id}.json"
                for family in PIXEL_PORTRAIT_PLAN.families
            ),
            "authoring/composite-slot-maps/package-master.json",
        }
        if files != expected_files:
            raise PackageIntegrityError("Pixel package contains a noncanonical file inventory.")
        expected_directories = cls._expected_package_directories(
            expected_files,
            tuple(technical_directories),
        )
        if directories != expected_directories:
            missing = sorted(expected_directories - directories)
            extra = sorted(directories - expected_directories)
            raise PackageIntegrityError(
                "Pixel package contains a missing or noncanonical directory inventory; "
                f"missing={missing}, extra={extra}."
            )
        return evidence

    @classmethod
    def _safe_tree_inventory(cls, root: Path) -> tuple[set[str], set[str]]:
        if not root.is_dir():
            raise PackageIntegrityError("Sealed pixel package root is unavailable.")
        files: set[str] = set()
        directories: set[str] = set()
        pending = [root]
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        while pending:
            current = pending.pop()
            try:
                entries = tuple(os.scandir(current))
            except OSError as exc:
                raise PackageIntegrityError(
                    "Sealed pixel package tree could not be inspected."
                ) from exc
            for entry in entries:
                path = Path(entry.path)
                metadata = entry.stat(follow_symlinks=False)
                is_junction_method = getattr(path, "is_junction", None)
                is_junction = bool(is_junction_method is not None and is_junction_method())
                is_reparse = bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)
                if entry.is_symlink() or is_junction or is_reparse:
                    raise PackageIntegrityError(
                        "Sealed pixel package cannot contain links or reparse points."
                    )
                relative = path.relative_to(root).as_posix()
                if "runtime" in PurePosixPath(relative).parts:
                    raise PackageIntegrityError(
                        "Sealed pixel package cannot contain a runtime directory."
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    directories.add(relative)
                    pending.append(path)
                elif stat.S_ISREG(metadata.st_mode):
                    files.add(relative)
                else:
                    raise PackageIntegrityError(
                        "Sealed pixel package contains an unsupported filesystem entry."
                    )
        return files, directories

    @classmethod
    def _read_canonical_json(
        cls,
        root: Path,
        relative: str,
        expected_keys: set[str],
    ) -> dict[str, object]:
        try:
            data = (root / relative).read_bytes()
            payload = json.loads(data)
        except (OSError, json.JSONDecodeError) as exc:
            raise PackageIntegrityError(
                f"Required package metadata is missing or invalid: {relative}"
            ) from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != expected_keys
            or data != cls._canonical_json(payload)
        ):
            raise PackageIntegrityError(f"Required package metadata is noncanonical: {relative}")
        return payload

    @staticmethod
    def _artifact_list(payload: object, label: str) -> tuple[ArtifactEvidence, ...]:
        if not isinstance(payload, list):
            raise PackageIntegrityError(f"Pixel package {label} inventory is invalid.")
        try:
            artifacts = tuple(ArtifactEvidence.model_validate(item) for item in payload)
        except ValidationError as exc:
            raise PackageIntegrityError(f"Pixel package {label} inventory is invalid.") from exc
        if len({artifact.path for artifact in artifacts}) != len(artifacts):
            raise PackageIntegrityError(f"Pixel package {label} paths must be unique.")
        return artifacts

    @classmethod
    def _validate_package_provenance(
        cls,
        root: Path,
        evidence: SealEvidence,
        *,
        base_sources: tuple[ArtifactEvidence, ...],
        technical_seal: SealEvidence,
        family_artifacts: dict[str, ArtifactEvidence],
        master_artifact: ArtifactEvidence,
    ) -> tuple[ProvenanceRecord, ...]:
        payload = cls._read_canonical_json(
            root,
            "provenance.json",
            {"records", "schema_version"},
        )
        if payload["schema_version"] != "1.1":
            raise PackageIntegrityError("Pixel package provenance schema is invalid.")
        try:
            records = _PROVENANCE_RECORDS_ADAPTER.validate_python(payload["records"])
        except ValidationError as exc:
            raise PackageIntegrityError("Pixel package provenance is invalid.") from exc
        ids = tuple(record.provenance_id for record in records)
        if ids != evidence.provenance_ids or len(ids) != len(set(ids)):
            raise PackageIntegrityError("Pixel package provenance does not match seal evidence.")
        try:
            cls._validate_rights_chain(records)
        except PackageSealError as exc:
            raise PackageIntegrityError(str(exc)) from exc

        expected_base_ids = tuple(
            f"base-set-{Path(filename).stem}" for filename in BASE_SOURCE_FILENAMES
        )
        base_records = records[: len(base_sources)]
        if (
            tuple(record.provenance_id for record in base_records) != expected_base_ids
            or tuple(record.artifact for record in base_records) != base_sources
            or any(
                record.source_class is not SourceClass.CREATIVE_CANON
                or record.rights is None
                or not record.rights.is_complete
                or record.rights_basis_provenance_id is not None
                for record in base_records
            )
        ):
            raise PackageIntegrityError(
                "Base-set provenance must retain complete direct creative-canon rights."
            )

        technical_root = root / cls.TECHNICAL_SOURCE_ROOT
        technical_records = cls(root)._read_technical_provenance(
            technical_root,
            technical_seal,
        )
        expected_technical = cls._remap_technical_provenance(technical_records)
        technical_start = len(base_sources)
        technical_end = technical_start + len(expected_technical)
        if records[technical_start:technical_end] != expected_technical:
            raise PackageIntegrityError(
                "Imported technical provenance or rights-basis chain changed."
            )
        expected_derived_count = (
            len(PIXEL_PORTRAIT_PLAN.panels) + len(PIXEL_PORTRAIT_PLAN.families) + 1
        )
        if len(records) != technical_end + expected_derived_count:
            raise PackageIntegrityError("Pixel package derived provenance inventory is incomplete.")
        if records[-1].artifact != master_artifact or tuple(
            record.artifact
            for record in records[technical_end + len(PIXEL_PORTRAIT_PLAN.panels) : -1]
        ) != tuple(family_artifacts[family.family_id] for family in PIXEL_PORTRAIT_PLAN.families):
            raise PackageIntegrityError("Pixel package composite provenance is invalid.")
        return records

    @classmethod
    def _validate_published_panels(
        cls,
        root: Path,
        *,
        base_sources: tuple[ArtifactEvidence, ...],
        provenance: tuple[ProvenanceRecord, ...],
    ) -> tuple[
        dict[str, PixelPanelCandidate],
        dict[str, ArtifactEvidence],
        dict[str, ArtifactEvidence],
        tuple[str, ...],
    ]:
        payload = cls._read_canonical_json(
            root,
            "authoring/panel-definitions.json",
            {
                "approval_history_sha256",
                "panels",
                "plan_id",
                "plan_version",
                "schema_version",
            },
        )
        if (
            payload["schema_version"] != "1.1"
            or payload["plan_id"] != PIXEL_PORTRAIT_PLAN.plan_id
            or payload["plan_version"] != PIXEL_PORTRAIT_PLAN.version
            or not isinstance(payload["panels"], list)
            or len(payload["panels"]) != len(PIXEL_PORTRAIT_PLAN.panels)
        ):
            raise PackageIntegrityError("Published panel-definition inventory is invalid.")
        candidates: dict[str, PixelPanelCandidate] = {}
        panel_artifacts: dict[str, ArtifactEvidence] = {}
        report_artifacts: dict[str, ArtifactEvidence] = {}
        approval_ids: list[str] = []
        for expected, entry in zip(
            PIXEL_PORTRAIT_PLAN.panels,
            payload["panels"],
            strict=True,
        ):
            if not isinstance(entry, dict) or set(entry) != {
                "active_approval_id",
                "active_candidate",
                "definition",
                "package_artifact",
                "validation_report_artifact",
            }:
                raise PackageIntegrityError("Published panel metadata is malformed.")
            definition = type(expected).model_validate(entry["definition"])
            candidate = PixelPanelCandidate.model_validate(entry["active_candidate"])
            artifact = ArtifactEvidence.model_validate(entry["package_artifact"])
            report = ArtifactEvidence.model_validate(entry["validation_report_artifact"])
            approval_id = entry["active_approval_id"]
            if (
                definition != expected
                or candidate.panel_id != expected.panel_id
                or candidate.status.value != "approved"
                or candidate.prompt_id != expected.prompt_id
                or candidate.prompt_version != expected.prompt_version
                or artifact.path != expected.package_path
                or report.path != f"authoring/panel-validation-reports/{expected.panel_id}.json"
                or not isinstance(approval_id, str)
                or not approval_id
            ):
                raise PackageIntegrityError(
                    f"Published panel lineage is noncanonical: {expected.panel_id}"
                )
            if (
                artifact.sha256,
                artifact.byte_length,
                artifact.width,
                artifact.height,
            ) != (
                candidate.normalized_panel.sha256,
                candidate.normalized_panel.byte_length,
                candidate.normalized_panel.width,
                candidate.normalized_panel.height,
            ):
                raise PackageIntegrityError(
                    f"Published panel evidence changed: {expected.panel_id}"
                )
            cls._validate_artifact_at(root, artifact, require_alpha=True)
            cls._validate_artifact_at(root, report, require_alpha=False)
            candidates[expected.panel_id] = candidate
            panel_artifacts[expected.panel_id] = artifact
            report_artifacts[expected.panel_id] = report
            approval_ids.append(approval_id)
        if len(set(approval_ids)) != len(approval_ids):
            raise PackageIntegrityError("Active panel approval identifiers must be unique.")

        base_by_name = {Path(item.path).name: item for item in base_sources}
        technical_by_path = {
            record.artifact.path: record.artifact
            for record in provenance
            if record.artifact.path.startswith(f"{cls.TECHNICAL_SOURCE_ROOT}/")
        }
        neutral = candidates["presence-neutral"].normalized_panel
        for definition in PIXEL_PORTRAIT_PLAN.panels:
            candidate = candidates[definition.panel_id]
            if definition.panel_id == "presence-neutral":
                if definition.technical_source_path is None:
                    raise PackageIntegrityError("Neutral source definition is invalid.")
                expected_inputs = (
                    *(base_by_name[name] for name in BASE_SOURCE_FILENAMES),
                    technical_by_path[
                        f"{cls.TECHNICAL_SOURCE_ROOT}/{definition.technical_source_path}"
                    ],
                )
            elif definition.family_id == "presence-states":
                if definition.base_source_role is None:
                    raise PackageIntegrityError("Presence source definition is invalid.")
                expected_inputs = (
                    base_by_name["juana-avatar-character-sheet.png"],
                    base_by_name[f"juana-avatar-{definition.base_source_role}.png"],
                    neutral,
                )
            else:
                if definition.technical_source_path is None:
                    raise PackageIntegrityError("Technical source definition is invalid.")
                expected_inputs = (
                    base_by_name["juana-avatar-character-sheet.png"],
                    neutral,
                    technical_by_path[
                        f"{cls.TECHNICAL_SOURCE_ROOT}/{definition.technical_source_path}"
                    ],
                )
            if candidate.input_artifacts != expected_inputs:
                raise PackageIntegrityError(
                    f"Published panel source dependencies changed: {definition.panel_id}"
                )
        return (
            candidates,
            panel_artifacts,
            report_artifacts,
            tuple(approval_ids),
        )

    @classmethod
    def _validate_published_composites(
        cls,
        root: Path,
        *,
        candidates: dict[str, PixelPanelCandidate],
        panel_artifacts: dict[str, ArtifactEvidence],
        family_artifacts: dict[str, ArtifactEvidence],
        master_artifact: ArtifactEvidence,
    ) -> tuple[
        tuple[CompositeReviewSheet, ...],
        CompositeReviewSheet,
        tuple[str, ...],
        str,
    ]:
        payload = cls._read_canonical_json(
            root,
            "authoring/composite-sheets.json",
            {
                "active_composite_ids",
                "active_families",
                "active_master",
                "approval_history_sha256",
                "composition_version",
                "history",
                "schema_version",
            },
        )
        if (
            payload["schema_version"] != "1.1"
            or payload["composition_version"] != _COMPOSITION_VERSION
            or not isinstance(payload["history"], list)
        ):
            raise PackageIntegrityError("Published composite metadata is invalid.")
        history = tuple(CompositeReviewSheet.model_validate(item) for item in payload["history"])
        history_by_id = {item.composite_id: item for item in history}
        if len(history_by_id) != len(history):
            raise PackageIntegrityError("Published composite history has duplicate IDs.")
        family_entries = payload["active_families"]
        if not isinstance(family_entries, list) or len(family_entries) != len(
            PIXEL_PORTRAIT_PLAN.families
        ):
            raise PackageIntegrityError("Published family composite inventory is invalid.")

        source_families: list[CompositeReviewSheet] = []
        family_approval_ids: list[str] = []
        for definition, entry in zip(
            PIXEL_PORTRAIT_PLAN.families,
            family_entries,
            strict=True,
        ):
            if not isinstance(entry, dict) or set(entry) != {
                "active_approval_id",
                "definition",
                "package_artifact",
                "slot_map_path",
                "source_composite",
            }:
                raise PackageIntegrityError("Published family composite metadata is malformed.")
            published_definition = type(definition).model_validate(entry["definition"])
            source = CompositeReviewSheet.model_validate(entry["source_composite"])
            artifact = ArtifactEvidence.model_validate(entry["package_artifact"])
            approval_id = entry["active_approval_id"]
            slot_map_path = entry["slot_map_path"]
            if (
                published_definition != definition
                or source.scope is not CompositeScope.FAMILY
                or source.family_id != definition.family_id
                or source.status is not CompositeStatus.APPROVED
                or source.member_ids != definition.panel_ids
                or history_by_id.get(source.composite_id) != source
                or artifact != family_artifacts[definition.family_id]
                or slot_map_path != f"authoring/composite-slot-maps/{definition.family_id}.json"
                or not isinstance(approval_id, str)
                or not approval_id
            ):
                raise PackageIntegrityError(
                    f"Published family lineage is noncanonical: {definition.family_id}"
                )
            expected_member_artifacts = tuple(
                candidates[panel_id].normalized_panel for panel_id in definition.panel_ids
            )
            if (
                source.member_artifacts != expected_member_artifacts
                or source.member_hashes != tuple(item.sha256 for item in expected_member_artifacts)
            ):
                raise PackageIntegrityError(
                    f"Published family lineage changed: {definition.family_id}"
                )
            members = tuple(
                (
                    panel_id,
                    source.member_hashes[index],
                    source.member_artifacts[index],
                    (root / panel_artifacts[panel_id].path).read_bytes(),
                )
                for index, panel_id in enumerate(definition.panel_ids)
            )
            sheet_data, slots, width, height = cls._render_composite(
                members,
                rows=definition.rows,
                columns=definition.columns,
                cell_width=512,
                cell_height=512,
            )
            expected_artifact = cls._artifact(
                definition.sheet_package_path,
                sheet_data,
                width,
                height,
            )
            if artifact != expected_artifact or (root / artifact.path).read_bytes() != sheet_data:
                raise PackageIntegrityError(
                    f"Published family sheet is not deterministic: {definition.family_id}"
                )
            expected_slot_map = cls._slot_map(
                source,
                rows=definition.rows,
                columns=definition.columns,
                cell_width=512,
                cell_height=512,
                output_width=width,
                output_height=height,
                slots=slots,
            )
            if (root / str(slot_map_path)).read_bytes() != cls._canonical_json(expected_slot_map):
                raise PackageIntegrityError(
                    f"Published family slot map is inconsistent: {definition.family_id}"
                )
            source_families.append(source)
            family_approval_ids.append(approval_id)

        master_entry = payload["active_master"]
        if not isinstance(master_entry, dict) or set(master_entry) != {
            "active_approval_id",
            "package_artifact",
            "slot_map_path",
            "source_composite",
        }:
            raise PackageIntegrityError("Published package-master metadata is malformed.")
        source_master = CompositeReviewSheet.model_validate(master_entry["source_composite"])
        published_master = ArtifactEvidence.model_validate(master_entry["package_artifact"])
        master_approval_id = master_entry["active_approval_id"]
        if (
            source_master.scope is not CompositeScope.PACKAGE_MASTER
            or source_master.status is not CompositeStatus.APPROVED
            or history_by_id.get(source_master.composite_id) != source_master
            or source_master.member_ids != tuple(item.composite_id for item in source_families)
            or source_master.member_hashes
            != tuple(item.artifact.sha256 for item in source_families)
            or source_master.member_artifacts != tuple(item.artifact for item in source_families)
            or published_master != master_artifact
            or master_entry["slot_map_path"] != "authoring/composite-slot-maps/package-master.json"
            or not isinstance(master_approval_id, str)
            or not master_approval_id
        ):
            raise PackageIntegrityError("Published package-master lineage is invalid.")
        master_cell_width = max(item.artifact.width for item in source_families)
        master_cell_height = max(item.artifact.height for item in source_families)
        master_members = tuple(
            (
                source.composite_id,
                source.artifact.sha256,
                source.artifact,
                (root / family_artifacts[str(source.family_id)].path).read_bytes(),
            )
            for source in source_families
        )
        master_data, master_slots, master_width, master_height = cls._render_composite(
            master_members,
            rows=_PACKAGE_MASTER_ROWS,
            columns=_PACKAGE_MASTER_COLUMNS,
            cell_width=master_cell_width,
            cell_height=master_cell_height,
        )
        expected_master_artifact = cls._artifact(
            PACKAGE_MASTER_PATH,
            master_data,
            master_width,
            master_height,
        )
        if (
            master_artifact != expected_master_artifact
            or (root / master_artifact.path).read_bytes() != master_data
        ):
            raise PackageIntegrityError("Published package master is not deterministic.")
        expected_master_slot_map = cls._slot_map(
            source_master,
            rows=_PACKAGE_MASTER_ROWS,
            columns=_PACKAGE_MASTER_COLUMNS,
            cell_width=master_cell_width,
            cell_height=master_cell_height,
            output_width=master_width,
            output_height=master_height,
            slots=master_slots,
        )
        if (
            root / "authoring/composite-slot-maps/package-master.json"
        ).read_bytes() != cls._canonical_json(expected_master_slot_map):
            raise PackageIntegrityError("Published package-master slot map is inconsistent.")
        active_ids = payload["active_composite_ids"]
        expected_active_ids = [
            *(item.composite_id for item in source_families),
            source_master.composite_id,
        ]
        if active_ids != expected_active_ids:
            raise PackageIntegrityError("Published active composite IDs are noncanonical.")
        return (
            tuple(source_families),
            source_master,
            tuple(family_approval_ids),
            master_approval_id,
        )

    @classmethod
    def _validate_package_approvals(
        cls,
        root: Path,
        evidence: SealEvidence,
        *,
        candidates: dict[str, PixelPanelCandidate],
        panel_approval_ids: tuple[str, ...],
        source_families: tuple[CompositeReviewSheet, ...],
        source_master: CompositeReviewSheet,
        family_approval_ids: tuple[str, ...],
        master_approval_id: str,
    ) -> None:
        payload = cls._read_canonical_json(
            root,
            "approvals.json",
            {
                "active_family_approval_ids",
                "active_master_approval_id",
                "active_panel_approval_ids",
                "composite_approvals",
                "panel_decisions",
                "schema_version",
            },
        )
        if payload["schema_version"] != "1.1":
            raise PackageIntegrityError("Pixel package approval schema is invalid.")
        try:
            panel_decisions = _PANEL_APPROVALS_ADAPTER.validate_python(payload["panel_decisions"])
            composite_approvals = _COMPOSITE_APPROVALS_ADAPTER.validate_python(
                payload["composite_approvals"]
            )
        except ValidationError as exc:
            raise PackageIntegrityError("Pixel package approval history is invalid.") from exc
        if len({item.approval_id for item in panel_decisions}) != len(panel_decisions) or len(
            {item.approval_id for item in composite_approvals}
        ) != len(composite_approvals):
            raise PackageIntegrityError("Pixel package approval IDs must be unique.")
        panel_evidence = cls._read_canonical_json(
            root,
            "authoring/panel-definitions.json",
            {
                "approval_history_sha256",
                "panels",
                "plan_id",
                "plan_version",
                "schema_version",
            },
        )
        composite_evidence = cls._read_canonical_json(
            root,
            "authoring/composite-sheets.json",
            {
                "active_composite_ids",
                "active_families",
                "active_master",
                "approval_history_sha256",
                "composition_version",
                "history",
                "schema_version",
            },
        )
        expected_panel_history = hashlib.sha256(
            cls._canonical_json(payload["panel_decisions"])
        ).hexdigest()
        expected_composite_history = hashlib.sha256(
            cls._canonical_json(payload["composite_approvals"])
        ).hexdigest()
        if (
            panel_evidence["approval_history_sha256"] != expected_panel_history
            or composite_evidence["approval_history_sha256"] != expected_composite_history
        ):
            raise PackageIntegrityError(
                "Pixel package approval history differs from independent authoring evidence."
            )
        if payload["active_panel_approval_ids"] != list(panel_approval_ids):
            raise PackageIntegrityError("Active panel approval IDs are noncanonical.")
        if payload["active_family_approval_ids"] != list(family_approval_ids):
            raise PackageIntegrityError("Active family approval IDs are noncanonical.")
        if payload["active_master_approval_id"] != master_approval_id:
            raise PackageIntegrityError("Active master approval ID is noncanonical.")

        panel_by_id = {item.approval_id: item for item in panel_decisions}
        for definition, approval_id in zip(
            PIXEL_PORTRAIT_PLAN.panels,
            panel_approval_ids,
            strict=True,
        ):
            candidate = candidates[definition.panel_id]
            panel_approval = panel_by_id.get(approval_id)
            expected_scope = {
                candidate.raw_artifact.path,
                candidate.normalized_panel.path,
                candidate.validation_report.path,
            }
            if (
                panel_approval is None
                or panel_approval.panel_id != definition.panel_id
                or panel_approval.candidate_id != candidate.candidate_id
                or panel_approval.decision is not ApprovalDecision.APPROVE
                or set(panel_approval.reviewed_artifacts) != expected_scope
            ):
                raise PackageIntegrityError(
                    f"Active panel approval is invalid: {definition.panel_id}"
                )

        composite_by_id = {item.approval_id: item for item in composite_approvals}
        for source, approval_id in zip(
            source_families,
            family_approval_ids,
            strict=True,
        ):
            composite_approval = composite_by_id.get(approval_id)
            if (
                composite_approval is None
                or composite_approval.composite_id != source.composite_id
                or tuple(composite_approval.reviewed_artifacts) != (source.artifact.path,)
            ):
                raise PackageIntegrityError(
                    f"Active family approval is invalid: {source.family_id}"
                )
        master_approval = composite_by_id.get(master_approval_id)
        if (
            master_approval is None
            or master_approval.composite_id != source_master.composite_id
            or tuple(master_approval.reviewed_artifacts) != (source_master.artifact.path,)
        ):
            raise PackageIntegrityError("Active package-master approval is invalid.")
        expected_seal_approvals = (
            *panel_approval_ids,
            *family_approval_ids,
            master_approval_id,
        )
        if evidence.approval_ids != expected_seal_approvals:
            raise PackageIntegrityError(
                "Pixel package active approvals do not match seal evidence."
            )

    @classmethod
    def _active_panel_approval_from_package(
        cls,
        root: Path,
        approval_id: str,
    ) -> PixelPanelApproval:
        payload = cls._read_canonical_json(
            root,
            "approvals.json",
            {
                "active_family_approval_ids",
                "active_master_approval_id",
                "active_panel_approval_ids",
                "composite_approvals",
                "panel_decisions",
                "schema_version",
            },
        )
        decisions = _PANEL_APPROVALS_ADAPTER.validate_python(payload["panel_decisions"])
        matches = tuple(decision for decision in decisions if decision.approval_id == approval_id)
        if len(matches) != 1:
            raise PackageIntegrityError("Active panel approval is missing or duplicated.")
        return matches[0]

    @classmethod
    def _validate_authoring_profiles(
        cls,
        root: Path,
        *,
        candidates: dict[str, PixelPanelCandidate],
        panel_artifacts: dict[str, ArtifactEvidence],
        report_artifacts: dict[str, ArtifactEvidence],
    ) -> PortraitIdentityLock:
        anchors = cls._read_canonical_json(
            root,
            "authoring/anchor-profiles.json",
            {"family_anchors", "identity_lock", "schema_version"},
        )
        if anchors["schema_version"] != "1.1":
            raise PackageIntegrityError("Pixel anchor-profile schema is invalid.")
        identity_lock = PortraitIdentityLock.model_validate(anchors["identity_lock"])
        expected_family_anchors = [
            {
                "family_id": family.family_id,
                "required_anchors": [
                    item.value for item in family.anchor_contract.required_anchors
                ],
            }
            for family in PIXEL_PORTRAIT_PLAN.families
        ]
        if anchors["family_anchors"] != expected_family_anchors:
            raise PackageIntegrityError("Pixel family anchor profiles are noncanonical.")

        style = cls._read_canonical_json(
            root,
            "authoring/pixel-style.json",
            {
                "file_canvas",
                "hair_orientation",
                "logical_canvas",
                "normalization",
                "palette",
                "profile",
                "schema_version",
            },
        )
        expected_style = {
            "file_canvas": {"height": 512, "width": 512},
            "hair_orientation": identity_lock.hair_orientation.value,
            "logical_canvas": {"height": 256, "width": 256},
            "normalization": {
                "dither": "NONE",
                "downsample": "LANCZOS",
                "logical_pixel_scale": 2,
                "max_colors": 64,
                "method": "FASTOCTREE",
                "upscale": "NEAREST",
            },
            "palette": {
                "max_colors": identity_lock.palette_max_colors,
                "sha256": identity_lock.palette_sha256,
            },
            "profile": "pixel-talking-portrait",
            "schema_version": "1.1",
        }
        if style != expected_style:
            raise PackageIntegrityError("Pixel style metadata is noncanonical.")

        for definition in PIXEL_PORTRAIT_PLAN.panels:
            candidate = candidates[definition.panel_id]
            artifact = panel_artifacts[definition.panel_id]
            report_artifact = report_artifacts[definition.panel_id]
            report = cls._read_canonical_json(
                root,
                report_artifact.path,
                {
                    "attempt",
                    "normalized_sha256",
                    "normalization",
                    "palette",
                    "palette_sha256",
                    "panel_id",
                    "raw_sha256",
                    "schema_version",
                    "valid",
                },
            )
            palette = report["palette"]
            if (
                report["schema_version"] != "1.0"
                or report["valid"] is not True
                or report["panel_id"] != definition.panel_id
                or report["attempt"] != candidate.attempt
                or report["raw_sha256"] != candidate.raw_artifact.sha256
                or report["normalized_sha256"] != artifact.sha256
                or not isinstance(palette, list)
                or not 1 <= len(palette) <= 64
                or any(
                    not isinstance(color, list)
                    or len(color) != 4
                    or any(
                        isinstance(channel, bool)
                        or not isinstance(channel, int)
                        or not 0 <= channel <= 255
                        for channel in color
                    )
                    for color in palette
                )
            ):
                raise PackageIntegrityError(
                    f"Panel validation report is invalid: {definition.panel_id}"
                )
            palette_sha256 = hashlib.sha256(
                json.dumps(palette, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            expected_normalization = {
                "actual_colors": len(palette),
                "dither": "NONE",
                "downsample": "LANCZOS",
                "file_size": [512, 512],
                "logical_pixel_scale": 2,
                "logical_size": [256, 256],
                "max_colors": 64,
                "method": "FASTOCTREE",
                "upscale": "NEAREST",
            }
            if (
                report["palette_sha256"] != palette_sha256
                or report["normalization"] != expected_normalization
            ):
                raise PackageIntegrityError(
                    f"Panel validation report does not match pixel style: {definition.panel_id}"
                )
        neutral_report = cls._read_canonical_json(
            root,
            report_artifacts["presence-neutral"].path,
            {
                "attempt",
                "normalized_sha256",
                "normalization",
                "palette",
                "palette_sha256",
                "panel_id",
                "raw_sha256",
                "schema_version",
                "valid",
            },
        )
        if neutral_report["palette_sha256"] != identity_lock.palette_sha256:
            raise PackageIntegrityError(
                "Neutral validation palette does not match the identity lock."
            )
        return identity_lock

    @classmethod
    def _validate_package_gaps(
        cls,
        root: Path,
        evidence: SealEvidence,
    ) -> None:
        payload = cls._read_canonical_json(
            root,
            "gaps.json",
            {"gaps", "schema_version"},
        )
        if payload["schema_version"] != "1.1":
            raise PackageIntegrityError("Pixel package gap schema is invalid.")
        try:
            gaps = _GAP_RECORDS_ADAPTER.validate_python(payload["gaps"])
        except ValidationError as exc:
            raise PackageIntegrityError("Pixel package gaps are invalid.") from exc
        if (
            any(gap.blocks_visual_seal for gap in gaps)
            or len({gap.gap_id for gap in gaps}) != len(gaps)
            or tuple(gap.gap_id for gap in gaps) != evidence.unresolved_gap_ids
        ):
            raise PackageIntegrityError(
                "Pixel package gaps are blocking, duplicated, or inconsistent."
            )

    @classmethod
    def _validate_derived_provenance(
        cls,
        provenance: tuple[ProvenanceRecord, ...],
        *,
        candidates: dict[str, PixelPanelCandidate],
        panel_artifacts: dict[str, ArtifactEvidence],
        family_artifacts: dict[str, ArtifactEvidence],
        master_artifact: ArtifactEvidence,
        source_families: tuple[CompositeReviewSheet, ...],
        source_master: CompositeReviewSheet,
    ) -> None:
        base_rights_id = "base-set-juana-avatar-character-sheet"
        by_id = {record.provenance_id: record for record in provenance}
        expected_panels = tuple(
            ProvenanceRecord(
                provenance_id=f"pixel-panel:{definition.panel_id}",
                source_class=SourceClass.TECHNICAL_REFERENCE,
                artifact=panel_artifacts[definition.panel_id],
                authoritative_source=(
                    "Deterministic pixel normalization of one explicitly approved panel candidate."
                ),
                rights_basis_provenance_id=base_rights_id,
                derived_from_sha256=(
                    *(
                        artifact.sha256
                        for artifact in candidates[definition.panel_id].input_artifacts
                    ),
                    candidates[definition.panel_id].raw_artifact.sha256,
                ),
                provider=candidates[definition.panel_id].provider,
                model=candidates[definition.panel_id].model,
                prompt_id=candidates[definition.panel_id].prompt_id,
                prompt_version=candidates[definition.panel_id].prompt_version,
            )
            for definition in PIXEL_PORTRAIT_PLAN.panels
        )
        expected_families = tuple(
            ProvenanceRecord(
                provenance_id=f"pixel-family:{family.family_id}",
                source_class=SourceClass.TECHNICAL_REFERENCE,
                artifact=family_artifacts[family.family_id],
                authoritative_source=(
                    "Deterministic approved family composition from fixed pixel panels."
                ),
                rights_basis_provenance_id=base_rights_id,
                derived_from_sha256=tuple(
                    panel_artifacts[panel_id].sha256 for panel_id in family.panel_ids
                ),
            )
            for family in PIXEL_PORTRAIT_PLAN.families
        )
        expected_master = ProvenanceRecord(
            provenance_id="pixel-package-master",
            source_class=SourceClass.CREATIVE_CANON,
            artifact=master_artifact,
            authoritative_source=(
                "Deterministic approved package-master composition from nine family sheets."
            ),
            rights_basis_provenance_id=base_rights_id,
            derived_from_sha256=tuple(
                family_artifacts[family.family_id].sha256 for family in PIXEL_PORTRAIT_PLAN.families
            ),
        )
        expected = (*expected_panels, *expected_families, expected_master)
        if tuple(by_id.get(item.provenance_id) for item in expected) != expected:
            raise PackageIntegrityError("Pixel package derived provenance changed.")
        if tuple(item.member_hashes for item in source_families) != tuple(
            tuple(panel_artifacts[panel_id].sha256 for panel_id in family.panel_ids)
            for family in PIXEL_PORTRAIT_PLAN.families
        ) or source_master.member_hashes != tuple(
            family_artifacts[family.family_id].sha256 for family in PIXEL_PORTRAIT_PLAN.families
        ):
            raise PackageIntegrityError("Pixel package composite provenance dependencies changed.")

    @classmethod
    def _validate_artifact_at(
        cls,
        root: Path,
        artifact: ArtifactEvidence,
        *,
        require_alpha: bool,
    ) -> bytes:
        path = root / artifact.path
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PackageIntegrityError(
                f"Published artifact is unavailable: {artifact.path}"
            ) from exc
        if len(data) != artifact.byte_length or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise PackageIntegrityError(f"Published artifact evidence changed: {artifact.path}")
        if artifact.path.endswith(".png"):
            cls._validate_png(
                data,
                expected_width=artifact.width,
                expected_height=artifact.height,
                require_alpha=require_alpha,
                label=f"Published artifact {artifact.path}",
            )
        return data

    @classmethod
    def _validate_rgba_png(
        cls,
        data: bytes,
        *,
        expected_width: int,
        expected_height: int,
        label: str,
    ) -> None:
        cls._validate_png(
            data,
            expected_width=expected_width,
            expected_height=expected_height,
            require_alpha=True,
            label=label,
        )

    @staticmethod
    def _validate_png(
        data: bytes,
        *,
        expected_width: int,
        expected_height: int,
        require_alpha: bool,
        label: str,
    ) -> None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG":
                    raise PackageIntegrityError(f"{label} must be a PNG image.")
                image.load()
                if image.size != (expected_width, expected_height):
                    raise PackageIntegrityError(f"{label} dimensions are inconsistent.")
                if require_alpha:
                    if "A" not in image.getbands():
                        raise PackageIntegrityError(f"{label} must contain an alpha channel.")
                    alpha = image.getchannel("A")
                    try:
                        if alpha.getextrema()[1] == 0:
                            raise PackageIntegrityError(f"{label} cannot be fully transparent.")
                    finally:
                        alpha.close()
        except PackageIntegrityError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PackageIntegrityError(f"{label} must be a valid PNG image.") from exc

    @staticmethod
    def _package_file_hashes(staging: Path) -> dict[str, str]:
        files = sorted(
            (
                path
                for path in staging.rglob("*")
                if path.is_file() and path.relative_to(staging).as_posix() != "seal.json"
            ),
            key=lambda path: path.relative_to(staging).as_posix(),
        )
        return {
            path.relative_to(staging).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        }

    @staticmethod
    def _validate_safe_ancestry(path: Path, label: str) -> None:
        lexical = Path(os.path.abspath(path))
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        for item in (lexical, *lexical.parents):
            if not os.path.lexists(item):
                continue
            try:
                metadata = item.lstat()
                is_junction_method = getattr(item, "is_junction", None)
                is_junction = bool(is_junction_method is not None and is_junction_method())
            except OSError as exc:
                raise WorkspacePathError(f"{label} ancestry could not be verified.") from exc
            is_reparse = bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)
            if stat.S_ISLNK(metadata.st_mode) or is_junction or is_reparse:
                raise WorkspacePathError(
                    f"{label} ancestry cannot contain symlinks, junctions, or reparse points."
                )

    def _validate_package_destination(self, destination: Path) -> None:
        if destination.exists() or os.path.lexists(destination):
            raise PackageDestinationExistsError(
                f"CharacterDesignPackage destination already exists: {destination}"
            )
        self._validate_safe_ancestry(destination.parent, "Package destination")
        root = self.root.resolve()
        destination_resolved = destination.resolve(strict=False)
        if destination_resolved == root or destination_resolved.is_relative_to(root):
            raise WorkspacePathError(
                "CharacterDesignPackage destination cannot be inside the authoring workspace."
            )

    @staticmethod
    def _cleanup_staging(staging: Path, expected_parent: Path) -> None:
        if not os.path.lexists(staging):
            return
        lexical = Path(os.path.abspath(staging))
        if lexical.parent != expected_parent or not lexical.name.startswith(
            f".{staging.name.split('.seal-', 1)[0].lstrip('.')}.seal-"
        ):
            return
        try:
            metadata = lexical.lstat()
            is_junction_method = getattr(lexical, "is_junction", None)
            is_junction = bool(is_junction_method is not None and is_junction_method())
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
            is_reparse = bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or is_junction
                or is_reparse
            ):
                return
            shutil.rmtree(lexical)
        except OSError:
            return

    @staticmethod
    def _expected_package_directories(
        expected_files: set[str],
        technical_directories: tuple[str, ...],
    ) -> set[str]:
        directories = {
            *_CANONICAL_PACKAGE_DIRECTORIES,
            *_ADDITIVE_PACKAGE_DIRECTORIES,
            *(
                f"{FilesystemPixelPortraitWorkspace.TECHNICAL_SOURCE_ROOT}/{item}"
                for item in technical_directories
            ),
        }
        for relative in tuple(directories):
            parts = PurePosixPath(relative).parts
            for index in range(1, len(parts)):
                directories.add(PurePosixPath(*parts[:index]).as_posix())
        for relative in expected_files:
            parts = PurePosixPath(relative).parts[:-1]
            for index in range(1, len(parts) + 1):
                directories.add(PurePosixPath(*parts[:index]).as_posix())
        return directories

    def _validate_composite_history(
        self,
        state: PixelPortraitAuthoringState,
    ) -> None:
        versions: dict[tuple[CompositeScope, str | None], int] = {}
        composites = {composite.composite_id: composite for composite in state.composites}
        for composite in state.composites:
            key = (composite.scope, composite.family_id)
            version = versions.get(key, 0) + 1
            versions[key] = version
            if composite.composition_version != _COMPOSITION_VERSION:
                raise PackageIntegrityError(
                    "Historical composite composition version is not supported."
                )
            if composite.scope is CompositeScope.FAMILY:
                if composite.family_id is None:
                    raise PackageIntegrityError(
                        "Historical family composite is missing its family identifier."
                    )
                composite_id = f"family-{composite.family_id}-v{version}"
                relative_root = f"composites/family/{composite_id}"
                try:
                    family = self._plan.family(composite.family_id)
                except KeyError as exc:
                    raise PackageIntegrityError(
                        "Historical composite family is not part of the fixed plan."
                    ) from exc
                rows = family.rows
                columns = family.columns
                cell_width = 512
                cell_height = 512
            else:
                composite_id = f"package-master-v{version}"
                relative_root = f"composites/package-master/{composite_id}"
                rows = _PACKAGE_MASTER_ROWS
                columns = _PACKAGE_MASTER_COLUMNS
                cell_width = 0
                cell_height = 0
            if (
                composite.composite_id != composite_id
                or composite.artifact.path != f"{relative_root}/sheet.png"
            ):
                raise PackageIntegrityError(
                    "Historical composite identity or path is not deterministic."
                )
            members = self._historical_composite_members(
                state,
                composites,
                composite,
            )
            if composite.scope is CompositeScope.PACKAGE_MASTER:
                cell_width = max(member[2].width for member in members)
                cell_height = max(member[2].height for member in members)
            sheet_data, slots, output_width, output_height = self._render_composite(
                members,
                rows=rows,
                columns=columns,
                cell_width=cell_width,
                cell_height=cell_height,
            )
            expected_artifact = self._artifact(
                composite.artifact.path,
                sheet_data,
                output_width,
                output_height,
            )
            try:
                actual_sheet = self._verified_artifact_data(composite.artifact)
            except PackageIntegrityError as exc:
                raise PackageIntegrityError(
                    f"Historical composite sheet is invalid: {composite.artifact.path}"
                ) from exc
            if actual_sheet != sheet_data or composite.artifact != expected_artifact:
                raise PackageIntegrityError(
                    f"Historical composite sheet is not deterministic: {composite.artifact.path}"
                )
            expected_slot_map = self._slot_map(
                composite,
                rows=rows,
                columns=columns,
                cell_width=cell_width,
                cell_height=cell_height,
                output_width=output_width,
                output_height=output_height,
                slots=slots,
            )
            slot_map_path = self.resolve_artifact(f"{relative_root}/slot-map.json")
            try:
                slot_map_data = slot_map_path.read_bytes()
            except OSError as exc:
                raise PackageIntegrityError(
                    f"Historical composite slot map is unavailable: {relative_root}"
                ) from exc
            if slot_map_data != self._canonical_json(expected_slot_map):
                raise PackageIntegrityError(
                    f"Historical composite slot map is not deterministic: {relative_root}"
                )

    def _historical_composite_members(
        self,
        state: PixelPortraitAuthoringState,
        composites: dict[str, CompositeReviewSheet],
        composite: CompositeReviewSheet,
    ) -> tuple[tuple[str, str, ArtifactEvidence, bytes], ...]:
        if composite.scope is CompositeScope.FAMILY:
            if composite.family_id is None:
                raise PackageIntegrityError(
                    "Historical family composite is missing its family identifier."
                )
            try:
                family = self._plan.family(composite.family_id)
            except KeyError as exc:
                raise PackageIntegrityError(
                    "Historical composite family is not part of the fixed plan."
                ) from exc
            if composite.member_ids != family.panel_ids:
                raise PackageIntegrityError(
                    "Historical family composite members do not match the fixed plan."
                )
            if not composite.member_artifacts:
                raise PackageIntegrityError(
                    "Historical family composite member artifact evidence is unavailable."
                )
            result: list[tuple[str, str, ArtifactEvidence, bytes]] = []
            for panel_id, member_hash, artifact in zip(
                composite.member_ids,
                composite.member_hashes,
                composite.member_artifacts,
                strict=True,
            ):
                if artifact not in tuple(
                    candidate.normalized_panel for candidate in state.panels[panel_id].candidates
                ):
                    raise PackageIntegrityError(
                        "Historical family composite member evidence is unavailable."
                    )
                result.append(
                    (
                        panel_id,
                        member_hash,
                        artifact,
                        self._verified_artifact_data(artifact),
                    )
                )
            return tuple(result)

        referenced = tuple(composites[member_id] for member_id in composite.member_ids)
        expected_family_ids = tuple(family.family_id for family in self._plan.families)
        if tuple(member.family_id for member in referenced) != expected_family_ids or any(
            member.scope is not CompositeScope.FAMILY for member in referenced
        ):
            raise PackageIntegrityError(
                "Historical package master members do not match fixed family order."
            )
        if composite.member_artifacts != tuple(member.artifact for member in referenced):
            raise PackageIntegrityError(
                "Historical package master member artifact evidence is inconsistent."
            )
        result = []
        for member, member_hash, artifact in zip(
            referenced,
            composite.member_hashes,
            composite.member_artifacts,
            strict=True,
        ):
            if artifact.sha256 != member_hash:
                raise PackageIntegrityError(
                    "Historical package master member hash is inconsistent."
                )
            result.append(
                (
                    member.composite_id,
                    member_hash,
                    artifact,
                    self._verified_artifact_data(artifact),
                )
            )
        return tuple(result)

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Reuse the process-owned, operating-system workspace file lock."""
        self._validate_root_ancestry()
        with FilesystemAuthoringWorkspace(self.root).exclusive():
            self._exclusive_owner = get_ident()
            try:
                yield
            finally:
                self._exclusive_owner = None

    @contextmanager
    def _write_guard(self) -> Iterator[None]:
        if self._exclusive_owner == get_ident():
            yield
            return
        with self.exclusive():
            yield

    @classmethod
    def _normalize_pixel_panel(
        cls,
        image: Image.Image,
        panel: PixelPanelDefinition,
    ) -> tuple[bytes, tuple[tuple[int, int, int, int], ...]]:
        logical = image.resize(
            (panel.logical_width, panel.logical_height),
            Image.Resampling.LANCZOS,
        )
        try:
            quantized = logical.quantize(
                colors=64,
                method=Image.Quantize.FASTOCTREE,
                dither=Image.Dither.NONE,
            )
        finally:
            logical.close()
        try:
            logical_rgba = quantized.convert("RGBA")
        finally:
            quantized.close()
        try:
            colors = logical_rgba.getcolors(maxcolors=65)
            if colors is None or len(colors) > 64:
                raise CandidateValidationError(
                    "Pixel panel quantization exceeded the 64-color palette."
                )
            palette = tuple(sorted(cast(tuple[int, int, int, int], color) for _, color in colors))
            output = logical_rgba.resize(
                (panel.file_width, panel.file_height),
                Image.Resampling.NEAREST,
            )
        finally:
            logical_rgba.close()
        try:
            buffer = io.BytesIO()
            output.save(
                buffer,
                format="PNG",
                optimize=False,
                compress_level=9,
            )
            return buffer.getvalue(), palette
        finally:
            output.close()

    def _verified_artifact_data(self, artifact: ArtifactEvidence) -> bytes:
        path = self.resolve_artifact(artifact.path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PackageIntegrityError(f"Artifact is unavailable: {artifact.path}") from exc
        if len(data) != artifact.byte_length:
            raise PackageIntegrityError(f"Artifact byte length changed: {artifact.path}")
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise PackageIntegrityError(f"Artifact digest changed: {artifact.path}")
        if artifact.path.endswith(".png"):
            try:
                image = self._load_png(data)
            except CandidateValidationError as exc:
                raise PackageIntegrityError(
                    f"Artifact is no longer a valid PNG: {artifact.path}"
                ) from exc
            try:
                if image.size != (artifact.width, artifact.height):
                    raise PackageIntegrityError(f"Artifact dimensions changed: {artifact.path}")
            finally:
                image.close()
        return data

    @classmethod
    def _read_base_sources(
        cls,
        source_paths: tuple[Path, ...],
    ) -> dict[str, tuple[Path, bytes, int, int]]:
        sources_by_name = {path.name: Path(path) for path in source_paths}
        result: dict[str, tuple[Path, bytes, int, int]] = {}
        for filename in BASE_SOURCE_FILENAMES:
            path = sources_by_name[filename]
            cls._reject_source_symlink(path, "Base source image")
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise WorkspaceError(f"Base source image is unavailable: {filename}") from exc
            image = cls._load_png(data)
            try:
                width, height = image.size
            finally:
                image.close()
            result[filename] = (path, data, width, height)
        return result

    def _read_technical_provenance(
        self,
        root: Path,
        seal: SealEvidence,
    ) -> tuple[ProvenanceRecord, ...]:
        try:
            payload = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PackageIntegrityError(
                "Sealed technical source provenance is missing or invalid."
            ) from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "records"}
            or payload.get("schema_version") != "1.0"
        ):
            raise PackageIntegrityError("Sealed technical source provenance is missing or invalid.")
        try:
            records = _PROVENANCE_RECORDS_ADAPTER.validate_python(payload["records"])
        except ValidationError as exc:
            raise PackageIntegrityError(
                "Sealed technical source provenance is missing or invalid."
            ) from exc
        if not records:
            raise PackageIntegrityError(
                "Sealed technical source provenance must contain artifact records."
            )
        provenance_ids = tuple(record.provenance_id for record in records)
        if len(set(provenance_ids)) != len(provenance_ids):
            raise PackageIntegrityError(
                "Sealed technical source provenance identifiers must be unique."
            )
        if provenance_ids != seal.provenance_ids:
            raise PackageIntegrityError(
                "Sealed technical source provenance does not match seal evidence."
            )
        artifact_paths = tuple(record.artifact.path for record in records)
        if len(set(artifact_paths)) != len(artifact_paths):
            raise PackageIntegrityError(
                "Sealed technical source provenance artifact paths must be unique."
            )
        known_ids = set(provenance_ids)
        if any(
            record.rights_basis_provenance_id not in known_ids
            for record in records
            if record.rights_basis_provenance_id is not None
        ):
            raise PackageIntegrityError(
                "Sealed technical source provenance has a missing rights basis."
            )
        for record in records:
            if not record.artifact.path.endswith(".png"):
                raise PackageIntegrityError(
                    "Sealed technical provenance records must describe raster PNG artifacts."
                )
            if record.artifact.path not in seal.file_hashes:
                raise PackageIntegrityError(
                    "Sealed technical provenance artifact is absent from seal evidence: "
                    f"{record.artifact.path}"
                )
            self._verified_artifact_data_at(root, record.artifact)
        return records

    @classmethod
    def _remap_technical_provenance(
        cls,
        records: tuple[ProvenanceRecord, ...],
    ) -> tuple[ProvenanceRecord, ...]:
        return tuple(
            record.model_copy(
                update={
                    "provenance_id": (f"{cls.TECHNICAL_PROVENANCE_PREFIX}{record.provenance_id}"),
                    "artifact": record.artifact.model_copy(
                        update={"path": f"{cls.TECHNICAL_SOURCE_ROOT}/{record.artifact.path}"}
                    ),
                    "rights_basis_provenance_id": (
                        f"{cls.TECHNICAL_PROVENANCE_PREFIX}{record.rights_basis_provenance_id}"
                        if record.rights_basis_provenance_id is not None
                        else None
                    ),
                }
            )
            for record in records
        )

    def _validate_required_technical_provenance(
        self,
        records: tuple[ProvenanceRecord, ...],
        *,
        locked: bool = False,
    ) -> None:
        prefix = f"{self.TECHNICAL_SOURCE_ROOT}/" if locked else ""
        available = {record.artifact.path for record in records}
        required = {
            f"{prefix}{panel.technical_source_path}"
            for panel in self._plan.panels
            if panel.technical_source_path is not None
        }
        missing = sorted(required - available)
        if missing:
            raise PackageIntegrityError(
                "Missing required technical source provenance: " + ", ".join(missing)
            )

    @classmethod
    def _verified_artifact_data_at(
        cls,
        root: Path,
        artifact: ArtifactEvidence,
    ) -> bytes:
        resolved_root = root.resolve()
        path = (root / artifact.path).resolve(strict=False)
        if not path.is_relative_to(resolved_root) or not path.is_file():
            raise PackageIntegrityError(
                f"Technical provenance artifact is unavailable: {artifact.path}"
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PackageIntegrityError(
                f"Technical provenance artifact is unavailable: {artifact.path}"
            ) from exc
        if len(data) != artifact.byte_length:
            raise PackageIntegrityError(
                f"Technical provenance artifact byte length mismatch: {artifact.path}"
            )
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise PackageIntegrityError(
                f"Technical provenance artifact digest mismatch: {artifact.path}"
            )
        try:
            image = cls._load_png(data)
        except CandidateValidationError as exc:
            raise PackageIntegrityError(
                f"Technical provenance artifact is not a valid PNG: {artifact.path}"
            ) from exc
        try:
            if image.size != (artifact.width, artifact.height):
                raise PackageIntegrityError(
                    f"Technical provenance artifact dimensions mismatch: {artifact.path}"
                )
        finally:
            image.close()
        return data

    @classmethod
    def _snapshot_source_tree(
        cls,
        root: Path,
    ) -> tuple[tuple[str, ...], dict[str, bytes]]:
        cls._reject_source_symlink(root, "Technical source package")
        if not root.is_dir():
            raise WorkspaceError("Technical source package is unavailable.")
        directories: list[str] = []
        files: dict[str, bytes] = {}
        try:
            paths = sorted(root.rglob("*"), key=lambda path: path.as_posix())
            for path in paths:
                if path.is_symlink():
                    raise WorkspacePathError("Technical source package cannot contain symlinks.")
                relative_path = path.relative_to(root).as_posix()
                if path.is_dir():
                    directories.append(relative_path)
                elif path.is_file():
                    files[relative_path] = path.read_bytes()
                else:
                    raise WorkspacePathError(
                        "Technical source package contains an unsupported entry."
                    )
        except WorkspacePathError:
            raise
        except OSError as exc:
            raise WorkspaceError("Technical source package is unavailable.") from exc
        return tuple(directories), files

    @staticmethod
    def _validate_declared_technical_files(
        root: Path,
        seal: SealEvidence,
    ) -> None:
        expected = {*seal.file_hashes, "seal.json"}
        actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
        undeclared = sorted(actual - expected)
        if undeclared:
            raise PackageIntegrityError(
                "Sealed technical source package contains undeclared files: "
                + ", ".join(undeclared)
            )

    @staticmethod
    def _reject_source_symlink(path: Path, label: str) -> None:
        if path.is_symlink():
            raise WorkspacePathError(f"{label} cannot be a symlink.")

    @staticmethod
    def _load_png(data: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format != "PNG":
                    raise CandidateValidationError("Pixel panel output must be a valid PNG image.")
                source.load()
                return source.convert("RGBA")
        except CandidateValidationError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise CandidateValidationError("Pixel panel output must be a valid PNG image.") from exc

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

    @staticmethod
    def _canonical_json(payload: object) -> bytes:
        return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @classmethod
    def _write_json_exclusive(cls, path: Path, payload: object) -> None:
        cls._write_bytes_exclusive(path, cls._canonical_json(payload))

    @staticmethod
    def _initial_gaps(rights: RightsMetadata) -> tuple[GapRecord, ...]:
        if rights.is_complete:
            return ()
        return (
            GapRecord(
                gap_id="source-rights-incomplete",
                area="provenance",
                description=(
                    "Base-set source rights must be completed before visual package sealing."
                ),
                blocks_visual_seal=True,
            ),
        )
