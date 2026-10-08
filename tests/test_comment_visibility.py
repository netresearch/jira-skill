"""`jira-comment add --visibility`: restricted comments reach Jira as its REST API expects.

The payload tests go through the real ``LazyJiraClient`` and the real
``atlassian.Jira`` class and patch only ``Jira.post``, so they assert the request
body the instance receives — a wrapper or library that dropped or renamed the
field would fail them. The parser and dry-run tests use a mock client.
"""

import json
import sys
from unittest import mock

import click.testing
import pytest
from atlassian import Jira
from conftest import load_script, make_mock_client


def _post(argv):
    """Run ``jira-comment`` with the real client stack; return (result, post mock)."""
    module = load_script("jira-comment", "workflow")
    lib_client = sys.modules["lib.client"]
    real = Jira(url="https://jira.example.com", token="dummy", cloud=False)
    with (
        mock.patch.object(lib_client, "get_jira_client", return_value=real),
        mock.patch.object(Jira, "post", return_value={"id": "10001"}) as post,
        mock.patch.object(module, "check_mentions_cli", return_value=None),
    ):
        result = click.testing.CliRunner().invoke(module.cli, argv)
    return result, post


def _invoke(argv):
    """Run ``jira-comment`` with a mock client (for parser and dry-run cases)."""
    module = load_script("jira-comment", "workflow")
    client = make_mock_client()
    client.issue_add_comment.return_value = {"id": "10001"}
    with (
        mock.patch.object(module, "LazyJiraClient", return_value=client),
        mock.patch.object(module, "check_mentions_cli", return_value=None),
    ):
        result = click.testing.CliRunner().invoke(module.cli, argv)
    return result, client


@pytest.mark.parametrize(
    "option, expected",
    [
        ("role:Developers", {"type": "role", "value": "Developers"}),
        ("group:jira-developers", {"type": "group", "value": "jira-developers"}),
        ("  ROLE :  Service Desk Team ", {"type": "role", "value": "Service Desk Team"}),
        ("group:team:ops", {"type": "group", "value": "team:ops"}),
    ],
)
def test_visibility_reaches_the_rest_payload(option, expected):
    result, post = _post(["add", "PROJ-1", "Internal", "--visibility", option, "--no-preflight"])
    assert result.exit_code == 0, result.output
    assert post.call_args.args[0] == "rest/api/2/issue/PROJ-1/comment"
    assert post.call_args.kwargs["data"] == {"body": "Internal", "visibility": expected}
    assert f"Visible to: {expected['type']} {expected['value']}" in result.output


def test_without_visibility_the_payload_has_no_restriction():
    result, post = _post(["add", "PROJ-1", "Public note", "--no-preflight"])
    assert result.exit_code == 0, result.output
    assert post.call_args.kwargs["data"] == {"body": "Public note"}
    assert "Visible to" not in result.output


@pytest.mark.parametrize("option", ["Developers", "user:jane", "role:", ":Developers", ""])
def test_invalid_visibility_is_refused_before_anything_is_sent(option):
    result, client = _invoke(["add", "PROJ-1", "Note", "--visibility", option, "--no-preflight"])
    assert result.exit_code == 2
    assert "role:<project role> or group:<group>" in result.output
    assert repr(option) in result.output
    client.issue_add_comment.assert_not_called()


def test_json_dry_run_shows_the_exact_restriction_and_sends_nothing():
    result, client = _invoke(["--json", "add", "PROJ-1", "Note", "--visibility", "role:Developers", "--dry-run"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["visibility"] == {"type": "role", "value": "Developers"}
    client.issue_add_comment.assert_not_called()


def test_text_dry_run_names_the_restriction():
    result, client = _invoke(["add", "PROJ-1", "Note", "--visibility", "group:jira-developers", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would add to PROJ-1 (visible to group jira-developers):" in result.output
    client.issue_add_comment.assert_not_called()


def test_dry_run_without_visibility_has_no_restriction():
    result, _ = _invoke(["--json", "add", "PROJ-1", "Note", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "visibility" not in json.loads(result.output)
