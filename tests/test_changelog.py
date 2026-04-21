"""Tests for changelog helpers in lib/changelog.py."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.changelog import (
    compute_time_in_status,
    extract_status_transitions,
    format_timedelta,
)

UTC = timezone.utc


def _dt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_status_transitions()
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractStatusTransitions:
    """extract_status_transitions() must pick only status items from Jira changelog."""

    def test_returns_empty_for_missing_changelog(self):
        assert extract_status_transitions({}) == []

    def test_returns_empty_for_no_status_items(self):
        issue = {
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-01T12:00:00.000+0000",
                        "items": [{"field": "description", "fromString": "a", "toString": "b"}],
                    }
                ]
            }
        }
        assert extract_status_transitions(issue) == []

    def test_extracts_status_items(self):
        issue = {
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-01T12:00:00.000+0000",
                        "items": [
                            {"field": "summary", "fromString": "Old", "toString": "New"},
                            {"field": "status", "fromString": "Open", "toString": "In Progress"},
                        ],
                    },
                    {
                        "created": "2024-01-05T08:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "In Progress", "toString": "Done"}],
                    },
                ]
            }
        }
        result = extract_status_transitions(issue)
        assert len(result) == 2
        assert result[0]["from"] == "Open"
        assert result[0]["to"] == "In Progress"
        assert result[1]["from"] == "In Progress"
        assert result[1]["to"] == "Done"

    def test_sorts_by_timestamp_ascending(self):
        """Jira may not return histories strictly in chronological order."""
        issue = {
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-05T08:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "In Progress", "toString": "Done"}],
                    },
                    {
                        "created": "2024-01-01T12:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "Open", "toString": "In Progress"}],
                    },
                ]
            }
        }
        result = extract_status_transitions(issue)
        assert result[0]["from"] == "Open"
        assert result[1]["from"] == "In Progress"

    def test_parses_jira_timestamp_format(self):
        issue = {
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-01T12:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "Open", "toString": "Done"}],
                    }
                ]
            }
        }
        result = extract_status_transitions(issue)
        assert result[0]["created"] == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: compute_time_in_status()
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeTimeInStatus:
    """compute_time_in_status() must sum durations per status correctly."""

    def test_no_transitions_all_time_in_current_status(self):
        created = _dt(2024, 1, 1)
        now = _dt(2024, 1, 4)
        result = compute_time_in_status(created, [], current_status="Open", now=now)
        assert result == {"Open": timedelta(days=3)}

    def test_single_transition(self):
        created = _dt(2024, 1, 1)
        transitions = [
            {"created": _dt(2024, 1, 5), "from": "Open", "to": "In Progress"},
        ]
        now = _dt(2024, 1, 10)
        result = compute_time_in_status(created, transitions, current_status="In Progress", now=now)
        assert result["Open"] == timedelta(days=4)
        assert result["In Progress"] == timedelta(days=5)

    def test_multiple_transitions(self):
        created = _dt(2024, 1, 1)
        transitions = [
            {"created": _dt(2024, 1, 3), "from": "Open", "to": "In Progress"},
            {"created": _dt(2024, 1, 10), "from": "In Progress", "to": "Review"},
            {"created": _dt(2024, 1, 15), "from": "Review", "to": "Done"},
        ]
        now = _dt(2024, 1, 20)
        result = compute_time_in_status(created, transitions, current_status="Done", now=now)
        assert result["Open"] == timedelta(days=2)
        assert result["In Progress"] == timedelta(days=7)
        assert result["Review"] == timedelta(days=5)
        assert result["Done"] == timedelta(days=5)

    def test_re_entering_status_accumulates(self):
        """When an issue goes back to an earlier status, durations must sum."""
        created = _dt(2024, 1, 1)
        transitions = [
            {"created": _dt(2024, 1, 3), "from": "Open", "to": "In Progress"},
            {"created": _dt(2024, 1, 5), "from": "In Progress", "to": "Review"},
            {"created": _dt(2024, 1, 6), "from": "Review", "to": "In Progress"},  # kicked back
            {"created": _dt(2024, 1, 10), "from": "In Progress", "to": "Done"},
        ]
        now = _dt(2024, 1, 12)
        result = compute_time_in_status(created, transitions, current_status="Done", now=now)
        # In Progress: 2 days (3→5) + 4 days (6→10) = 6 days
        assert result["In Progress"] == timedelta(days=6)
        assert result["Review"] == timedelta(days=1)
        assert result["Done"] == timedelta(days=2)
        assert result["Open"] == timedelta(days=2)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: format_timedelta()
# ═══════════════════════════════════════════════════════════════════════════════


class TestFormatTimedelta:
    """format_timedelta() must produce human-readable strings."""

    def test_days_with_hours(self):
        assert format_timedelta(timedelta(days=3, hours=4)) == "3d 4h"

    def test_just_hours(self):
        assert format_timedelta(timedelta(hours=5, minutes=30)) == "5h 30m"

    def test_just_minutes(self):
        assert format_timedelta(timedelta(minutes=42)) == "42m"

    def test_zero(self):
        assert format_timedelta(timedelta(0)) == "0m"

    def test_negative_treated_as_zero(self):
        """Clock skew / reordering should never produce negative durations."""
        assert format_timedelta(timedelta(seconds=-1)) == "0m"
