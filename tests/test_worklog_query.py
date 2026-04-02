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
