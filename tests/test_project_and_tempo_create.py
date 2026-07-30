"""Tests for jira-create's `project` command and the tempo-account script.

Follows the same `mock.patch("lib.client.get_jira_client", ...)` pattern used
by the existing dry-run tests in test_cli_smoke.py's TestMockedCommands: the
LazyJiraClient wrapper stays real, only the underlying client factory is
swapped for a mock, so `ctx.obj["client"].project(...)` etc. resolve through
the wrapper exactly as they would against a live Jira instance.
"""

import json
from unittest import mock

import click.testing
from conftest import load_script

_create_mod = load_script("jira-create", "workflow")
_tempo_mod = load_script("tempo-account", "workflow")


def _make_mock_client(url: str = "https://jira.example.com", **attrs):
    mc = mock.Mock()
    mc.url = url
    for key, value in attrs.items():
        setattr(mc, key, value)
    return mc


# ═══════════════════════════════════════════════════════════════════════════════
# jira-create project
# ═══════════════════════════════════════════════════════════════════════════════


class TestProjectCreate:
    def test_project_dry_run_resolves_source_but_does_not_create(self):
        """Dry-run still resolves --from-project (read-only) but must not call
        create_project_from_shared_template — same convention as jira-link's
        dry-run resolving the link type without creating the link."""
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "OPSFX",
                    "--lead",
                    "tobias.hein",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.project.assert_called_once_with("OPSFX")
        mock_client.create_project_from_shared_template.assert_not_called()

    def test_project_create_success(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "LSB", "id": 20202}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                ["project", "LSB", "Landessportbund Sachsen", "--from-project", "OPSFX", "--lead", "tobias.hein"],
            )
        assert result.exit_code == 0, result.output
        mock_client.create_project_from_shared_template.assert_called_once_with(
            10101, "LSB", "Landessportbund Sachsen", "tobias.hein"
        )
        assert "LSB" in result.output

    def test_project_create_unresolvable_source_errors_out(self):
        mock_client = _make_mock_client()
        mock_client.project.side_effect = Exception("404 project not found")
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "DOES-NOT-EXIST",
                    "--lead",
                    "tobias.hein",
                ],
            )
        assert result.exit_code != 0
        mock_client.create_project_from_shared_template.assert_not_called()

    def test_project_create_with_bootstrap_issues(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "LSB", "id": 20202}
        mock_client.create_issue.side_effect = [
            {"key": "LSB-1"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "OPSFX",
                    "--lead",
                    "tobias.hein",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 1
        call = mock_client.create_issue.call_args_list[0]
        assert call.kwargs["fields"]["project"] == {"key": "LSB"}
        assert call.kwargs["fields"]["issuetype"] == {"name": "Issue Number One"}
        assert call.kwargs["fields"]["summary"] == "Projektmanagement"

    def test_project_create_bootstrap_issue_falls_back_to_task(self):
        """If 'Issue Number One' isn't in the --from-project template's issue
        type scheme, retries once with Task rather than losing the issue."""
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "LSB", "id": 20202}
        mock_client.create_issue.side_effect = [
            Exception("issue type Issue Number One not available"),
            {"key": "LSB-1"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "OPSFX",
                    "--lead",
                    "tobias.hein",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 2
        first_call, second_call = mock_client.create_issue.call_args_list
        assert first_call.kwargs["fields"]["issuetype"] == {"name": "Issue Number One"}
        assert second_call.kwargs["fields"]["issuetype"] == {"name": "Task"}
        assert second_call.kwargs["fields"]["summary"] == "Projektmanagement"

    def test_project_create_bootstrap_issue_failure_does_not_abort(self):
        """Both attempts (Issue Number One, then Task fallback) failing only
        warns — the project creation that already succeeded is unaffected."""
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "LSB", "id": 20202}
        mock_client.create_issue.side_effect = [
            Exception("issue type Issue Number One not available"),
            Exception("issue type Task not available either"),
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "OPSFX",
                    "--lead",
                    "tobias.hein",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 2

    def test_project_create_bootstrap_json_output_stays_parseable(self):
        """`--json` output must be pure JSON even when --bootstrap-issues runs.

        The bootstrap helper announces its issue via success(), which writes to
        stdout; unguarded it appends a `✓` line to the payload and every
        `--json … | jq` pipeline over `project` fails to parse.
        """
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "LSB", "id": 20202}
        mock_client.create_issue.side_effect = [{"key": "LSB-1"}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "--json",
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "OPSFX",
                    "--lead",
                    "tobias.hein",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 1
        # Fails with "Extra data" if the ✓ line leaks into stdout.
        payload = json.loads(result.output)
        assert payload["key"] == "LSB"
        assert "Projektmanagement" not in result.output

    def test_project_create_bootstrap_quiet_prints_only_the_key(self):
        """`--quiet` contracts to just the project key — no bootstrap ✓ line."""
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "LSB", "id": 20202}
        mock_client.create_issue.side_effect = [{"key": "LSB-1"}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "--quiet",
                    "project",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--from-project",
                    "OPSFX",
                    "--lead",
                    "tobias.hein",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 1
        assert result.output.strip() == "LSB"


# ═══════════════════════════════════════════════════════════════════════════════
# tempo-account customer create
# ═══════════════════════════════════════════════════════════════════════════════


class TestTempoCustomerCreate:
    def test_customer_create_dry_run(self):
        mock_client = _make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _tempo_mod.cli, ["customer", "create", "LSB", "Landessportbund Sachsen", "--dry-run"]
            )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.tempo_account_add_new_customer.assert_not_called()

    def test_customer_create_success(self):
        mock_client = _make_mock_client()
        mock_client.tempo_account_add_new_customer.return_value = {"key": "LSB", "id": 55}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["customer", "create", "LSB", "Landessportbund Sachsen"])
        assert result.exit_code == 0, result.output
        mock_client.tempo_account_add_new_customer.assert_called_once_with("LSB", "Landessportbund Sachsen")


# ═══════════════════════════════════════════════════════════════════════════════
# tempo-account account create / link
# ═══════════════════════════════════════════════════════════════════════════════


class TestTempoAccountCreate:
    def test_account_create_dry_run(self):
        mock_client = _make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _tempo_mod.cli,
                [
                    "account",
                    "create",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--lead",
                    "tobias.hein",
                    "--customer-key",
                    "LSB",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.tempo_account_add_account.assert_not_called()

    def test_account_create_success_payload_shape(self):
        mock_client = _make_mock_client()
        mock_client.tempo_account_add_account.return_value = {"id": 42, "key": "LSB"}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _tempo_mod.cli,
                [
                    "account",
                    "create",
                    "LSB",
                    "Landessportbund Sachsen",
                    "--lead",
                    "tobias.hein",
                    "--customer-key",
                    "LSB",
                ],
            )
        assert result.exit_code == 0, result.output
        mock_client.tempo_account_add_account.assert_called_once_with(
            {
                "key": "LSB",
                "name": "Landessportbund Sachsen",
                "lead": {"name": "tobias.hein"},
                "customer": {"key": "LSB"},
            }
        )
        assert "42" in result.output

    def test_account_link_dry_run(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["account", "link", "42", "LSB", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.tempo_account_associate_with_jira_project.assert_not_called()

    def test_account_link_success(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.tempo_account_associate_with_jira_project.return_value = {"id": 999}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["account", "link", "42", "LSB", "--default"])
        assert result.exit_code == 0, result.output
        mock_client.tempo_account_associate_with_jira_project.assert_called_once_with(42, 10101, default_account=True)

    def test_account_link_unresolvable_project_errors_out(self):
        mock_client = _make_mock_client()
        mock_client.project.side_effect = Exception("404 project not found")
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["account", "link", "42", "DOES-NOT-EXIST"])
        assert result.exit_code != 0
        mock_client.tempo_account_associate_with_jira_project.assert_not_called()
