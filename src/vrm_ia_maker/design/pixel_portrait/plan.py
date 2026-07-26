"""Fixed source-of-truth plan for panel-first pixel portrait authoring."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, NamedTuple

from pydantic import ConfigDict, Field, model_validator

from ..contracts import NonEmptyString, PackageRelativePath, StrictDesignModel
from .contracts import NEUTRAL_PANEL_ID, PanelRuntimeRole


class PanelSourceRole(StrEnum):
    """Input role used to resolve one panel generation request."""

    BASE_CHARACTER_SHEET = "base_character_sheet"
    BASE_STATE = "base_state"
    APPROVED_NEUTRAL = "approved_neutral"
    TECHNICAL_REFERENCE = "technical_reference"


class PixelAnchorRequirement(StrEnum):
    """Named geometry or alignment evidence required for a panel."""

    PIVOT = "pivot"
    EYE = "eye"
    MOUTH = "mouth"
    SHOULDERS = "shoulders"
    PRESENCE_ALIGNMENT = "presence_alignment"
    FACE_TURNAROUND_ALIGNMENT = "face_turnaround_alignment"
    FACIAL_MECHANICS_ALIGNMENT = "facial_mechanics_alignment"
    UPPER_BODY_ALIGNMENT = "upper_body_alignment"
    EXPRESSION_ALIGNMENT = "expression_alignment"
    VISEME_ALIGNMENT = "viseme_alignment"
    HAIR_CONSTRUCTION_ALIGNMENT = "hair_construction_alignment"
    OUTFIT_CONSTRUCTION_ALIGNMENT = "outfit_construction_alignment"
    MATERIAL_REFERENCE_ALIGNMENT = "material_reference_alignment"


BASE_ANCHOR_REQUIREMENTS = (
    PixelAnchorRequirement.PIVOT,
    PixelAnchorRequirement.EYE,
    PixelAnchorRequirement.MOUTH,
    PixelAnchorRequirement.SHOULDERS,
)

_FAMILY_ANCHOR_REQUIREMENTS = (
    ("presence-states", PixelAnchorRequirement.PRESENCE_ALIGNMENT),
    ("face-turnaround", PixelAnchorRequirement.FACE_TURNAROUND_ALIGNMENT),
    ("facial-mechanics", PixelAnchorRequirement.FACIAL_MECHANICS_ALIGNMENT),
    ("upper-body-turnaround", PixelAnchorRequirement.UPPER_BODY_ALIGNMENT),
    ("expressions", PixelAnchorRequirement.EXPRESSION_ALIGNMENT),
    ("visemes", PixelAnchorRequirement.VISEME_ALIGNMENT),
    ("hair-construction", PixelAnchorRequirement.HAIR_CONSTRUCTION_ALIGNMENT),
    ("outfit-construction", PixelAnchorRequirement.OUTFIT_CONSTRUCTION_ALIGNMENT),
    ("material-reference", PixelAnchorRequirement.MATERIAL_REFERENCE_ALIGNMENT),
)


def _family_anchor_requirement(family_id: str) -> PixelAnchorRequirement:
    for known_family_id, requirement in _FAMILY_ANCHOR_REQUIREMENTS:
        if known_family_id == family_id:
            return requirement
    raise ValueError(f"Unknown pixel anchor family: {family_id}")


class _FamilySpec(NamedTuple):
    family_id: str
    panel_prefix: str
    members: tuple[str, ...]
    rows: int
    columns: int
    path_pattern: str
    instruction_subject: str


_FAMILY_SPECS = (
    _FamilySpec(
        "presence-states",
        "presence",
        ("neutral", "thinking", "explaining", "approval", "doubt", "error"),
        2,
        3,
        "references/presence-states/{member}.png",
        "presence state",
    ),
    _FamilySpec(
        "face-turnaround",
        "face",
        (
            "neutral-front",
            "left-profile",
            "right-profile",
            "left-three-quarter",
            "right-three-quarter",
        ),
        2,
        3,
        "references/face/{member}.png",
        "face view",
    ),
    _FamilySpec(
        "facial-mechanics",
        "mechanics",
        (
            "eyes-open",
            "eyes-closed",
            "blink-left",
            "blink-right",
            "jaw-open",
            "neutral-mouth",
        ),
        2,
        3,
        "references/face/mechanics/{member}.png",
        "facial articulation",
    ),
    _FamilySpec(
        "upper-body-turnaround",
        "body",
        ("front", "left", "right", "back"),
        2,
        2,
        "references/body/a-pose-{member}.png",
        "upper-body A-pose view",
    ),
    _FamilySpec(
        "expressions",
        "expression",
        ("neutral", "happy", "sad", "angry", "surprised", "relaxed"),
        2,
        3,
        "references/expressions/{member}.png",
        "facial expression",
    ),
    _FamilySpec(
        "visemes",
        "viseme",
        ("neutral", "aa", "ih", "ou", "ee", "oh"),
        2,
        3,
        "references/visemes/{member}.png",
        "mouth articulation",
    ),
    _FamilySpec(
        "hair-construction",
        "hair",
        ("front", "left", "right", "back", "top", "hairline"),
        2,
        3,
        "references/hair/{member}.png",
        "hair construction view",
    ),
    _FamilySpec(
        "outfit-construction",
        "outfit",
        ("front", "left", "right", "back"),
        2,
        2,
        "references/outfit/{member}.png",
        "outfit construction view",
    ),
    _FamilySpec(
        "material-reference",
        "material",
        ("skin", "hair", "eyes", "outfit", "accessories", "combined-palette"),
        2,
        3,
        "references/materials/{member}.png",
        "material reference",
    ),
)


class _CanonicalPanelMetadata(NamedTuple):
    family_id: str
    family_position: int
    package_path: str
    technical_source_path: str | None
    base_source_role: str | None
    source_roles: tuple[PanelSourceRole, ...]
    dependencies: tuple[str, ...]
    runtime_role: PanelRuntimeRole
    prompt_instruction: str
    request_width: int
    request_height: int
    logical_width: int
    logical_height: int
    file_width: int
    file_height: int
    prompt_id: str
    prompt_version: str


def _canonical_family_spec(family_id: str) -> tuple[int, _FamilySpec]:
    for position, spec in enumerate(_FAMILY_SPECS):
        if spec.family_id == family_id:
            return position, spec
    raise ValueError(f"Unknown canonical pixel family identifier: {family_id}")


def _canonical_runtime_role(panel_id: str, family_id: str) -> PanelRuntimeRole:
    if family_id == "presence-states":
        return PanelRuntimeRole.STATE
    if panel_id in {
        "mechanics-eyes-open",
        "mechanics-eyes-closed",
        "mechanics-blink-left",
        "mechanics-blink-right",
    }:
        return PanelRuntimeRole.EYE_PATCH
    if family_id == "visemes":
        return PanelRuntimeRole.MOUTH_PATCH
    return PanelRuntimeRole.AUTHORING_ONLY


def _canonical_panel_metadata(panel_id: str) -> _CanonicalPanelMetadata:
    for spec in _FAMILY_SPECS:
        for position, member in enumerate(spec.members):
            canonical_panel_id = f"{spec.panel_prefix}-{member}"
            if canonical_panel_id != panel_id:
                continue
            package_path = spec.path_pattern.format(member=member)
            is_presence = spec.family_id == "presence-states"
            is_neutral = panel_id == NEUTRAL_PANEL_ID
            if is_neutral:
                technical_source_path: str | None = "references/face/neutral-front.png"
                source_roles = (
                    PanelSourceRole.BASE_CHARACTER_SHEET,
                    PanelSourceRole.BASE_STATE,
                    PanelSourceRole.TECHNICAL_REFERENCE,
                )
            elif is_presence:
                technical_source_path = None
                source_roles = (
                    PanelSourceRole.BASE_CHARACTER_SHEET,
                    PanelSourceRole.BASE_STATE,
                    PanelSourceRole.APPROVED_NEUTRAL,
                )
            else:
                technical_source_path = package_path
                source_roles = (
                    PanelSourceRole.BASE_CHARACTER_SHEET,
                    PanelSourceRole.APPROVED_NEUTRAL,
                    PanelSourceRole.TECHNICAL_REFERENCE,
                )
            return _CanonicalPanelMetadata(
                family_id=spec.family_id,
                family_position=position,
                package_path=package_path,
                technical_source_path=technical_source_path,
                base_source_role=member if is_presence else None,
                source_roles=source_roles,
                dependencies=() if is_neutral else (NEUTRAL_PANEL_ID,),
                runtime_role=_canonical_runtime_role(panel_id, spec.family_id),
                prompt_instruction=(f"Render only the named {spec.instruction_subject}: {member}."),
                request_width=1024,
                request_height=1024,
                logical_width=256,
                logical_height=256,
                file_width=512,
                file_height=512,
                prompt_id=f"pixel-panel.{panel_id}",
                prompt_version="pixel-panel-v1",
            )
    raise ValueError(f"Unknown canonical pixel panel identifier: {panel_id}")


class PixelAnchorContract(StrictDesignModel):
    """Immutable exact anchor requirements shared by one panel family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family_id: NonEmptyString
    required_anchors: Annotated[
        tuple[PixelAnchorRequirement, ...],
        Field(min_length=1),
    ]

    @model_validator(mode="after")
    def validate_canonical_requirements(self) -> PixelAnchorContract:
        """Reject missing, extra, reordered, or duplicated anchor requirements."""
        if len(self.required_anchors) != len(set(self.required_anchors)):
            raise ValueError("Pixel anchor requirements must not contain duplicates.")
        expected = (
            *BASE_ANCHOR_REQUIREMENTS,
            _family_anchor_requirement(self.family_id),
        )
        if self.required_anchors != expected:
            raise ValueError(
                "Pixel panels must declare the exact canonical anchor requirements "
                "for their family."
            )
        return self


