"""Validated contracts for modular VRM asset composition."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    model_validator,
)

SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
NonEmptyString = Annotated[str, Field(min_length=1)]
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _validate_hex_color(value: str) -> str:
    if (
        len(value) != 7
        or not value.startswith("#")
        or any(digit not in _HEX_DIGITS for digit in value[1:])
    ):
        raise ValueError("Material override colors must use #RRGGBB.")
    return value


HexColor = Annotated[str, AfterValidator(_validate_hex_color)]


class StrictModel(BaseModel):
    """Base model that rejects contract drift and validates assignments."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Provenance(StrictModel):
    """Legal and origin metadata required for every asset pack."""

    author: NonEmptyString
    source: NonEmptyString
    license: NonEmptyString
    commercial_use: bool
    modification_allowed: bool
    redistribution_allowed: bool
    source_url: HttpUrl | None = None


class ComponentSlot(StrEnum):
    """Canonical singular slots supported by the initial production contract."""

    HAIR = "hair"
    OUTFIT = "outfit"
    ACCESSORY = "accessory"


class ComponentKind(StrEnum):
    """How Blender must integrate a selected component."""

    RIGID_ATTACHMENT = "rigid_attachment"
    SKINNED_MESH = "skinned_mesh"


def _validate_component_integration_contract(
    kind: ComponentKind,
    attachment_bone: str | None,
    required_bones: tuple[str, ...],
) -> None:
    if kind is ComponentKind.RIGID_ATTACHMENT and attachment_bone is None:
        raise ValueError("Rigid attachments require attachment_bone.")
    if kind is ComponentKind.SKINNED_MESH and not required_bones:
        raise ValueError("Skinned meshes require at least one required_bone.")


class AssetReference(StrictModel):
    """Immutable identity and integrity metadata for one source asset."""

    asset_id: NonEmptyString
    path: Path
    object_name: NonEmptyString
    sha256: SHA256
    byte_length: Annotated[int, Field(gt=0)]


class BaseAsset(AssetReference):
    """Humanoid source asset that owns the authoritative armature."""

    required_objects: tuple[NonEmptyString, ...]
    required_bones: tuple[NonEmptyString, ...]
    required_expressions: tuple[NonEmptyString, ...]


class ComponentAsset(AssetReference):
    """Selectable asset that is attached or rebound to the base armature."""

    slot: ComponentSlot
    kind: ComponentKind
    required: StrictBool = False
    attachment_bone: NonEmptyString | None = None
    required_bones: tuple[NonEmptyString, ...] = ()
    material_names: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_integration_contract(self) -> ComponentAsset:
        """Require integration metadata appropriate for the component kind."""
        _validate_component_integration_contract(
            self.kind,
            self.attachment_bone,
            self.required_bones,
        )
        return self


class AssetPackManifest(StrictModel):
    """Catalog of traceable assets available to an avatar build."""

    schema_version: Literal["1.0"] = "1.0"
    pack_id: NonEmptyString
    provenance: Provenance
    base_asset: BaseAsset
    components: tuple[ComponentAsset, ...]

    @model_validator(mode="after")
    def validate_catalog_uniqueness(self) -> AssetPackManifest:
        """Reject ambiguous identifiers and duplicate slot candidates."""
        asset_ids = [self.base_asset.asset_id, *(item.asset_id for item in self.components)]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("Asset identifiers must be unique within an asset pack.")
        return self


class ComponentSelection(StrictModel):
    """One explicit selection for a singular component slot."""

    asset_id: NonEmptyString
    enabled: StrictBool = True


class AvatarMetadata(StrictModel):
    """Metadata embedded in the final VRM document."""

    author: NonEmptyString
    contact_url: HttpUrl | None = None
    license: NonEmptyString
    commercial_use: bool
    redistribution: bool


class AssemblyManifest(StrictModel):
    """Reproducible user-selected composition for one avatar build."""

    schema_version: Literal["1.0"] = "1.0"
    character_id: NonEmptyString
    display_name: NonEmptyString
    asset_pack_id: NonEmptyString
    selections: dict[ComponentSlot, ComponentSelection]
    material_overrides: dict[NonEmptyString, HexColor] = Field(default_factory=dict)
    metadata: AvatarMetadata


