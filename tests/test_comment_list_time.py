# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""`jira-comment list` prints each comment's time in local time, with the zone named.

Case one is the real one (2026-11-27): NRS-4914's comment created
`2026-11-25T11:16:05.000+0000` was listed as `[2026-11-25 11:16]`, which reads
as local time, while it was 12:16 in Berlin. Time booked from it lands an hour off.
"""

import time

import pytest
from conftest import load_script, make_mock_client, run_cli

_mod = load_script("jira-comment", "workflow")


@pytest.fixture
def berlin(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _client(created):
    mc = make_mock_client()
    comment = {"id": "1", "author": {"displayName": "Someone", "name": "someone"}, "body": "text"}
    if created is not None:
        comment["created"] = created
    mc.issue = lambda key, fields=None: {"fields": {"comment": {"comments": [comment], "total": 1}}}
    return mc


@pytest.mark.parametrize(
    ("created", "shown"),
    [
        ("2026-11-25T11:16:05.000+0000", "[2026-11-25 12:16 CET]"),
        ("2026-07-01T23:30:00.000+0000", "[2026-07-02 01:30 CEST]"),
        ("2026-11-25T12:16:05.000+0100", "[2026-11-25 12:16 CET]"),
        ("not a date at all", "[not a date at all]"),
        (None, "[N/A]"),
    ],
)
def test_table_shows_local_time_with_zone(berlin, created, shown):
    result, _ = run_cli(_mod, ["list", "PROJ-1"], _client(created))
    assert result.exit_code == 0
    assert shown in result.output


def test_json_keeps_the_raw_stamp(berlin):
    result, _ = run_cli(_mod, ["--json", "list", "PROJ-1"], _client("2026-11-25T11:16:05.000+0000"))
    assert result.exit_code == 0
    assert "2026-11-25T11:16:05.000+0000" in result.output
