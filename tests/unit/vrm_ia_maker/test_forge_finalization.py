"""Unit tests for production Forge finalization and publication."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from vrm_ia_maker import CompiledAssemblySpec, load_forge_build_report
from vrm_ia_maker.forge.ports import (
    BlenderExecutionConfig,
    BlenderExecutionResult,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def _compiled_payload(schema_version: str = "1.1") -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "character_id": "procedural-avatar",
        "display_name": "Procedural Avatar",
        "asset_pack_id": "procedural-pack",
        "provenance": {
            "author": "Katherine E. Aguirre / Juana IA",
            "source": "repository-owned procedural fixture",
            "license": "CC0-1.0",
            "commercial_use": True,
            "modification_allowed": True,
            "redistribution_allowed": True,
        },
        "base_asset": {
            "asset_id": "base-v1",
            "path": "assets/base.glb",
            "object_name": "Armature",
            "sha256": DIGEST_A,
        },
        "components": [
            {
                "asset_id": "hair-v1",
                "slot": "hair",
                "kind": "rigid_attachment",
                "path": "assets/hair.glb",
                "object_name": "Hair",
                "sha256": DIGEST_B,
                "attachment_bone": "head",
                "material_names": ["Hair_Primary"],
            }
        ],
        "disabled_components": [
            {
                "asset_id": "brooch-v1",
                "slot": "accessory",
                "object_name": "Brooch",
            }
        ],
        "material_overrides": {"Hair_Primary": "#271C24"},
        "vrm_spec": {
            "spec_version": "1.0",
            "avatar_id": "procedural-avatar",
            "display_name": "Procedural Avatar",
            "base_asset_id": "base-v1",
            "bones": {"hips": "hips", "head": "head"},
            "expression_map": {
                "blink": [{"shape_key": "blink", "weight": 1.0}],
                "aa": [{"shape_key": "aa", "weight": 1.0}],
            },
            "look_at": {
                "horizontal_inner_degrees": 15.0,
                "horizontal_outer_degrees": 30.0,
                "vertical_down_degrees": 10.0,
                "vertical_up_degrees": 10.0,
            },
            "metadata": {
                "author": "Katherine E. Aguirre / Juana IA",
                "license": "CC0-1.0",
                "commercial_use": True,
                "redistribution": True,
            },
        },
    }
    if schema_version == "1.1":
        payload["base_adapter_id"] = "procedural-base-adapter"
        payload["base_adapter_version"] = "1.0.0"
    return payload


def _spec(schema_version: str = "1.1") -> CompiledAssemblySpec:
    return CompiledAssemblySpec.model_validate(_compiled_payload(schema_version))


def _evidence_payload(spec: CompiledAssemblySpec) -> dict[str, object]:
    assert spec.base_adapter_id is not None
    assert spec.base_adapter_version is not None
    return {
        "schema_version": "1.0",
        "character_id": spec.character_id,
        "base_adapter_id": spec.base_adapter_id,
        "base_adapter_version": spec.base_adapter_version,
        "armature_objects": ["Armature"],
        "selected_components": [
            {
                "asset_id": component.asset_id,
                "slot": component.slot.value,
                "kind": component.kind.value,
                "object_name": component.object_name,
            }
            for component in spec.components
        ],
        "disabled_components": [
            component.model_dump(mode="json") for component in spec.disabled_components
        ],
        "scene_objects_before_export": ["Armature", "Body", "Hair"],
        "humanoid_bones": sorted(spec.vrm_spec.bones),
        "expressions": sorted(spec.vrm_spec.expression_map),
        "look_at": spec.vrm_spec.look_at.model_dump(mode="json"),
        "metadata": spec.vrm_spec.metadata.model_dump(mode="json"),
    }


def _write_vrm(
    path: Path,
    spec: CompiledAssemblySpec,
    *,
    custom_expressions: frozenset[str] = frozenset(),
    look_at_type: str = "bone",
    bone_target_overrides: Mapping[str, str] | None = None,
    expression_target_overrides: Mapping[str, str] | None = None,
) -> None:
    expression_names = set(spec.vrm_spec.expression_map)
    bone_target_overrides = bone_target_overrides or {}
    expression_target_overrides = expression_target_overrides or {}
    bone_targets = list(dict.fromkeys(spec.vrm_spec.bones.values()))
    shape_key_names = list(
        dict.fromkeys(
            binding.shape_key
            for bindings in spec.vrm_spec.expression_map.values()
            for binding in bindings
        )
    )
    nodes = [{"name": spec.base_asset.object_name}]
    bone_node_indices: dict[str, int] = {}
    for bone_name in bone_targets:
        bone_node_indices[bone_name] = len(nodes)
        nodes.append({"name": bone_name})
    expression_node_index = len(nodes)
    nodes.append({"name": "ExpressionMesh", "mesh": 0})
    nodes.extend({"name": component.object_name} for component in spec.components)

    def expression_value(expression_name: str) -> dict[str, object]:
        binds = []
        for binding in spec.vrm_spec.expression_map[expression_name]:
            shape_key = expression_target_overrides.get(
                expression_name,
                binding.shape_key,
            )
            binds.append(
                {
                    "node": expression_node_index,
                    "index": shape_key_names.index(shape_key),
                    "weight": binding.weight,
                }
            )
        return {"morphTargetBinds": binds}

    document = {
        "asset": {"version": "2.0"},
        "extensionsUsed": ["VRMC_vrm"],
        "extensions": {
            "VRMC_vrm": {
                "specVersion": "1.0",
                "meta": {
                    "name": spec.display_name,
                    "authors": [spec.vrm_spec.metadata.author],
                },
                "humanoid": {
                    "humanBones": {
                        slot_name: {
                            "node": bone_node_indices[
                                bone_target_overrides.get(slot_name, target_name)
                            ]
                        }
                        for slot_name, target_name in spec.vrm_spec.bones.items()
                    }
                },
                "expressions": {
                    "preset": {
                        expression_name: expression_value(expression_name)
                        for expression_name in expression_names.difference(
                            custom_expressions
                        )
                    },
                    "custom": {
                        expression_name: expression_value(expression_name)
                        for expression_name in expression_names.intersection(
                            custom_expressions
                        )
                    },
                },
                "lookAt": {"type": look_at_type},
            }
        },
        "meshes": [
            {
                "extras": {
                    "targetNames": shape_key_names,
                }
            }
        ],
        "nodes": nodes,
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    total_length = 12 + 8 + len(json_chunk)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
    )


class FakeExecutor:
    def __init__(
        self,
        spec: CompiledAssemblySpec,
        *,
        result: BlenderExecutionResult | None = None,
        write_vrm: Callable[[Path, CompiledAssemblySpec], None] | None = _write_vrm,
        evidence: dict[str, object] | None = None,
        after_write: Callable[[], None] | None = None,
    ) -> None:
        self.spec = spec
        self.result = result or BlenderExecutionResult(0, "done", "", 1.25)
        self.write_vrm = write_vrm
        self.evidence = evidence or _evidence_payload(spec)
        self.after_write = after_write
        self.calls: list[dict[str, object]] = []

    def execute(
        self,
        *,
        script_path: Path,
        arguments: Sequence[str],
        config: BlenderExecutionConfig,
    ) -> BlenderExecutionResult:
        args = list(arguments)
        spec_path = Path(args[args.index("--spec") + 1])
        output_path = Path(args[args.index("--output") + 1])
        evidence_path = Path(args[args.index("--evidence") + 1])
        self.calls.append(
            {
                "script_path": script_path,
                "arguments": args,
                "config": config,
                "spec_path": spec_path,
            }
        )
        assert json.loads(spec_path.read_text(encoding="utf-8"))["schema_version"] == "1.1"
        if self.result.returncode == 0 and not self.result.timed_out:
            if self.write_vrm is not None:
                self.write_vrm(output_path, self.spec)
            evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
            if self.after_write is not None:
                self.after_write()
        return self.result


def _finalizer() -> Any:
    try:
        from vrm_ia_maker.forge.finalize import finalize_compiled_assembly
    except ModuleNotFoundError:
        pytest.fail("Missing production Forge finalization use case.", pytrace=False)
    return finalize_compiled_assembly


def _assert_no_staging_files(root: Path) -> None:
    assert [path for path in root.rglob("*") if path.name.startswith(".forge-")] == []


def test_finalizes_valid_schema_1_1_and_publishes_verified_pair(tmp_path: Path) -> None:
    spec = _spec()
    executor = FakeExecutor(spec)
    output_path = tmp_path / "vrm" / "avatar.vrm"
    report_path = tmp_path / "reports" / "build.json"

    result = _finalizer()(
        spec=spec,
        output_path=output_path,
        report_path=report_path,
        execution_config=BlenderExecutionConfig(timeout_seconds=10),
        executor=executor,
    )

    assert result.success is True
    assert result.vrm_path == output_path.resolve()
    assert result.report_path == report_path.resolve()
    assert result.exit_code == 0
    assert result.error is None
    assert len(executor.calls) == 1
    assert executor.calls[0]["script_path"].name == "finalize_assembly.py"
    assert Path(executor.calls[0]["spec_path"]).exists() is False
    report = load_forge_build_report(report_path)
    payload = output_path.read_bytes()
    assert report.vrm_sha256 == hashlib.sha256(payload).hexdigest()
    assert report.vrm_byte_length == len(payload)
    assert report.evidence.character_id == spec.character_id
    _assert_no_staging_files(tmp_path)


def test_rejects_schema_1_0_before_blender_execution(tmp_path: Path) -> None:
    spec = _spec("1.0")
    executor = FakeExecutor(_spec())

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "avatar.vrm",
        report_path=tmp_path / "build.json",
        execution_config=BlenderExecutionConfig(),
        executor=executor,
    )

    assert result.success is False
    assert result.exit_code is None
    assert "schema 1.1" in result.error
    assert executor.calls == []


@pytest.mark.parametrize("existing_target", ["vrm", "report"])
def test_preserves_existing_targets_without_launching_blender(
    tmp_path: Path,
    existing_target: str,
) -> None:
    spec = _spec()
    executor = FakeExecutor(spec)
    output_path = tmp_path / "avatar.vrm"
    report_path = tmp_path / "build.json"
    target = output_path if existing_target == "vrm" else report_path
    target.write_text("existing", encoding="utf-8")

    result = _finalizer()(
        spec=spec,
        output_path=output_path,
        report_path=report_path,
        execution_config=BlenderExecutionConfig(),
        executor=executor,
    )

    assert result.success is False
    assert "already exists" in result.error
    assert target.read_text(encoding="utf-8") == "existing"
    assert executor.calls == []


def test_nonzero_or_timeout_result_never_publishes_outputs(tmp_path: Path) -> None:
    spec = _spec()
    executor = FakeExecutor(
        spec,
        result=BlenderExecutionResult(124, "partial", "timed out", 0.1, timed_out=True),
    )

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "avatar.vrm",
        report_path=tmp_path / "build.json",
        execution_config=BlenderExecutionConfig(),
        executor=executor,
    )

    assert result.success is False
    assert result.exit_code == 124
    assert result.timed_out is True
    assert "timed out" in result.error
    assert not (tmp_path / "avatar.vrm").exists()
    assert not (tmp_path / "build.json").exists()
    _assert_no_staging_files(tmp_path)


def test_zero_exit_without_vrm_is_a_structured_failure(tmp_path: Path) -> None:
    spec = _spec()
    executor = FakeExecutor(spec, write_vrm=None)

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "avatar.vrm",
        report_path=tmp_path / "build.json",
        execution_config=BlenderExecutionConfig(),
        executor=executor,
    )

    assert result.success is False
    assert "did not create staged VRM" in result.error
    _assert_no_staging_files(tmp_path)


def test_rejects_malformed_vrm_and_mismatched_evidence(tmp_path: Path) -> None:
    spec = _spec()

    def write_invalid(path: Path, _specification: CompiledAssemblySpec) -> None:
        path.write_bytes(b"not a VRM")

    malformed_result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "malformed.vrm",
        report_path=tmp_path / "malformed.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(spec, write_vrm=write_invalid),
    )
    evidence = _evidence_payload(spec)
    evidence["character_id"] = "different-avatar"
    evidence_result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "mismatch.vrm",
        report_path=tmp_path / "mismatch.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(spec, evidence=evidence),
    )

    assert malformed_result.success is False
    assert "glTF" in malformed_result.error or "VRM" in malformed_result.error
    assert evidence_result.success is False
    assert "character_id" in evidence_result.error
    _assert_no_staging_files(tmp_path)


def test_accepts_adapter_expression_exported_as_vrm_custom_expression(
    tmp_path: Path,
) -> None:
    payload = _compiled_payload()
    payload["vrm_spec"]["expression_map"]["smirk"] = [  # type: ignore[index]
        {"shape_key": "smirk", "weight": 0.75}
    ]
    spec = CompiledAssemblySpec.model_validate(payload)

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "custom-expression.vrm",
        report_path=tmp_path / "custom-expression.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(
            spec,
            write_vrm=lambda path, specification: _write_vrm(
                path,
                specification,
                custom_expressions=frozenset({"smirk"}),
            ),
        ),
    )

    assert result.success is True


def test_rejects_duplicate_component_evidence(tmp_path: Path) -> None:
    spec = _spec()
    evidence = _evidence_payload(spec)
    selected_components = evidence["selected_components"]
    assert isinstance(selected_components, list)
    selected_components.append(dict(selected_components[0]))

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "duplicate-evidence.vrm",
        report_path=tmp_path / "duplicate-evidence.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(spec, evidence=evidence),
    )

    assert result.success is False
    assert "selected_components" in result.error


def test_rejects_vrm_without_bone_look_at(tmp_path: Path) -> None:
    spec = _spec()

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "expression-look-at.vrm",
        report_path=tmp_path / "expression-look-at.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(
            spec,
            write_vrm=lambda path, specification: _write_vrm(
                path,
                specification,
                look_at_type="expression",
            ),
        ),
    )

    assert result.success is False
    assert "look-at" in result.error


def test_rejects_vrm_with_wrong_humanoid_bone_target(tmp_path: Path) -> None:
    spec = _spec()

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "wrong-bone.vrm",
        report_path=tmp_path / "wrong-bone.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(
            spec,
            write_vrm=lambda path, specification: _write_vrm(
                path,
                specification,
                bone_target_overrides={"head": "hips"},
            ),
        ),
    )

    assert result.success is False
    assert "humanoid bone target" in result.error


def test_rejects_vrm_with_wrong_expression_shape_key(tmp_path: Path) -> None:
    spec = _spec()

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "wrong-expression.vrm",
        report_path=tmp_path / "wrong-expression.json",
        execution_config=BlenderExecutionConfig(),
        executor=FakeExecutor(
            spec,
            write_vrm=lambda path, specification: _write_vrm(
                path,
                specification,
                expression_target_overrides={"blink": "aa"},
            ),
        ),
    )

    assert result.success is False
    assert "expression bindings" in result.error


def test_rejects_ambiguous_object_identities_before_blender(
    tmp_path: Path,
) -> None:
    payload = _compiled_payload()
    payload["components"][0]["object_name"] = "Armature"  # type: ignore[index]
    spec = CompiledAssemblySpec.model_validate(payload)
    executor = FakeExecutor(spec)

    result = _finalizer()(
        spec=spec,
        output_path=tmp_path / "duplicate-object.vrm",
        report_path=tmp_path / "duplicate-object.json",
        execution_config=BlenderExecutionConfig(),
        executor=executor,
    )

    assert result.success is False
    assert "object identities" in result.error
    assert executor.calls == []


def test_rolls_back_its_vrm_when_report_target_appears_during_execution(
    tmp_path: Path,
) -> None:
    spec = _spec()
    output_path = tmp_path / "avatar.vrm"
    report_path = tmp_path / "build.json"
    executor = FakeExecutor(
        spec,
        after_write=lambda: report_path.write_text("competitor", encoding="utf-8"),
    )

    result = _finalizer()(
        spec=spec,
        output_path=output_path,
        report_path=report_path,
        execution_config=BlenderExecutionConfig(),
        executor=executor,
    )

    assert result.success is False
    assert "already exists" in result.error
    assert output_path.exists() is False
    assert report_path.read_text(encoding="utf-8") == "competitor"
    _assert_no_staging_files(tmp_path)
