"""Shared Blender subprocess execution for retained build and render paths.

This module is the single source of truth for Blender executable discovery,
subprocess lifecycle management, bounded execution, and output capture. Forge
and preview rendering depend on this seam but do not own its process mechanics.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

logger = logging.getLogger(__name__)

# Platform-specific paths remain a temporary compatibility fallback. New paths
# belong in config/defaults.yaml under blender.platform_hints.
_PLATFORM_HINTS: dict[str, list[str]] = {
    "win32": [
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
    ],
    "linux": ["/usr/bin/blender", "/usr/local/bin/blender"],
    "darwin": [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "/opt/homebrew/bin/blender",
    ],
}

_DEFAULT_TIMEOUT_SECONDS = 300.0
_TERMINATION_GRACE_SECONDS = 0.5
_POST_TERMINATION_WAIT_SECONDS = 5.0
_READER_JOIN_TIMEOUT_SECONDS = 2.0
_TIMEOUT_RETURN_CODE = 124  # Conventional command timeout status.


class BlenderNotFoundError(RuntimeError):
    """Raised when the Blender executable cannot be located."""

    def __init__(self, message: str, locations_checked: list[str]) -> None:
        super().__init__(message)
        self.locations_checked = locations_checked


@dataclass
class RunnerResult:
    """Structured result from a Blender subprocess invocation."""

    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


def resolve_blender_executable(config: dict[str, Any] | None = None) -> Path:
    """Resolve Blender using environment, configuration, PATH, then hints.

    Resolution order is intentionally stable during migration:

    1. ``SEIDR_BLENDER_PATH``
    2. legacy ``BLENDER_PATH``
    3. explicit ``blender.executable`` file path
    4. the ``blender`` command on ``PATH``
    5. a configured executable name on ``PATH``
    6. configured platform hints
    7. deprecated built-in platform hints
    """

    checked: list[str] = []

    for variable_name in ("SEIDR_BLENDER_PATH", "BLENDER_PATH"):
        value = os.environ.get(variable_name)
        if not value:
            continue
        checked.append(f"env:{variable_name}={value}")
        candidate = Path(value)
        if candidate.is_file():
            logger.debug("Blender resolved through %s: %s", variable_name, candidate)
            return candidate

    blender_config = (config or {}).get("blender", {})
    configured_executable = blender_config.get("executable")
    if configured_executable and configured_executable != "blender":
        checked.append(f"config:blender.executable={configured_executable}")
        candidate = Path(configured_executable)
        if candidate.is_file():
            logger.debug("Blender resolved through explicit configuration: %s", candidate)
            return candidate

    path_candidate = shutil.which("blender")
    checked.append("PATH:blender")
    if path_candidate:
        logger.debug("Blender resolved through PATH: %s", path_candidate)
        return Path(path_candidate)

    configured_command = configured_executable or "blender"
    if configured_command != "blender":
        path_candidate = shutil.which(configured_command)
        checked.append(f"PATH:{configured_command}")
        if path_candidate:
            logger.debug(
                "Blender resolved through configured PATH command %s: %s",
                configured_command,
                path_candidate,
            )
            return Path(path_candidate)

    import sys

    configured_hints: list[str] = []
    platform_hints = blender_config.get("platform_hints", {})
    if isinstance(platform_hints, dict):
        raw_hints = platform_hints.get(sys.platform, [])
        if isinstance(raw_hints, list):
            configured_hints = [str(hint) for hint in raw_hints]

    if configured_hints:
        hints = configured_hints
        hint_source = "config"
    else:
        hints = _PLATFORM_HINTS.get(sys.platform, [])
        hint_source = "deprecated-constant"

    for hint in hints:
        checked.append(f"platform-hint({hint_source}):{hint}")
        candidate = Path(hint)
        if candidate.is_file():
            logger.debug(
                "Blender resolved through platform hint (%s): %s",
                hint_source,
                candidate,
            )
            return candidate

    raise BlenderNotFoundError(
        "Blender executable not found. Set SEIDR_BLENDER_PATH to the full "
        "executable path or configure blender.executable in config/user.yaml.",
        locations_checked=checked,
    )


def _subprocess_group_options() -> dict[str, Any]:
    """Return platform-specific options that isolate the Blender process tree."""

    if os.name == "nt":
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        }
    return {"start_new_session": True}


def _drain_stream(
    stream: IO[str],
    output: list[str],
    errors: list[Exception],
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Drain one subprocess stream without allowing callbacks to stop capture."""

    try:
        for line in stream:
            normalized = line.rstrip("\n")
            output.append(normalized)
            if on_line is not None:
                try:
                    on_line(normalized)
                except Exception:
                    logger.debug("Blender stdout callback failed", exc_info=True)
    except Exception as exc:  # pragma: no cover - platform pipe failures are rare
        errors.append(exc)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate the Blender process group, even after its leader has exited."""

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_POST_TERMINATION_WAIT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.warning(
                "Unable to terminate Blender with taskkill; falling back to process.kill()",
                exc_info=True,
            )
        if process.poll() is None:
            process.kill()
        return

    # POSIX launches Blender with start_new_session=True, so the process ID is
    # also the process-group ID. The group may still contain descendants after
    # the leader exits, so process.poll() must not short-circuit this cleanup.
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        logger.warning(
            "Unable to terminate the Blender process group; falling back to process.kill()",
            exc_info=True,
        )
        if process.poll() is None:
            process.kill()
        return

    deadline = time.monotonic() + _TERMINATION_GRACE_SECONDS
    while time.monotonic() < deadline:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return
        except OSError:
            break
        time.sleep(0.02)

    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        logger.warning(
            "Unable to force-kill the Blender process group; falling back to process.kill()",
            exc_info=True,
        )
        if process.poll() is None:
            process.kill()


def _close_pipe(pipe: IO[Any] | None) -> None:
    """Close a subprocess pipe after its reader thread has stopped."""

    if pipe is None:
        return
    with contextlib.suppress(AttributeError, OSError):
        pipe.close()


def _wait_for_reader_threads(
    readers: list[threading.Thread],
    deadline: float,
) -> bool:
    """Wait until all output readers finish or the monotonic deadline expires."""

    for reader in readers:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        reader.join(timeout=remaining)
    return all(not reader.is_alive() for reader in readers)


def _wait_for_process_after_termination(process: subprocess.Popen[str]) -> None:
    """Reap the direct Blender process without blocking indefinitely."""

    try:
        process.wait(timeout=_POST_TERMINATION_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        logger.error(
            "Blender process did not terminate within %.1f seconds after timeout",
            _POST_TERMINATION_WAIT_SECONDS,
        )
        if process.poll() is None:
            with contextlib.suppress(OSError):
                process.kill()
            try:
                process.wait(timeout=_POST_TERMINATION_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.error("Blender process remained unreaped after the final kill attempt")


def run_blender(
    script_path: Path,
    args: list[str],
    config: dict[str, Any] | None = None,
    timeout: int | None = None,
    on_line: Callable[[str], None] | None = None,
) -> RunnerResult:
    """Launch Blender with bounded execution and concurrent output capture.

    The invocation remains ``blender --background --python <script> -- <args>``.
    The timeout covers both the direct process and output streams inherited by
    descendants, so a child cannot keep the runner blocked after Blender exits.
    """

    blender_executable = resolve_blender_executable(config)
    timeout_seconds = (
        float(timeout)
        if timeout is not None
        else float(
            (config or {}).get("blender", {}).get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        )
    )

    command: list[str] = [
        str(blender_executable),
        "--background",
        "--python",
        str(script_path),
        "--",
        *args,
    ]

    logger.debug("Launching Blender subprocess: %s", " ".join(command))
    start_time = time.monotonic()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    reader_errors: list[Exception] = []
    timed_out = False

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_subprocess_group_options(),
        )
    except OSError as exc:
        raise OSError(
            f"Failed to launch Blender subprocess. Executable: {blender_executable}. Error: {exc}"
        ) from exc

    if process.stdout is None or process.stderr is None:
        logger.error(
            "Blender subprocess stdout/stderr are None despite PIPE configuration. "
            "Output cannot be captured safely."
        )
        try:
            process.kill()
            process.wait(timeout=_POST_TERMINATION_WAIT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            logger.error("Unable to stop Blender after invalid pipe state", exc_info=True)
        duration = time.monotonic() - start_time
        return RunnerResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout="",
            stderr="",
            duration_seconds=duration,
            timed_out=False,
        )

    readers = [
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, stdout_lines, reader_errors, on_line),
            name="blender-stdout-reader",
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, stderr_lines, reader_errors),
            name="blender-stderr-reader",
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        logger.warning(
            "Blender subprocess timed out after %.3f seconds (script: %s)",
            timeout_seconds,
            script_path,
        )
    else:
        if not _wait_for_reader_threads(readers, deadline):
            timed_out = True
            logger.warning(
                "Blender subprocess output remained open after the process leader exited; "
                "terminating descendants at the %.3f-second deadline (script: %s)",
                timeout_seconds,
                script_path,
            )

    readers_finished = all(not reader.is_alive() for reader in readers)
    if timed_out:
        _terminate_process_tree(process)
        _wait_for_process_after_termination(process)
        readers_finished = _wait_for_reader_threads(
            readers,
            time.monotonic() + _READER_JOIN_TIMEOUT_SECONDS,
        )

    if readers_finished:
        # Closing TextIOWrapper objects is safe only after their reader threads
        # have exited. Closing them while a thread is blocked in iteration can
        # deadlock on CPython's internal I/O lock.
        _close_pipe(process.stdout)
        _close_pipe(process.stderr)
    else:
        logger.error(
            "Blender output readers remained blocked after process-tree termination; "
            "returning without closing their streams to preserve bounded execution"
        )

    for error in reader_errors:
        logger.error("Error reading Blender subprocess output: %s", error)

    duration = time.monotonic() - start_time
    returncode = process.returncode if process.returncode is not None else -1
    if timed_out and returncode == 0:
        # A leader may exit successfully while a descendant keeps inherited
        # output pipes open. Preserve timeout failure semantics for Forge.
        returncode = _TIMEOUT_RETURN_CODE

    result = RunnerResult(
        returncode=returncode,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
        duration_seconds=duration,
        timed_out=timed_out,
    )

    logger.debug(
        "Blender subprocess finished: returncode=%d, duration=%.3fs, timed_out=%s",
        returncode,
        duration,
        timed_out,
    )
    return result