class PixelPanelDefinition(StrictDesignModel):
    """One fixed panel, its evidence roles, and its canonical destination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    panel_id: NonEmptyString
    family_id: NonEmptyString
    family_position: Annotated[int, Field(strict=True, ge=0)]
    package_path: PackageRelativePath
    technical_source_path: PackageRelativePath | None = None
    base_source_role: NonEmptyString | None = None
    anchor_contract: PixelAnchorContract
    source_roles: Annotated[tuple[PanelSourceRole, ...], Field(min_length=1)]
    dependencies: tuple[NonEmptyString, ...] = ()
    runtime_role: PanelRuntimeRole = PanelRuntimeRole.AUTHORING_ONLY
    prompt_instruction: NonEmptyString
    request_width: Literal[1024] = 1024
    request_height: Literal[1024] = 1024
    logical_width: Literal[256] = 256
    logical_height: Literal[256] = 256
    file_width: Literal[512] = 512
    file_height: Literal[512] = 512
    prompt_id: NonEmptyString
    prompt_version: Literal["pixel-panel-v1"] = "pixel-panel-v1"

    @model_validator(mode="after")
    def validate_sources_and_dependencies(self) -> PixelPanelDefinition:
        """Keep source parameters aligned with explicit roles and dependencies."""
        if self.anchor_contract.family_id != self.family_id:
            raise ValueError("The anchor contract must match the panel family.")
        if self.panel_id in self.dependencies:
            raise ValueError("A pixel panel cannot depend on itself.")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("Pixel panel dependencies must be unique.")
        if len(self.source_roles) != len(set(self.source_roles)):
            raise ValueError("Pixel panel source roles must be unique.")

        has_base_state = PanelSourceRole.BASE_STATE in self.source_roles
        if has_base_state != (self.base_source_role is not None):
            raise ValueError(
                "The base_state source role and base_source_role must be declared together."
            )
        has_technical_reference = PanelSourceRole.TECHNICAL_REFERENCE in self.source_roles
        if has_technical_reference != (self.technical_source_path is not None):
            raise ValueError(
                "The technical_reference source role and technical_source_path "
                "must be declared together."
            )
        if (
            PanelSourceRole.APPROVED_NEUTRAL in self.source_roles
            and NEUTRAL_PANEL_ID not in self.dependencies
        ):
            raise ValueError(
                "The approved_neutral source role requires presence-neutral dependency."
            )
        canonical = _canonical_panel_metadata(self.panel_id)
        actual = (
            self.family_id,
            self.family_position,
            self.package_path,
            self.technical_source_path,
            self.base_source_role,
            self.source_roles,
            self.dependencies,
            self.runtime_role,
            self.prompt_instruction,
            self.request_width,
            self.request_height,
            self.logical_width,
            self.logical_height,
            self.file_width,
            self.file_height,
            self.prompt_id,
            self.prompt_version,
        )
        if actual != canonical:
            raise ValueError("Pixel panel definitions must match the canonical panel metadata.")
        return self


class PixelFamilyDefinition(StrictDesignModel):
    """One ordered family and its deterministic review-sheet grid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family_id: NonEmptyString
    panel_ids: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    rows: Annotated[int, Field(strict=True, gt=0)]
    columns: Annotated[int, Field(strict=True, gt=0)]
    family_position: Annotated[int, Field(strict=True, ge=0)]
    sheet_package_path: PackageRelativePath
    anchor_contract: PixelAnchorContract

    @property
    def ordered_panel_ids(self) -> tuple[str, ...]:
        """Return the canonical member sequence using an explicit ordered name."""
        return self.panel_ids

    @property
    def sheet_rows(self) -> int:
        """Return the deterministic sheet row count."""
        return self.rows

    @property
    def sheet_columns(self) -> int:
        """Return the deterministic sheet column count."""
        return self.columns

    @model_validator(mode="after")
    def validate_sheet(self) -> PixelFamilyDefinition:
        """Require unique members, enough cells, and the canonical sheet path."""
        if self.anchor_contract.family_id != self.family_id:
            raise ValueError("The anchor contract must match the pixel family.")
        if len(self.panel_ids) != len(set(self.panel_ids)):
            raise ValueError("Pixel family panel identifiers must be unique.")
        if len(self.panel_ids) > self.rows * self.columns:
            raise ValueError("Pixel family grid capacity must cover every member.")
        expected_path = f"references/master/approved-sheets/{self.family_id}.png"
        if self.sheet_package_path != expected_path:
            raise ValueError("Pixel family sheets must use their canonical approved-sheets path.")
        canonical_position, canonical = _canonical_family_spec(self.family_id)
        canonical_panel_ids = tuple(
            f"{canonical.panel_prefix}-{member}" for member in canonical.members
        )
        if (
            self.panel_ids,
            self.rows,
            self.columns,
            self.family_position,
            self.sheet_package_path,
        ) != (
            canonical_panel_ids,
            canonical.rows,
            canonical.columns,
            canonical_position,
            f"references/master/approved-sheets/{canonical.family_id}.png",
        ):
            raise ValueError("Pixel family definitions must match the canonical family metadata.")
        return self


