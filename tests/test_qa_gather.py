"""Tests for jira-qa-gather.py body rendering.

The bundle used to print metadata only (status, counts, links, URLs,
siblings), so a reviewer needed a second call (`jira-issue.py work KEY`) per
ticket to read the description and the comments. These tests pin the new
default — description + every comment, rendered like `work` — plus the
`--no-body` escape hatch and the `description` / `comments` JSON keys.
"""

import json

from conftest import load_script, make_mock_client, run_cli

_mod = load_script("jira-qa-gather", "utility")

_ISSUE = {
    "key": "QA-7",
    "fields": {
        "summary": "Upgrade traefik to 3.6",
        "status": {"name": "QA"},
        "assignee": {"displayName": "Rev Iewer", "name": "reviewer"},
        "project": {"key": "QA"},
        "description": "Line one of the description\nLine two",
        # Embedded block is deliberately short: the paginated fetch must win.
        "comment": {"total": 2, "comments": [{"id": "1", "body": "embedded only"}]},
        "issuelinks": [],
    },
}

_COMMENTS = [
    {
        "id": "1",
        "author": {"displayName": "Imp Lementer", "name": "implementer"},
        "created": "2026-08-20T09:15:00.000+0200",
        "body": "Rolled out to staging, MR https://git.example.com/ops/traefik/-/merge_requests/42",
    },
    {
        "id": "2",
        "author": {"displayName": "Rev Iewer", "name": "reviewer"},
        "created": "2026-08-21T10:00:00.000+0200",
        "body": "Second comment body",
    },
]


def _client():
    mc = make_mock_client()
    mc.issue.return_value = _ISSUE
    mc.get.return_value = {"comments": _COMMENTS, "total": len(_COMMENTS), "startAt": 0, "maxResults": 100}
    mc.issue_get_worklog.return_value = {"worklogs": []}
    mc.get_issue_remote_links.return_value = []
    mc.jql.return_value = {"issues": []}
    return mc


def test_default_output_prints_description_and_all_comments():
    result, mc = run_cli(_mod, ["QA-7", "--no-siblings"], _client())
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Description:" in out
    assert "  Line one of the description" in out
    assert "COMMENTS (2 total — chronological)" in out
    assert "--- [2026-08-20 09:15] Imp Lementer (implementer) ---" in out
    assert "Second comment body" in out
    # Paginated fetch replaced the truncated embedded block.
    assert "embedded only" not in out
    mc.get.assert_called_once()
    assert mc.get.call_args.args[0] == "rest/api/2/issue/QA-7/comment"
    # Metadata sections still precede the comment bodies.
    assert out.index("Issue links: none") < out.index("COMMENTS (")


def test_no_body_restores_metadata_only_shape():
    result, _ = run_cli(_mod, ["QA-7", "--no-siblings", "--no-body"], _client())
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Description:" not in out
    assert "COMMENTS (" not in out
    assert "Second comment body" not in out
    # The header still reports the real (paginated) comment count.
    assert "Comments: 2" in out
    # URL extraction still reads every comment.
    assert "https://git.example.com/ops/traefik/-/merge_requests/42" in out


def test_json_carries_description_and_comments():
    result, _ = run_cli(_mod, ["QA-7", "--no-siblings", "--json"], _client())
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["description"] == "Line one of the description\nLine two"
    assert [c["id"] for c in data["comments"]] == ["1", "2"]
    assert data["comments"][1]["body"] == "Second comment body"


def test_paginated_fetch_failure_falls_back_to_embedded_block():
    mc = _client()
    mc.get.side_effect = RuntimeError("boom")
    result, _ = run_cli(_mod, ["QA-7", "--no-siblings", "--json"], mc)
    assert result.exit_code == 0, result.output
    assert "Failed to page through comments" in result.stderr
    data = json.loads(result.stdout)
    assert [c["id"] for c in data["comments"]] == ["1"]


def test_help_mentions_no_body():
    result, _ = run_cli(_mod, ["--help"])
    assert result.exit_code == 0
    assert "--no-body" in result.output
