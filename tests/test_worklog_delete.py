"""`jira-worklog.py delete` and the issue's remaining estimate."""

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from conftest import load_script

worklog = load_script("jira-worklog", "core")


def run_delete(monkeypatch, *args):
    client = MagicMock()
    client.get.return_value = {"id": "42", "timeSpent": "15m", "started": "2026-01-02T09:00:00.000+0000", "author": {}}
    monkeypatch.setattr(worklog, "LazyJiraClient", lambda *a, **kw: client)
    result = CliRunner().invoke(worklog.cli, ["delete", "PROJ-1", "42", *args])
    assert result.exit_code == 0, result.output
    return client


@pytest.mark.parametrize(
    ("args", "params"),
    [
        ((), None),
        (("--keep-remaining",), {"adjustEstimate": "leave"}),
    ],
)
def test_delete_passes_the_estimate_mode(monkeypatch, args, params):
    client = run_delete(monkeypatch, *args)

    client.delete.assert_called_once_with("rest/api/2/issue/PROJ-1/worklog/42", params=params)


@pytest.mark.parametrize("worklog_id", ["../../PROJ-2", "42#", "4 2", "", "²", "٤٢"])
def test_a_non_numeric_worklog_id_sends_nothing(monkeypatch, worklog_id):
    client = MagicMock()
    monkeypatch.setattr(worklog, "LazyJiraClient", lambda *a, **kw: client)
    result = CliRunner().invoke(worklog.cli, ["delete", "PROJ-1", worklog_id])

    assert result.exit_code == 2, result.output
    assert "WORKLOG_ID" in result.output
    client.get.assert_not_called()
    client.delete.assert_not_called()


def test_a_response_for_another_worklog_deletes_nothing(monkeypatch):
    client = MagicMock()
    # What GET issue/PROJ-2 returns when the path was retargeted: no worklog id.
    client.get.return_value = {"id": "10002", "key": "PROJ-2", "fields": {}}
    monkeypatch.setattr(worklog, "LazyJiraClient", lambda *a, **kw: client)
    result = CliRunner().invoke(worklog.cli, ["delete", "PROJ-1", "42"])

    assert result.exit_code == 1, result.output
    assert "nothing deleted" in result.output
    client.delete.assert_not_called()


def test_a_leading_zero_still_matches_the_fetched_id(monkeypatch):
    client = run_delete(monkeypatch)  # fetched id "42"
    client.get.reset_mock()
    client.delete.reset_mock()
    result = CliRunner().invoke(worklog.cli, ["delete", "PROJ-1", "042"])

    assert result.exit_code == 0, result.output
    client.get.assert_called_once_with("rest/api/2/issue/PROJ-1/worklog/042")
    client.delete.assert_called_once_with("rest/api/2/issue/PROJ-1/worklog/042", params=None)


def test_dry_run_deletes_nothing(monkeypatch):
    client = run_delete(monkeypatch, "--keep-remaining", "--dry-run")

    client.delete.assert_not_called()
