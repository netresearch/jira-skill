"""Tests for jira-move.py `issue` type-change verification messaging (#116).

Jira's REST edit endpoint silently refuses some issue-type conversions
(notably between Sub-Task types). The command already detects this via a
read-after-write check; this verifies the error message explains the REST
limitation and points the user at the UI Move action.
"""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import click.testing

_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str = "jira-move", subdir: str = "workflow"):
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_script()


def _make_mock_client(url: str = "https://jira.example.com"):
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    mc.url = url
    return mc


def _run(args, mock_client=None):
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_mod.cli, args)
    return result, mock_client


def _issue(issue_type: str, *, project: str = "FX", status: str = "Open", summary: str = "S"):
    return {
        "fields": {
            "summary": summary,
            "issuetype": {"name": issue_type},
            "status": {"name": status},
            "project": {"key": project},
        }
    }


def _put_response(status_code: int = 204):
    resp = mock.Mock()
    resp.status_code = status_code
    return resp


class TestSubtaskTypeRejection:
    def test_rejected_type_change_explains_rest_limitation(self):
        """#116: a silently-rejected Sub-Task→Sub-Task change must point at the UI."""
        mc = _make_mock_client()
        # 1) initial fetch (Sub: Task), 2) read-after-write fetch (still Sub: Task)
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Task"}, "project": {"key": "FX"}}},
        ]
        mc._session.put.return_value = _put_response(204)

        result, _ = _run(["issue", "FX-1095", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        out = result.output
        assert "rejected by Jira's REST edit endpoint" in out
        assert "still type Sub: Task" in out
        assert "Move' action" in out
        # The old, uninformative phrasing must be gone.
        assert "Type verification failed" not in out

    def test_successful_type_change_reports_success(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}}},
        ]
        mc._session.put.return_value = _put_response(204)

        result, _ = _run(["issue", "FX-1095", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 0, result.output
        assert "Sub: Task → Sub: Bug" in result.output
