"""H-017: Non-Blender unit tests for forge.runner and oracle_eye.eye.

These tests mock run_blender so they run in any environment.
Target: lift forge/runner.py above 28%, oracle_eye/eye.py above 36%.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ─── forge/runner.py non-Blender tests ───────────────────────────────────────


class TestForgeRunnerNonBlender:
    """Test the orchestration and pre-launch logic in forge.runner.build()."""

    def _make_spec(self, avatar_id: str = "forge_test") -> Any:
        from seidr_smidja.loom.schema import AvatarSpec

        return AvatarSpec.model_validate(
            {
                "spec_version": "1.0",
                "avatar_id": avatar_id,
                "display_name": "Forge Test",
                "base_asset_id": "vroid/sample_a",
                "metadata": {"author": "Test", "license": "CC0-1.0"},
            }
        )

    def test_build_raises_when_base_asset_missing(self, tmp_path: Path) -> None:
        from seidr_smidja.forge.exceptions import ForgeBuildError
        from seidr_smidja.forge.runner import build

        spec = self._make_spec()
        missing_base = tmp_path / "nonexistent.vrm"
        # Does not exist

        with pytest.raises(ForgeBuildError, match="Base asset not found"):
            build(spec, missing_base, tmp_path / "output")

    def test_build_raises_when_output_dir_uncreatable(self, tmp_path: Path) -> None:
        from seidr_smidja.forge.exceptions import ForgeBuildError
        from seidr_smidja.forge.runner import build

        spec = self._make_spec()
        base_asset = tmp_path / "base.vrm"
        base_asset.write_bytes(b"\x00" * 16)

        # Point at a path that can't be created (file as parent)
        bad_output = tmp_path / "base.vrm" / "cannot_create_here"

        with pytest.raises((ForgeBuildError, OSError)):
            build(spec, base_asset, bad_output)

    def test_build_constructs_correct_blender_args(self, tmp_path: Path) -> None:
        """Verify the blender args list contains spec, base, and output flags."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.forge.runner import build

        spec = self._make_spec("args_test")
        base_asset = tmp_path / "base.vrm"
        base_asset.write_bytes(b"\x00" * 16)
        output_dir = tmp_path / "output"

        captured_args: list[list[str]] = []

        def mock_run_blender(script_path, args, **kwargs):
            captured_args.append(list(args))
            # Create the expected VRM file so build() can find it
            vrm_path = output_dir / f"{spec.avatar_id}.vrm"
            output_dir.mkdir(parents=True, exist_ok=True)
            vrm_path.write_bytes(b"\x00" * 16)
            return RunnerResult(returncode=0, stdout="", stderr="", duration_seconds=0.1)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=mock_run_blender):
            build(spec, base_asset, output_dir)

        assert len(captured_args) == 1
        args = captured_args[0]
        assert "--spec" in args
        assert "--base" in args
        assert "--output" in args

    def test_build_returns_forge_result_on_blender_success(self, tmp_path: Path) -> None:
        """A zero exit code + vrm file created = success=True ForgeResult."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.forge.runner import ForgeResult, build

        spec = self._make_spec("success_test")
        base_asset = tmp_path / "base.vrm"
        base_asset.write_bytes(b"\x00" * 16)
        output_dir = tmp_path / "output"

        def mock_run_blender(script_path, args, **kwargs):
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{spec.avatar_id}.vrm").write_bytes(b"\x00" * 16)
            return RunnerResult(returncode=0, stdout="Build OK", stderr="", duration_seconds=0.5)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=mock_run_blender):
            result = build(spec, base_asset, output_dir)

        assert isinstance(result, ForgeResult)
        assert result.success is True
        assert result.vrm_path is not None

    def test_build_returns_failure_on_nonzero_exit_code(self, tmp_path: Path) -> None:
        """A non-zero exit code = success=False even if file would have been created."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.forge.runner import build

        spec = self._make_spec("fail_test")
        base_asset = tmp_path / "base.vrm"
        base_asset.write_bytes(b"\x00" * 16)
        output_dir = tmp_path / "output"

        def mock_run_blender(script_path, args, **kwargs):
            return RunnerResult(
                returncode=1, stdout="", stderr="Build failed", duration_seconds=0.1
            )

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=mock_run_blender):
            result = build(spec, base_asset, output_dir)

        assert result.success is False
        assert result.exit_code == 1

    def test_build_with_annall_logs_events(self, tmp_path: Path, null_annall: Any) -> None:
        """When annall is provided, forge.started and forge.completed events are logged."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.forge.runner import build

        spec = self._make_spec("annall_test")
        base_asset = tmp_path / "base.vrm"
        base_asset.write_bytes(b"\x00" * 16)
        output_dir = tmp_path / "output"

        events_logged: list[str] = []
        original_log_event = null_annall.log_event

        def tracking_log_event(session_id, event):
            events_logged.append(event.event_type)
            return original_log_event(session_id, event)

        null_annall.log_event = tracking_log_event
        session_id = null_annall.open_session({})

        def mock_run_blender(script_path, args, **kwargs):
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{spec.avatar_id}.vrm").write_bytes(b"\x00" * 16)
            return RunnerResult(returncode=0, stdout="", stderr="", duration_seconds=0.1)

        with patch("seidr_smidja.forge.runner.run_blender", side_effect=mock_run_blender):
            build(spec, base_asset, output_dir, annall=null_annall, session_id=session_id)

        assert "forge.started" in events_logged
        assert "forge.completed" in events_logged

    def test_build_raises_forge_build_error_when_blender_not_found(self, tmp_path: Path) -> None:
        """BlenderNotFoundError must be wrapped as ForgeBuildError."""
        from seidr_smidja._internal.blender_runner import BlenderNotFoundError
        from seidr_smidja.forge.exceptions import ForgeBuildError
        from seidr_smidja.forge.runner import build

        spec = self._make_spec("not_found_test")
        base_asset = tmp_path / "base.vrm"
        base_asset.write_bytes(b"\x00" * 16)

        with (
            patch(
                "seidr_smidja.forge.runner.run_blender",
                side_effect=BlenderNotFoundError("blender not found", []),
            ),
            pytest.raises(ForgeBuildError, match="Blender not found"),
        ):
            build(spec, base_asset, tmp_path / "output")


# ─── oracle_eye/eye.py non-Blender tests ─────────────────────────────────────


class TestOracleEyeNonBlender:
    """H-017: Test oracle_eye.render() pre-launch logic and result shaping."""

    def test_render_raises_when_vrm_missing(self, tmp_path: Path) -> None:
        from seidr_smidja.oracle_eye.eye import RenderError, render

        vrm_path = tmp_path / "nonexistent.vrm"
        with pytest.raises(RenderError, match="VRM file not found"):
            render(vrm_path, tmp_path / "output")

    def test_render_returns_result_on_blender_success(self, tmp_path: Path) -> None:
        """When run_blender returns success, RenderResult.success must be True."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.oracle_eye.eye import RenderResult, render

        vrm_path = tmp_path / "test.vrm"
        vrm_path.write_bytes(b"\x00" * 16)
        output_dir = tmp_path / "renders"

        def mock_run_blender(script_path, args, **kwargs):
            output_dir.mkdir(parents=True, exist_ok=True)
            from seidr_smidja.oracle_eye.eye import STANDARD_VIEWS

            for view in STANDARD_VIEWS:
                (output_dir / f"{view.value}.png").write_bytes(b"\x00" * 16)
            return RunnerResult(returncode=0, stdout="render ok", stderr="", duration_seconds=0.2)

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=mock_run_blender):
            result = render(vrm_path, output_dir)

        assert isinstance(result, RenderResult)
        assert result.success is True
        assert result.errors == []

    def test_render_returns_failure_result_on_nonzero_exit(self, tmp_path: Path) -> None:
        """Blender exit code != 0 produces a RenderResult with success=False (D-006)."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.oracle_eye.eye import render

        vrm_path = tmp_path / "test.vrm"
        vrm_path.write_bytes(b"\x00" * 16)
        output_dir = tmp_path / "renders"

        def mock_run_blender(script_path, args, **kwargs):
            return RunnerResult(
                returncode=1, stdout="", stderr="render failed", duration_seconds=0.1
            )

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=mock_run_blender):
            result = render(vrm_path, output_dir)

        # D-006: Oracle Eye failures are soft — RenderResult returned, not an exception
        assert result.success is False

    def test_render_raises_on_blender_not_found(self, tmp_path: Path) -> None:
        """BlenderNotFoundError must be wrapped as RenderError."""
        from seidr_smidja._internal.blender_runner import BlenderNotFoundError
        from seidr_smidja.oracle_eye.eye import RenderError, render

        vrm_path = tmp_path / "test.vrm"
        vrm_path.write_bytes(b"\x00" * 16)

        with (
            patch(
                "seidr_smidja.oracle_eye.eye.run_blender",
                side_effect=BlenderNotFoundError("not found", []),
            ),
            pytest.raises(RenderError),
        ):
            render(vrm_path, tmp_path / "output")

    def test_list_standard_views_returns_all_views(self) -> None:
        from seidr_smidja.oracle_eye.eye import RenderView, list_standard_views

        views = list_standard_views()
        assert len(views) == len(list(RenderView))

    def test_render_uses_full_standard_views_when_none_given(self, tmp_path: Path) -> None:
        """When views=None, all STANDARD_VIEWS must be requested."""
        from seidr_smidja._internal.blender_runner import RunnerResult
        from seidr_smidja.oracle_eye.eye import STANDARD_VIEWS, render

        vrm_path = tmp_path / "test.vrm"
        vrm_path.write_bytes(b"\x00" * 16)

        captured_args: list[list[str]] = []

        def mock_run_blender(script_path, args, **kwargs):
            captured_args.append(list(args))
            return RunnerResult(returncode=1, stdout="", stderr="", duration_seconds=0.1)

        with patch("seidr_smidja.oracle_eye.eye.run_blender", side_effect=mock_run_blender):
            render(vrm_path, tmp_path / "output", views=None)

        assert len(captured_args) == 1
        args_str = " ".join(captured_args[0])
        # All standard views should appear in the args
        for view in STANDARD_VIEWS:
            assert view.value in args_str, f"View '{view.value}' not in blender args"
