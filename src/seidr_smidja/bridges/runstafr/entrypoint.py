"""Compatibility entrypoint for the legacy ``seidr`` command.

The distribution is now named ``vrm-ia-maker``. This narrow wrapper keeps the
legacy executable available during migration while reporting the installed
project identity correctly. All non-version commands continue to delegate to
the inherited Click application unchanged.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from typing import NoReturn

_DISTRIBUTION_NAME = "vrm-ia-maker"
_FALLBACK_VERSION = "0.1.0.dev0"


def _distribution_version() -> str:
    """Return the installed VRM IA Maker distribution version."""
    try:
        return version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return _FALLBACK_VERSION


def _delegate_to_legacy_cli(args: Sequence[str] | None) -> NoReturn | None:
    """Delegate non-version commands to the inherited Click application."""
    from seidr_smidja.bridges.runstafr.cli import cli

    if args is None:
        cli(standalone_mode=True)
        return None

    cli.main(args=list(args), prog_name="seidr", standalone_mode=False)
    return None


def main(argv: Sequence[str] | None = None) -> NoReturn | None:
    """Run the compatibility command surface."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(f"seidr, version {_distribution_version()}")
        return None
    if args == ["version"]:
        print(f"{_DISTRIBUTION_NAME} {_distribution_version()}")
        return None

    return _delegate_to_legacy_cli(None if argv is None else args)
