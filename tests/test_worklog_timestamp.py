"""Tests for ``normalize_iso_timestamp`` in ``core/jira-worklog.py``.

Jira's worklog API wants exactly ``YYYY-MM-DDTHH:MM:SS.sss+ZZZZ``; the helper
exists so ``--started`` accepts the ISO spellings people and tools actually
produce. These tests pin every accepted shape, that an offset the caller
supplied is never silently dropped, and that a value without one is anchored to
the offset in force **on its own date** rather than today's.

The zone is pinned per test rather than read from the machine. An expectation
built from the same call the implementation makes would compare the code
against itself and pass for any offset it happened to produce — including the
wrong one.
"""

import os
import time
from unittest import mock

import click.testing
import pytest
from conftest import load_script, make_mock_client

_worklog_mod = load_script("jira-worklog", "core")
normalize_iso_timestamp = _worklog_mod.normalize_iso_timestamp


@pytest.fixture
def berlin(monkeypatch):
    """Europe/Berlin: +0100 in winter, +0200 in summer.

    A zone with a DST shift is the point — a fixed-offset zone cannot tell a
    correct implementation from one reading the offset at call time.
    """
    if not hasattr(time, "tzset"):
        pytest.skip("TZ switching needs time.tzset (POSIX)")
    monkeypatch.setitem(os.environ, "TZ", "Europe/Berlin")
    time.tzset()
    yield
    # monkeypatch restores TZ; tzset must be re-run for it to take effect.
    time.tzset()


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

    def test_negative_offset_is_compacted(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00.000-05:00") == "2025-01-15T09:00:00.000-0500"

    def test_compact_offset_without_milliseconds(self):
        assert normalize_iso_timestamp("2025-01-15T09:00:00+0100") == "2025-01-15T09:00:00.000+0100"

    def test_minutes_only_with_offset(self):
        assert normalize_iso_timestamp("2025-01-15T09:00+01:00") == "2025-01-15T09:00:00.000+0100"

    def test_zulu_becomes_numeric_zero(self):
        """Jira rejects the `Z` spelling; +0000 is the same instant."""
        assert normalize_iso_timestamp("2025-01-15T09:00:00Z") == "2025-01-15T09:00:00.000+0000"

    def test_an_offset_bearing_input_ignores_the_local_zone(self, berlin):
        """A July timestamp at +0100 keeps +0100, not Berlin's summer +0200."""
        assert normalize_iso_timestamp("2025-07-15T09:00:00+01:00") == "2025-07-15T09:00:00.000+0100"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: shapes with no offset — local time for that date is supplied
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocalOffsetIsResolvedForTheTimestampsOwnDate:
    """The offset comes from the timestamp's date, never from `now()`.

    Every expectation here is a literal. Under the old implementation all four
    winter cases returned Berlin's *current* offset, so they passed in January
    and were an hour wrong from late March to late October.
    """

    @pytest.mark.parametrize(
        "given,expected",
        [
            ("2025-01-15", "2025-01-15T00:00:00.000+0100"),
            ("2025-01-15T09:00", "2025-01-15T09:00:00.000+0100"),
            ("2025-01-15T09:00:00", "2025-01-15T09:00:00.000+0100"),
            ("2025-01-15T09:00:00.000", "2025-01-15T09:00:00.000+0100"),
        ],
    )
    def test_winter_dates_get_winter_offset(self, berlin, given, expected):
        assert normalize_iso_timestamp(given) == expected

    @pytest.mark.parametrize(
        "given,expected",
        [
            ("2025-07-15", "2025-07-15T00:00:00.000+0200"),
            ("2025-07-15T09:00", "2025-07-15T09:00:00.000+0200"),
            ("2025-07-15T09:00:00", "2025-07-15T09:00:00.000+0200"),
            ("2025-07-15T09:00:00.000", "2025-07-15T09:00:00.000+0200"),
        ],
    )
    def test_summer_dates_get_summer_offset(self, berlin, given, expected):
        assert normalize_iso_timestamp(given) == expected

    def test_the_two_halves_of_the_year_differ(self, berlin):
        """The assertion the tautological version could not make: one zone, one
        wall-clock time, two dates, two different offsets."""
        winter = normalize_iso_timestamp("2025-01-15T09:00:00")
        summer = normalize_iso_timestamp("2025-07-15T09:00:00")
        assert winter.endswith("+0100"), winter
        assert summer.endswith("+0200"), summer


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

    def test_a_naive_timestamp_is_sent_with_its_own_dates_offset(self, berlin):
        payload = self._add("2025-07-15T09:00:00")
        assert payload["started"] == "2025-07-15T09:00:00.000+0200"
