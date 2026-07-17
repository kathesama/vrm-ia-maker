"""Unit tests for the production Blender execution port and retained adapter."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from seidr_smidja._internal.blender_runner import RunnerResult


def _module(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f"Missing production Forge module: {name}", pytrace=False)


def test_execution_configuration_requires_a_positive_timeout() -> None:
    ports = _module("vrm_ia_maker.forge.ports")
    config = ports.BlenderExecutionConfig(
        executable=Path("C:/tools/blender.exe"),
        timeout_seconds=42.5,
        platform_hints={"win32": (Path("C:/fallback/blender.exe"),)},
    )

    assert config.timeout_seconds == 42.5
    assert config.executable == Path("C:/tools/blender.exe")
    with pytest.raises(ValueError, match="positive"):
        ports.BlenderExecutionConfig(timeout_seconds=0)


def test_retained_adapter_translates_typed_execution_without_copying_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = _module("vrm_ia_maker.forge.ports")
    adapter_module = _module("vrm_ia_maker.forge.adapters.retained_blender_runner")
    captured: dict[str, Any] = {}

    def fake_run_blender(**kwargs: object) -> RunnerResult:
        captured.update(kwargs)
        return RunnerResult(
            returncode=7,
            stdout="captured stdout",
            stderr="captured stderr",
            duration_seconds=1.25,
            timed_out=True,
        )

    monkeypatch.setattr(adapter_module, "run_blender", fake_run_blender)
    adapter = adapter_module.RetainedBlenderRunnerAdapter()
    config = ports.BlenderExecutionConfig(
        executable=Path("C:/tools/blender.exe"),
        timeout_seconds=9.5,
        platform_hints={"win32": (Path("C:/fallback/blender.exe"),)},
    )

    result = adapter.execute(
        script_path=Path("forge/blender/finalize_assembly.py"),
        arguments=("--spec", "compiled.json", "--output", "avatar.vrm"),
        config=config,
    )

    assert captured == {
        "script_path": Path("forge/blender/finalize_assembly.py"),
        "args": ["--spec", "compiled.json", "--output", "avatar.vrm"],
        "config": {
            "blender": {
                "executable": str(Path("C:/tools/blender.exe")),
                "timeout_seconds": 9.5,
                "platform_hints": {
                    "win32": [str(Path("C:/fallback/blender.exe"))],
                },
            }
        },
    }
    assert result == ports.BlenderExecutionResult(
        returncode=7,
        stdout="captured stdout",
        stderr="captured stderr",
        duration_seconds=1.25,
        timed_out=True,
    )


def test_retained_adapter_omits_optional_runner_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = _module("vrm_ia_maker.forge.ports")
    adapter_module = _module("vrm_ia_maker.forge.adapters.retained_blender_runner")
    captured: dict[str, Any] = {}

    def fake_run_blender(**kwargs: object) -> RunnerResult:
        captured.update(kwargs)
        return RunnerResult(0, "", "", 0.2)

    monkeypatch.setattr(adapter_module, "run_blender", fake_run_blender)

    adapter_module.RetainedBlenderRunnerAdapter().execute(
        script_path=Path("finalize.py"),
        arguments=(),
        config=ports.BlenderExecutionConfig(),
    )

    assert captured["config"] == {
        "blender": {
            "timeout_seconds": 300.0,
        }
    }
