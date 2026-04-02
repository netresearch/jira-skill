"""Tests for jira-worklog-query.py — cross-cutting worklog query tool."""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

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
            "2026-03-30", "2026-04-02",
            user="psiedler", project="HMKG",
            issues=["HMKG-123"], epic="HMKG-1940", sprint="Sprint 42",
        )
        assert "worklogDate" in jql
        assert "worklogAuthor" in jql
        assert "project" in jql
        assert "issueKey" in jql
        assert "Epic Link" in jql
        assert "sprint" in jql
        # All clauses joined with AND
        assert jql.count(" AND ") == 6


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
                {"id": "1001", "started": "2026-03-30T09:00:00.000+0200", "timeSpentSeconds": 3600,
                 "author": {"displayName": "Paul", "name": "psiedler"}},
            ],
            "total": 1,
            "maxResults": 1048576,
        }
        result = _mod.fetch_worklogs(mock_client, "HMKG-100", 1743289200000, 1743548400000)
        assert len(result) == 1
        assert result[0]["_issue_key"] == "HMKG-100"

    def test_adds_issue_key_to_worklogs(self):
        mock_client = mock.MagicMock()
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [{"id": "1001", "started": "2026-03-30T09:00:00.000+0200"}],
            "total": 1,
            "maxResults": 1048576,
        }
        result = _mod.fetch_worklogs(mock_client, "HMKG-999", 0, 9999999999999)
        assert result[0]["_issue_key"] == "HMKG-999"
