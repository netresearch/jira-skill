# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

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


def _json_response(payload, status_code: int = 200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status = mock.Mock()
    return resp


# HMKG on jira.netresearch.de (read 2026-11-10): Task runs the management
# workflow with "UAT Stage", Technical task the technical one without it.
HMKG_STATUSES = {
    "Task": ["Analyse", "Closed", "Deploy to Prod", "Done", "In Progress", "New", "Open", "UAT Stage"],
    "Technical task": ["Analyse", "Closed", "Done", "In Progress", "New", "Open", "QA", "Waiting for QA"],
}
SAME_STATUSES = {"Sub: Task": ["Open", "Done"], "Sub: Bug": ["Open", "Done"]}


def _scheme(mapping: dict[str, str]):
    """projectconfig workflowscheme payload: {type name: workflow name}."""
    types = [{"id": str(i), "name": name} for i, name in enumerate(mapping)]
    by_wf: dict[str, list[str]] = {}
    for t in types:
        by_wf.setdefault(mapping[t["name"]], []).append(t["id"])
    return {"issueTypes": types, "mappings": [{"name": wf, "issueTypes": ids} for wf, ids in by_wf.items()]}


def _gets(statuses: dict, scheme=None, later_statuses: dict | None = None):
    """side_effect for client._session.get: statuses per call, scheme or 403."""
    calls = {"statuses": 0}

    def get(url, timeout=None):
        if url.endswith("/statuses"):
            calls["statuses"] += 1
            data = later_statuses if later_statuses is not None and calls["statuses"] > 1 else statuses
            return _json_response([{"name": n, "statuses": [{"name": s} for s in ss]} for n, ss in data.items()])
        if "/rest/projectconfig/1/workflowscheme/" in url:
            return _json_response(scheme) if scheme is not None else _json_response({}, 403)
        raise AssertionError(f"unexpected GET {url}")

    return get


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
        mc._session.get.side_effect = _gets(SAME_STATUSES)

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
        mc._session.get.side_effect = _gets(SAME_STATUSES)

        result, _ = _run(["issue", "FX-1095", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 0, result.output
        assert "Sub: Task → Sub: Bug" in result.output


class TestRequestTimeout:
    def test_put_carries_the_client_timeout(self):
        """The raw session PUT bypasses the library's timeout; it must pass its own."""
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(SAME_STATUSES)

        result, _ = _run(["issue", "FX-1095", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 0, result.output
        assert mc._session.put.call_args.kwargs.get("timeout") == _mod.JIRA_TIMEOUT


class TestWorkflowGuard:
    """A type change whose target type runs another workflow is refused before the PUT,
    and an inconsistent result is rolled back after it (HMKG-2540, 2026-11-06)."""

    def test_refuses_when_target_workflow_lacks_the_status(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="UAT Stage")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES)

        result, _ = _run(["issue", "HMKG-2540", "HMKG", "--issue-type", "Technical task"], mc)

        assert result.exit_code == 1, result.output
        assert "status 'UAT Stage' does not exist in the workflow of 'Technical task'" in result.output
        assert "Move' action" in result.output
        mc._session.put.assert_not_called()

    def test_dry_run_refuses_as_well(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="UAT Stage")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES)

        result, _ = _run(["issue", "HMKG-2540", "HMKG", "--issue-type", "Technical task", "--dry-run"], mc)

        assert result.exit_code == 1, result.output
        assert "DRY RUN" not in result.output

    def test_refuses_when_the_scheme_names_different_workflows(self):
        """A status both workflows have does not make the change safe."""
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="In Progress")]
        mc._session.get.side_effect = _gets(
            HMKG_STATUSES, scheme=_scheme({"Task": "Management", "Technical task": "Technical"})
        )

        result, _ = _run(["issue", "HMKG-1", "HMKG", "--issue-type", "Technical task"], mc)

        assert result.exit_code == 1, result.output
        assert "'Task' uses workflow 'Management', 'Technical task' uses 'Technical'" in result.output
        mc._session.put.assert_not_called()

    def test_unreadable_scheme_falls_back_to_comparing_status_sets(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="In Progress")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES)  # scheme answers 403

        result, _ = _run(["issue", "HMKG-1", "HMKG", "--issue-type", "Technical task"], mc)

        assert result.exit_code == 1, result.output
        assert "have different statuses" in result.output
        mc._session.put.assert_not_called()

    def test_same_workflow_passes(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=_scheme({"Sub: Task": "W", "Sub: Bug": "W"}))

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 0, result.output
        mc._session.put.assert_called_once()

    def test_inconsistent_result_is_rolled_back(self):
        """If the status is not in the new type's workflow after the change, the old type returns."""
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
            {"fields": {"issuetype": {"name": "Sub: Task"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(SAME_STATUSES, later_statuses={"Sub: Task": ["Open"], "Sub: Bug": ["Done"]})

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "The type was set back to Sub: Task" in result.output
        assert mc._session.put.call_count == 2
        assert mc._session.put.call_args.kwargs["json"] == {"fields": {"issuetype": {"name": "Sub: Task"}}}

    def test_failed_rollback_is_reported(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
            {"fields": {"issuetype": {"name": "Sub: Bug"}}},
        ]
        mc._session.put.side_effect = [_put_response(204), _put_response(400)]
        mc._session.get.side_effect = _gets(SAME_STATUSES, later_statuses={"Sub: Task": ["Open"], "Sub: Bug": ["Done"]})

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "FAILED (HTTP 400, type now Sub: Bug)" in result.output
