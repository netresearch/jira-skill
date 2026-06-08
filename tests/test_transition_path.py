"""Tests for jira-transition.py `path` — greedy workflow walker.

`path` collapses a multi-stage transition chain into one command by running
the list -> pick -> do loop internally. The Jira API only exposes transitions
from the issue's *current* status, so the walk is greedy: take the target if
directly reachable, else the single non-backward transition, else stop.
"""

from conftest import load_script, make_mock_client, run_cli

_mod = load_script("jira-transition", "workflow")


def _run(args, mock_client=None):
    return run_cli(_mod, args, mock_client)


def _t(name: str, to: str):
    """A transition dict in Server/DC shape ({'to': 'Status'})."""
    return {"id": name, "name": name, "to": to}


def _client_at(status: str):
    mc = make_mock_client()
    mc.issue.return_value = {"fields": {"status": {"name": status}}}
    return mc


# QA -> UAT Stage -> Ready for deployment -> Resolved -> Closed, each step
# offering one forward transition plus a backward Reopen.
def _linear_chain():
    return [
        [_t("QA passed", "UAT Stage"), _t("Reopen", "Reopened")],
        [_t("UAT passed", "Ready for deployment"), _t("Reopen", "Reopened")],
        [_t("deployed", "Resolved"), _t("Reopen", "Reopened")],
        [_t("Close", "Closed"), _t("Reopen", "Reopened")],
    ]


class TestGreedyWalk:
    def test_walks_full_chain_to_target(self):
        mc = _client_at("QA")
        mc.get_issue_transitions.side_effect = _linear_chain()

        result, _ = _run(["path", "NRSIQ-57", "Closed", "--resolution", "Done"], mc)

        assert result.exit_code == 0, result.output
        assert mc.set_issue_status.call_count == 4
        # Final transition lands on Closed and carries the resolution.
        final = mc.set_issue_status.call_args_list[-1]
        assert final.args[1] == "Closed"
        assert final.kwargs["fields"] == {"resolution": {"name": "Done"}}
        # Intermediate steps must NOT set a resolution.
        assert mc.set_issue_status.call_args_list[0].kwargs["fields"] is None
        assert "UAT Stage -> Ready for deployment -> Resolved -> Closed" in result.output

    def test_already_at_target_is_noop(self):
        mc = _client_at("Closed")
        result, _ = _run(["path", "NRSIQ-57", "Closed"], mc)
        assert result.exit_code == 0, result.output
        assert mc.set_issue_status.call_count == 0
        assert "already in status" in result.output

    def test_ambiguous_step_stops_and_lists_options(self):
        mc = _client_at("Open")
        # Two forward (non-backward) transitions -> walker must not guess.
        mc.get_issue_transitions.side_effect = [
            [_t("Start", "In Progress"), _t("Postpone", "On Hold")],
        ]
        result, _ = _run(["path", "NRSIQ-57", "Closed"], mc)
        assert result.exit_code == 1, result.output
        assert mc.set_issue_status.call_count == 0
        assert "ambiguous next step" in result.output
        assert "In Progress" in result.output and "On Hold" in result.output

    def test_dry_run_shows_first_step_only(self):
        mc = _client_at("QA")
        mc.get_issue_transitions.side_effect = _linear_chain()
        result, _ = _run(["path", "NRSIQ-57", "Closed", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert mc.set_issue_status.call_count == 0
        assert "DRY RUN" in result.output
        assert "QA passed -> UAT Stage" in result.output
