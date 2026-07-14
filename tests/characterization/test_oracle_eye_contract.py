"""Behavior-to-preserve tests for legacy preview render orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from seidr_smidja._internal.blender_runner import BlenderNotFoundError, RunnerResult
from seidr_smidja.oracle_eye.eye import (
    STANDARD_VIEWS,
    RenderError,
    RenderView,
    render,
)


class _AnnallRecorder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[Any] = []

    def log_event(self, _session_id: str, event: Any) -> None:
        if self.fail:
            raise RuntimeError("telemetry unavailable")
        self.events.append(event)


def _vrm(tmp_path: Path) -> Path:
    path = tmp_path / "avatar.vrm"
    path.write_bytes(b"vrm")
    return path


class TestPreviewRenderContract:
    def test_default_render_requests_all_standard_views_and_succeeds(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "renders"
        captured_args: list[str] = []

        def fake_run_blender(*, args, **_kwargs):
            captured_args.extend(args)
            for view in STANDARD_VIEWS:
                (output_dir / f"{view.value}.png").write_bytes(b"png")
            return RunnerResult(0, "rendered", "", 0.1)

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=fake_run_blender):
            result = render(_vrm(tmp_path), output_dir)

        requested = captured_args[captured_args.index("--views") + 1].split(",")
        assert requested == [view.value for view in STANDARD_VIEWS]
        assert result.success is True
        assert set(result.render_paths) == set(requested)
        assert result.errors == []

    def test_subset_accepts_enum_and_string_names_and_reads_resolution(
        self, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "renders"
        captured_args: list[str] = []
        requested = [RenderView.FRONT, "side"]

        def fake_run_blender(*, args, **_kwargs):
            captured_args.extend(args)
            for view in ("front", "side"):
                (output_dir / f"{view}.png").write_bytes(b"png")
            return RunnerResult(0, "", "", 0.1)

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=fake_run_blender):
            result = render(
                _vrm(tmp_path),
                output_dir,
                views=requested,
                config={"oracle_eye": {"resolution": [640, 480]}},
            )

        assert captured_args[captured_args.index("--views") + 1] == "front,side"
        assert captured_args[captured_args.index("--width") + 1] == "640"
        assert captured_args[captured_args.index("--height") + 1] == "480"
        assert result.resolution == (640, 480)
        assert result.success is True

    def test_missing_pngs_are_a_soft_failure_with_partial_paths(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "renders"

        def fake_run_blender(**_kwargs):
            (output_dir / "front.png").write_bytes(b"png")
            return RunnerResult(0, "", "", 0.1)

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=fake_run_blender):
            result = render(_vrm(tmp_path), output_dir, views=["front", "side"])

        assert result.success is False
        assert result.render_paths == {"front": output_dir / "front.png"}
        assert any("Missing rendered views" in error for error in result.errors)

    def test_nonzero_exit_is_a_soft_failure(self, tmp_path: Path) -> None:
        with patch(
            "seidr_smidja.oracle_eye.eye.run_blender",
            return_value=RunnerResult(6, "", "renderer failed", 0.1),
        ):
            result = render(_vrm(tmp_path), tmp_path / "renders", views=["front"])

        assert result.success is False
        assert any("code 6" in error for error in result.errors)

    def test_timeout_is_a_soft_failure_with_an_explicit_error(self, tmp_path: Path) -> None:
        with patch(
            "seidr_smidja.oracle_eye.eye.run_blender",
            return_value=RunnerResult(-9, "", "", 0.1, timed_out=True),
        ):
            result = render(_vrm(tmp_path), tmp_path / "renders", views=["front"])

        assert result.success is False
        assert "Blender render subprocess timed out." in result.errors

    @pytest.mark.parametrize(
        "runner_error, expected_message",
        [
            (BlenderNotFoundError("missing", []), "Blender not found"),
            (OSError("permission denied"), "Failed to launch Blender subprocess"),
        ],
    )
    def test_infrastructure_launch_errors_are_hard_failures(
        self,
        tmp_path: Path,
        runner_error: Exception,
        expected_message: str,
    ) -> None:
        with (
            patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=runner_error),
            pytest.raises(RenderError, match=expected_message),
        ):
            render(_vrm(tmp_path), tmp_path / "renders")

    def test_telemetry_failure_does_not_change_render_result(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "renders"

        def fake_run_blender(**_kwargs):
            (output_dir / "front.png").write_bytes(b"png")
            return RunnerResult(0, "", "", 0.1)

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=fake_run_blender):
            result = render(
                _vrm(tmp_path),
                output_dir,
                views=["front"],
                annall=_AnnallRecorder(fail=True),
                session_id="session-1",
            )

        assert result.success is True