class ResolvedAsset(StrictModel):
    """Asset reference resolved to a build-time path and verified digest."""

    asset_id: NonEmptyString
    path: Path
    object_name: NonEmptyString
    sha256: SHA256


class ResolvedComponent(ResolvedAsset):
    """Selected component with all Blender integration metadata resolved."""

    slot: ComponentSlot
    kind: ComponentKind
    attachment_bone: NonEmptyString | None = None
    required_bones: tuple[NonEmptyString, ...] = ()
    material_names: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_integration_contract(self) -> ResolvedComponent:
        """Require resolved integration metadata appropriate for the component kind."""
        _validate_component_integration_contract(
            self.kind,
            self.attachment_bone,
            self.required_bones,
        )
        return self


class LegacyResolvedComponent(StrictModel):
    """Resolved component retaining spike-only schema 1.0 compatibility."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    asset_id: NonEmptyString
    path: Path
    object_name: NonEmptyString
    sha256: SHA256 | None = None
    slot: ComponentSlot
    kind: ComponentKind
    attachment_bone: NonEmptyString | None = None
    required_bones: tuple[NonEmptyString, ...] = ()
    material_names: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_integration_contract(self) -> LegacyResolvedComponent:
        """Preserve integration checks for retained schema 1.0 components."""
        _validate_component_integration_contract(
            self.kind,
            self.attachment_bone,
            self.required_bones,
        )
        return self


CompiledComponent = Annotated[
    ResolvedComponent | LegacyResolvedComponent,
    Field(union_mode="left_to_right"),
]


class DisabledComponent(StrictModel):
    """Component deliberately excluded from a compiled assembly."""

    asset_id: NonEmptyString
    slot: ComponentSlot
    object_name: NonEmptyString


class BuiltComponent(StrictModel):
    """Component integration recorded by the Blender finalizer."""

    asset_id: NonEmptyString
    slot: ComponentSlot
    kind: ComponentKind
    object_name: NonEmptyString


class ExpressionBind(StrictModel):
    """One adapter-provided morph-target binding for a VRM expression."""

    shape_key: NonEmptyString
    weight: Annotated[float, Field(ge=0.0, le=1.0)]


ExpressionBindings = Annotated[tuple[ExpressionBind, ...], Field(min_length=1)]


class LookAtSpec(StrictModel):
    """Base-specific look-at limits copied into the Blender-facing build spec."""

    horizontal_inner_degrees: Annotated[float, Field(ge=0.0)]
    horizontal_outer_degrees: Annotated[float, Field(ge=0.0)]
    vertical_down_degrees: Annotated[float, Field(ge=0.0)]
    vertical_up_degrees: Annotated[float, Field(ge=0.0)]


class BaseModelAdapterManifest(StrictModel):
    """Versioned base-specific mappings consumed by assembly compilation."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_id: NonEmptyString
    adapter_version: NonEmptyString
    base_asset_id: NonEmptyString
    bones: Annotated[dict[NonEmptyString, NonEmptyString], Field(min_length=1)]
    expression_map: Annotated[
        dict[NonEmptyString, ExpressionBindings],
        Field(min_length=1),
    ]
    look_at: LookAtSpec


class VrmBuildSpec(StrictModel):
    """Strict Blender-facing VRM configuration emitted by schema 1.1 compilers."""

    spec_version: Literal["1.0"] = "1.0"
    avatar_id: NonEmptyString
    display_name: NonEmptyString
    base_asset_id: NonEmptyString
    bones: Annotated[dict[NonEmptyString, NonEmptyString], Field(min_length=1)]
    expression_map: Annotated[
        dict[NonEmptyString, ExpressionBindings],
        Field(min_length=1),
    ]
    look_at: LookAtSpec
    metadata: AvatarMetadata


