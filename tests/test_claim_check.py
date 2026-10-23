# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the claim check: `work` and `comment add` on a ticket nobody took.

On 2026-10-23 an agent triaged NRS-4833 with `jira-issue.py work`, posted
"I am on it" with `jira-comment.py add`, and never assigned the ticket nor
started work on it. The ticket stayed Open and unassigned and looked untouched.
"""

import json
import sys

import pytest
from conftest import load_script, make_mock_client, run_cli
from lib import ticket_state
from lib.config import DEFAULT_QA_STATUSES, DEFAULT_RESOLVED_STATUSES, DEFAULT_WORKING_STATUSES

_issue_mod = load_script("jira-issue", "core")
_comment_mod = load_script("jira-comment", "workflow")

ME = {"name": "jdoe", "displayName": "Jane Doe"}
OTHER = {"name": "mmuster", "displayName": "Max Muster"}
STATUS_SETS = {
    "qa": frozenset(DEFAULT_QA_STATUSES),
    "working": frozenset(DEFAULT_WORKING_STATUSES),
    "resolved": frozenset(DEFAULT_RESOLVED_STATUSES),
}


@pytest.fixture(autouse=True)
def _default_status_sets(monkeypatch):
    """Use the built-in status sets, whatever profiles.json the developer has."""
    for mod in (_issue_mod, _comment_mod, ticket_state):
        if hasattr(mod, "load_status_sets"):
            monkeypatch.setattr(mod, "load_status_sets", lambda **_: STATUS_SETS)


def _stderr_so_far() -> str:
    """What the command has written to stderr up to now (inside CliRunner)."""
    sys.stderr.flush()
    return sys.stderr.buffer.getvalue().decode()


def _status(name, category):
    return {"name": name, "statusCategory": {"key": category}}


def _work_client(status, assignee, me=ME):
    mc = make_mock_client()
    mc.issue.return_value = {
        "key": "NRS-4833",
        "fields": {
            "summary": "Something broke",
            "status": status,
            "assignee": assignee,
            "description": "Body",
            "attachment": [],
            "issuelinks": [],
        },
    }
    mc.get.return_value = {"comments": [], "total": 0}
    mc.get_issue_remote_links.return_value = []
    mc.myself.return_value = me
    return mc


def _comment_client(status, assignee, me=ME):
    mc = make_mock_client()
    mc.issue.return_value = {
        "key": "NRS-4833",
        "fields": {"status": status, "assignee": assignee, "labels": [], "issuetype": {"name": "Task"}},
    }
    mc.myself.return_value = me
    mc.issue_add_comment.return_value = {"id": "4711"}
    return mc


# ═══════════════════════════════════════════════════════════════════════════════
# jira-issue.py work
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkClaimNotice:
    def test_open_unassigned_ticket_gets_the_claim_notice_with_commands(self):
        mc = _work_client(_status("Open", "new"), None)
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert result.exit_code == 0, result.output
        assert "CLAIM NRS-4833" in result.stderr
        assert "unassigned" in result.stderr
        assert "jira-issue.py update NRS-4833 --assignee me" in result.stderr
        assert "jira-transition.py list NRS-4833" in result.stderr
        assert "CLAIM" not in result.stdout

    def test_notice_is_written_before_the_body_is_fetched(self):
        mc = _work_client(_status("Open", "new"), None)
        seen = []
        mc.get.side_effect = lambda *a, **k: (seen.append(_stderr_so_far()), {"comments": [], "total": 0})[1]
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert result.exit_code == 0, result.output
        assert seen
        assert "CLAIM NRS-4833" in seen[0]

    def test_mine_and_in_progress_gets_no_notice(self):
        mc = _work_client(_status("In Progress", "indeterminate"), ME)
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert result.exit_code == 0, result.output
        assert "CLAIM" not in result.output

    def test_mine_but_in_qa_names_only_the_transition(self):
        mc = _work_client(_status("QA", "indeterminate"), ME)
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert "CLAIM NRS-4833" in result.stderr
        assert '"QA"' in result.stderr
        assert "--assignee me" not in result.stderr
        assert "jira-transition.py list NRS-4833" in result.stderr

    def test_someone_elses_in_progress_ticket_names_only_the_assignee(self):
        mc = _work_client(_status("In Progress", "indeterminate"), OTHER)
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert "CLAIM NRS-4833" in result.stderr
        assert "mmuster" in result.stderr
        assert "--assignee me" in result.stderr
        assert "jira-transition.py" not in result.stderr

    def test_resolved_ticket_asks_for_a_reopen(self):
        mc = _work_client(_status("Resolved", "done"), ME)
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert "CLAIM NRS-4833" in result.stderr
        assert '"Resolved"' in result.stderr

    def test_unknown_caller_still_flags_the_status(self):
        mc = _work_client(_status("Open", "new"), OTHER)
        mc.myself.side_effect = RuntimeError("boom")
        result, _ = run_cli(_issue_mod, ["work", "NRS-4833"], mc)
        assert result.exit_code == 0, result.output
        assert "CLAIM NRS-4833" in result.stderr
        assert "mmuster" not in result.stderr

    def test_json_output_stays_parseable_and_carries_the_claim(self):
        mc = _work_client(_status("Open", "new"), None)
        result, _ = run_cli(_issue_mod, ["--json", "work", "NRS-4833"], mc)
        assert result.exit_code == 0, result.output
        assert "CLAIM" not in result.stderr
        payload = json.loads(result.stdout)
        assert payload["key"] == "NRS-4833"
        assert payload["claim"]["needed"] is True
        assert "jira-issue.py update NRS-4833 --assignee me" in payload["claim"]["commands"]

    def test_json_output_for_a_claimed_ticket_says_not_needed(self):
        mc = _work_client(_status("In Progress", "indeterminate"), ME)
        result, _ = run_cli(_issue_mod, ["--json", "work", "NRS-4833"], mc)
        payload = json.loads(result.stdout)
        assert payload["claim"] == {"needed": False, "reasons": [], "commands": []}

    def test_failing_status_sets_do_not_cost_the_bundle(self, monkeypatch):
        def broken(**_):
            raise ValueError("profiles.json is broken")

        monkeypatch.setattr(_issue_mod, "load_status_sets", broken)
        mc = _work_client(_status("Open", "new"), None)
        result, _ = run_cli(_issue_mod, ["--json", "work", "NRS-4833"], mc)
        assert result.exit_code == 0, result.output
        assert "claim check unavailable (ValueError)" in result.stderr
        payload = json.loads(result.stdout)
        assert payload["claim"] is None
        assert payload["summary"] == "Something broke"

    def test_quiet_prints_only_the_key(self):
        mc = _work_client(_status("Open", "new"), None)
        result, _ = run_cli(_issue_mod, ["--quiet", "work", "NRS-4833"], mc)
        assert result.output == "NRS-4833\n"


# ═══════════════════════════════════════════════════════════════════════════════
# jira-comment.py add
# ═══════════════════════════════════════════════════════════════════════════════


class TestCommentClaimWarning:
    def test_open_unassigned_ticket_warns_before_posting(self):
        mc = _comment_client(_status("Open", "new"), None)
        seen = []
        mc.issue_add_comment.side_effect = lambda *a, **k: (seen.append(_stderr_so_far()), {"id": "4711"})[1]
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "I am on it"], mc)
        assert result.exit_code == 0, result.output
        assert seen
        assert "NRS-4833 is not claimed" in seen[0]
        mc.issue_add_comment.assert_called_once()

    def test_someone_elses_ticket_in_qa_warns(self):
        mc = _comment_client(_status("QA", "indeterminate"), OTHER)
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "text"], mc)
        assert "NRS-4833 is not claimed" in result.stderr

    def test_mine_and_open_does_not_warn(self):
        mc = _comment_client(_status("Open", "new"), ME)
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "text"], mc)
        assert result.exit_code == 0, result.output
        assert "is not claimed" not in result.output

    def test_someone_elses_ticket_in_progress_does_not_warn(self):
        mc = _comment_client(_status("In Progress", "indeterminate"), OTHER)
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "text"], mc)
        assert "is not claimed" not in result.output

    def test_quiet_does_not_warn(self):
        mc = _comment_client(_status("Open", "new"), None)
        result, _ = run_cli(_comment_mod, ["--quiet", "add", "NRS-4833", "text"], mc)
        assert result.stdout == "4711\n"
        assert "is not claimed" not in result.stderr
        mc.issue.assert_not_called()

    def test_json_stdout_stays_parseable(self):
        mc = _comment_client(_status("Open", "new"), None)
        result, _ = run_cli(_comment_mod, ["--json", "add", "NRS-4833", "text"], mc)
        assert result.exit_code == 0, result.output
        assert "NRS-4833 is not claimed" in result.stderr
        payload = json.loads(result.stdout)
        assert payload["id"] == "4711"
        assert payload["ticket_state"]["status"] == "Open"

    def test_one_extra_issue_read_and_one_myself(self):
        mc = _comment_client(_status("Open", "new"), None)
        run_cli(_comment_mod, ["add", "NRS-4833", "text"], mc)
        # One read before the post for the warning, one after for a fresh state
        # block (an automation rule may move the ticket on a comment).
        assert mc.issue.call_count == 2
        assert mc.myself.call_count == 1

    def test_dry_run_reads_nothing(self):
        mc = _comment_client(_status("Open", "new"), None)
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "text", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        mc.issue.assert_not_called()
        assert "is not claimed" not in result.output

    def test_ticket_state_off_also_silences_the_warning(self, monkeypatch):
        monkeypatch.setenv("JIRA_TICKET_STATE", "0")
        mc = _comment_client(_status("Open", "new"), None)
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "text"], mc)
        assert "is not claimed" not in result.output
        mc.issue.assert_not_called()

    def test_failed_lookup_still_posts(self):
        mc = _comment_client(_status("Open", "new"), None)
        mc.issue.side_effect = RuntimeError("down")
        result, _ = run_cli(_comment_mod, ["add", "NRS-4833", "text"], mc)
        assert result.exit_code == 0, result.output
        mc.issue_add_comment.assert_called_once()
