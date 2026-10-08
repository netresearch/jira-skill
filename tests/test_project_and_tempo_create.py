# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

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
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "TMPL",
                    "--lead",
                    "jane.doe",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.project.assert_called_once_with("TMPL")
        mock_client.create_project_from_shared_template.assert_not_called()

    def test_project_create_success(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                ["project", "NEWP", "Example Customer GmbH", "--from-project", "TMPL", "--lead", "jane.doe"],
            )
        assert result.exit_code == 0, result.output
        mock_client.create_project_from_shared_template.assert_called_once_with(
            10101, "NEWP", "Example Customer GmbH", "jane.doe"
        )
        assert "NEWP" in result.output

    def test_project_create_unresolvable_source_errors_out(self):
        mock_client = _make_mock_client()
        mock_client.project.side_effect = Exception("404 project not found")
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "DOES-NOT-EXIST",
                    "--lead",
                    "jane.doe",
                ],
            )
        assert result.exit_code != 0
        mock_client.create_project_from_shared_template.assert_not_called()

    def test_project_create_with_bootstrap_issues(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
        mock_client.create_issue.side_effect = [
            {"key": "NEWP-1"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "TMPL",
                    "--lead",
                    "jane.doe",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 1
        call = mock_client.create_issue.call_args_list[0]
        assert call.kwargs["fields"]["project"] == {"key": "NEWP"}
        assert call.kwargs["fields"]["issuetype"] == {"name": "Issue Number One"}
        assert call.kwargs["fields"]["summary"] == "Projektmanagement"

    def test_project_create_bootstrap_issue_falls_back_to_task(self):
        """If 'Issue Number One' isn't in the --from-project template's issue
        type scheme, retries once with Task rather than losing the issue."""
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
        mock_client.create_issue.side_effect = [
            Exception("issue type Issue Number One not available"),
            {"key": "NEWP-1"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "project",
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "TMPL",
                    "--lead",
                    "jane.doe",
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
        mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
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
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "TMPL",
                    "--lead",
                    "jane.doe",
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
        mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
        mock_client.create_issue.side_effect = [{"key": "NEWP-1"}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "--json",
                    "project",
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "TMPL",
                    "--lead",
                    "jane.doe",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 1
        # Fails with "Extra data" if the ✓ line leaks into stdout.
        payload = json.loads(result.output)
        assert payload["key"] == "NEWP"
        assert "Projektmanagement" not in result.output

    def test_project_create_bootstrap_quiet_prints_only_the_key(self):
        """`--quiet` contracts to just the project key — no bootstrap ✓ line."""
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
        mock_client.create_issue.side_effect = [{"key": "NEWP-1"}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                [
                    "--quiet",
                    "project",
                    "NEWP",
                    "Example Customer GmbH",
                    "--from-project",
                    "TMPL",
                    "--lead",
                    "jane.doe",
                    "--bootstrap-issues",
                ],
            )
        assert result.exit_code == 0, result.output
        assert mock_client.create_issue.call_count == 1
        assert result.output.strip() == "NEWP"


_ROLES = {
    "Developers": "https://jira.example.com/rest/api/2/project/X/role/10001",
    "Customers": "https://jira.example.com/rest/api/2/project/X/role/10002",
    "Administrators": "https://jira.example.com/rest/api/2/project/X/role/10003",
}

_SOURCE_ACTORS = {
    "10001": [{"type": "atlassian-group-role-actor", "name": "developers-group"}],
    "10002": [
        {"type": "atlassian-group-role-actor", "name": "customer-group"},
        {"type": "atlassian-user-role-actor", "name": "jane.customer"},
    ],
    "10003": [
        {"type": "atlassian-group-role-actor", "name": "jira-administrators"},
        {"type": "atlassian-group-role-actor", "name": "leads-group"},
    ],
}

# Jira's default role members, present right after creation.
_NEW_PROJECT_ACTORS = {
    "10001": [],
    "10002": [],
    "10003": [{"type": "atlassian-group-role-actor", "name": "jira-administrators"}],
}


def _role_client(**attrs):
    """Mock client whose TMPL project holds _SOURCE_ACTORS and NEWP _NEW_PROJECT_ACTORS."""
    mock_client = _make_mock_client(**attrs)
    mock_client.project.return_value = {"id": 10101}
    mock_client.create_project_from_shared_template.return_value = {"key": "NEWP", "id": 20202}
    mock_client.get_project_roles.return_value = _ROLES
    mock_client.get_project_actors_for_role_project.side_effect = lambda project, role_id: (
        _SOURCE_ACTORS if project == "TMPL" else _NEW_PROJECT_ACTORS
    )[role_id]
    return mock_client


_BASE_ARGS = ["project", "NEWP", "Example Customer GmbH", "--from-project", "TMPL", "--lead", "jane.doe"]


class TestProjectSettingsAndRoles:
    def test_copy_roles_adds_only_missing_members(self):
        mock_client = _role_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, [*_BASE_ARGS, "--copy-roles"])
        assert result.exit_code == 0, result.output
        calls = [c.args for c in mock_client.add_project_actor_in_role.call_args_list]
        assert sorted(calls) == sorted(
            [
                ("NEWP", "10001", "developers-group", "group"),
                ("NEWP", "10002", "customer-group", "group"),
                ("NEWP", "10002", "jane.customer", "user"),
                ("NEWP", "10003", "leads-group", "group"),
            ]
        )
        assert "Copied 4 role member(s)" in result.output

    def test_copy_roles_runs_before_bootstrap_issue(self):
        """The bootstrap issue's default assignee must already be assignable."""
        mock_client = _role_client()
        order = []
        mock_client.add_project_actor_in_role.side_effect = lambda *a: order.append("role")
        mock_client.create_issue.side_effect = lambda **kw: order.append("issue") or {"key": "NEWP-1"}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, [*_BASE_ARGS, "--copy-roles", "--bootstrap-issues"])
        assert result.exit_code == 0, result.output
        assert order.index("issue") > max(i for i, step in enumerate(order) if step == "role")

    def test_copy_roles_failed_add_warns_and_continues(self):
        mock_client = _role_client()
        mock_client.add_project_actor_in_role.side_effect = [Exception("group does not exist"), None, None, None]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, [*_BASE_ARGS, "--copy-roles"])
        assert result.exit_code == 0, result.output
        assert mock_client.add_project_actor_in_role.call_count == 4
        assert "Copied 3 role member(s)" in result.output

    def test_copy_roles_dry_run_lists_source_members_without_writing(self):
        mock_client = _role_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, [*_BASE_ARGS, "--copy-roles", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "customer-group (group)" in result.output
        assert "jane.customer (user)" in result.output
        mock_client.create_project_from_shared_template.assert_not_called()
        mock_client.add_project_actor_in_role.assert_not_called()

    def test_without_copy_roles_no_role_calls(self):
        mock_client = _role_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, _BASE_ARGS)
        assert result.exit_code == 0, result.output
        mock_client.get_project_roles.assert_not_called()
        mock_client.add_project_actor_in_role.assert_not_called()
        mock_client.update_project.assert_not_called()

    def test_category_and_assignee_type_update_project(self):
        mock_client = _role_client()
        mock_client.get_all_project_categories.return_value = [
            {"id": "10002", "name": "Agency"},
            {"id": "10006", "name": "Support"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli, [*_BASE_ARGS, "--category", "support", "--assignee-type", "PROJECT_LEAD"]
            )
        assert result.exit_code == 0, result.output
        mock_client.update_project.assert_called_once_with(
            "NEWP", {"categoryId": 10006, "assigneeType": "PROJECT_LEAD"}
        )

    def test_unknown_category_aborts_before_creating(self):
        mock_client = _role_client()
        mock_client.get_all_project_categories.return_value = [{"id": "10006", "name": "Support"}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, [*_BASE_ARGS, "--category", "Suport"])
        assert result.exit_code != 0
        mock_client.create_project_from_shared_template.assert_not_called()

    def test_json_output_stays_parseable_with_settings_and_roles(self):
        mock_client = _role_client()
        mock_client.get_all_project_categories.return_value = [{"id": "10006", "name": "Support"}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _create_mod.cli,
                ["--json", *_BASE_ARGS, "--copy-roles", "--category", "Support", "--assignee-type", "PROJECT_LEAD"],
            )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["key"] == "NEWP"


# ═══════════════════════════════════════════════════════════════════════════════
# tempo-account customer create
# ═══════════════════════════════════════════════════════════════════════════════


class TestTempoCustomerCreate:
    def test_customer_create_dry_run(self):
        mock_client = _make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["customer", "create", "NEWP", "Example Customer GmbH", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.tempo_account_add_new_customer.assert_not_called()

    def test_customer_create_success(self):
        mock_client = _make_mock_client()
        mock_client.tempo_account_add_new_customer.return_value = {"key": "NEWP", "id": 55}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["customer", "create", "NEWP", "Example Customer GmbH"])
        assert result.exit_code == 0, result.output
        mock_client.tempo_account_add_new_customer.assert_called_once_with("NEWP", "Example Customer GmbH")


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
                    "NEWP",
                    "Example Customer GmbH",
                    "--lead",
                    "jane.doe",
                    "--customer-key",
                    "NEWP",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.tempo_account_add_account.assert_not_called()

    def test_account_create_success_payload_shape(self):
        mock_client = _make_mock_client()
        mock_client.tempo_account_add_account.return_value = {"id": 42, "key": "NEWP"}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _tempo_mod.cli,
                [
                    "account",
                    "create",
                    "NEWP",
                    "Example Customer GmbH",
                    "--lead",
                    "jane.doe",
                    "--customer-key",
                    "NEWP",
                ],
            )
        assert result.exit_code == 0, result.output
        mock_client.tempo_account_add_account.assert_called_once_with(
            {
                "key": "NEWP",
                "name": "Example Customer GmbH",
                "lead": {"name": "jane.doe"},
                "customer": {"key": "NEWP"},
            }
        )
        assert "42" in result.output

    def test_account_link_dry_run(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["account", "link", "42", "NEWP", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.tempo_account_associate_with_jira_project.assert_not_called()

    def test_account_link_success(self):
        mock_client = _make_mock_client()
        mock_client.project.return_value = {"id": 10101}
        mock_client.tempo_account_associate_with_jira_project.return_value = {"id": 999}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_tempo_mod.cli, ["account", "link", "42", "NEWP", "--default"])
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
