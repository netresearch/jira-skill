"""`jira-worklog.py delete` and the issue's remaining estimate."""

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from conftest import load_script

worklog = load_script("jira-worklog", "core")


def run_delete(monkeypatch, *args):
    client = MagicMock()
    client.get.return_value = {"timeSpent": "15m", "started": "2026-01-02T09:00:00.000+0000", "author": {}}
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


def test_dry_run_deletes_nothing(monkeypatch):
    client = run_delete(monkeypatch, "--keep-remaining", "--dry-run")

    client.delete.assert_not_called()
