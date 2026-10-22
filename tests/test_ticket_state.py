# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the ticket state block appended by the writing commands."""

import json

import pytest
from conftest import load_script, make_mock_client, run_cli
from lib import ticket_state
from lib.ticket_state import print_ticket_state, render_ticket_state, ticket_hints

_comment_mod = load_script("jira-comment", "workflow")
_worklog_mod = load_script("jira-worklog", "core")
_transition_mod = load_script("jira-transition", "workflow")
_create_mod = load_script("jira-create", "workflow")

ME = {"name": "jdoe", "displayName": "Jane Doe"}


def _fields(
    status="Open",
    category="new",
    assignee=None,
    resolution=None,
    spent=None,
    estimate=None,
    remaining=None,
    labels=None,
    issuetype="Task",
):
    tracking = {}
    if spent is not None:
        tracking["timeSpentSeconds"] = spent
    if estimate is not None:
        tracking["originalEstimateSeconds"] = estimate
    if remaining is not None:
        tracking["remainingEstimateSeconds"] = remaining
    return {
        "status": {"name": status, "statusCategory": {"key": category}},
        "assignee": assignee,
        "resolution": {"name": resolution} if resolution else None,
        "timetracking": tracking,
        "labels": labels or [],
        "issuetype": {"name": issuetype},
    }


def _client(fields, key="PROJ-123", me=ME):
    mc = make_mock_client()
    mc.issue.return_value = {"key": key, "fields": fields}
    mc.myself.return_value = me
    return mc


# ═══════════════════════════════════════════════════════════════════════════════
# Case one: the state two real tickets were written to six times on 2026-10-22
# ═══════════════════════════════════════════════════════════════════════════════


class TestOpenUnassignedTicket:
    def test_comment_on_open_unassigned_ticket_says_claim_it(self):
        mc = _client(_fields())
        mc.issue_add_comment.return_value = {"id": "616872"}
        result, _ = run_cli(_comment_mod, ["add", "PROJ-123", "Merged and applied"], mc)
        assert result.exit_code == 0, result.output
        assert "── PROJ-123 · Task · Open · resolution: – · assignee: unassigned" in result.output
        assert '(!) ticket is "Open" while you work on it: claim it (assign + start work)' in result.output

    def test_state_is_fetched_with_the_fields_it_renders(self):
        mc = _client(_fields())
        mc.issue_add_comment.return_value = {"id": "1"}
        run_cli(_comment_mod, ["add", "PROJ-123", "text"], mc)
        mc.issue.assert_called_with("PROJ-123", fields=ticket_state.FIELDS)
        for field in ("status", "assignee", "resolution", "timetracking", "labels", "issuetype"):
            assert field in ticket_state.FIELDS.split(",")


# ═══════════════════════════════════════════════════════════════════════════════
# Hints: each one fires in its state and stays silent in the healthy one
# ═══════════════════════════════════════════════════════════════════════════════


