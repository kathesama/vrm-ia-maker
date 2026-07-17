"""Production Forge orchestration for Blender finalization and publication."""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from vrm_ia_maker.contracts import (
    BlenderBuildEvidence,
    CompiledAssemblySpec,
    ForgeBuildReport,
    VrmBuildSpec,
)
from vrm_ia_maker.forge.ports import (
    BlenderExecutionConfig,
    BlenderExecutionPort,
    BlenderExecutionResult,
)
from vrm_ia_maker.manifest_loader import load_forge_build_report

_GLTF_MAGIC = 0x46546C67
_GLTF_VERSION = 2
_JSON_CHUNK_TYPE = 0x4E4F534A
_BLENDER_SCRIPT = Path(__file__).parent / "blender" / "finalize_assembly.py"


@dataclass(frozen=True)
class ForgeFinalizationResult:
    """Typed outcome from one production Forge finalization attempt."""

    success: bool
    vrm_path: Path | None
    report_path: Path | None
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    error: str | None


def finalize_compiled_assembly(
    *,
    spec: CompiledAssemblySpec,
    output_path: Path,
    report_path: Path,
    execution_config: BlenderExecutionConfig,
    executor: BlenderExecutionPort,
) -> ForgeFinalizationResult:
    """Finalize one schema 1.1 assembly and publish a verified output pair."""
    output_target = output_path.resolve()
    report_target = report_path.resolve()

    contract_error = _validate_request(spec, output_target, report_target)
    if contract_error is not None:
        return _failure(contract_error)

    for target in (output_target, report_target):
        if target.exists():
            return _failure(f"Output target already exists: {target}.")

    try:
        output_target.parent.mkdir(parents=True, exist_ok=True)
        report_target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _failure(f"Cannot create Forge output directory: {exc}")

    token = uuid4().hex
    spec_stage = output_target.parent / f".forge-{token}.spec.json"
    vrm_stage = output_target.parent / f".forge-{token}.{output_target.name}"
    evidence_stage = report_target.parent / f".forge-{token}.evidence.json"
    report_stage = report_target.parent / f".forge-{token}.{report_target.name}"
    staging_paths = (spec_stage, vrm_stage, evidence_stage, report_stage)
    execution_result: BlenderExecutionResult | None = None
    published_vrm = False
    published_report = False

    try:
        spec_stage.write_text(
            spec.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            execution_result = executor.execute(
                script_path=_BLENDER_SCRIPT,
                arguments=(
                    "--spec",
                    str(spec_stage),
                    "--output",
                    str(vrm_stage),
                    "--evidence",
                    str(evidence_stage),
                ),
                config=execution_config,
            )
        except Exception as exc:
            return _failure(f"Blender execution failed: {exc}")

        if execution_result.timed_out:
            return _failure("Blender execution timed out.", execution_result)
        if execution_result.returncode != 0:
            return _failure(
                f"Blender exited with code {execution_result.returncode}.",
                execution_result,
            )
        if not vrm_stage.is_file() or vrm_stage.stat().st_size == 0:
            return _failure(
                "Blender did not create staged VRM output.",
                execution_result,
            )
        if not evidence_stage.is_file() or evidence_stage.stat().st_size == 0:
            return _failure(
                "Blender did not create staged build evidence.",
                execution_result,
            )

        try:
            evidence = BlenderBuildEvidence.model_validate_json(
                evidence_stage.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValidationError) as exc:
            return _failure(f"Blender build evidence is invalid: {exc}", execution_result)

        assert isinstance(spec.vrm_spec, VrmBuildSpec)
        evidence_error = _validate_evidence(spec, evidence)
        if evidence_error is not None:
            return _failure(evidence_error, execution_result)

        try:
            _validate_vrm(vrm_stage, spec)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            return _failure(f"Staged VRM validation failed: {exc}", execution_result)

        vrm_payload = vrm_stage.read_bytes()
        assert spec.base_adapter_id is not None
        assert spec.base_adapter_version is not None
        report = ForgeBuildReport(
            character_id=spec.character_id,
            display_name=spec.display_name,
            asset_pack_id=spec.asset_pack_id,
            base_adapter_id=spec.base_adapter_id,
            base_adapter_version=spec.base_adapter_version,
            vrm_path=output_target,
            vrm_sha256=hashlib.sha256(vrm_payload).hexdigest(),
            vrm_byte_length=len(vrm_payload),
            blender_exit_code=0,
            blender_duration_seconds=execution_result.duration_seconds,
            evidence=evidence,
        )
        report_stage.write_text(
            report.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        load_forge_build_report(report_stage)

        try:
            os.link(vrm_stage, output_target)
            published_vrm = True
            os.link(report_stage, report_target)
            published_report = True
        except FileExistsError as exc:
            _rollback_publication(
                output_target,
                report_target,
                published_vrm=published_vrm,
                published_report=published_report,
            )
            return _failure(
                f"Output target already exists during publication: {exc.filename}.",
                execution_result,
            )
        except OSError as exc:
            _rollback_publication(
                output_target,
                report_target,
                published_vrm=published_vrm,
                published_report=published_report,
            )
            return _failure(f"Forge output publication failed: {exc}", execution_result)

        return ForgeFinalizationResult(
            success=True,
            vrm_path=output_target,
            report_path=report_target,
            exit_code=execution_result.returncode,
            stdout=execution_result.stdout,
            stderr=execution_result.stderr,
            duration_seconds=execution_result.duration_seconds,
            timed_out=False,
            error=None,
        )
    except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        return _failure(f"Forge finalization failed: {exc}", execution_result)
    finally:
        for path in staging_paths:
            with suppress(OSError):
                path.unlink(missing_ok=True)


def _validate_request(
    spec: CompiledAssemblySpec,
    output_target: Path,
    report_target: Path,
) -> str | None:
    if spec.schema_version != "1.1" or not isinstance(spec.vrm_spec, VrmBuildSpec):
        return "Production Forge requires CompiledAssemblySpec schema 1.1."
    if spec.base_adapter_id is None or spec.base_adapter_version is None:
        return "Production Forge requires base adapter traceability."
    if output_target.suffix.lower() != ".vrm":
        return "Forge VRM output target must use the .vrm extension."
    if report_target.suffix.lower() != ".json":
        return "Forge report target must use the .json extension."
    if os.path.normcase(output_target) == os.path.normcase(report_target):
        return "Forge VRM and report targets must be different files."
    object_names = [
        spec.base_asset.object_name,
        *(component.object_name for component in spec.components),
        *(component.object_name for component in spec.disabled_components),
    ]
    if len(object_names) != len(set(object_names)):
        return "Production Forge requires unique object identities."
    return None


def _validate_evidence(
    spec: CompiledAssemblySpec,
    evidence: BlenderBuildEvidence,
) -> str | None:
    if evidence.character_id != spec.character_id:
        return "Blender evidence character_id does not match the compiled assembly."
    if (
        evidence.base_adapter_id != spec.base_adapter_id
        or evidence.base_adapter_version != spec.base_adapter_version
    ):
        return "Blender evidence base adapter identity does not match the compiled assembly."

    expected_components = sorted(
        (
            component.asset_id,
            component.slot.value,
            component.kind.value,
            component.object_name,
        )
        for component in spec.components
    )
    actual_components = sorted(
        (
            component.asset_id,
            component.slot.value,
            component.kind.value,
            component.object_name,
        )
        for component in evidence.selected_components
    )
    if actual_components != expected_components:
        return "Blender evidence selected_components do not match the compiled assembly."

    expected_disabled = sorted(
        (component.asset_id, component.slot.value, component.object_name)
        for component in spec.disabled_components
    )
    actual_disabled = sorted(
        (component.asset_id, component.slot.value, component.object_name)
        for component in evidence.disabled_components
    )
    if actual_disabled != expected_disabled:
        return "Blender evidence disabled_components do not match the compiled assembly."

    assert isinstance(spec.vrm_spec, VrmBuildSpec)
    if sorted(evidence.humanoid_bones) != sorted(spec.vrm_spec.bones):
        return "Blender evidence humanoid_bones do not match VrmBuildSpec."
    if sorted(evidence.expressions) != sorted(spec.vrm_spec.expression_map):
        return "Blender evidence expressions do not match VrmBuildSpec."
    if evidence.look_at != spec.vrm_spec.look_at:
        return "Blender evidence look_at does not match VrmBuildSpec."
    if evidence.metadata != spec.vrm_spec.metadata:
        return "Blender evidence metadata does not match VrmBuildSpec."

    scene_objects = set(evidence.scene_objects_before_export)
    required_objects = {
        spec.base_asset.object_name,
        *(component.object_name for component in spec.components),
    }
    if not required_objects.issubset(scene_objects):
        return "Blender evidence scene is missing selected objects."
    disabled_objects = {component.object_name for component in spec.disabled_components}
    if scene_objects & disabled_objects:
        return "Blender evidence scene contains disabled objects."
    return None


def _validate_vrm(path: Path, spec: CompiledAssemblySpec) -> None:
    document = _read_glb_json(path)
    extensions_used = document.get("extensionsUsed", [])
    if not isinstance(extensions_used, list) or "VRMC_vrm" not in extensions_used:
        raise ValueError("VRM does not declare the VRMC_vrm extension.")
    extensions = document.get("extensions", {})
    if not isinstance(extensions, dict):
        raise ValueError("VRM extensions must be an object.")
    vrm = extensions.get("VRMC_vrm")
    if not isinstance(vrm, dict):
        raise ValueError("VRM does not contain the VRMC_vrm extension.")
    spec_version = vrm.get("specVersion")
    if not isinstance(spec_version, str) or not spec_version.startswith("1."):
        raise ValueError(f"Expected VRM 1.x, found {spec_version!r}.")

    assert isinstance(spec.vrm_spec, VrmBuildSpec)
    nodes = document.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("VRM nodes must be an array.")
    human_bones = vrm.get("humanoid", {}).get("humanBones", {})
    if not isinstance(human_bones, dict):
        raise ValueError("VRM humanoid humanBones must be an object.")
    missing_bones = sorted(set(spec.vrm_spec.bones).difference(human_bones))
    if missing_bones:
        raise ValueError(f"VRM is missing humanoid bones: {missing_bones}.")
    for slot_name, expected_target in spec.vrm_spec.bones.items():
        binding = human_bones.get(slot_name)
        if not isinstance(binding, dict):
            raise ValueError(f"VRM humanoid bone {slot_name!r} must be an object.")
        actual_target = _node_name(
            nodes,
            binding.get("node"),
            f"VRM humanoid bone {slot_name!r}",
        )
        if actual_target != expected_target:
            raise ValueError(
                f"VRM humanoid bone target mismatch for {slot_name!r}: "
                f"expected {expected_target!r}, found {actual_target!r}."
            )

    expressions = vrm.get("expressions", {})
    if not isinstance(expressions, dict):
        raise ValueError("VRM expressions must be an object.")
    preset_expressions = expressions.get("preset", {})
    custom_expressions = expressions.get("custom", {})
    if not isinstance(preset_expressions, dict):
        raise ValueError("VRM preset expressions must be an object.")
    if not isinstance(custom_expressions, dict):
        raise ValueError("VRM custom expressions must be an object.")
    exported_expressions = set(preset_expressions) | set(custom_expressions)
    missing_expressions = sorted(
        set(spec.vrm_spec.expression_map).difference(exported_expressions)
    )
    if missing_expressions:
        raise ValueError(f"VRM is missing expressions: {missing_expressions}.")
    for expression_name, expected_bindings in spec.vrm_spec.expression_map.items():
        expression_values = [
            section[expression_name]
            for section in (preset_expressions, custom_expressions)
            if expression_name in section
        ]
        if len(expression_values) != 1 or not isinstance(expression_values[0], dict):
            raise ValueError(
                f"VRM expression {expression_name!r} must have one definition."
            )
        actual_bindings = _read_expression_bindings(
            document,
            nodes,
            expression_name,
            expression_values[0],
        )
        expected_values = sorted(
            (binding.shape_key, binding.weight) for binding in expected_bindings
        )
        actual_values = sorted(actual_bindings)
        if len(actual_values) != len(expected_values) or any(
            actual_name != expected_name
            or not math.isclose(
                actual_weight,
                expected_weight,
                rel_tol=1e-6,
                abs_tol=1e-6,
            )
            for (actual_name, actual_weight), (expected_name, expected_weight) in zip(
                actual_values,
                expected_values,
                strict=True,
            )
        ):
            raise ValueError(
                f"VRM expression bindings do not match VrmBuildSpec for "
                f"{expression_name!r}."
            )

    look_at = vrm.get("lookAt")
    if not isinstance(look_at, dict) or look_at.get("type") != "bone":
        raise ValueError("VRM look-at must use bone mode.")

    metadata = vrm.get("meta", {})
    if not isinstance(metadata, dict) or metadata.get("name") != spec.display_name:
        raise ValueError("VRM metadata name does not match VrmBuildSpec.")
    authors = metadata.get("authors", [])
    if (
        not isinstance(authors, list)
        or spec.vrm_spec.metadata.author not in authors
    ):
        raise ValueError("VRM metadata author does not match VrmBuildSpec.")

    node_names = [
        node.get("name")
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("name"), str)
    ]
    selected_names = {component.object_name for component in spec.components}
    missing_selected = sorted(
        name for name in selected_names if node_names.count(name) == 0
    )
    if missing_selected:
        raise ValueError(f"VRM is missing selected component nodes: {missing_selected}.")
    ambiguous_selected = sorted(
        name for name in selected_names if node_names.count(name) > 1
    )
    if ambiguous_selected:
        raise ValueError(
            f"VRM contains ambiguous selected component nodes: {ambiguous_selected}."
        )
    disabled_names = {component.object_name for component in spec.disabled_components}
    leaked_disabled = sorted(name for name in disabled_names if name in node_names)
    if leaked_disabled:
        raise ValueError(f"VRM contains disabled component nodes: {leaked_disabled}.")


def _read_expression_bindings(
    document: dict[str, object],
    nodes: list[object],
    expression_name: str,
    expression: dict[str, object],
) -> list[tuple[str, float]]:
    raw_bindings = expression.get("morphTargetBinds")
    if not isinstance(raw_bindings, list):
        raise ValueError(
            f"VRM expression {expression_name!r} morphTargetBinds must be an array."
        )
    meshes = document.get("meshes")
    if not isinstance(meshes, list):
        raise ValueError("VRM meshes must be an array.")

    bindings: list[tuple[str, float]] = []
    for index, raw_binding in enumerate(raw_bindings):
        label = f"VRM expression {expression_name!r} binding {index}"
        if not isinstance(raw_binding, dict):
            raise ValueError(f"{label} must be an object.")
        node = _array_object(nodes, raw_binding.get("node"), f"{label} node")
        mesh = _array_object(meshes, node.get("mesh"), f"{label} mesh")
        extras = mesh.get("extras")
        if not isinstance(extras, dict):
            raise ValueError(f"{label} mesh extras must be an object.")
        target_names = extras.get("targetNames")
        if not isinstance(target_names, list) or not all(
            isinstance(name, str) for name in target_names
        ):
            raise ValueError(f"{label} targetNames must be an array of strings.")
        target_index = _array_index(
            target_names,
            raw_binding.get("index"),
            f"{label} target",
        )
        weight = raw_binding.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, int | float):
            raise ValueError(f"{label} weight must be a number.")
        bindings.append((target_names[target_index], float(weight)))
    return bindings