class PixelPortraitPlanDefinition(StrictDesignModel):
    """Immutable ordered inventory and dependency graph for the pixel profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: Literal["juana-talking-bust-v2-pixel"] = "juana-talking-bust-v2-pixel"
    version: Literal["1.0"] = "1.0"
    base_prompt: NonEmptyString
    families: Annotated[tuple[PixelFamilyDefinition, ...], Field(min_length=1)]
    panels: Annotated[tuple[PixelPanelDefinition, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_inventory(self) -> PixelPortraitPlanDefinition:
        """Require exact membership, stable order, and a topological panel graph."""
        family_ids = [family.family_id for family in self.families]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("Pixel family identifiers must be unique.")
        expected_family_ids = tuple(spec.family_id for spec in _FAMILY_SPECS)
        expected_family_members = tuple(
            tuple(f"{spec.panel_prefix}-{member}" for member in spec.members)
            for spec in _FAMILY_SPECS
        )
        if (
            tuple(family_ids) != expected_family_ids
            or tuple(family.panel_ids for family in self.families) != expected_family_members
        ):
            raise ValueError("Pixel portrait plans must preserve the fixed nine-family inventory.")
        if [family.family_position for family in self.families] != list(range(len(self.families))):
            raise ValueError("Pixel family positions must be contiguous and stable.")
        sheet_paths = [family.sheet_package_path for family in self.families]
        if len(sheet_paths) != len(set(sheet_paths)):
            raise ValueError("Pixel family sheet package paths must be unique.")

        panel_ids = [panel.panel_id for panel in self.panels]
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("Panel identifiers must be unique.")
        package_paths = [panel.package_path for panel in self.panels]
        if len(package_paths) != len(set(package_paths)):
            raise ValueError("Panel package paths must be unique.")
        prompt_ids = [panel.prompt_id for panel in self.panels]
        if len(prompt_ids) != len(set(prompt_ids)):
            raise ValueError("Panel prompt identifiers must be unique.")

        referenced_panel_ids = tuple(
            panel_id for family in self.families for panel_id in family.panel_ids
        )
        if len(referenced_panel_ids) != len(set(referenced_panel_ids)):
            raise ValueError("Each panel can belong to only one pixel family.")
        if len(panel_ids) != len(referenced_panel_ids) or set(panel_ids) != set(
            referenced_panel_ids
        ):
            raise ValueError("Every family member must have exactly one panel definition.")
        if tuple(panel_ids) != referenced_panel_ids:
            raise ValueError("Panel definitions must follow exact family member order.")

        panels_by_id = {panel.panel_id: panel for panel in self.panels}
        for family in self.families:
            for position, panel_id in enumerate(family.panel_ids):
                panel = panels_by_id[panel_id]
                if panel.family_id != family.family_id:
                    raise ValueError("Panel family identifiers must match family membership.")
                if panel.family_position != position:
                    raise ValueError("Panel family positions must be contiguous and stable.")
                if panel.anchor_contract != family.anchor_contract:
                    raise ValueError("Panel anchor requirements must match their pixel family.")

        known_panels: set[str] = set()
        for panel in self.panels:
            if any(dependency not in known_panels for dependency in panel.dependencies):
                raise ValueError("Panel dependencies must reference earlier panels.")
            known_panels.add(panel.panel_id)
        if self.panels[0].panel_id != NEUTRAL_PANEL_ID:
            raise ValueError("presence-neutral must be the first pixel panel.")
        if self.panels[0].dependencies:
            raise ValueError("presence-neutral cannot have panel dependencies.")
        if any(NEUTRAL_PANEL_ID not in panel.dependencies for panel in self.panels[1:]):
            raise ValueError("Every panel after presence-neutral must depend on presence-neutral.")
        return self

    def panel(self, panel_id: str) -> PixelPanelDefinition:
        """Return a panel by its stable identifier."""
        for panel in self.panels:
            if panel.panel_id == panel_id:
                return panel
        raise KeyError(f"Unknown pixel portrait panel: {panel_id}")

    def family(self, family_id: str) -> PixelFamilyDefinition:
        """Return a family by its stable identifier."""
        for family in self.families:
            if family.family_id == family_id:
                return family
        raise KeyError(f"Unknown pixel portrait family: {family_id}")


def _anchor_contract(family_id: str) -> PixelAnchorContract:
    return PixelAnchorContract(
        family_id=family_id,
        required_anchors=(
            *BASE_ANCHOR_REQUIREMENTS,
            _family_anchor_requirement(family_id),
        ),
    )


def _panel(panel_id: str) -> PixelPanelDefinition:
    canonical = _canonical_panel_metadata(panel_id)
    return PixelPanelDefinition(
        panel_id=panel_id,
        family_id=canonical.family_id,
        family_position=canonical.family_position,
        package_path=canonical.package_path,
        technical_source_path=canonical.technical_source_path,
        base_source_role=canonical.base_source_role,
        anchor_contract=_anchor_contract(canonical.family_id),
        source_roles=canonical.source_roles,
        dependencies=canonical.dependencies,
        runtime_role=canonical.runtime_role,
        prompt_instruction=canonical.prompt_instruction,
        prompt_id=canonical.prompt_id,
    )


_FAMILIES = tuple(
    PixelFamilyDefinition(
        family_id=spec.family_id,
        panel_ids=tuple(f"{spec.panel_prefix}-{member}" for member in spec.members),
        rows=spec.rows,
        columns=spec.columns,
        family_position=position,
        sheet_package_path=(f"references/master/approved-sheets/{spec.family_id}.png"),
        anchor_contract=_anchor_contract(spec.family_id),
    )
    for position, spec in enumerate(_FAMILY_SPECS)
)

_PANELS = tuple(
    _panel(f"{spec.panel_prefix}-{member}") for spec in _FAMILY_SPECS for member in spec.members
)

_BASE_PROMPT = (
    "Render the younger base-set Juana identity with the viewer-left shaved side "
    "and viewer-right long hair. Produce fine pixel art on one 256x256 logical grid "
    "emitted as 512x512 nearest-neighbor-safe artwork. Use a transparent or solid "
    "neutral background with no scenery. Include no text, labels, or extra panels. "
    "Preserve only the named view or articulation. Do not invent hidden geometry or "
    "measurements."
)

PIXEL_PORTRAIT_PLAN = PixelPortraitPlanDefinition(
    base_prompt=_BASE_PROMPT,
    families=_FAMILIES,
    panels=_PANELS,
)
