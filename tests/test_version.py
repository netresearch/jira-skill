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


class TestValidateIsoDate:
    def test_accepts_iso_date(self):
        assert _mod._validate_iso_date("2026-05-31") == "2026-05-31"

    def test_accepts_leap_day(self):
        assert _mod._validate_iso_date("2024-02-29") == "2024-02-29"

    def test_rejects_invalid_day(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("2026-02-30")

    def test_rejects_timestamp(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("2026-05-31T00:00:00Z")

    def test_rejects_garbage(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("tomorrow")

    def test_rejects_slashes(self):
        with pytest.raises(click.BadParameter):
            _mod._validate_iso_date("2026/05/31")


class TestCreate:
    def test_create_minimal(self):
        mc = _make_mock_client()
        mc.post.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["create", "PROJ", "1.4.0"], mc)
        assert result.exit_code == 0, result.output
        mc.post.assert_called_once()
        path = mc.post.call_args.args[0]
        assert path == "rest/api/2/version"
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["name"] == "1.4.0"
        assert body["project"] == "PROJ"
        assert body.get("released", False) is False
        assert body.get("archived", False) is False

    def test_create_with_dates_and_description(self):
        mc = _make_mock_client()
        mc.post.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(
            ["create", "PROJ", "1.4.0",
             "--description", "Q2 2026",
             "--start-date", "2026-05-01",
             "--release-date", "2026-05-31"],
            mc,
        )
        assert result.exit_code == 0, result.output
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["description"] == "Q2 2026"
        assert body["startDate"] == "2026-05-01"
        assert body["releaseDate"] == "2026-05-31"

    def test_create_released_and_archived_flags(self):
        mc = _make_mock_client()
        mc.post.return_value = _make_version("10042", "1.4.0", released=True, archived=True)
        result, _ = _run(
            ["create", "PROJ", "1.4.0", "--released", "--archived",
             "--release-date", "2026-05-31"],
            mc,
        )
        assert result.exit_code == 0, result.output
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["released"] is True
        assert body["archived"] is True

    def test_create_rejects_bad_date(self):
        mc = _make_mock_client()
        result, _ = _run(["create", "PROJ", "1.4.0", "--release-date", "2026/05/31"], mc)
        assert result.exit_code != 0
        assert "YYYY-MM-DD" in result.output or "Invalid date" in result.output
        mc.post.assert_not_called()

    def test_create_dry_run(self):
        mc = _make_mock_client()
        result, _ = _run(["create", "PROJ", "1.4.0", "--release-date", "2026-05-31", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.post.assert_not_called()
        assert "DRY RUN" in result.output
        assert "1.4.0" in result.output


class TestCreateConflict:
    def test_duplicate_name_409(self):
        mc = _make_mock_client()
        # atlassian-python-api raises HTTPError on 4xx; simulate that shape
        from requests.exceptions import HTTPError
        from requests import Response
        resp = Response()
        resp.status_code = 409
        resp._content = b'{"errors":{"name":"A version with this name already exists."}}'
        err = HTTPError("409 Conflict", response=resp)
        mc.post.side_effect = err

        result, _ = _run(["create", "PROJ", "1.4.0"], mc)
        assert result.exit_code != 0
        # Clean message, not a stack trace
        assert "already exists" in result.output.lower()
        assert "1.4.0" in result.output
        assert "PROJ" in result.output


class TestSafeUpdate:
    def test_merges_patch_onto_current(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=False,
            description="old", start_date="2026-05-01", release_date="2026-05-31",
        )
        mc.put.return_value = {}
        _mod._safe_update_version(mc, "10042", description="new", releaseDate="2026-06-07")

        mc.get.assert_called_once_with("rest/api/2/version/10042")
        path = mc.put.call_args.args[0]
        assert path == "rest/api/2/version/10042"
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["description"] == "new"
        assert body["releaseDate"] == "2026-06-07"
        # Untouched fields retained from GET
        assert body["name"] == "1.4.0"
        assert body["startDate"] == "2026-05-01"
        assert body["released"] is False

    def test_explicit_none_sets_null(self):
        """Clearing a field (e.g. unrelease) means explicit None -> null in the PUT body."""
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=True, release_date="2026-05-31",
        )
        mc.put.return_value = {}
        _mod._safe_update_version(mc, "10042", released=False, releaseDate=None)
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is False
        assert "releaseDate" in body
        assert body["releaseDate"] is None

    def test_does_not_send_unset_kwargs(self):
        """Kwargs not passed by the caller must not appear in the patch."""
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", description="orig")
        mc.put.return_value = {}
        _mod._safe_update_version(mc, "10042", name="1.4.0-rc")
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["name"] == "1.4.0-rc"
        # description retained from GET, not cleared
        assert body["description"] == "orig"


class TestUpdate:
    def test_update_description(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", description="old")
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--description", "new"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["description"] == "new"
        assert body["name"] == "1.4.0"  # retained

    def test_update_name(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--name", "1.4.0-final"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["name"] == "1.4.0-final"

    def test_update_dates(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        mc.put.return_value = {}
        result, _ = _run(
            ["update", "10042", "--start-date", "2026-05-01", "--release-date", "2026-06-07"], mc
        )
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["startDate"] == "2026-05-01"
        assert body["releaseDate"] == "2026-06-07"

    def test_update_released_flag(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=False)
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--released"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is True

    def test_update_unreleased_clears_release_date(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=True, release_date="2026-05-31")
        mc.put.return_value = {}
        result, _ = _run(["update", "10042", "--unreleased"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is False
        assert body["releaseDate"] is None

    def test_update_dry_run(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["update", "10042", "--description", "new", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.put.assert_not_called()
        assert "DRY RUN" in result.output

    def test_update_rejects_bad_date(self):
        mc = _make_mock_client()
        result, _ = _run(["update", "10042", "--release-date", "tomorrow"], mc)
        assert result.exit_code != 0
        mc.put.assert_not_called()


class TestReleaseUnrelease:
    def test_release_with_date(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=False)
        mc.put.return_value = {}
        result, _ = _run(["release", "10042", "--release-date", "2026-05-31"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is True
        assert body["releaseDate"] == "2026-05-31"

    def test_release_defaults_to_today(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", released=False)
        mc.put.return_value = {}
        result, _ = _run(["release", "10042"], mc)
        assert result.exit_code == 0, result.output
        from datetime import date
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is True
        assert body["releaseDate"] == date.today().isoformat()

    def test_unrelease_clears_release_date(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version(
            "10042", "1.4.0", released=True, release_date="2026-05-31"
        )
        mc.put.return_value = {}
        result, _ = _run(["unrelease", "10042"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["released"] is False
        assert body["releaseDate"] is None

    def test_release_dry_run(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["release", "10042", "--release-date", "2026-05-31", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.put.assert_not_called()
        assert "DRY RUN" in result.output


class TestArchiveUnarchive:
    def test_archive(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", archived=False)
        mc.put.return_value = {}
        result, _ = _run(["archive", "10042"], mc)
        assert result.exit_code == 0, result.output
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["archived"] is True
        # Other fields untouched
        assert body["name"] == "1.4.0"

    def test_unarchive(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0", archived=True)
        mc.put.return_value = {}
        result, _ = _run(["unarchive", "10042"], mc)
        assert result.exit_code == 0
        body = mc.put.call_args.kwargs.get("data") or mc.put.call_args.kwargs.get("json")
        assert body["archived"] is False

    def test_archive_dry_run(self):
        mc = _make_mock_client()
        mc.get.return_value = _make_version("10042", "1.4.0")
        result, _ = _run(["archive", "10042", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.put.assert_not_called()


class TestSelfUrl:
    def test_builds_self_url(self):
        mc = _make_mock_client(url="https://jira.example.com")
        assert _mod._version_self_url(mc, "10042") == \
            "https://jira.example.com/rest/api/2/version/10042"

    def test_strips_trailing_slash(self):
        mc = _make_mock_client(url="https://jira.example.com/")
        assert _mod._version_self_url(mc, "10042") == \
            "https://jira.example.com/rest/api/2/version/10042"

    def test_preserves_context_path(self):
        mc = _make_mock_client(url="https://corp.example.com/jira")
        assert _mod._version_self_url(mc, "10042") == \
            "https://corp.example.com/jira/rest/api/2/version/10042"

    def test_raises_without_url(self):
        mc = mock.Mock()
        mc.url = ""
        with pytest.raises(RuntimeError):
            _mod._version_self_url(mc, "10042")


class TestMove:
    def test_move_after(self):
        mc = _make_mock_client(url="https://jira.example.com")
        mc.post.return_value = {}
        result, _ = _run(["move", "10045", "--after", "10042"], mc)
        assert result.exit_code == 0, result.output
        path = mc.post.call_args.args[0]
        assert path == "rest/api/2/version/10045/move"
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body["after"] == "https://jira.example.com/rest/api/2/version/10042"

    def test_move_position(self):
        mc = _make_mock_client()
        mc.post.return_value = {}
        result, _ = _run(["move", "10042", "--position", "First"], mc)
        assert result.exit_code == 0, result.output
        body = mc.post.call_args.kwargs.get("data") or mc.post.call_args.kwargs.get("json")
        assert body == {"position": "First"}

    def test_move_requires_after_or_position(self):
        mc = _make_mock_client()
        result, _ = _run(["move", "10042"], mc)
        assert result.exit_code != 0
        mc.post.assert_not_called()

    def test_move_after_and_position_mutually_exclusive(self):
        mc = _make_mock_client()
        result, _ = _run(["move", "10042", "--after", "10041", "--position", "Last"], mc)
        assert result.exit_code != 0
        mc.post.assert_not_called()

    def test_move_dry_run(self):
        mc = _make_mock_client()
        result, _ = _run(["move", "10042", "--position", "First", "--dry-run"], mc)
        assert result.exit_code == 0
        mc.post.assert_not_called()


class TestMerge:
    def test_merge_executes(self):
        mc = _make_mock_client()
        mc.post.return_value = {}
        result, _ = _run(["merge", "10050", "INTO", "10042"], mc)
        assert result.exit_code == 0, result.output
        path = mc.post.call_args.args[0]
        assert path == "rest/api/2/version/10050/mergeto/10042"

    def test_merge_requires_INTO(self):
        mc = _make_mock_client()
        result, _ = _run(["merge", "10050", "BESIDE", "10042"], mc)
        assert result.exit_code != 0
        mc.post.assert_not_called()

    def test_merge_dry_run_fetches_counts(self):
        mc = _make_mock_client()
        mc.get.side_effect = [
            {"issuesFixedCount": 7, "issuesAffectedCount": 1},  # src relatedIssueCounts
            _make_version("10050", "1.4.0-dup"),                 # src version
            _make_version("10042", "1.4.0"),                     # dst version
        ]
        result, _ = _run(["merge", "10050", "INTO", "10042", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        mc.post.assert_not_called()
        assert "DRY RUN" in result.output
        assert "7" in result.output   # fixed count
        assert "1" in result.output   # affected count
        assert "1.4.0-dup" in result.output
        assert "1.4.0" in result.output

    def test_merge_does_not_issue_separate_delete(self):
        """mergeto deletes the source server-side; no extra DELETE needed."""
        mc = _make_mock_client()
        mc.post.return_value = {}
        result, _ = _run(["merge", "10050", "INTO", "10042"], mc)
        assert result.exit_code == 0
        mc.delete.assert_not_called()


class TestDeleteDryRun:
    def test_delete_dry_run_fetches_counts(self):
        mc = _make_mock_client()
        mc.get.side_effect = [
            _make_version("10050", "1.4.0-dup"),
            {"issuesFixedCount": 7, "issuesAffectedCount": 1},
        ]
        result, _ = _run(["delete", "10050", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        mc.delete.assert_not_called()
        assert "DRY RUN" in result.output
        assert "7" in result.output
        assert "1" in result.output
        assert "1.4.0-dup" in result.output


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
