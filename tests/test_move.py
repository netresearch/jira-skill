"""Tests for jira-move.py `issue` type-change verification messaging (#116).

Jira's REST edit endpoint silently refuses some issue-type conversions
(notably between Sub-Task types). The command already detects this via a
read-after-write check; this verifies the error message explains the REST
limitation and points the user at the UI Move action.
"""

from unittest import mock

from conftest import load_script, make_mock_client, run_cli

_mod = load_script("jira-move", "workflow")


def _make_mock_client(url: str = "https://jira.example.com"):
    return make_mock_client(url)


def _run(args, mock_client=None):
    return run_cli(_mod, args, mock_client)


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
