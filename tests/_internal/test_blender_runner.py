"""Tests for seidr_smidja._internal.blender_runner — AUDIT-004 coverage.

Verifies that resolve_blender_executable() reads platform hints from the config
dict when available (config-driven path), and falls back to the deprecated
_PLATFORM_HINTS constant when the config key is absent.

No Blender process is launched — all tests mock filesystem presence checks.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from seidr_smidja._internal.blender_runner import (
    _PLATFORM_HINTS,
    BlenderNotFoundError,
    resolve_blender_executable,
)


def _fake_isfile(path_obj: Path) -> bool:
    """Pretend every path we hand to this test suite exists as a file."""
    return True


class TestResolveBlenderExecutableConfigHints:
    """AUDIT-004: Runner reads platform hints from config when available."""

    def test_reads_platform_hints_from_config(self, tmp_path: Path) -> None:
        """When config contains blender.platform_hints for the current platform,
        those hints are used instead of the deprecated constant."""
        fake_blender = tmp_path / "blender_from_config.exe"
        fake_blender.touch()

        config: dict[str, Any] = {
            "blender": {
                "platform_hints": {
                    sys.platform: [str(fake_blender)],
                }
            }
        }

        # Patch env vars away and PATH lookup to ensure we reach step 4
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shutil.which", return_value=None),
        ):
            result = resolve_blender_executable(config=config)

        assert result == fake_blender

    def test_falls_back_to_deprecated_constant_when_config_key_absent(self, tmp_path: Path) -> None:
        """When config has no blender.platform_hints key, the _PLATFORM_HINTS
        constant is used as a fallback (deprecated but still present in v0.1)."""
        # We need a path from _PLATFORM_HINTS that we can fake as existing.
        platform_hints = _PLATFORM_HINTS.get(sys.platform, [])
        if not platform_hints:
            pytest.skip(f"No _PLATFORM_HINTS entries for platform '{sys.platform}'")

        first_hint = platform_hints[0]

        config: dict[str, Any] = {
            "blender": {
                # Intentionally NO platform_hints key
                "executable": "blender",
            }
        }

        # Patch Path.is_file as an unbound method — the mock receives `self` as
        # the Path instance, so the lambda must accept and use it correctly.
        def _fake_is_file(path_self: Path) -> bool:
            return str(path_self) == first_hint

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shutil.which", return_value=None),
            patch.object(Path, "is_file", _fake_is_file),
        ):
            result = resolve_blender_executable(config=config)

        assert str(result) == first_hint

    def test_config_hints_for_other_platform_not_used(self, tmp_path: Path) -> None:
        """Hints keyed under a different platform name do not affect resolution
        for the current platform."""
        other_platform = "win32" if sys.platform != "win32" else "linux"
        fake_blender = tmp_path / "wrong_platform.exe"
        fake_blender.touch()

        config: dict[str, Any] = {
            "blender": {
                "platform_hints": {
                    other_platform: [str(fake_blender)],
                }
            }
        }

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.is_file", return_value=False),
            pytest.raises(BlenderNotFoundError),
        ):
            resolve_blender_executable(config=config)

    def test_no_config_no_hints_raises_not_found(self) -> None:
        """When config is None and no platform hints exist for the current platform,
        and PATH and env are both empty, BlenderNotFoundError is raised."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.is_file", return_value=False),
            pytest.raises(BlenderNotFoundError),
        ):
            resolve_blender_executable(config=None)

    def test_env_var_takes_precedence_over_config_hints(self, tmp_path: Path) -> None:
        """SEIDR_BLENDER_PATH env var always wins over config platform hints."""
        env_blender = tmp_path / "env_blender.exe"
        env_blender.touch()

        config: dict[str, Any] = {
            "blender": {
                "platform_hints": {
                    sys.platform: [str(tmp_path / "config_hint.exe")],
                }
            }
        }

        with patch.dict("os.environ", {"SEIDR_BLENDER_PATH": str(env_blender)}):
            result = resolve_blender_executable(config=config)

        assert result == env_blender
