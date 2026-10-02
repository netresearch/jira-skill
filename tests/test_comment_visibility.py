"""`jira-comment add --visibility`: restricted comments reach the client as Jira expects.

The assertion is on the arguments handed to ``issue_add_comment`` — the payload
the instance receives — not on the CLI's own output.
"""

from unittest import mock

import click.testing
import pytest
from conftest import load_script, make_mock_client


def _invoke(argv):
    module = load_script("jira-comment", "workflow")
    client = make_mock_client()
    client.issue_add_comment.return_value = {"id": "10001"}
    runner = click.testing.CliRunner()
    with (
        mock.patch.object(module, "LazyJiraClient", return_value=client),
        mock.patch.object(module, "check_mentions_cli", return_value=None),
    ):
        result = runner.invoke(module.cli, argv)
    return result, client


@pytest.mark.parametrize(
    "option, expected",
    [
        ("role:Developers", {"type": "role", "value": "Developers"}),
        ("group:jira-developers", {"type": "group", "value": "jira-developers"}),
        ("Role: Developers", {"type": "role", "value": "Developers"}),
    ],
)
def test_visibility_is_passed_to_the_client(option, expected):
    result, client = _invoke(["add", "PROJ-1", "Internal note", "--visibility", option, "--no-preflight"])
    assert result.exit_code == 0, result.output
    client.issue_add_comment.assert_called_once_with("PROJ-1", "Internal note", visibility=expected)
    assert f"Visible to: {expected['type']} {expected['value']}" in result.output


def test_without_visibility_the_call_is_unchanged():
    result, client = _invoke(["add", "PROJ-1", "Public note", "--no-preflight"])
    assert result.exit_code == 0, result.output
    client.issue_add_comment.assert_called_once_with("PROJ-1", "Public note")


@pytest.mark.parametrize("option", ["Developers", "user:jane", "role:", ":Developers"])
def test_invalid_visibility_is_refused_before_anything_is_sent(option):
    result, client = _invoke(["add", "PROJ-1", "Note", "--visibility", option, "--no-preflight"])
    assert result.exit_code != 0
    assert "role:<project role> or group:<group>" in result.output
    client.issue_add_comment.assert_not_called()


def test_dry_run_shows_the_restriction_and_sends_nothing():
    module_result, client = _invoke(["--json", "add", "PROJ-1", "Note", "--visibility", "role:Developers", "--dry-run"])
    assert module_result.exit_code == 0, module_result.output
    assert '"visibility"' in module_result.output and '"Developers"' in module_result.output
    client.issue_add_comment.assert_not_called()
