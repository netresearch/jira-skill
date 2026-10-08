# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the self-review check in jira-qa-gather.py.

Workflows that unassign a ticket on its move into QA leave every QA ticket
"Unassigned", so the assignee can no longer tell a reviewer that the work is
their own. The check reads the changelog (who moved it into QA, who last
moved it to In Progress) and the worklog authors instead. Cases live in
``fixtures/qa_self_review.json``.
"""

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
        "changelog": {"histories": case["histories"]},
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
