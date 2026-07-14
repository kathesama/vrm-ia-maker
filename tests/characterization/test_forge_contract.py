"""Behavior-to-preserve tests for legacy Forge orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from seidr_smidja._internal.blender_runner import BlenderNotFoundError, RunnerResult
from seidr_smidja.forge.exceptions import ForgeBuildError
from seidr_smidja.forge.runner import ForgeResult, build
from seidr_smidja.loom.schema import AvatarSpec


def _spec(avatar_id: str = "characterized") -> AvatarSpec:
    return AvatarSpec.model_validate(
        {
            "spec_version": "1.0",
            "avatar_id": avatar_id,
            "display_name": "Characterized Avatar",
            "base_asset_id": "vroid/sample_a",
            "metadata": {"author": "Test", "license": "CC0-1.0"},
        }
    )


def _base_asset(tmp_path: Path) -> Path:
    asset = tmp_path / "base.vrm"
    asset.write_bytes(b"test-base")
    return asset


class _AnnallRecorder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[Any] = []

    def log_event(self, _session_id: str, event: Any) -> None:
        if self.fail:
            raise RuntimeError("telemetry unavailable")
        self.events.append(event)


class TestForgeOrchestrationContract:
    def test_serializes_spec_and_builds_exact_blender_arguments(self, tmp_path: Path) -> None:
        spec = _spec("argument-contract")
        output_dir = tmp_path / "output"
        captured: dict[str, Any] = {}

        def fake_run_blender(*, script_path, args, on_line, **_kwargs):
            captured["script_path"] = script_path
            captured["args"] = list(args)
            spec_path = Path(args[args.index("--spec") + 1])
            captured["spec_path"] = spec_path
            captured["spec_data"] = json.loads(spec_path.read_text(encoding="utf-8"))
            on_line("forge-line")
            output_path = Path(args[args.index("--output") + 1])
            output_path.write_bytes(b"vrm")
            return RunnerResult(0, "forge-line", "", 0.1)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=fake_run_blender):
            result = build(spec, _base_asset(tmp_path), output_dir)

        assert captured["args"][0::2] == ["--spec", "--base", "--output"]
        assert captured["spec_data"]["avatar_id"] == "argument-contract"
        assert captured["args"][-1] == str(output_dir / "argument-contract.vrm")
        assert captured["spec_path"].exists() is False
        assert result.success is True
        assert result.stdout_capture == "forge-line"

    def test_creates_output_directory_before_invoking_runner(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "nested" / "output"

        def fake_run_blender(*, args, **_kwargs):
            assert output_dir.is_dir()
            Path(args[args.index("--output") + 1]).write_bytes(b"vrm")
            return RunnerResult(0, "", "", 0.1)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=fake_run_blender):
            result = build(_spec(), _base_asset(tmp_path), output_dir)

        assert result.success is True

    def test_zero_exit_without_output_file_is_a_structured_failure(self, tmp_path: Path) -> None:
        with patch(
            "seidr_smidja.forge.runner.run_blender",
            return_value=RunnerResult(0, "done", "", 0.1),
        ):
            result = build(_spec(), _base_asset(tmp_path), tmp_path / "output")

        assert isinstance(result, ForgeResult)
        assert result.success is False
        assert result.exit_code == 0
        assert result.vrm_path is None

    def test_nonzero_exit_keeps_partial_output_visible_but_marks_failure(
        self, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "output"

        def fake_run_blender(*, args, **_kwargs):
            Path(args[args.index("--output") + 1]).write_bytes(b"partial")
            return RunnerResult(4, "partial", "failed", 0.1)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=fake_run_blender):
            result = build(_spec("partial"), _base_asset(tmp_path), output_dir)

        assert result.success is False
        assert result.exit_code == 4
        assert result.vrm_path == output_dir / "partial.vrm"
        assert result.stderr_capture == "failed"

    def test_timeout_state_is_included_in_failure_telemetry(self, tmp_path: Path) -> None:
        recorder = _AnnallRecorder()
        with patch(
            "seidr_smidja.forge.runner.run_blender",
            return_value=RunnerResult(-9, "partial", "timeout", 0.1, timed_out=True),
        ):
            result = build(
                _spec("timed-out"),
                _base_asset(tmp_path),
                tmp_path / "output",
                annall=recorder,
                session_id="session-1",
            )

        assert result.success is False
        failed_event = next(
            event for event in recorder.events if event.event_type == "forge.failed"
        )
        assert failed_event.payload["timed_out"] is True
        assert failed_event.payload["exit_code"] == -9

    def test_telemetry_failure_never_breaks_a_successful_build(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"

        def fake_run_blender(*, args, **_kwargs):
            Path(args[args.index("--output") + 1]).write_bytes(b"vrm")
            return RunnerResult(0, "", "", 0.1)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=fake_run_blender):
            result = build(
                _spec(),
                _base_asset(tmp_path),
                output_dir,
                annall=_AnnallRecorder(fail=True),
                session_id="session-1",
            )

        assert result.success is True

    @pytest.mark.parametrize(
        "runner_error, expected_message",
        [
            (BlenderNotFoundError("missing", []), "Blender not found"),
            (OSError("permission denied"), "Failed to launch Blender subprocess"),
        ],
    )
    def test_runner_launch_errors_are_wrapped_and_temp_files_are_removed(
        self,
        tmp_path: Path,
        runner_error: Exception,
        expected_message: str,
    ) -> None:
        temporary_spec_paths: list[Path] = []

        def failing_runner(*, args, **_kwargs):
            temporary_spec_paths.append(Path(args[args.index("--spec") + 1]))
            raise runner_error

        with (
            patch("seidr_smidja.forge.runner.run_blender", side_effect=failing_runner),
            pytest.raises(ForgeBuildError, match=expected_message),
        ):
            build(_spec(), _base_asset(tmp_path), tmp_path / "output")

        assert temporary_spec_paths
        assert all(path.exists() is False for path in temporary_spec_paths)
