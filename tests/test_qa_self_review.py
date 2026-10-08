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
            "reporter": {"name": "rep", "displayName": "Rep Orter"},
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
    assert sr["reporter"] == "Rep Orter (rep)"


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


def _as_cloud(value):
    """Rename every user ``name`` to ``accountId``, the only key Cloud sends."""
    if isinstance(value, dict):
        return {("accountId" if k == "name" else k): _as_cloud(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_cloud(v) for v in value]
    return value


@pytest.mark.parametrize(("name", "verdict"), [("implementer_is_reviewer", "self"), ("other_implementer", "other")])
def test_cloud_account_ids(name, verdict):
    case = _FIXTURE["cases"][name]
    issue = _as_cloud(_issue(case))
    sr = _mod.compute_self_review(issue, _as_cloud(_worklogs(case)), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["verdict"] == verdict
    assert sr["implementer"] == case["expect"]["implementer"]
    assert sr["worklog_authors"] == case["worklog_authors"]
    assert sr["reporter"] == "Rep Orter (rep)"


def test_person_without_display_name_shows_the_key():
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    issue["fields"]["reporter"] = {"name": "rep"}
    sr = _mod.compute_self_review(issue, _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["reporter"] == "rep"


def test_reporter_is_not_a_signal():
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    issue["fields"]["reporter"] = {"name": "rev", "displayName": "Rev Iewer"}
    sr = _mod.compute_self_review(issue, _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["verdict"] == "other"
    assert sr["matched"] == []
    assert sr["reporter"] == "Rev Iewer (rev)"


def test_print_shows_resolution(capsys):
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    issue["fields"]["resolution"] = {"name": "Done"}
    _mod._print_self_review(_mod.compute_self_review(issue, [], "rev", _STATUS_SETS, _CATEGORIES))
    assert "Resolution: Done | Worklog empty: yes" in capsys.readouterr().out


@pytest.mark.parametrize("reviewer", [None, ""])
def test_unknown_reviewer_never_matches_a_missing_author(reviewer):
    # /myself failed or returned no key, and the handover has no author (its
    # key is ""): an unknown reviewer must not match an unknown author.
    case = _FIXTURE["cases"]["other_implementer"]
    issue = _issue(case)
    del issue["changelog"]["histories"][-1]["author"]
    sr = _mod.compute_self_review(issue, _worklogs(case), reviewer, _STATUS_SETS, _CATEGORIES)
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
    assert sr["reason"] == "could not read: status category of a move"


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


@pytest.mark.parametrize("payload", [None, {}, {"errorMessages": ["boom"]}])
def test_cli_worklog_without_a_list_is_unread(monkeypatch, payload):
    # Correct verdict with the worklog read is "self"; a response that carries
    # no worklog list must not turn it into "other".
    result, _ = _run("reviewer_only_in_worklog", ["--json"], monkeypatch, issue_get_worklog=lambda *a, **k: payload)
    assert result.exit_code == 0, result.output
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == "unknown"
    assert sr["worklog_empty"] is None


def test_earlier_round_names_every_author_and_event():
    # The reviewer implemented round one; QA rejected it and bob did round two.
    case = _FIXTURE["cases"]["reviewer_implemented_an_earlier_round"]
    sr = _mod.compute_self_review(_issue(case), _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["handover_authors"] == ["rev", "bob"]
    assert sr["in_progress_authors"] == ["rev", "bob"]
    assert sr["matched_events"] == [
        {"signal": "earlier_handover", "created": "2026-10-02T09:00:00+02:00", "from": "In Progress", "to": "QA"},
        {"signal": "earlier_in_progress", "created": "2026-10-01T09:00:00+02:00", "from": "Open", "to": "In Progress"},
    ]


def test_cli_text_lists_earlier_round(monkeypatch):
    result, _ = _run("reviewer_implemented_an_earlier_round", [], monkeypatch)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "matched: earlier_handover, earlier_in_progress" in out
    assert "    earlier_handover: 2026-10-02T09:00:00+02:00 (In Progress → QA)" in out
    assert "Handover authors (all rounds): rev, bob" in out
    assert "In progress authors (all rounds): rev, bob" in out


@pytest.mark.parametrize(("name", "verdict"), [("other_implementer", "unknown"), ("reviewer_only_in_worklog", "self")])
def test_cli_incomplete_worklog(monkeypatch, name, verdict):
    # The response says two entries exist but returns one: the missing entry
    # may be the reviewer's, unless a returned one already is.
    case = _FIXTURE["cases"][name]
    payload = {"total": len(case["worklog_authors"]) + 1, "worklogs": _worklogs(case)}
    result, _ = _run(name, ["--json"], monkeypatch, issue_get_worklog=lambda *a, **k: payload)
    assert result.exit_code == 0, result.output
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == verdict
    if verdict == "unknown":
        assert "worklog (incomplete)" in sr["reason"]
    assert sr["worklog_empty"] is None


def test_cli_incomplete_empty_worklog_is_not_empty(monkeypatch):
    payload = {"total": 3, "worklogs": []}
    result, _ = _run("other_implementer", [], monkeypatch, issue_get_worklog=lambda *a, **k: payload)
    assert "Worklog empty: unknown" in result.output


def test_worklog_entry_without_author_is_left_out():
    case = _FIXTURE["cases"]["other_implementer"]
    worklogs = [*_worklogs(case), {"author": {"displayName": "Gone"}, "timeSpentSeconds": 60}]
    sr = _mod.compute_self_review(_issue(case), worklogs, "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["worklog_authors"] == ["impl"]


def test_cli_complete_worklog_with_total_is_read(monkeypatch):
    case = _FIXTURE["cases"]["other_implementer"]
    payload = {"total": len(case["worklog_authors"]), "worklogs": _worklogs(case)}
    result, _ = _run("other_implementer", ["--json"], monkeypatch, issue_get_worklog=lambda *a, **k: payload)
    assert json.loads(result.stdout)["self_review"]["verdict"] == "other"


def test_unlisted_status_keeps_the_listed_matches():
    # An old move into a since-deleted status (id 99) must not hide the
    # reviewer's own, listed In Progress move.
    case = _FIXTURE["cases"]["reviewer_started_work"]
    issue = _issue(case)
    gone = {"field": "status", "from": "1", "fromString": "Open", "to": "99", "toString": "Gone"}
    issue["changelog"]["histories"].insert(
        0, {"author": {"name": "impl"}, "created": "2026-09-30T09:00:00.000+0200", "items": [gone]}
    )
    sr = _mod.compute_self_review(issue, _worklogs(case), "rev", _STATUS_SETS, _CATEGORIES)
    assert sr["verdict"] == "self"
    assert sr["matched"] == ["in_progress_by"]
    assert sr["in_progress_complete"] is False


def test_cli_status_without_category_is_unread(monkeypatch):
    # "In Progress" arrives without statusCategory: its moves have no known
    # category, so they must not read as "not In Progress".
    statuses = [dict(s) for s in _FIXTURE["statuses"]]
    del next(s for s in statuses if s["id"] == "3")["statusCategory"]
    result, _ = _run("other_implementer", ["--json"], monkeypatch, get_all_statuses=lambda *a, **k: statuses)
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == "unknown"
    assert sr["reason"] == "could not read: status category of a move"


@pytest.mark.parametrize(
    ("category", "verdict"),
    [
        ({"key": "undefined"}, "unknown"),  # Jira's "No Category"
        ({"key": "something-else"}, "unknown"),
        ({}, "unknown"),
        ({"key": "indeterminate"}, "self"),
    ],
)
def test_cli_only_known_categories_count(monkeypatch, category, verdict):
    # The reviewer made the move into status 3; unless its category is known,
    # that move must not read as "not In Progress" and clear the reviewer.
    statuses = [dict(s) for s in _FIXTURE["statuses"]]
    next(s for s in statuses if s["id"] == "3")["statusCategory"] = category
    result, _ = _run("reviewer_started_work", ["--json"], monkeypatch, get_all_statuses=lambda *a, **k: statuses)
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == verdict
    assert sr["in_progress_complete"] is (verdict == "self")


def test_cli_malformed_status_entry_is_skipped(monkeypatch):
    # One entry that is not a status object must not make the whole category
    # map unreadable: the other statuses still decide.
    statuses = [*_FIXTURE["statuses"], "junk", None]
    result, _ = _run("other_implementer", ["--json"], monkeypatch, get_all_statuses=lambda *a, **k: statuses)
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == "other"
    assert sr["in_progress_complete"] is True


@pytest.mark.parametrize("method", ["myself", "get_all_statuses", "issue_get_worklog", "get_issue_remote_links"])
def test_cli_warnings_redact_credentials(monkeypatch, method):
    exc = RuntimeError("401 for token=SECRET123 with Authorization: Bearer SECRET456")
    result, _ = _run("other_implementer", [], monkeypatch, **{method: exc})
    assert result.exit_code == 0, result.output
    assert "token=***" in result.output
    assert "SECRET123" not in result.output
    assert "SECRET456" not in result.output


def test_cli_new_and_done_are_known_categories(monkeypatch):
    # Moves into Closed (done) and back to Open (new) are known, not unread.
    result, _ = _run("closed_and_reopened_by_others", ["--json"], monkeypatch)
    sr = json.loads(result.stdout)["self_review"]
    assert sr["verdict"] == "other"
    assert sr["in_progress_complete"] is True


@pytest.mark.parametrize("payload", [None, {"errorMessages": ["boom"]}])
def test_cli_status_list_that_is_not_a_list_is_unread(monkeypatch, payload):
    result, _ = _run("other_implementer", ["--json"], monkeypatch, get_all_statuses=lambda *a, **k: payload)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["self_review"]["reason"] == "could not read: status categories"
    assert "Failed to fetch status categories" not in result.output


def test_cli_text_marks_in_progress_incomplete(monkeypatch):
    result, _ = _run("other_implementer", [], monkeypatch, get_all_statuses=RuntimeError("boom"))
    assert result.exit_code == 0, result.output
    assert "Self-review check: unknown (could not read: status categories)" in result.output
    assert "In progress by: none found (incomplete: a status category is unknown)" in result.output
    assert "In progress authors (all rounds): none (incomplete: a status category is unknown)" in result.output


def test_cli_json_carries_self_review(monkeypatch):
    result, mc = _run("implementer_is_reviewer", ["--json"], monkeypatch)
    assert result.exit_code == 0, result.output
    sr = json.loads(result.output)["self_review"]
    assert sr["verdict"] == "self"
    assert sr["reviewer"] == "rev"
    assert sr["implementer"] == "rev"
    assert sr["handover"]["from"] == "In Progress"
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
    out = result.output
    assert "Implementer (moved into QA): Imp Lementer (impl) at 2026-10-02T09:00:00+02:00 (In Progress → QA)" in out
    assert "Reviewer (you): rev" in out
    assert "Handover authors (all rounds): impl" in out
    assert "In progress authors (all rounds): impl" in out
    assert "In progress by: impl" in out
    assert "Creator / reporter (information only): Boss (boss) / Rep Orter (rep)" in out
    assert "Worklog authors: impl" in out
    assert "Resolution: none | Worklog empty: no" in out


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
