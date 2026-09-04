"""Tests for ``normalize_iso_timestamp`` in ``core/jira-worklog.py``.

Jira's worklog API wants exactly ``YYYY-MM-DDTHH:MM:SS.sss+ZZZZ``; the helper
exists so ``--started`` accepts the ISO spellings people and tools actually
produce. These tests pin every accepted shape, and in particular that an
offset the caller supplied is never silently dropped on the way to Jira.
"""

from datetime import datetime
from unittest import mock

import click.testing
from conftest import load_script, make_mock_client

_worklog_mod = load_script("jira-worklog", "core")
normalize_iso_timestamp = _worklog_mod.normalize_iso_timestamp


def _local_offset() -> str:
    """The compact local UTC offset the helper falls back to (e.g. ``+0100``)."""
    return datetime.now().astimezone().strftime("%z")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: shapes that already carry an offset
# ═══════════════════════════════════════════════════════════════════════════════


class TestOffsetPreserved:
    """A caller-supplied UTC offset must survive normalization."""

    def test_jira_format_passes_through(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000+0100") == "2025-01-15T09:00:00.000+0100"

    def test_colon_offset_is_compacted(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00+01:00") == "2025-01-15T09:00:00.000+0100"

    def test_milliseconds_with_colon_offset_keeps_offset(self):
        """Regression: the offset used to be stripped and never re-attached."""
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000+01:00") == "2025-01-15T09:00:00.000+0100"

    def test_microseconds_truncated_to_milliseconds(self):
        """datetime.isoformat() emits 6 fractional digits; Jira accepts 3."""
        assert normalize_iso_timestamp("2025-01-15T09:00:00.123456+01:00") == "2025-01-15T09:00:00.123+0100"

    def test_short_fraction_padded_to_milliseconds(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.5+01:00") == "2025-01-15T09:00:00.500+0100"

    def test_zulu_becomes_zero_offset(self):
        """Z is ISO-8601 for +00:00, but Jira only accepts the numeric form."""
        assert normalize_iso_timestamp("2025-01-15T09:00:00Z") == "2025-01-15T09:00:00.000+0000"

    def test_zulu_with_milliseconds(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000Z") == "2025-01-15T09:00:00.000+0000"

    def test_utc_colon_offset(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000+00:00") == "2025-01-15T09:00:00.000+0000"

    def test_negative_offset(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000-05:00") == "2025-01-15T09:00:00.000-0500"

    def test_compact_offset_without_milliseconds(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00+0100") == "2025-01-15T09:00:00.000+0100"

    def test_minutes_only_with_offset(self):
        assert normalize_iso_timestamp("2025-01-15T09:00+01:00") == "2025-01-15T09:00:00.000+0100"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: shapes with no offset — local time is supplied
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalTimezoneApplied:
    """A timestamp without an offset is anchored to the local zone."""

    def test_date_only(self):
        assert normalize_iso_timestamp("2025-01-15") == f"2025-01-15T00:00:00.000{_local_offset()}"

    def test_date_and_minutes(self):
        assert normalize_iso_timestamp("2025-01-15T09:00") == f"2025-01-15T09:00:00.000{_local_offset()}"

    def test_date_and_seconds(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00") == f"2025-01-15T09:00:00.000{_local_offset()}"

    def test_naive_with_milliseconds(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000") == f"2025-01-15T09:00:00.000{_local_offset()}"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: unrecognised input
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnrecognisedInput:
    """An unparseable value reaches Jira untouched, never half-rewritten."""

    def test_garbage_returned_verbatim(self):
        assert normalize_iso_timestamp("yesterday") == "yesterday"

    def test_partial_timestamp_returned_verbatim(self):
        assert normalize_iso_timestamp("2025-01-15T09") == "2025-01-15T09"

    def test_offset_never_stripped_without_being_reattached(self):
        """Whatever the body looks like, the result still carries the offset."""
        result = normalize_iso_timestamp("2025-01-15 09:00:00+01:00")
        assert result.endswith("+01:00") or result.endswith("+0100"), result


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: the CLI actually sends the normalized value
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorklogAddStarted:
    """``jira-worklog add --started`` must POST a Jira-shaped, offset-bearing timestamp."""

    def _add(self, started: str):
        mock_client = make_mock_client()
        mock_client.issue_add_json_worklog.return_value = {"id": "10001"}
        runner = click.testing.CliRunner()
        with mock.patch.object(_worklog_mod, "LazyJiraClient", return_value=mock_client):
            result = runner.invoke(_worklog_mod.cli, ["add", "TEST-1", "2h", "--started", started])
        assert result.exit_code == 0, result.output
        return mock_client.issue_add_json_worklog.call_args[0][1]

    def test_isoformat_with_microseconds_keeps_offset(self):
        """Regression: ``datetime.now().astimezone().isoformat()`` lost its offset."""
        payload = self._add("2025-01-15T09:00:00.123456+01:00")
        assert payload["started"] == "2025-01-15T09:00:00.123+0100"

    def test_zulu_timestamp_sent_in_numeric_form(self):
        payload = self._add("2025-01-15T09:00:00.000Z")
        assert payload["started"] == "2025-01-15T09:00:00.000+0000"
