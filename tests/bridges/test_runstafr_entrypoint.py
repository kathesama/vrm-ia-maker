"""Tests for the temporary legacy CLI compatibility entrypoint."""

from __future__ import annotations

from unittest.mock import patch

from seidr_smidja.bridges.runstafr.entrypoint import main


def test_version_flag_reports_legacy_command_and_new_distribution(capsys) -> None:
    assert main(["--version"]) is None
    assert capsys.readouterr().out == "seidr, version 0.1.0.dev0\n"


def test_version_command_reports_new_distribution(capsys) -> None:
    assert main(["version"]) is None
    assert capsys.readouterr().out == "vrm-ia-maker 0.1.0.dev0\n"


def test_non_version_command_delegates_without_rewriting_arguments() -> None:
    args = ["build", "character.yaml", "--json"]
    with patch(
        "seidr_smidja.bridges.runstafr.entrypoint._delegate_to_legacy_cli",
        return_value=None,
    ) as delegate:
        assert main(args) is None

    delegate.assert_called_once_with(args)
