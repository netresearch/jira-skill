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


SAME_SCHEME = _scheme({"Sub: Task": "W", "Sub: Bug": "W"})


def _gets(
    statuses: dict,
    scheme=None,
    transitions: list[str] | None = ("Done",),
    transitions_status: int = 200,
    later_transitions: list[str] | None = None,
    auth_error: tuple[str, ...] = (),
):
    """side_effect for client._session.get: statuses, scheme (or 403) and the issue's transition targets.

    ``later_transitions`` answers every transitions read after the first (the read after the PUT).
    ``auth_error`` names reads that raise AuthenticationError, as the client's response hook does
    on 401/403: "scheme", "transitions" (every read) or "later_transitions" (reads after the first).
    """
    calls = {"transitions": 0}

    def get(url, timeout=None):
        if url.endswith("/statuses"):
            return _json_response([{"name": n, "statuses": [{"name": s} for s in ss]} for n, ss in statuses.items()])
        if "/rest/projectconfig/1/workflowscheme/" in url:
            if "scheme" in auth_error:
                raise _mod.AuthenticationError("403 Forbidden")
            return _json_response(scheme) if scheme is not None else _json_response({}, 403)
        if url.endswith("/transitions"):
            calls["transitions"] += 1
            if "transitions" in auth_error or ("later_transitions" in auth_error and calls["transitions"] > 1):
                raise _mod.AuthenticationError("403 Forbidden")
            targets = later_transitions if later_transitions is not None and calls["transitions"] > 1 else transitions
            payload = {"transitions": [{"id": str(i), "to": {"name": s}} for i, s in enumerate(targets or [])]}
            return _json_response(payload, transitions_status)
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
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME)

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
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME)

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
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME)

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

    def test_issue_left_on_another_workflow_is_rolled_back(self):
        """The scheme view says both types share a workflow, but after the change the issue runs another one.

        Its transitions then lead to UAT Stage, a status of the management workflow only
        (the shape HMKG-2540 showed after the REST change of 2026-11-06), so the change is undone.
        """
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Technical task", project="HMKG", status="In Progress"),
            {"fields": {"issuetype": {"name": "Bug"}, "project": {"key": "HMKG"}, "status": {"name": "In Progress"}}},
            {"fields": {"issuetype": {"name": "Technical task"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(
            {**HMKG_STATUSES, "Bug": HMKG_STATUSES["Technical task"]},
            scheme=_scheme({"Task": "Management", "Technical task": "Technical", "Bug": "Technical"}),
            transitions=["QA", "Open"],
            later_transitions=["UAT Stage", "Open"],
        )

        result, _ = _run(["issue", "HMKG-2540", "HMKG", "--issue-type", "Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "does not run the workflow of Bug" in result.output
        assert "'UAT Stage'" in result.output
        assert "'Open'" not in result.output
        assert "The type was set back to Technical task" in result.output
        assert mc._session.put.call_count == 2
        assert mc._session.put.call_args.kwargs["json"] == {"fields": {"issuetype": {"name": "Technical task"}}}

    def test_failed_rollback_is_reported(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
            {"fields": {"issuetype": {"name": "Sub: Bug"}}},
        ]
        mc._session.put.side_effect = [_put_response(204), _put_response(400)]
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME, later_transitions=["Rejected"])

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "FAILED (HTTP 400, type now Sub: Bug)" in result.output

    def test_unreadable_transitions_warn_and_keep_the_change(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME, transitions_status=500)

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 0, result.output
        assert "Could not verify that FX-1 runs the workflow of Sub: Bug" in result.output
        mc._session.put.assert_called_once()

    def test_scheme_read_raising_authentication_error_falls_back_to_status_sets(self):
        """The client's response hook raises AuthenticationError on 403; that means "scheme unknown"."""
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="In Progress")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES, auth_error=("scheme",))

        result, _ = _run(["issue", "HMKG-1", "HMKG", "--issue-type", "Technical task"], mc)

        assert result.exit_code == 1, result.output
        assert "have different statuses" in result.output
        assert "Authentication failed" not in result.output
        mc._session.put.assert_not_called()

    def test_transitions_read_raising_authentication_error_after_the_change_warns(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME, auth_error=("later_transitions",))

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 0, result.output
        assert "Could not verify that FX-1 runs the workflow of Sub: Bug" in result.output
        mc._session.put.assert_called_once()

    def test_type_missing_from_the_scheme_falls_back_to_status_sets(self):
        """A readable scheme that does not name one of the two types is no proof of the same workflow."""
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="In Progress")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES, scheme=_scheme({"Task": "Management"}))

        result, _ = _run(["issue", "HMKG-1", "HMKG", "--issue-type", "Technical task"], mc)

        assert result.exit_code == 1, result.output
        assert "have different statuses" in result.output
        mc._session.put.assert_not_called()

    def test_issue_already_on_another_workflow_is_refused_for_a_third_type(self):
        """HMKG-2540 between 2026-11-06 and 2026-11-10: a Technical task running the management workflow."""
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Technical task", project="HMKG", status="UAT Stage")]
        mc._session.get.side_effect = _gets(
            {**HMKG_STATUSES, "Bug": HMKG_STATUSES["Technical task"]}, transitions=["Deploy to Prod", "Open"]
        )

        result, _ = _run(["issue", "HMKG-2540", "HMKG", "--issue-type", "Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "already runs another workflow than the one of Technical task" in result.output
        assert "'Deploy to Prod', 'UAT Stage'" in result.output
        assert "Change it to the type whose workflow it runs" in result.output
        mc._session.put.assert_not_called()

    def test_issue_already_on_another_workflow_can_be_set_back(self):
        """Setting the type whose workflow the issue runs is the repair, even though the scheme maps the types apart."""
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Technical task", project="HMKG", status="UAT Stage"),
            {"fields": {"issuetype": {"name": "Task"}, "project": {"key": "HMKG"}, "status": {"name": "UAT Stage"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(
            HMKG_STATUSES,
            scheme=_scheme({"Task": "Management", "Technical task": "Technical"}),
            transitions=["Deploy to Prod", "Open"],
        )

        result, _ = _run(["issue", "HMKG-2540", "HMKG", "--issue-type", "Task"], mc)

        assert result.exit_code == 0, result.output
        assert "Task has all its statuses, so the change repairs it" in result.output
        mc._session.put.assert_called_once()
        assert mc._session.put.call_args.kwargs["json"] == {"fields": {"issuetype": {"name": "Task"}}}

    def test_type_name_in_other_case_is_checked_under_the_project_spelling(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="UAT Stage")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES, transitions=["Deploy to Prod"])

        result, _ = _run(["issue", "HMKG-1", "HMKG", "--issue-type", "technical task"], mc)

        assert result.exit_code == 1, result.output
        assert "status 'UAT Stage' does not exist in the workflow of 'Technical task'" in result.output
        mc._session.put.assert_not_called()

    def test_exception_during_rollback_is_reported_as_failed_rollback(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
        ]
        mc._session.put.side_effect = [_put_response(204), _mod.requests.ConnectionError("connection reset")]
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=SAME_SCHEME, later_transitions=["Rejected"])

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "Setting the type back to Sub: Task FAILED (connection reset)" in result.output
        assert "Failed to move" not in result.output

    def test_equal_statuses_with_unreadable_scheme_are_refused(self):
        """Two workflows can share every status; without the scheme the change is unverifiable.

        The check after the change cannot catch this case either, because the old workflow
        offers no status the new type lacks.
        """
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Sub: Task")]
        mc._session.get.side_effect = _gets(SAME_STATUSES)  # scheme answers 403

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "cannot confirm that 'Sub: Task' and 'Sub: Bug' use the same workflow" in result.output
        assert "project-admin rights, which can read the scheme" in result.output
        assert "--assume-same-workflow" in result.output
        mc._session.put.assert_not_called()

    def test_equal_statuses_with_scheme_raising_authentication_error_are_refused(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Sub: Task")]
        mc._session.get.side_effect = _gets(SAME_STATUSES, auth_error=("scheme",))

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug", "--dry-run"], mc)

        assert result.exit_code == 1, result.output
        assert "cannot confirm" in result.output
        assert "DRY RUN" not in result.output
        mc._session.put.assert_not_called()

    def test_assume_same_workflow_allows_equal_statuses_without_the_scheme(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [
            _issue("Sub: Task"),
            {"fields": {"issuetype": {"name": "Sub: Bug"}, "project": {"key": "FX"}, "status": {"name": "Open"}}},
        ]
        mc._session.put.return_value = _put_response(204)
        mc._session.get.side_effect = _gets(SAME_STATUSES)

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug", "--assume-same-workflow"], mc)

        assert result.exit_code == 0, result.output
        mc._session.put.assert_called_once()

    def test_assume_same_workflow_does_not_override_different_statuses(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Task", project="HMKG", status="In Progress")]
        mc._session.get.side_effect = _gets(HMKG_STATUSES)

        result, _ = _run(["issue", "HMKG-1", "HMKG", "--issue-type", "Technical task", "--assume-same-workflow"], mc)

        assert result.exit_code == 1, result.output
        assert "have different statuses" in result.output
        mc._session.put.assert_not_called()

    def test_assume_same_workflow_does_not_override_a_readable_scheme(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Sub: Task")]
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=_scheme({"Sub: Task": "A", "Sub: Bug": "B"}))

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug", "--assume-same-workflow"], mc)

        assert result.exit_code == 1, result.output
        assert "'Sub: Task' uses workflow 'A', 'Sub: Bug' uses 'B'" in result.output
        mc._session.put.assert_not_called()

    def test_equal_statuses_with_a_type_missing_from_the_scheme_name_the_gap(self):
        mc = _make_mock_client()
        mc.issue.side_effect = [_issue("Sub: Task")]
        mc._session.get.side_effect = _gets(SAME_STATUSES, scheme=_scheme({"Sub: Task": "W"}))

        result, _ = _run(["issue", "FX-1", "FX", "--issue-type", "Sub: Bug"], mc)

        assert result.exit_code == 1, result.output
        assert "the workflow scheme of FX does not name both types" in result.output
        assert "cannot read the workflow scheme" not in result.output
        assert "project-admin rights" not in result.output
        assert "Check the project's workflow scheme" in result.output
        mc._session.put.assert_not_called()