class LegacyVrmBuildSpec(StrictModel):
    """Loose VRM payload retained only for compiled schema 1.0 compatibility."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    spec_version: Literal["1.0"] = "1.0"
    avatar_id: NonEmptyString
    display_name: NonEmptyString
    base_asset_id: NonEmptyString
    bones: dict[NonEmptyString, NonEmptyString]
    expression_map: dict[NonEmptyString, list[dict[str, object]]]
    look_at: dict[NonEmptyString, float]
    metadata: AvatarMetadata


class CompiledAssemblySpec(StrictModel):
    """Validated, resolved handoff from composition to Blender finalization."""

    schema_version: Literal["1.0", "1.1"] = "1.0"
    character_id: NonEmptyString
    display_name: NonEmptyString
    asset_pack_id: NonEmptyString
    base_adapter_id: NonEmptyString | None = None
    base_adapter_version: NonEmptyString | None = None
    provenance: Provenance
    base_asset: ResolvedAsset
    components: tuple[CompiledComponent, ...]
    disabled_components: tuple[DisabledComponent, ...]
    material_overrides: dict[NonEmptyString, HexColor]
    vrm_spec: Annotated[
        VrmBuildSpec | LegacyVrmBuildSpec,
        Field(union_mode="left_to_right"),
    ]

    @model_validator(mode="after")
    def validate_adapter_traceability(self) -> CompiledAssemblySpec:
        """Require adapter identity for schema 1.1 compiled specifications."""
        if self.schema_version == "1.1" and (
            self.base_adapter_id is None or self.base_adapter_version is None
        ):
            raise ValueError(
                "Compiled assembly schema 1.1 requires "
                "base_adapter_id and base_adapter_version."
            )
        if self.schema_version == "1.1" and not isinstance(self.vrm_spec, VrmBuildSpec):
            raise ValueError(
                "Compiled assembly schema 1.1 requires strict expression_map "
                "and look_at mappings."
            )
        if self.schema_version == "1.1" and any(
            isinstance(component, LegacyResolvedComponent) for component in self.components
        ):
            raise ValueError("Compiled assembly schema 1.1 rejects legacy component payloads.")
        if self.schema_version == "1.0" and (
            self.base_adapter_id is not None or self.base_adapter_version is not None
        ):
            raise ValueError(
                "Adapter traceability fields are available only in compiled assembly "
                "schema 1.1."
            )
        return self

    @model_validator(mode="after")
    def validate_component_slots(self) -> CompiledAssemblySpec:
        """Ensure each singular slot is represented at most once in the build."""
        slots = [component.slot for component in self.components]
        if len(slots) != len(set(slots)):
            raise ValueError("Compiled assemblies cannot contain duplicate component slots.")
        enabled_ids = {component.asset_id for component in self.components}
        disabled_ids = {component.asset_id for component in self.disabled_components}
        if enabled_ids & disabled_ids:
            raise ValueError("A component cannot be both enabled and disabled.")
        return self


class BlenderBuildEvidence(StrictModel):
    """Scene evidence emitted by the production Blender finalizer."""

    schema_version: Literal["1.0"] = "1.0"
    character_id: NonEmptyString
    base_adapter_id: NonEmptyString
    base_adapter_version: NonEmptyString
    armature_objects: Annotated[
        tuple[NonEmptyString, ...],
        Field(min_length=1, max_length=1),
    ]
    selected_components: tuple[BuiltComponent, ...]
    disabled_components: tuple[DisabledComponent, ...]
    scene_objects_before_export: Annotated[
        tuple[NonEmptyString, ...],
        Field(min_length=1),
    ]
    humanoid_bones: Annotated[
        tuple[NonEmptyString, ...],
        Field(min_length=1),
    ]
    expressions: Annotated[
        tuple[NonEmptyString, ...],
        Field(min_length=1),
    ]
    look_at: LookAtSpec
    metadata: AvatarMetadata


class ForgeBuildReport(StrictModel):
    """Verified report published beside one production VRM artifact."""

    schema_version: Literal["1.0"] = "1.0"
    character_id: NonEmptyString
    display_name: NonEmptyString
    asset_pack_id: NonEmptyString
    base_adapter_id: NonEmptyString
    base_adapter_version: NonEmptyString
    vrm_path: Path
    vrm_sha256: SHA256
    vrm_byte_length: Annotated[int, Field(gt=0)]
    blender_exit_code: Literal[0]
    blender_duration_seconds: Annotated[float, Field(ge=0.0)]
    evidence: BlenderBuildEvidence