class TestHints:
    def test_healthy_in_progress_ticket_has_no_hint(self):
        fields = _fields(status="In Progress", category="indeterminate", assignee=ME)
        assert ticket_hints(fields, "jdoe", writing=True) == []

    def test_open_ticket_hint_only_when_writing(self):
        fields = _fields(assignee=ME)
        assert any("claim it" in h for h in ticket_hints(fields, "jdoe", writing=True))
        assert not any("claim it" in h for h in ticket_hints(fields, "jdoe", writing=False))

    def test_unassigned_in_progress(self):
        fields = _fields(status="In Progress", category="indeterminate")
        assert ticket_hints(fields, "jdoe", writing=True) == ["ticket is unassigned while you work on it: assign it"]

    @pytest.mark.parametrize(
        ("status", "category", "resolution"),
        [("QA", "indeterminate", None), ("Resolved", "done", "Done"), ("Open", "new", None)],
    )
    def test_unassigned_hint_only_in_progress(self, status, category, resolution):
        # QA waits for the team pool unassigned by design (measured live,
        # 2026-10-22); Open has the claim hint; done tickets are unassigned.
        fields = _fields(status=status, category=category, resolution=resolution)
        assert not any("unassigned" in h for h in ticket_hints(fields, "jdoe", writing=True))

    def test_foreign_assignee(self):
        fields = _fields(status="In Progress", category="indeterminate", assignee={"name": "bob"})
        assert ticket_hints(fields, "jdoe", writing=True) == ["ticket is assigned to bob, not to you"]

    def test_foreign_assignee_only_when_writing(self):
        # A create for a colleague, or a transition that hands a ticket over,
        # sets that assignee on purpose.
        fields = _fields(status="In Progress", category="indeterminate", assignee={"name": "bob"})
        assert ticket_hints(fields, "jdoe", writing=False) == []

    def test_foreign_assignee_silent_without_known_identity(self):
        fields = _fields(status="In Progress", category="indeterminate", assignee={"name": "bob"})
        assert ticket_hints(fields, None, writing=True) == []

    def test_write_to_done_ticket(self):
        fields = _fields(status="Closed", category="done", resolution="Done")
        assert ticket_hints(fields, "jdoe", writing=True) == [
            'ticket is already "Closed": reopen it if the work continues'
        ]
        assert ticket_hints(fields, "jdoe", writing=False) == []

    def test_done_without_resolution(self):
        fields = _fields(status="Resolved", category="done")
        assert 'ticket is "Resolved" without a resolution' in ticket_hints(fields, "jdoe", writing=False)

    def test_resolution_on_open_ticket(self):
        fields = _fields(status="Reopened", category="indeterminate", assignee=ME, resolution="Done")
        assert ticket_hints(fields, "jdoe", writing=False) == ['ticket carries resolution "Done" but is "Reopened"']

    def test_logged_time_over_estimate(self):
        fields = _fields(status="In Progress", category="indeterminate", assignee=ME, spent=5 * 3600, estimate=4 * 3600)
        assert ticket_hints(fields, "jdoe", writing=False) == ["logged time 5h exceeds the estimate 4h"]

    def test_logged_time_within_estimate(self):
        fields = _fields(status="In Progress", category="indeterminate", assignee=ME, spent=4 * 3600, estimate=4 * 3600)
        assert ticket_hints(fields, "jdoe", writing=False) == []


# ═══════════════════════════════════════════════════════════════════════════════
# Rendering
# ═══════════════════════════════════════════════════════════════════════════════


class TestRender:
    def test_own_ticket_with_time_and_labels(self):
        fields = _fields(
            status="QA",
            category="indeterminate",
            assignee=ME,
            spent=75 * 60,
            estimate=2 * 3600,
            remaining=45 * 60,
            labels=["needs-code-review"],
        )
        lines = render_ticket_state("PROJ-124", fields, "jdoe", writing=True)
        assert lines == [
            "── PROJ-124 · Task · QA · resolution: – · assignee: jdoe (you)",
            "   time: logged 1h 15m / estimate 2h / remaining 45m · labels: needs-code-review",
        ]

    def test_resolution_is_shown(self):
        fields = _fields(status="Resolved", category="done", resolution="Done")
        assert "resolution: Done" in render_ticket_state("X-1", fields, None, writing=False)[0]


