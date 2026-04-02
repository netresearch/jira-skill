"""Tests for jira-worklog-query.py — cross-cutting worklog query tool."""

import importlib.util
import sys
from pathlib import Path

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
