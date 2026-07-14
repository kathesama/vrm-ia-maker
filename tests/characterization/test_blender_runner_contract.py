"""Characterization and regression tests for the shared Blender runner."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from seidr_smidja._internal import blender_runner
from seidr_smidja._internal.blender_runner import (
    BlenderNotFoundError,
    RunnerResult,
    resolve_blender_executable,
    run_blender,
)


@pytest.fixture
def fake_blender(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "helpers" / "fake_blender.py"
    executable = tmp_path / "fake-blender"
    shutil.copyfile(source, executable)
    executable.chmod(0o755)
    return executable


@pytest.fixture
def dummy_script(tmp_path: Path) -> Path:
    script = tmp_path / "injected.py"
    script.write_text("pass\n", encoding="utf-8")
    return script


def _run_with_fake(
    fake_blender: Path,
    dummy_script: Path,
    arguments: list[str],
    *,
    timeout: float = 5.0,
    on_line=None,
) -> RunnerResult:
    with patch.dict(
        os.environ,
        {"SEIDR_BLENDER_PATH": str(fake_blender)},
        clear=True,
    ):
        return run_blender(
            dummy_script,
            arguments,
            timeout=timeout,  # type: ignore[arg-type]
            on_line=on_line,
        )


class TestExecutableResolutionContract:
    def test_primary_environment_variable_wins_over_legacy_variable(self, tmp_path: Path) -> None:
        primary = tmp_path / "primary"
        legacy = tmp_path / "legacy"
        primary.touch()
        legacy.touch()

        with patch.dict(
            os.environ,
            {
                "SEIDR_BLENDER_PATH": str(primary),
                "BLENDER_PATH": str(legacy),
            },
            clear=True,
        ):
            assert resolve_blender_executable() == primary

    def test_invalid_primary_environment_variable_falls_back_to_legacy(
        self, tmp_path: Path
    ) -> None:
        legacy = tmp_path / "legacy"
        legacy.touch()

        with patch.dict(
            os.environ,
            {
                "SEIDR_BLENDER_PATH": str(tmp_path / "missing"),
                "BLENDER_PATH": str(legacy),
            },
            clear=True,
        ):
            assert resolve_blender_executable() == legacy

    def test_explicit_config_path_wins_over_path_lookup(self, tmp_path: Path) -> None:
        configured = tmp_path / "configured"
        configured.touch()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value=str(tmp_path / "path-blender")),
        ):
            result = resolve_blender_executable({"blender": {"executable": str(configured)}})

        assert result == configured

    def test_path_lookup_wins_over_platform_hints(self, tmp_path: Path) -> None:
        path_blender = tmp_path / "path-blender"
        hint_blender = tmp_path / "hint-blender"
        hint_blender.touch()

        config = {
            "blender": {
                "platform_hints": {sys.platform: [str(hint_blender)]},
            }
        }
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("shutil.which", return_value=str(path_blender)),
        ):
            assert resolve_blender_executable(config) == path_blender

    def test_not_found_error_records_every_attempt(self, tmp_path: Path) -> None:
        config = {
            "blender": {
                "executable": str(tmp_path / "missing-config"),
                "platform_hints": {sys.platform: [str(tmp_path / "missing-hint")]},
            }
        }
        with (
            patch.dict(
                os.environ,
                {"SEIDR_BLENDER_PATH": str(tmp_path / "missing-env")},
                clear=True,
            ),
            patch("shutil.which", return_value=None),
            pytest.raises(BlenderNotFoundError) as exc_info,
        ):
            resolve_blender_executable(config)

        checked = exc_info.value.locations_checked
        assert any(item.startswith("env:SEIDR_BLENDER_PATH=") for item in checked)
        assert any(item.startswith("config:blender.executable=") for item in checked)
        assert "PATH:blender" in checked
        assert any(item.startswith("PATH:") and item != "PATH:blender" for item in checked)
        assert any(item.startswith("platform-hint(config):") for item in checked)
        assert "SEIDR_BLENDER_PATH" in str(exc_info.value)


class TestSubprocessContract:
    def test_constructs_the_exact_blender_invocation(
        self, fake_blender: Path, dummy_script: Path, tmp_path: Path
    ) -> None:
        record_path = tmp_path / "argv.json"
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "record-argv", "--record", str(record_path), "extra"],
        )

        assert result.returncode == 0
        assert json.loads(record_path.read_text(encoding="utf-8")) == [
            "--background",
            "--python",
            str(dummy_script),
            "--",
            "--scenario",
            "record-argv",
            "--record",
            str(record_path),
            "extra",
        ]

    def test_captures_stdout_in_order_and_streams_lines(
        self, fake_blender: Path, dummy_script: Path
    ) -> None:
        streamed: list[str] = []
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "stdout"],
            on_line=streamed.append,
        )

        assert result.stdout == "first\nsecond\nthird"
        assert streamed == ["first", "second", "third"]
        assert result.stderr == ""
        assert result.timed_out is False

    def test_callback_failure_does_not_stop_capture(
        self, fake_blender: Path, dummy_script: Path
    ) -> None:
        def failing_callback(_line: str) -> None:
            raise RuntimeError("observer failed")

        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "stdout"],
            on_line=failing_callback,
        )

        assert result.returncode == 0
        assert result.stdout == "first\nsecond\nthird"

    def test_captures_stdout_and_stderr_concurrently(
        self, fake_blender: Path, dummy_script: Path
    ) -> None:
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "stdout-and-stderr"],
        )

        assert result.stdout == "stdout-line"
        assert result.stderr == "stderr-line"

    def test_nonzero_exit_code_is_preserved(self, fake_blender: Path, dummy_script: Path) -> None:
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "nonzero", "--exit-code", "9"],
        )

        assert result.returncode == 9
        assert result.stderr == "build failed"
        assert result.timed_out is False

    def test_invalid_utf8_is_replaced_in_captured_output(
        self, fake_blender: Path, dummy_script: Path
    ) -> None:
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "invalid-utf8"],
        )

        assert result.stdout == "before-\ufffd-after"

    def test_silent_process_obeys_the_requested_timeout(
        self, fake_blender: Path, dummy_script: Path
    ) -> None:
        started = time.monotonic()
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "sleep", "--seconds", "30"],
            timeout=0.1,
        )
        elapsed = time.monotonic() - started

        assert result.timed_out is True
        assert result.returncode != 0
        assert elapsed < 2.0

    def test_large_stderr_cannot_deadlock_timeout_enforcement(
        self, fake_blender: Path, dummy_script: Path
    ) -> None:
        started = time.monotonic()
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            [
                "--scenario",
                "stderr-flood-sleep",
                "--bytes",
                str(1024 * 1024),
                "--seconds",
                "30",
            ],
            timeout=0.15,
        )
        elapsed = time.monotonic() - started

        assert result.timed_out is True
        assert len(result.stderr) == 1024 * 1024
        assert elapsed < 2.0

    @pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
    def test_timeout_force_kills_descendants_that_ignore_sigterm(
        self, fake_blender: Path, dummy_script: Path, tmp_path: Path
    ) -> None:
        child_pid_path = tmp_path / "child.pid"
        result = _run_with_fake(
            fake_blender,
            dummy_script,
            ["--scenario", "child-sleep", "--child-pid", str(child_pid_path)],
            timeout=0.3,
        )

        assert result.timed_out is True
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))

        deadline = time.monotonic() + 2.0
        while _process_is_running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _process_is_running(child_pid) is False

    @pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
    def test_timeout_still_applies_after_leader_exits_with_inherited_pipes(
        self, fake_blender: Path, dummy_script: Path, tmp_path: Path
    ) -> None:
        child_pid_path = tmp_path / "orphan-child.pid"
        started = time.monotonic()

        result = _run_with_fake(
            fake_blender,
            dummy_script,
            [
                "--scenario",
                "leader-exits-child-holds-pipes",
                "--child-pid",
                str(child_pid_path),
            ],
            timeout=0.3,
        )
        elapsed = time.monotonic() - started

        assert result.timed_out is True
        assert result.returncode == blender_runner._TIMEOUT_RETURN_CODE
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))

        deadline = time.monotonic() + 2.0
        while _process_is_running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.02)

        assert _process_is_running(child_pid) is False
        assert elapsed < 2.0

    def test_explicit_timeout_wins_over_configuration(self, dummy_script: Path) -> None:
        process = _completed_mock_process()
        with (
            patch.object(
                blender_runner, "resolve_blender_executable", return_value=Path("blender")
            ),
            patch("subprocess.Popen", return_value=process),
        ):
            run_blender(
                dummy_script,
                [],
                config={"blender": {"timeout_seconds": 9}},
                timeout=0.25,  # type: ignore[arg-type]
            )

        assert process.wait.call_args_list[0].kwargs["timeout"] == 0.25

    def test_configuration_timeout_is_used_when_explicit_value_is_absent(
        self, dummy_script: Path
    ) -> None:
        process = _completed_mock_process()
        with (
            patch.object(
                blender_runner, "resolve_blender_executable", return_value=Path("blender")
            ),
            patch("subprocess.Popen", return_value=process),
        ):
            run_blender(
                dummy_script,
                [],
                config={"blender": {"timeout_seconds": 0.75}},
            )

        assert process.wait.call_args_list[0].kwargs["timeout"] == 0.75

    @pytest.mark.skipif(os.name == "nt", reason="POSIX subprocess option assertion")
    def test_posix_launch_starts_a_new_process_session(self, dummy_script: Path) -> None:
        process = _completed_mock_process()
        with (
            patch.object(
                blender_runner, "resolve_blender_executable", return_value=Path("blender")
            ),
            patch("subprocess.Popen", return_value=process) as popen,
        ):
            run_blender(dummy_script, [])

        assert popen.call_args.kwargs["start_new_session"] is True
        assert "creationflags" not in popen.call_args.kwargs

    def test_windows_launch_uses_a_new_process_group(self, dummy_script: Path) -> None:
        process = _completed_mock_process()
        windows_flag = 0x00000200
        windows_executable = Path("blender.exe")
        with (
            patch.object(blender_runner.os, "name", "nt"),
            patch.object(
                blender_runner.subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                windows_flag,
                create=True,
            ),
            patch.object(
                blender_runner,
                "resolve_blender_executable",
                return_value=windows_executable,
            ),
            patch("subprocess.Popen", return_value=process) as popen,
        ):
            run_blender(dummy_script, [])

        assert popen.call_args.kwargs["creationflags"] == windows_flag
        assert "start_new_session" not in popen.call_args.kwargs

    def test_windows_timeout_uses_taskkill_for_the_process_tree(self) -> None:
        process = MagicMock()
        process.pid = 1234
        process.poll.side_effect = [None, None]

        with (
            patch.object(blender_runner.os, "name", "nt"),
            patch("subprocess.run") as run,
        ):
            blender_runner._terminate_process_tree(process)

        run.assert_called_once_with(
            ["taskkill", "/PID", "1234", "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=blender_runner._POST_TERMINATION_WAIT_SECONDS,
        )
        process.kill.assert_called_once_with()

    def test_launch_error_names_the_resolved_executable(self, dummy_script: Path) -> None:
        executable = Path("/opt/blender/blender")
        with (
            patch.object(blender_runner, "resolve_blender_executable", return_value=executable),
            patch("subprocess.Popen", side_effect=PermissionError("denied")),
            pytest.raises(OSError, match=str(executable)),
        ):
            run_blender(dummy_script, [])


def _completed_mock_process() -> MagicMock:
    process = MagicMock()
    process.stdout = io.StringIO("")
    process.stderr = io.StringIO("")
    process.returncode = 0
    process.wait.return_value = 0
    return process


def _process_is_running(pid: int) -> bool:
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        fields = proc_stat.read_text(encoding="utf-8").split()
        if len(fields) >= 3 and fields[2] == "Z":
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
