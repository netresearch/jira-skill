# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the self-review check in jira-qa-gather.py.

Workflows that unassign a ticket on its move into QA leave every QA ticket
"Unassigned", so the assignee can no longer tell a reviewer that the work is
their own. The check reads the changelog (who moved it into QA, who last
moved it to In Progress) and the worklog authors instead. Cases live in
``fixtures/qa_self_review.json``.
"""

import copy
import json
from pathlib import Path

import pytest
from conftest import load_script, make_mock_client, run_cli

_mod = load_script("jira-qa-gather", "utility")

_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "qa_self_review.json").read_text())
_STATUS_SETS = {
    "qa": frozenset({"QA"}),
    "working": frozenset({"Open", "In Progress"}),
    "resolved": frozenset({"Closed"}),
}
_CATEGORIES = {s["id"]: s["statusCategory"]["key"] for s in _FIXTURE["statuses"]}


def _issue(case: dict) -> dict:
    creator = {"name": case["creator"], "displayName": case["creator"].title()}
    return {
        "key": "QA-9",
        "fields": {
            "summary": "Self-review fixture",
            "status": {"name": "QA"},
            "assignee": None,
            "project": {"key": "QA"},
            "creator": creator,
            "reporter": creator,
            "resolution": None,
            "issuelinks": [],
        },
        # A copy: tests that edit a history must not leak into the shared fixture.
        "changelog": {"histories": copy.deepcopy(case["histories"])},
    }


def _worklogs(case: dict) -> list[dict]:
    return [{"author": {"name": a}, "timeSpentSeconds": 600} for a in case["worklog_authors"]]


@pytest.mark.parametrize("name", sorted(_FIXTURE["cases"]))
def test_verdict(name):
    case = _FIXTURE["cases"][name]
    sr = _mod.compute_self_review(_issue(case), _worklogs(case), case["reviewer"], _STATUS_SETS, _CATEGORIES)
    expect = case["expect"]
    assert sr["verdict"] == expect["verdict"]
    assert sr["matched"] == expect["matched"]
    assert sr["implementer"] == expect["implementer"]
    assert sr["in_progress_by"] == expect["in_progress_by"]
    assert sr["worklog_authors"] == sorted(set(case["worklog_authors"]))
    # Creator / reporter are shown, never matched.
    assert sr["creator"] == f"{case['creator'].title()} ({case['creator']})"


def test_unreadable_worklog_is_unknown_not_other():
    case = _FIXTURE["cases"]["other_implementer"]
    sr = _mod.compute_self_review(_issue(case), None, "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["verdict"] == "unknown"
    assert "worklog" in sr["reason"]
    assert sr["worklog_empty"] is None
    assert sr["worklog_authors"] is None


def test_handover_without_author_is_unknown_not_other():
    # A deleted/anonymous user or a post-function leaves the history without
    # an author; the implementer is then unknown, not "someone else".
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    del issue["changelog"]["histories"][-1]["author"]
    sr = _mod.compute_self_review(issue, _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["implementer"] is None
    assert sr["verdict"] == "unknown"
    assert "implementer" in sr["reason"]


def test_unknown_reviewer_never_matches_a_missing_author():
    # /myself failed and the handover has no author: None must not equal None.
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    del issue["changelog"]["histories"][-1]["author"]
    sr = _mod.compute_self_review(issue, _worklogs(case), None, _STATUS_SETS, _CATEGORIES)
    assert sr["matched"] == []
    assert sr["verdict"] == "unknown"


def test_truncated_changelog_is_unknown_not_other():
    # Cloud caps the embedded changelog; a later handover may be missing.
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    issue["changelog"]["total"] = len(case["histories"]) + 1
    sr = _mod.compute_self_review(issue, _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["verdict"] == "unknown"
    assert "changelog" in sr["reason"]
    issue["changelog"]["total"] = len(case["histories"])
    assert _mod.compute_self_review(issue, _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)["verdict"] == "other"


def test_move_to_unlisted_status_is_unknown_not_other():
    # "In Progress" (id 3) missing from the categories, e.g. a deleted status:
    # whoever made that move may have been the reviewer.
    case = _FIXTURE["cases"]["other_implementer"]
    categories = {k: v for k, v in _CATEGORIES.items() if k != "3"}
    sr = _mod.compute_self_review(_issue(case), _worklogs(case), "rev", _STATUS_SETS, categories)
    assert sr["in_progress_by"] is None
    assert sr["verdict"] == "unknown"
    assert "status categories" in sr["reason"]


def test_resolution_and_worklog_empty():
    case = _FIXTURE["cases"]["no_into_qa"]
    issue = _issue(case)
    issue["fields"]["resolution"] = {"name": "Done"}
    sr = _mod.compute_self_review(issue, [], "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["resolution"] == "Done"
    assert sr["worklog_empty"] is True


def _client(case: dict, reviewer: str):
    mc = make_mock_client()
    mc.issue.return_value = _issue(case)
    mc.get.return_value = {"comments": [], "total": 0, "startAt": 0, "maxResults": 100}
    mc.issue_get_worklog.return_value = {"worklogs": _worklogs(case)}
    mc.myself.return_value = {"name": reviewer, "displayName": reviewer.title()}
    mc.get_all_statuses.return_value = _FIXTURE["statuses"]
    mc.get_issue_remote_links.return_value = []
    return mc


def _run(case_name: str, args: list[str], monkeypatch, **side_effects):
    monkeypatch.setattr(_mod, "load_status_sets", lambda **_: _STATUS_SETS)
    case = _FIXTURE["cases"][case_name]
    mc = _client(case, case["reviewer"])
    for method, exc in side_effects.items():
        getattr(mc, method).side_effect = exc
    return run_cli(_mod, ["QA-9", "--no-siblings", *args], mc)


@pytest.mark.parametrize(
    ("method", "field"),
    [("issue_get_worklog", "worklog_empty"), ("myself", "reviewer"), ("get_all_statuses", "in_progress_by")],
)
def test_cli_failed_fetch_reads_as_unknown_not_other(monkeypatch, method, field):
    # Without the failure this case is "other"; a signal that could not be
    # read must not clear the reviewer.
    result, _ = _run("other_implementer", ["--json"], monkeypatch, **{method: RuntimeError("boom")})
    assert result.exit_code == 0, result.output
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == "unknown"
    assert sr[field] is None


def test_cli_json_carries_self_review(monkeypatch):
    result, mc = _run("implementer_is_reviewer", ["--json"], monkeypatch)
    assert result.exit_code == 0, result.output
    sr = json.loads(result.output)["self_review"]
    assert sr["verdict"] == "self"
    assert sr["reviewer"] == "rev"
    assert sr["implementer"] == "rev"
    assert sr["handover"]["to"] == "QA"
    assert sr["worklog_empty"] is False
    assert mc.issue.call_args.kwargs["expand"] == "renderedFields,changelog"


def test_cli_text_warns_on_self_near_the_top(monkeypatch):
    result, _ = _run("implementer_is_reviewer", [], monkeypatch)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Self-review check: self (reviewer matches implementer)" in out
    assert "WARNING: you (rev) would be reviewing your own work - matched: implementer" in out
    assert out.index("Self-review check:") < out.index("Issue links:")


def test_cli_text_other_has_no_warning(monkeypatch):
    result, _ = _run("other_implementer", [], monkeypatch)
    assert result.exit_code == 0, result.output
    assert "Self-review check: other" in result.output
    assert "WARNING" not in result.output
    assert "Implementer (moved into QA): Imp Lementer (impl)" in result.output
    assert "Worklog empty: no" in result.output


def test_cli_text_without_handover(monkeypatch):
    result, _ = _run("no_into_qa", [], monkeypatch)
    assert result.exit_code == 0, result.output
    assert "Self-review check: unknown (no transition into a QA status in the changelog)" in result.output
    assert "Implementer (moved into QA): not found" in result.output
    assert "Worklog empty: yes" in result.output


def test_cli_text_unreadable_worklog(monkeypatch):
    result, _ = _run("other_implementer", [], monkeypatch, issue_get_worklog=RuntimeError("boom"))
    assert result.exit_code == 0, result.output
    assert "Self-review check: unknown (could not read: worklog)" in result.output
    assert "Worklog authors: not readable" in result.output
    assert "Worklog empty: unknown" in result.output