def _node_name(nodes: list[object], index: object, label: str) -> str:
    node = _array_object(nodes, index, f"{label} node")
    name = node.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{label} node must have a non-empty name.")
    return name


def _array_object(
    values: list[object],
    index: object,
    label: str,
) -> dict[str, object]:
    item = values[_array_index(values, index, label)]
    if not isinstance(item, dict):
        raise ValueError(f"{label} must reference an object.")
    return item


def _array_index(values: list[object], index: object, label: str) -> int:
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError(f"{label} index must be an integer.")
    if index < 0 or index >= len(values):
        raise ValueError(f"{label} index is out of range: {index}.")
    return index


def _read_glb_json(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if len(payload) < 20:
        raise ValueError("The VRM file is too short to be a glTF binary.")
    magic, version, total_length = struct.unpack_from("<III", payload, 0)
    if magic != _GLTF_MAGIC:
        raise ValueError("The VRM does not have the glTF binary magic header.")
    if version != _GLTF_VERSION:
        raise ValueError(f"Expected glTF 2.0, found version {version}.")
    if total_length != len(payload):
        raise ValueError(
            f"glTF length mismatch: header={total_length}, actual={len(payload)}."
        )
    json_length, chunk_type = struct.unpack_from("<II", payload, 12)
    if chunk_type != _JSON_CHUNK_TYPE:
        raise ValueError("The first glTF chunk is not JSON.")
    chunk_end = 20 + json_length
    if chunk_end > len(payload):
        raise ValueError("The glTF JSON chunk exceeds the file length.")
    document = json.loads(payload[20:chunk_end].rstrip(b"\x00 \t\r\n").decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("The glTF JSON chunk must contain an object.")
    return document


def _rollback_publication(
    output_target: Path,
    report_target: Path,
    *,
    published_vrm: bool,
    published_report: bool,
) -> None:
    if published_report:
        report_target.unlink(missing_ok=True)
    if published_vrm:
        output_target.unlink(missing_ok=True)


def _failure(
    error: str,
    execution_result: BlenderExecutionResult | None = None,
) -> ForgeFinalizationResult:
    return ForgeFinalizationResult(
        success=False,
        vrm_path=None,
        report_path=None,
        exit_code=None if execution_result is None else execution_result.returncode,
        stdout="" if execution_result is None else execution_result.stdout,
        stderr="" if execution_result is None else execution_result.stderr,
        duration_seconds=0.0 if execution_result is None else execution_result.duration_seconds,
        timed_out=False if execution_result is None else execution_result.timed_out,
        error=error,
    )
