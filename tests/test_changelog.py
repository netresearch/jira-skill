"""Tests for changelog helpers in lib/changelog.py."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.changelog import (
    classify_transition,
    compute_time_in_status,
    extract_status_transitions,
    extract_status_transitions_with_authors,
    find_transition_window,
    format_timedelta,
)

# Status sets used by classify_transition tests
_QA = frozenset({"QA", "Review", "QA2", "UAT"})
_WORKING = frozenset({"In Progress", "Open", "QA failed"})
_RESOLVED = frozenset({"Closed", "Resolved", "Done"})
_SETS = {"qa": _QA, "working": _WORKING, "resolved": _RESOLVED}

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


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_status_transitions_with_authors()
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractStatusTransitionsWithAuthors:
    """Augmented variant must preserve transition author identity."""

    def _issue(self, history):
        return {"changelog": {"histories": history}}

    def test_extracts_author_name_and_key(self):
        issue = self._issue(
            [
                {
                    "created": "2026-05-10T08:29:05.000+0000",
                    "author": {"name": "smendel", "displayName": "Sebastian Mendel"},
                    "items": [{"field": "status", "fromString": "In Progress", "toString": "QA"}],
                }
            ]
        )
        ts = extract_status_transitions_with_authors(issue)
        assert len(ts) == 1
        assert ts[0]["from"] == "In Progress"
        assert ts[0]["to"] == "QA"
        assert ts[0]["author_name"] == "Sebastian Mendel"
        assert ts[0]["author_key"] == "smendel"

    def test_falls_back_to_account_id_when_no_name(self):
        issue = self._issue(
            [
                {
                    "created": "2026-05-10T08:29:05.000+0000",
                    "author": {"accountId": "acc-1", "displayName": "Cloud User"},
                    "items": [{"field": "status", "fromString": "Open", "toString": "QA"}],
                }
            ]
        )
        ts = extract_status_transitions_with_authors(issue)
        assert ts[0]["author_key"] == "acc-1"

    def test_handles_missing_author(self):
        issue = self._issue(
            [
                {
                    "created": "2026-05-10T08:29:05.000+0000",
                    "items": [{"field": "status", "fromString": "Open", "toString": "QA"}],
                }
            ]
        )
        ts = extract_status_transitions_with_authors(issue)
        assert ts[0]["author_key"] == ""
        assert ts[0]["author_name"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: classify_transition()
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifyTransition:
    """Transitions classify by set membership, not by name."""

    def test_into_qa(self):
        t = {"from": "In Progress", "to": "QA"}
        assert classify_transition(t, _SETS) == "into_qa"

    def test_reject_to_working(self):
        t = {"from": "QA", "to": "In Progress"}
        assert classify_transition(t, _SETS) == "reject"

    def test_reject_to_qa_failed(self):
        """`QA → QA failed` must be reject (QA failed is in working set, not qa)."""
        t = {"from": "QA", "to": "QA failed"}
        assert classify_transition(t, _SETS) == "reject"

    def test_forward_qa_to_qa2(self):
        """Multi-stage QA progression is forward, NOT reject."""
        t = {"from": "QA", "to": "QA2"}
        assert classify_transition(t, _SETS) == "forward"

    def test_forward_review_to_uat(self):
        """Different two-stage naming (Review → UAT) classifies same as QA → QA2."""
        t = {"from": "Review", "to": "UAT"}
        assert classify_transition(t, _SETS) == "forward"

    def test_resolved_takes_precedence_over_qa(self):
        """`QA → Closed` is resolved, even though source is QA."""
        t = {"from": "QA", "to": "Closed"}
        assert classify_transition(t, _SETS) == "resolved"

    def test_out_when_qa_to_unknown(self):
        """`QA → SomethingUnknown` (not in any set) is `out`."""
        t = {"from": "QA", "to": "SomethingNew"}
        assert classify_transition(t, _SETS) == "out"

    def test_other_when_neither_side_qa(self):
        t = {"from": "Open", "to": "In Progress"}
        assert classify_transition(t, _SETS) == "other"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: find_transition_window()
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindTransitionWindow:
    """find_transition_window returns previous and next adjacent timestamps."""

    def _ts(self, *dts):
        return [{"created": d, "from": "x", "to": "y", "author_name": "", "author_key": ""} for d in dts]

    def test_returns_neighbors(self):
        ts = self._ts(_dt(2026, 5, 1), _dt(2026, 5, 5), _dt(2026, 5, 10))
        prev, nxt = find_transition_window(ts, 1)
        assert prev == _dt(2026, 5, 1)
        assert nxt == _dt(2026, 5, 10)

    def test_first_transition_has_no_prev(self):
        ts = self._ts(_dt(2026, 5, 1), _dt(2026, 5, 5))
        prev, nxt = find_transition_window(ts, 0)
        assert prev is None
        assert nxt == _dt(2026, 5, 5)

    def test_last_transition_has_no_next(self):
        ts = self._ts(_dt(2026, 5, 1), _dt(2026, 5, 5))
        prev, nxt = find_transition_window(ts, 1)
        assert prev == _dt(2026, 5, 1)
        assert nxt is None

    def test_out_of_bounds_returns_none(self):
        ts = self._ts(_dt(2026, 5, 1))
        assert find_transition_window(ts, 5) == (None, None)
        assert find_transition_window(ts, -1) == (None, None)
