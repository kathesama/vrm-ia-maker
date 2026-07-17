"""Unit tests for the standalone production Blender finalizer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class FakeCollection(list[Any]):
    def __init__(self, factory: type[Any]) -> None:
        super().__init__()
        self._factory = factory

    def add(self) -> Any:
        value = self._factory()
        self.append(value)
        return value


class FakeStringValue:
    def __init__(self) -> None:
        self.value = ""


class FakeMorphTargetBind:
    def __init__(self) -> None:
        self.node = SimpleNamespace(mesh_object_name="")
        self.index = ""
        self.weight = 0.0


class FakeExpression:
    def __init__(self) -> None:
        self.morph_target_binds = FakeCollection(FakeMorphTargetBind)


class FakeCustomExpression(FakeExpression):
    def __init__(self) -> None:
        super().__init__()
        self.custom_name = ""


class FakePreset:
    def __init__(self) -> None:
        self.blink_left = FakeExpression()
        self.aa = FakeExpression()

    def name_to_expression_dict(self) -> dict[str, FakeExpression]:
        return {
            "blinkLeft": self.blink_left,
            "aa": self.aa,
        }


class FakeExpressions:
    def __init__(self) -> None:
        self.preset = FakePreset()
        self.custom = FakeCollection(FakeCustomExpression)
        self.initial_automatic_expression_assignment = True


class FakeHumanBoneName:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeHumanBone:
    def __init__(self) -> None:
        self.node = SimpleNamespace(bone_name="")


class FakeHumanBones:
    def __init__(self) -> None:
        self.initial_automatic_bone_assignment = True
        self.filter_by_human_bone_hierarchy = True
        self.allow_non_humanoid_rig = True
        self._bones = {
            FakeHumanBoneName(name): FakeHumanBone()
            for name in ("hips", "head", "leftEye", "rightEye")
        }

    def human_bone_name_to_human_bone(
        self,
    ) -> dict[FakeHumanBoneName, FakeHumanBone]:
        return self._bones


class FakeRangeMap:
    def __init__(self) -> None:
        self.input_max_value = 0.0
        self.output_scale = 0.0


class FakeLookAt:
    def __init__(self) -> None:
        self.type = ""
        self.offset_from_head_bone = (0.0, 0.0, 0.0)
        self.range_map_horizontal_inner = FakeRangeMap()
        self.range_map_horizontal_outer = FakeRangeMap()
        self.range_map_vertical_down = FakeRangeMap()
        self.range_map_vertical_up = FakeRangeMap()


class FakeMeta:
    def __init__(self) -> None:
        self.vrm_name = ""
        self.version = ""
        self.authors = FakeCollection(FakeStringValue)
        self.contact_information = ""
        self.avatar_permission = ""
        self.allow_excessively_violent_usage = True
        self.allow_excessively_sexual_usage = True
        self.commercial_usage = ""
        self.allow_political_or_religious_usage = True
        self.allow_antisocial_or_hate_usage = True
        self.credit_notation = ""
        self.allow_redistribution = False
        self.modification = ""
        self.other_license_url = ""


class FakeArmature:
    def __init__(self) -> None:
        human_bones = FakeHumanBones()
        vrm1 = SimpleNamespace(
            humanoid=SimpleNamespace(human_bones=human_bones),
            expressions=FakeExpressions(),
            look_at=FakeLookAt(),
            meta=FakeMeta(),
        )
        self.name = "Armature"
        self.type = "ARMATURE"
        self.data = SimpleNamespace(
            bones={
                "hips": SimpleNamespace(head_local=(0.0, 0.0, 0.9)),
                "head": SimpleNamespace(head_local=(0.0, 0.0, 1.5)),
                "L_Eye": SimpleNamespace(head_local=(-0.03, -0.1, 1.7)),
                "R_Eye": SimpleNamespace(head_local=(0.03, -0.1, 1.7)),
            },
            vrm_addon_extension=SimpleNamespace(spec_version="", vrm1=vrm1),
        )


def _mesh(name: str, *shape_keys: str) -> Any:
    return SimpleNamespace(
        name=name,
        type="MESH",
        data=SimpleNamespace(
            shape_keys=SimpleNamespace(
                key_blocks=[SimpleNamespace(name=key) for key in shape_keys]
            )
        ),
    )


def _vrm_spec() -> dict[str, object]:
    return {
        "spec_version": "1.0",
        "avatar_id": "procedural-avatar",
        "display_name": "Procedural Avatar",
        "base_asset_id": "base-v1",
        "bones": {
            "hips": "hips",
            "head": "head",
            "leftEye": "L_Eye",
            "rightEye": "R_Eye",
        },
        "expression_map": {
            "blinkLeft": [{"shape_key": "blinkLeft", "weight": 1.0}],
            "smirk": [{"shape_key": "smirk", "weight": 0.75}],
        },
        "look_at": {
            "horizontal_inner_degrees": 15.0,
            "horizontal_outer_degrees": 30.0,
            "vertical_down_degrees": 10.0,
            "vertical_up_degrees": 12.0,
        },
        "metadata": {
            "author": "Katherine E. Aguirre / Juana IA",
            "contact_url": "https://example.com/juana",
            "license": "CC-BY-4.0",
            "commercial_use": True,
            "redistribution": True,
        },
    }


def _vrm_setup_module() -> Any:
    try:
        from vrm_ia_maker.forge.blender import vrm_setup
    except ModuleNotFoundError:
        pytest.fail("Missing production Blender VRM setup module.", pytrace=False)
    return vrm_setup


def _finalizer_module() -> Any:
    try:
        from vrm_ia_maker.forge.blender import finalize_assembly
    except ModuleNotFoundError:
        pytest.fail("Missing production Blender assembly module.", pytrace=False)
    return finalize_assembly


def test_configures_vrm_only_from_strict_adapter_data() -> None:
    armature = FakeArmature()
    head = _mesh("Head", "Basis", "blinkLeft", "smirk")

    configured = _vrm_setup_module().configure_vrm(
        armature=armature,
        scene_objects=[armature, head],
        vrm_spec=_vrm_spec(),
    )

    extension = armature.data.vrm_addon_extension
    vrm1 = extension.vrm1
    human_bones = vrm1.humanoid.human_bones
    mapped = {
        key.value: value.node.bone_name
        for key, value in human_bones.human_bone_name_to_human_bone().items()
    }
    assert extension.spec_version == "1.0"
    assert mapped == {
        "hips": "hips",
        "head": "head",
        "leftEye": "L_Eye",
        "rightEye": "R_Eye",
    }
    assert human_bones.initial_automatic_bone_assignment is False
    assert human_bones.filter_by_human_bone_hierarchy is False
    assert human_bones.allow_non_humanoid_rig is False

    blink_bind = vrm1.expressions.preset.blink_left.morph_target_binds[0]
    assert (blink_bind.node.mesh_object_name, blink_bind.index, blink_bind.weight) == (
        "Head",
        "blinkLeft",
        1.0,
    )
    assert len(vrm1.expressions.custom) == 1
    custom = vrm1.expressions.custom[0]
    assert custom.custom_name == "smirk"
    assert custom.morph_target_binds[0].weight == 0.75
    assert vrm1.expressions.initial_automatic_expression_assignment is False

    look_at = vrm1.look_at
    assert look_at.type == "bone"
    assert look_at.offset_from_head_bone == pytest.approx((0.0, -0.1, 0.2))
    assert look_at.range_map_horizontal_inner.input_max_value == 90.0
    assert look_at.range_map_horizontal_inner.output_scale == 15.0
    assert look_at.range_map_horizontal_outer.output_scale == 30.0
    assert look_at.range_map_vertical_down.output_scale == 10.0
    assert look_at.range_map_vertical_up.output_scale == 12.0

    meta = vrm1.meta
    assert meta.vrm_name == "Procedural Avatar"
    assert meta.version == "1.0"
    assert [author.value for author in meta.authors] == [
        "Katherine E. Aguirre / Juana IA"
    ]
    assert meta.contact_information == "https://example.com/juana"
    assert meta.avatar_permission == "everyone"
    assert meta.commercial_usage == "corporation"
    assert meta.credit_notation == "required"
    assert meta.allow_redistribution is True
    assert meta.modification == "prohibited"
    assert meta.other_license_url.endswith("/CC-BY-4.0.html")

    assert configured == {
        "humanoid_bones": ["head", "hips", "leftEye", "rightEye"],
        "expressions": ["blinkLeft", "smirk"],
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda spec: spec["bones"].update({"head": "missing"}),  # type: ignore[union-attr]
            "missing armature bone",
        ),
        (
            lambda spec: spec["bones"].update({"rightEye": "head"}),  # type: ignore[union-attr]
            "more than one VRM humanoid slot",
        ),
        (
            lambda spec: spec["expression_map"].update(  # type: ignore[union-attr]
                {"aa": [{"shape_key": "missing", "weight": 1.0}]}
            ),
            "missing shape key",
        ),
    ],
)
def test_rejects_invalid_adapter_driven_vrm_mappings(
    mutate: Any,
    message: str,
) -> None:
    spec = _vrm_spec()
    mutate(spec)

    with pytest.raises(RuntimeError, match=message):
        _vrm_setup_module().configure_vrm(
            armature=FakeArmature(),
            scene_objects=[_mesh("Head", "blinkLeft", "smirk")],
            vrm_spec=spec,
        )


def test_rejects_ambiguous_shape_key_ownership() -> None:
    with pytest.raises(RuntimeError, match="more than one mesh"):
        _vrm_setup_module().configure_vrm(
            armature=FakeArmature(),
            scene_objects=[
                _mesh("Head", "blinkLeft", "smirk"),
                _mesh("Duplicate", "smirk"),
            ],
            vrm_spec=_vrm_spec(),
        )


def test_standalone_finalizer_validates_hash_color_and_object_identity(
    tmp_path: Path,
) -> None:
    module = _finalizer_module()
    asset_path = tmp_path / "asset.glb"
    asset_path.write_bytes(b"traceable asset")
    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()

    module._verify_asset_hash(asset_path, digest, "base-v1")
    assert module._hex_to_rgba("#ff8040") == pytest.approx(
        (1.0, 128 / 255, 64 / 255, 1.0)
    )
    expected = SimpleNamespace(name="Hair.001")
    assert module._find_object([expected], "Hair") is expected

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        module._verify_asset_hash(asset_path, "0" * 64, "base-v1")
    with pytest.raises(ValueError, match="#RRGGBB"):
        module._hex_to_rgba("#nothex")
    with pytest.raises(RuntimeError, match="ambiguous"):
        module._find_object(
            [SimpleNamespace(name="Hair.001"), SimpleNamespace(name="Hair.002")],
            "Hair",
        )
    with pytest.raises(RuntimeError, match="ambiguous"):
        module._find_object(
            [SimpleNamespace(name="Hair"), SimpleNamespace(name="Hair.001")],
            "Hair",
        )


def test_standalone_finalizer_rejects_nonproduction_compiled_schema() -> None:
    with pytest.raises(ValueError, match="schema_version must be 1.1"):
        _finalizer_module()._validate_compiled_spec({"schema_version": "1.0"})


def test_blender_modules_do_not_import_retained_or_spike_implementation() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "vrm_ia_maker" / "forge" / "blender"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "seidr_smidja" not in source
    assert "spikes." not in source
    assert "TURBOSQUID" not in source
    assert "name_to_expression_dict()" in source
    assert "range_map_horizontal_inner" in source
