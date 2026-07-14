#!/usr/bin/env python3
"""Small executable used to characterize Blender subprocess behavior."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _user_arguments() -> list[str]:
    arguments = sys.argv[1:]
    if "--" not in arguments:
        return []
    marker = arguments.index("--")
    return arguments[marker + 1 :]


def _value(arguments: list[str], name: str, default: str | None = None) -> str | None:
    if name not in arguments:
        return default
    index = arguments.index(name)
    if index + 1 >= len(arguments):
        raise SystemExit(f"Missing value for {name}")
    return arguments[index + 1]


def main() -> int:
    arguments = _user_arguments()
    scenario = _value(arguments, "--scenario", "success")

    if scenario == "record-argv":
        record_path = _value(arguments, "--record")
        if record_path is None:
            raise SystemExit("--record is required")
        Path(record_path).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
        return 0

    if scenario == "stdout":
        for line in ("first", "second", "third"):
            print(line, flush=True)
        return 0

    if scenario == "stdout-and-stderr":
        print("stdout-line", flush=True)
        print("stderr-line", file=sys.stderr, flush=True)
        return 0

    if scenario == "invalid-utf8":
        os.write(sys.stdout.fileno(), b"before-\xff-after\n")
        return 0

    if scenario == "nonzero":
        print("build failed", file=sys.stderr, flush=True)
        return int(_value(arguments, "--exit-code", "7") or "7")

    if scenario == "sleep":
        time.sleep(float(_value(arguments, "--seconds", "30") or "30"))
        return 0

    if scenario == "stderr-flood-sleep":
        size = int(_value(arguments, "--bytes", str(1024 * 1024)) or "0")
        os.write(sys.stderr.fileno(), b"x" * size)
        time.sleep(float(_value(arguments, "--seconds", "30") or "30"))
        return 0

    if scenario == "child-sleep":
        pid_path_value = _value(arguments, "--child-pid")
        if pid_path_value is None:
            raise SystemExit("--child-pid is required")
        pid_path = Path(pid_path_value)
        child_code = (
            "import os, signal, sys, time; "
            "from pathlib import Path; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8'); "
            "time.sleep(30)"
        )
        python_executable = sys.executable or shutil.which("python3")
        if not python_executable:
            raise SystemExit("Python executable not found")
        subprocess.Popen([python_executable, "-c", child_code, str(pid_path)])
        deadline = time.monotonic() + 2.0
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(30)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