# ═══════════════════════════════════════════════════════════════════════════════
# When the block is printed, and what it never does
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrinting:
    def test_prints_to_stderr(self, capsys):
        print_ticket_state(_client(_fields()), "PROJ-123", {})
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "── PROJ-123" in captured.err

    @pytest.mark.parametrize("flag", ["json", "quiet"])
    def test_machine_output_suppresses_it(self, capsys, flag):
        mc = _client(_fields())
        print_ticket_state(mc, "PROJ-123", {flag: True})
        assert capsys.readouterr().err == ""
        mc.issue.assert_not_called()

    @pytest.mark.parametrize("value", ["0", "false", "off", "NO"])
    def test_env_switch_turns_it_off(self, capsys, monkeypatch, value):
        monkeypatch.setenv("JIRA_TICKET_STATE", value)
        mc = _client(_fields())
        print_ticket_state(mc, "PROJ-123", {})
        assert capsys.readouterr().err == ""
        mc.issue.assert_not_called()

    def test_lookup_error_costs_one_line_and_no_exception(self, capsys):
        mc = make_mock_client()
        mc.issue.side_effect = RuntimeError("boom")
        print_ticket_state(mc, "PROJ-123", {})
        assert capsys.readouterr().err == "── PROJ-123: ticket state unavailable (RuntimeError)\n"

    def test_unknown_identity_still_renders(self, capsys):
        mc = _client(_fields(status="In Progress", category="indeterminate", assignee={"name": "bob"}))
        mc.myself.side_effect = RuntimeError("no myself")
        print_ticket_state(mc, "PROJ-123", {})
        err = capsys.readouterr().err
        assert "assignee: bob" in err
        assert "not to you" not in err

    def test_non_dict_issue_prints_nothing(self, capsys):
        print_ticket_state(make_mock_client(), "PROJ-123", {})
        assert capsys.readouterr().err == ""


class TestCommandWiring:
    def test_json_comment_output_stays_parseable(self):
        mc = _client(_fields())
        mc.issue_add_comment.return_value = {"id": "1"}
        result, _ = run_cli(_comment_mod, ["--json", "add", "PROJ-123", "text"], mc)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["id"] == "1"
        assert "── PROJ-123" not in result.output
        mc.issue.assert_not_called()

    def test_worklog_add_shows_logged_time(self):
        fields = _fields(status="In Progress", category="indeterminate", assignee=ME, spent=3600)
        mc = _client(fields)
        mc.issue_add_json_worklog.return_value = {"id": "9"}
        result, _ = run_cli(_worklog_mod, ["add", "PROJ-123", "1h"], mc)
        assert result.exit_code == 0, result.output
        assert "time: logged 1h / estimate – / remaining –" in result.output

    def test_transition_shows_new_state(self):
        mc = _client(_fields(status="QA", category="indeterminate", labels=["needs-code-review"]))
        mc.get_issue_transitions.return_value = [{"id": "301", "name": "✅ QA", "to": "QA"}]
        result, _ = run_cli(_transition_mod, ["do", "PROJ-123", "301"], mc)
        assert result.exit_code == 0, result.output
        assert "── PROJ-123 · Task · QA" in result.output

    def test_transition_to_done_does_not_say_reopen(self):
        mc = _client(_fields(status="Done", category="done", assignee=ME, resolution="Fixed"))
        mc.get_issue_transitions.return_value = [{"id": "31", "name": "Done", "to": "Done"}]
        result, _ = run_cli(_transition_mod, ["do", "PROJ-123", "31"], mc)
        assert result.exit_code == 0, result.output
        assert "── PROJ-123 · Task · Done · resolution: Fixed" in result.output
        assert "(!)" not in result.output

    def test_transition_to_done_without_resolution_still_warns(self):
        mc = _client(_fields(status="Done", category="done"))
        mc.get_issue_transitions.return_value = [{"id": "31", "name": "Done", "to": "Done"}]
        result, _ = run_cli(_transition_mod, ["do", "PROJ-123", "31"], mc)
        assert result.exit_code == 0, result.output
        assert '(!) ticket is "Done" without a resolution' in result.output

    def test_created_ticket_does_not_say_claim(self):
        mc = _client(_fields(assignee={"name": "bob"}), key="PROJ-125")
        mc.create_issue.return_value = {"key": "PROJ-125", "id": "125"}
        result, _ = run_cli(_create_mod, ["issue", "PROJ", "Summary", "--type", "Task"], mc)
        assert result.exit_code == 0, result.output
        assert "── PROJ-125 · Task · Open" in result.output
        assert "(!)" not in result.output
