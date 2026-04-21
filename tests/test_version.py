"""Tests for jira-version.py — project versions CRUD."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import click.testing
import pytest

_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str = "jira-version", subdir: str = "workflow"):
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_script()


def _make_mock_client(url: str = "https://jira.example.com"):
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    mc.url = url  # atlassian.Jira exposes .url on the client instance
    return mc


def _run(args, mock_client=None):
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_mod.cli, args)
    return result, mock_client


def _make_version(
    vid: str = "10042",
    name: str = "1.4.0",
    project: str = "PROJ",
    released: bool = False,
    archived: bool = False,
    description: str | None = None,
    start_date: str | None = None,
    release_date: str | None = None,
) -> dict:
    """Build a version dict matching the Jira REST API shape."""
    v = {
        "id": vid,
        "name": name,
        "projectId": 10000,
        "project": project,
        "released": released,
        "archived": archived,
        "self": f"https://jira.example.com/rest/api/2/version/{vid}",
    }
    if description is not None:
        v["description"] = description
    if start_date is not None:
        v["startDate"] = start_date
    if release_date is not None:
        v["releaseDate"] = release_date
    return v


class TestList:
    def test_list_flat_endpoint_default(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10042", "1.4.0", released=False,
                          start_date="2026-05-01", release_date="2026-05-31"),
            _make_version("10048", "1.6.0", released=False),
        ]
        result, _ = _run(["list", "PROJ"], mc)
        assert result.exit_code == 0, result.output
        # The flat endpoint returns ALL versions; filter happens client-side
        mc.get.assert_called_once_with("rest/api/2/project/PROJ/versions")
        assert "10042" in result.output
        assert "1.4.0" in result.output
        # Default --status unreleased: both are unreleased so both show
        assert "10048" in result.output

    def test_list_table_columns(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10042", "1.4.0", released=False,
                          start_date="2026-05-01", release_date="2026-05-31"),
        ]
        result, _ = _run(["list", "PROJ"], mc)
        assert result.exit_code == 0
        # Header keywords
        for header in ("ID", "NAME", "STATUS", "START", "RELEASE", "ISSUES"):
            assert header in result.output


class TestHelp:
    """All subcommands must respond to --help with exit code 0."""

    @pytest.mark.parametrize(
        "subcmd",
        ["list", "get", "create", "update", "release", "unrelease",
         "archive", "unarchive", "move", "merge", "delete"],
    )
    def test_subcommand_help(self, subcmd):
        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, [subcmd, "--help"])
        assert result.exit_code == 0, result.output

    def test_cli_help_lists_all_subcommands(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, ["--help"])
        assert result.exit_code == 0
        for sub in ("list", "get", "create", "update", "release", "unrelease",
                    "archive", "unarchive", "move", "merge", "delete"):
            assert sub in result.output
