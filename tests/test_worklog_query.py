"""Tests for jira-worklog-query.py — cross-cutting worklog query tool."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import click.testing

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script():
    """Load jira-worklog-query via importlib."""
    path = _scripts_path / "utility" / "jira-worklog-query.py"
    spec = importlib.util.spec_from_file_location("jira_worklog_query", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_script()


class TestBuildJql:
    """Test JQL query building from filters."""

    def test_date_range_only(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02")
        assert 'worklogDate >= "2026-03-30"' in jql
        assert 'worklogDate <= "2026-04-02"' in jql

    def test_with_user(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", user="psiedler")
        assert 'worklogAuthor = "psiedler"' in jql

    def test_with_project(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", project="HMKG")
        assert 'project = "HMKG"' in jql

    def test_with_single_issue(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", issues=["HMKG-123"])
        assert 'issueKey in ("HMKG-123")' in jql

    def test_with_multiple_issues(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", issues=["HMKG-123", "HMKG-456"])
        assert 'issueKey in ("HMKG-123", "HMKG-456")' in jql

    def test_with_epic(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", epic="HMKG-1940")
        assert '"Epic Link" = "HMKG-1940"' in jql

    def test_with_sprint(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", sprint="Sprint 42")
        assert 'sprint = "Sprint 42"' in jql

    def test_sprint_numeric(self):
        """Numeric sprint IDs should not be quoted."""
        jql = _mod.build_jql("2026-03-30", "2026-04-02", sprint="916")
        assert "sprint = 916" in jql

    def test_all_filters_combined(self):
        jql = _mod.build_jql(
            "2026-03-30",
            "2026-04-02",
            user="psiedler",
            project="HMKG",
            issues=["HMKG-123"],
            epic="HMKG-1940",
            sprint="Sprint 42",
        )
        assert "worklogDate" in jql
        assert "worklogAuthor" in jql
        assert "project" in jql
        assert "issueKey" in jql
        assert "Epic Link" in jql
        assert "sprint" in jql
        # All clauses joined with AND
        assert jql.count(" AND ") == 6

    def test_escapes_quotes_in_values(self):
        """Values with double quotes are escaped to prevent JQL injection."""
        jql = _mod.build_jql("2026-03-30", "2026-04-02", sprint='Sprint "42"')
        assert 'sprint = "Sprint \\"42\\""' in jql

    def test_escapes_backslash_in_values(self):
        jql = _mod.build_jql("2026-03-30", "2026-04-02", user="domain\\user")
        assert 'worklogAuthor = "domain\\\\user"' in jql


class TestSecondsToHuman:
    """Test time formatting."""

    def test_hours_and_minutes(self):
        assert _mod.seconds_to_human(9000) == "2h 30m"

    def test_hours_only(self):
        assert _mod.seconds_to_human(7200) == "2h"

    def test_minutes_only(self):
        assert _mod.seconds_to_human(1800) == "30m"

    def test_days(self):
        # 8h workday
        assert _mod.seconds_to_human(28800) == "1d"

    def test_days_and_hours(self):
        assert _mod.seconds_to_human(36000) == "1d 2h"

    def test_zero(self):
        assert _mod.seconds_to_human(0) == "0m"

    def test_complex(self):
        # 1d 3h 15m = 28800 + 10800 + 900 = 40500
        assert _mod.seconds_to_human(40500) == "1d 3h 15m"


# Test fixture data
SAMPLE_WORKLOGS = [
    {
        "author": {"displayName": "Paul Siedler", "name": "psiedler", "accountId": "abc123"},
        "started": "2026-03-30T09:00:00.000+0200",
        "timeSpentSeconds": 3600,
        "timeSpent": "1h",
        "comment": "Code review",
        "id": "1001",
        "_issue_key": "HMKG-100",
    },
    {
        "author": {"displayName": "Jane Doe", "name": "jdoe", "accountId": "def456"},
        "started": "2026-03-31T10:00:00.000+0200",
        "timeSpentSeconds": 7200,
        "timeSpent": "2h",
        "comment": "Implementation",
        "id": "1002",
        "_issue_key": "HMKG-100",
    },
    {
        "author": {"displayName": "Paul Siedler", "name": "psiedler", "accountId": "abc123"},
        "started": "2026-04-01T14:00:00.000+0200",
        "timeSpentSeconds": 5400,
        "timeSpent": "1h 30m",
        "comment": "Testing",
        "id": "1003",
        "_issue_key": "HMKG-200",
    },
    {
        "author": {"displayName": "Paul Siedler", "name": "psiedler", "accountId": "abc123"},
        "started": "2026-04-10T09:00:00.000+0200",
        "timeSpentSeconds": 1800,
        "timeSpent": "30m",
        "comment": "Outside date range",
        "id": "1004",
        "_issue_key": "HMKG-300",
    },
]


ISSUE_MAP = {
    "HMKG-100": "Fix login validation",
    "HMKG-200": "Update API docs",
}


class TestFormatSummary:
    """Test summary output formatting."""

    def test_groups_by_issue(self):
        wls = SAMPLE_WORKLOGS[:3]  # exclude the out-of-range one
        output = _mod.format_summary(wls, ISSUE_MAP)
        assert "HMKG-100" in output
        assert "HMKG-200" in output
        assert "Fix login validation" in output

    def test_shows_total_per_issue(self):
        wls = SAMPLE_WORKLOGS[:3]
        output = _mod.format_summary(wls, ISSUE_MAP)
        # HMKG-100 has 1h + 2h = 3h
        assert "3h" in output

    def test_shows_grand_total(self):
        wls = SAMPLE_WORKLOGS[:3]
        output = _mod.format_summary(wls, ISSUE_MAP)
        # 1h + 2h + 1h30m = 4h 30m
        assert "4h 30m" in output

    def test_empty_worklogs(self):
        output = _mod.format_summary([], {})
        assert "no worklogs" in output.lower()


class TestFormatDetail:
    """Test detail output formatting."""

    def test_shows_individual_entries(self):
        wls = SAMPLE_WORKLOGS[:3]
        output = _mod.format_detail(wls)
        assert "Code review" in output
        assert "Implementation" in output
        assert "Testing" in output

    def test_shows_date_and_author(self):
        wls = SAMPLE_WORKLOGS[:1]
        output = _mod.format_detail(wls)
        assert "2026-03-30" in output
        assert "Paul Siedler" in output

    def test_shows_issue_key(self):
        wls = SAMPLE_WORKLOGS[:1]
        output = _mod.format_detail(wls)
        assert "HMKG-100" in output

    def test_empty_worklogs(self):
        output = _mod.format_detail([])
        assert "no worklogs" in output.lower()


class TestFilterWorklogs:
    """Test client-side worklog filtering."""

    def test_no_filters_returns_all(self):
        result = _mod.filter_worklogs(SAMPLE_WORKLOGS)
        assert len(result) == 4

    def test_filter_by_user_name(self):
        result = _mod.filter_worklogs(SAMPLE_WORKLOGS, user="psiedler")
        assert len(result) == 3
        assert all(w["author"]["name"] == "psiedler" for w in result)

    def test_filter_by_account_id(self):
        result = _mod.filter_worklogs(SAMPLE_WORKLOGS, user="abc123")
        assert len(result) == 3

    def test_filter_by_display_name(self):
        result = _mod.filter_worklogs(SAMPLE_WORKLOGS, user="Jane Doe")
        assert len(result) == 1

    def test_filter_by_date_range(self):
        result = _mod.filter_worklogs(SAMPLE_WORKLOGS, from_date="2026-03-30", to_date="2026-04-01")
        assert len(result) == 3
        assert "1004" not in [w["id"] for w in result]

    def test_filter_by_user_and_date(self):
        result = _mod.filter_worklogs(SAMPLE_WORKLOGS, user="psiedler", from_date="2026-03-30", to_date="2026-04-01")
        assert len(result) == 2
        assert all(w["author"]["name"] == "psiedler" for w in result)

    def test_empty_list(self):
        result = _mod.filter_worklogs([])
        assert result == []


class TestDetectTempo:
    """Test Tempo plugin detection."""

    def test_tempo_available(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_client._session.get.return_value = mock_response
        assert _mod.detect_tempo(mock_client) is True

    def test_tempo_not_available(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.status_code = 404
        mock_client._session.get.return_value = mock_response
        assert _mod.detect_tempo(mock_client) is False

    def test_tempo_auth_failure(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.status_code = 403
        mock_client._session.get.return_value = mock_response
        assert _mod.detect_tempo(mock_client) is False

    def test_tempo_connection_error(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_client._session.get.side_effect = Exception("Connection refused")
        assert _mod.detect_tempo(mock_client) is False


class TestNormalizeTempoWorklog:
    """Test Tempo-to-Jira worklog normalization."""

    def test_basic_normalization(self):
        tempo_wl = {
            "tempoWorklogId": 12345,
            "issue": {"key": "PROJ-123", "id": 10456},
            "timeSpentSeconds": 3600,
            "started": "2026-04-01",
            "comment": "Work done",
            "author": {"name": "jdoe", "displayName": "John Doe"},
        }
        result = _mod.normalize_tempo_worklog(tempo_wl)
        assert result["id"] == "12345"
        assert result["_issue_key"] == "PROJ-123"
        assert result["timeSpentSeconds"] == 3600
        assert result["comment"] == "Work done"
        assert result["author"]["name"] == "jdoe"

    def test_date_padded_to_timestamp(self):
        tempo_wl = {
            "tempoWorklogId": 1,
            "issue": {"key": "X-1"},
            "started": "2026-04-01",
        }
        result = _mod.normalize_tempo_worklog(tempo_wl)
        assert result["started"] == "2026-04-01T00:00:00.000+0000"
        # Still works with [:10] slicing for date comparison
        assert result["started"][:10] == "2026-04-01"

    def test_already_timestamp_not_padded(self):
        tempo_wl = {
            "tempoWorklogId": 1,
            "issue": {"key": "X-1"},
            "started": "2026-04-01T09:30:00.000+0200",
        }
        result = _mod.normalize_tempo_worklog(tempo_wl)
        assert result["started"] == "2026-04-01T09:30:00.000+0200"

    def test_missing_fields(self):
        result = _mod.normalize_tempo_worklog({})
        assert result["id"] == ""
        assert result["_issue_key"] == "Unknown"
        assert result["timeSpentSeconds"] == 0
        assert result["comment"] == ""


SAMPLE_TEMPO_RESPONSE = [
    {
        "tempoWorklogId": 101,
        "issue": {"key": "HMKG-100", "id": 10001},
        "timeSpentSeconds": 3600,
        "started": "2026-04-01",
        "comment": "Feature work",
        "author": {"name": "psiedler", "displayName": "Paul Siedler"},
    },
    {
        "tempoWorklogId": 102,
        "issue": {"key": "HMKG-200", "id": 10002},
        "timeSpentSeconds": 5400,
        "started": "2026-04-02",
        "comment": "Code review",
        "author": {"name": "psiedler", "displayName": "Paul Siedler"},
    },
]


class TestFetchWorklogsTempo:
    """Test Tempo worklog fetching."""

    def test_basic_fetch(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_TEMPO_RESPONSE
        mock_client._session.get.return_value = mock_response

        mock_client.jql.return_value = {
            "issues": [
                {"key": "HMKG-100", "fields": {"summary": "Fix login"}},
                {"key": "HMKG-200", "fields": {"summary": "Update docs"}},
            ],
            "total": 2,
            "startAt": 0,
            "maxResults": 50,
        }

        worklogs, issue_map = _mod.fetch_worklogs_tempo(mock_client, "2026-04-01", "2026-04-02", user="psiedler")
        assert len(worklogs) == 2
        assert worklogs[0]["_issue_key"] == "HMKG-100"
        assert worklogs[0]["timeSpentSeconds"] == 3600
        assert issue_map["HMKG-100"] == "Fix login"
        assert issue_map["HMKG-200"] == "Update docs"

    def test_passes_filters_to_api(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.json.return_value = []
        mock_client._session.get.return_value = mock_response

        _mod.fetch_worklogs_tempo(mock_client, "2026-04-01", "2026-04-30", user="psiedler", project="HMKG")

        params = mock_client._session.get.call_args.kwargs["params"]
        assert params["dateFrom"] == "2026-04-01"
        assert params["dateTo"] == "2026-04-30"
        assert params["worker"] == "psiedler"
        assert params["projectKey"] == "HMKG"

    def test_paginated_response(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"

        page1_response = mock.MagicMock()
        page1_response.json.return_value = {
            "results": SAMPLE_TEMPO_RESPONSE[:1],
            "metadata": {"count": 2, "offset": 0, "limit": 1, "next": "/rest/tempo-timesheets/4/worklogs?offset=1"},
        }
        page2_response = mock.MagicMock()
        page2_response.json.return_value = {
            "results": SAMPLE_TEMPO_RESPONSE[1:],
            "metadata": {"count": 2, "offset": 1, "limit": 1},
        }
        mock_client._session.get.side_effect = [page1_response, page2_response]
        mock_client.jql.return_value = {
            "issues": [
                {"key": "HMKG-100", "fields": {"summary": "Issue"}},
                {"key": "HMKG-200", "fields": {"summary": "Issue"}},
            ],
            "total": 2,
            "startAt": 0,
            "maxResults": 50,
        }

        worklogs, issue_map = _mod.fetch_worklogs_tempo(mock_client, "2026-04-01", "2026-04-02")
        assert len(worklogs) == 2
        assert mock_client._session.get.call_count == 2

    def test_empty_result(self):
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.json.return_value = []
        mock_client._session.get.return_value = mock_response

        worklogs, issue_map = _mod.fetch_worklogs_tempo(mock_client, "2026-04-01", "2026-04-02")
        assert worklogs == []
        assert issue_map == {}

    def test_normalizes_to_jira_format(self):
        """Verify returned worklogs work with existing filter/format functions."""
        mock_client = mock.MagicMock()
        mock_client.url = "https://jira.example.com"
        mock_response = mock.MagicMock()
        mock_response.json.return_value = SAMPLE_TEMPO_RESPONSE
        mock_client._session.get.return_value = mock_response
        mock_client.jql.return_value = {
            "issues": [
                {"key": "HMKG-100", "fields": {"summary": "Test"}},
                {"key": "HMKG-200", "fields": {"summary": "Test"}},
            ],
            "total": 2,
            "startAt": 0,
            "maxResults": 50,
        }

        worklogs, _ = _mod.fetch_worklogs_tempo(mock_client, "2026-04-01", "2026-04-02")

        # Should work with filter_worklogs
        filtered = _mod.filter_worklogs(worklogs, user="psiedler")
        assert len(filtered) == 2

        # Should work with format_detail
        output = _mod.format_detail(worklogs)
        assert "HMKG-100" in output
        assert "Paul Siedler" in output


class TestSearchIssues:
    """Test issue search with mocked client."""

    def test_single_page(self):
        mock_client = mock.MagicMock()
        mock_client.jql.return_value = {
            "issues": [
                {"key": "HMKG-100", "fields": {"summary": "Fix login"}},
                {"key": "HMKG-200", "fields": {"summary": "Update docs"}},
            ],
            "total": 2,
            "startAt": 0,
            "maxResults": 50,
        }
        result = _mod.search_issues(mock_client, 'worklogDate >= "2026-03-30"')
        assert len(result) == 2
        assert result[0]["key"] == "HMKG-100"
        assert result[0]["summary"] == "Fix login"

    def test_pagination(self):
        mock_client = mock.MagicMock()
        mock_client.jql.side_effect = [
            {
                "issues": [{"key": f"HMKG-{i}", "fields": {"summary": f"Issue {i}"}} for i in range(50)],
                "total": 75,
                "startAt": 0,
                "maxResults": 50,
            },
            {
                "issues": [{"key": f"HMKG-{i}", "fields": {"summary": f"Issue {i}"}} for i in range(50, 75)],
                "total": 75,
                "startAt": 50,
                "maxResults": 50,
            },
        ]
        result = _mod.search_issues(mock_client, "some jql")
        assert len(result) == 75

    def test_empty_result(self):
        mock_client = mock.MagicMock()
        mock_client.jql.return_value = {"issues": [], "total": 0, "startAt": 0, "maxResults": 50}
        result = _mod.search_issues(mock_client, "some jql")
        assert result == []


class TestFetchWorklogs:
    """Test per-issue worklog fetch with mocked client."""

    def test_basic_fetch(self):
        mock_client = mock.MagicMock()
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [
                {
                    "id": "1001",
                    "started": "2026-03-30T09:00:00.000+0200",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "Paul", "name": "psiedler"},
                },
            ],
            "total": 1,
            "maxResults": 1048576,
        }
        result = _mod.fetch_worklogs(mock_client, "HMKG-100")
        assert len(result) == 1
        assert result[0]["_issue_key"] == "HMKG-100"

    def test_adds_issue_key_to_worklogs(self):
        mock_client = mock.MagicMock()
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [{"id": "1001", "started": "2026-03-30T09:00:00.000+0200"}],
            "total": 1,
            "maxResults": 1048576,
        }
        result = _mod.fetch_worklogs(mock_client, "HMKG-999")
        assert result[0]["_issue_key"] == "HMKG-999"


class TestCli:
    """Test CLI end-to-end with mocked client."""

    def test_default_query(self):
        mock_client = mock.MagicMock()
        mock_client.myself.return_value = {"name": "psiedler", "displayName": "Paul Siedler"}
        mock_client.jql.return_value = {
            "issues": [{"key": "HMKG-100", "fields": {"summary": "Fix login"}}],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [
                {
                    "id": "1001",
                    "started": "2026-04-01T09:00:00.000+0200",
                    "timeSpentSeconds": 3600,
                    "timeSpent": "1h",
                    "author": {"displayName": "Paul Siedler", "name": "psiedler"},
                    "comment": "Work done",
                }
            ],
            "total": 1,
            "maxResults": 1048576,
        }

        with mock.patch.object(_mod, "LazyJiraClient", return_value=mock_client):
            runner = click.testing.CliRunner()
            result = runner.invoke(_mod.cli, ["--from", "2026-04-01", "--to", "2026-04-01"])
            assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
            assert "HMKG-100" in result.output

    def test_json_output(self):
        mock_client = mock.MagicMock()
        mock_client.myself.return_value = {"name": "psiedler"}
        mock_client.jql.return_value = {"issues": [], "total": 0, "startAt": 0, "maxResults": 50}

        with mock.patch.object(_mod, "LazyJiraClient", return_value=mock_client):
            runner = click.testing.CliRunner()
            result = runner.invoke(_mod.cli, ["--json"])
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert isinstance(parsed, list)


class TestCliTempo:
    """Test CLI with Tempo backend."""

    def _make_tempo_client(self, mock_client):
        """Set up mock client for Tempo path."""
        mock_client.url = "https://jira.example.com"
        mock_client.myself.return_value = {"name": "psiedler", "displayName": "Paul Siedler"}
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "tempoWorklogId": 101,
                "issue": {"key": "HMKG-100", "id": 10001},
                "timeSpentSeconds": 3600,
                "started": "2026-04-01",
                "comment": "Feature work",
                "author": {"name": "psiedler", "displayName": "Paul Siedler"},
            },
        ]
        mock_client._session.get.return_value = mock_response
        mock_client.jql.return_value = {
            "issues": [{"key": "HMKG-100", "fields": {"summary": "Fix login"}}],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }

    @mock.patch.object(_mod, "LazyJiraClient")
    def test_tempo_backend_flag(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client_cls.return_value = mock_client
        self._make_tempo_client(mock_client)

        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, ["--backend", "tempo", "--from", "2026-04-01", "--to", "2026-04-01"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        assert "HMKG-100" in result.output
        assert "via Tempo" in result.output

    @mock.patch.object(_mod, "LazyJiraClient")
    def test_auto_detect_uses_tempo(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client_cls.return_value = mock_client
        self._make_tempo_client(mock_client)
        # detect_tempo will use the same _session.get mock which returns 200

        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, ["--backend", "auto", "--from", "2026-04-01", "--to", "2026-04-01"])
        assert result.exit_code == 0, f"CLI failed: {result.output}\n{result.exception}"
        assert "HMKG-100" in result.output

    @mock.patch.object(_mod, "LazyJiraClient")
    def test_jira_backend_flag_skips_tempo(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.myself.return_value = {"name": "psiedler"}
        mock_client.jql.return_value = {
            "issues": [{"key": "HMKG-100", "fields": {"summary": "Fix login"}}],
            "total": 1,
            "startAt": 0,
            "maxResults": 50,
        }
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [
                {
                    "id": "1001",
                    "started": "2026-04-01T09:00:00.000+0200",
                    "timeSpentSeconds": 3600,
                    "author": {"displayName": "Paul Siedler", "name": "psiedler"},
                    "comment": "Work done",
                }
            ],
            "total": 1,
            "maxResults": 1048576,
        }

        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, ["--backend", "jira", "--from", "2026-04-01", "--to", "2026-04-01"])
        assert result.exit_code == 0
        assert "HMKG-100" in result.output
        assert "via Tempo" not in result.output

    @mock.patch.object(_mod, "LazyJiraClient")
    def test_tempo_empty_result(self, mock_client_cls):
        mock_client = mock.MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.url = "https://jira.example.com"
        mock_client.myself.return_value = {"name": "psiedler"}
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client._session.get.return_value = mock_response

        runner = click.testing.CliRunner()
        result = runner.invoke(_mod.cli, ["--backend", "tempo"])
        assert result.exit_code == 0
        assert "No worklogs found" in result.output
