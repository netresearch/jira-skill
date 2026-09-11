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

# The zone this session started in, read before any fixture has touched it.
_AMBIENT_TZNAME = time.tzname


@pytest.fixture
def berlin():
    """Europe/Berlin: +0100 in winter, +0200 in summer.

    A zone with a DST shift is the point — a fixed-offset zone cannot tell a
    correct implementation from one reading the offset at call time.

    TZ is saved and restored here rather than through ``monkeypatch``: the
    process timezone only changes when ``tzset()`` runs, and monkeypatch tears
    down *after* the fixture that requested it. A ``tzset()`` in this teardown
    would therefore re-apply Berlin, and the restore that follows would never
    take effect — leaking this zone into every later test in the session.
    """
    if not hasattr(time, "tzset"):
        pytest.skip("TZ switching needs time.tzset (POSIX)")
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
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

    @pytest.mark.parametrize("given", ["2025-01-15T09:00:00+25:00", "2025-01-15T09:00:00+12:99"])
    def test_an_out_of_range_offset_is_not_compacted(self, given):
        """`\\d{2}` would match these and emit `+2500`/`+1299` — a value that is
        neither valid nor the untouched passthrough promised for unreadable
        input, and one Jira would reject after the rewrite."""
        assert normalize_iso_timestamp(given) == given

    @pytest.mark.parametrize("given", ["2025-02-30", "2025-02-30T09:00:00", "2025-13-01T09:00"])
    def test_a_date_that_does_not_exist_is_returned_verbatim(self, berlin, given):
        """The shape matches but the calendar does not. Parsing is the first
        step that can reject the input; an uncaught ValueError would abort the
        command with a traceback instead of letting Jira answer."""
        assert normalize_iso_timestamp(given) == given


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


class TestTheFixtureDoesNotLeakItsZone:
    """The fixture changes a process-wide setting, so its restore is worth an
    assertion of its own: a leaked TZ silently re-points every later test in the
    session at Europe/Berlin, and they would still pass — wrongly.

    The baseline is captured at import, before any fixture has run, so the
    comparison is against the zone the session started in rather than against
    another call to the code under test.
    """

    def test_the_fixture_really_switches_the_zone(self, berlin):
        assert time.tzname[0] == "CET", time.tzname

    def test_the_ambient_zone_is_restored_afterwards(self):
        """Runs after the case above; `_AMBIENT_TZNAME` predates both."""
        if _AMBIENT_TZNAME[0] == "CET":
            pytest.skip("session already runs in Berlin; a leak is undetectable here")
        assert time.tzname == _AMBIENT_TZNAME, f"fixture leaked {time.tzname}, expected {_AMBIENT_TZNAME}"
