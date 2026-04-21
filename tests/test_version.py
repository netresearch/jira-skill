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


class TestListPaginated:
    def test_list_with_query_uses_paginated_endpoint(self):
        mc = _make_mock_client()
        mc.get.return_value = {
            "isLast": True,
            "values": [_make_version("10042", "1.4.0-rc1", released=False)],
        }
        result, _ = _run(["list", "PROJ", "--query", "rc"], mc)
        assert result.exit_code == 0, result.output
        # First positional arg to .get should be the paginated path
        called_path = mc.get.call_args.args[0]
        assert called_path == "rest/api/2/project/PROJ/version"
        called_params = mc.get.call_args.kwargs.get("params", {})
        assert called_params.get("query") == "rc"

    def test_list_with_order_by_uses_paginated_endpoint(self):
        mc = _make_mock_client()
        mc.get.return_value = {"isLast": True, "values": []}
        result, _ = _run(["list", "PROJ", "--order-by", "releaseDate"], mc)
        assert result.exit_code == 0, result.output
        called_params = mc.get.call_args.kwargs.get("params", {})
        assert called_params.get("orderBy") == "releaseDate"

    def test_list_paginated_follows_next_page(self):
        mc = _make_mock_client()
        mc.get.side_effect = [
            {"isLast": False, "values": [_make_version("10042", "1.4.0")], "startAt": 0, "maxResults": 1},
            {"isLast": True, "values": [_make_version("10045", "1.5.0")], "startAt": 1, "maxResults": 1},
        ]
        result, _ = _run(["list", "PROJ", "--query", "1."], mc)
        assert result.exit_code == 0, result.output
        assert mc.get.call_count == 2
        assert "10042" in result.output and "10045" in result.output

    def test_status_all_filters_nothing_on_paginated(self):
        mc = _make_mock_client()
        mc.get.return_value = {
            "isLast": True,
            "values": [
                _make_version("10042", "1.4.0", released=False),
                _make_version("10041", "1.3.0", released=True),
                _make_version("10030", "1.2.0", archived=True),
            ],
        }
        result, _ = _run(["list", "PROJ", "--query", ".", "--status", "all"], mc)
        assert result.exit_code == 0
        for vid in ("10042", "10041", "10030"):
            assert vid in result.output


class TestListOutputModes:
    def test_list_json_output(self):
        mc = _make_mock_client()
        versions = [_make_version("10042", "1.4.0"), _make_version("10048", "1.6.0")]
        mc.get.return_value = versions
        result, _ = _run(["--json", "list", "PROJ"], mc)
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert {v["id"] for v in parsed} == {"10042", "10048"}

    def test_list_quiet_output(self):
        mc = _make_mock_client()
        mc.get.return_value = [_make_version("10042", "1.4.0"), _make_version("10048", "1.6.0")]
        result, _ = _run(["--quiet", "list", "PROJ"], mc)
        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln]
        assert lines == ["10042", "10048"]


class TestGetById:
    def test_get_by_id(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=False, description="Q2 release",
            start_date="2026-05-01", release_date="2026-05-31",
        )
        result, _ = _run(["get", "10042"], mc)
        assert result.exit_code == 0, result.output
        mc.get.assert_called_once_with("rest/api/2/version/10042")
        assert "1.4.0" in result.output
        assert "Q2 release" in result.output
        assert "2026-05-31" in result.output

    def test_get_by_id_json(self):
        mc = _make_mock_client()
        v = _make_version("10042", "1.4.0")
        mc.get.return_value = v
        result, _ = _run(["--json", "get", "10042"], mc)
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["id"] == "10042"


class TestGetByName:
    def test_get_by_name_requires_project(self):
        mc = _make_mock_client()
        result, _ = _run(["get", "1.4.0"], mc)
        assert result.exit_code != 0
        assert "--project" in result.output.lower() or "project" in result.output.lower()

    def test_get_by_name_resolves(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10041", "1.3.0"),
            _make_version("10042", "1.4.0"),
        ]
        result, _ = _run(["get", "1.4.0", "--project", "PROJ"], mc)
        assert result.exit_code == 0, result.output
        mc.get.assert_called_once_with("rest/api/2/project/PROJ/versions")
        assert "10042" in result.output

    def test_get_by_name_no_match(self):
        mc = _make_mock_client()
        mc.get.return_value = [_make_version("10041", "1.3.0")]
        result, _ = _run(["get", "1.4.0", "--project", "PROJ"], mc)
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "no version" in result.output.lower()

    def test_get_by_name_ambiguous(self):
        mc = _make_mock_client()
        mc.get.return_value = [
            _make_version("10042", "1.4.0"),
            _make_version("10043", "1.4.0"),  # duplicate name
        ]
        result, _ = _run(["get", "1.4.0", "--project", "PROJ"], mc)
        assert result.exit_code != 0
        assert "multiple" in result.output.lower() or "ambiguous" in result.output.lower()


class TestGetCounts:
    def test_counts_fetches_both_endpoints(self):
        mc = _make_mock_client()
        # Three GETs: version, relatedIssueCounts, unresolvedIssueCount
        mc.get.side_effect = [
            _make_version("10042", "1.4.0"),
            {"issuesFixedCount": 12, "issuesAffectedCount": 3},
            {"issuesUnresolvedCount": 4},
        ]
        result, _ = _run(["get", "10042", "--counts"], mc)
        assert result.exit_code == 0, result.output
        assert mc.get.call_count == 3
        paths = [c.args[0] for c in mc.get.call_args_list]
        assert paths[0] == "rest/api/2/version/10042"
        assert paths[1] == "rest/api/2/version/10042/relatedIssueCounts"
        assert paths[2] == "rest/api/2/version/10042/unresolvedIssueCount"
        assert "fixed=12" in result.output
        assert "affected=3" in result.output
        assert "unresolved=4" in result.output


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
