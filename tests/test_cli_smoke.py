"""Smoke tests for CLI scripts — verify --help works and basic error handling.

These tests use click.testing.CliRunner with mocked Jira clients to verify
that CLI scripts load correctly, parse options, and handle errors gracefully.
"""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import click.testing

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str, subdir: str = "core"):
    """Load a hyphenated CLI script via importlib."""
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════════════
# Load all CLI modules once
# ═══════════════════════════════════════════════════════════════════════════════

_issue_mod = _load_script("jira-issue", "core")
_search_mod = _load_script("jira-search", "core")
_worklog_mod = _load_script("jira-worklog", "core")
_create_mod = _load_script("jira-create", "workflow")
_transition_mod = _load_script("jira-transition", "workflow")
_comment_mod = _load_script("jira-comment", "workflow")
_sprint_mod = _load_script("jira-sprint", "workflow")
_board_mod = _load_script("jira-board", "workflow")
_fields_mod = _load_script("jira-fields", "utility")
_user_mod = _load_script("jira-user", "utility")
_link_mod = _load_script("jira-link", "utility")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: --help exits cleanly for all CLI scripts
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpOutput:
    """Every CLI script must respond to --help with exit code 0."""

    def _run_help(self, cli):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0, f"--help failed: {result.output}"
        return result.output

    def test_issue_help(self):
        output = self._run_help(_issue_mod.cli)
        assert 'issue' in output.lower()

    def test_search_help(self):
        output = self._run_help(_search_mod.cli)
        assert 'search' in output.lower() or 'query' in output.lower()

    def test_worklog_help(self):
        output = self._run_help(_worklog_mod.cli)
        assert 'worklog' in output.lower()

    def test_create_help(self):
        output = self._run_help(_create_mod.cli)
        assert 'create' in output.lower() or 'issue' in output.lower()

    def test_transition_help(self):
        output = self._run_help(_transition_mod.cli)
        assert 'transition' in output.lower()

    def test_comment_help(self):
        output = self._run_help(_comment_mod.cli)
        assert 'comment' in output.lower()

    def test_sprint_help(self):
        output = self._run_help(_sprint_mod.cli)
        assert 'sprint' in output.lower()

    def test_board_help(self):
        output = self._run_help(_board_mod.cli)
        assert 'board' in output.lower()

    def test_fields_help(self):
        output = self._run_help(_fields_mod.cli)
        assert 'field' in output.lower()

    def test_user_help(self):
        output = self._run_help(_user_mod.cli)
        assert 'user' in output.lower()

    def test_link_help(self):
        output = self._run_help(_link_mod.cli)
        assert 'link' in output.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Subcommand --help exits cleanly
# ═══════════════════════════════════════════════════════════════════════════════

class TestSubcommandHelp:
    """Subcommands must respond to --help with exit code 0."""

    def _run_help(self, cli, args):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, f"--help failed: {result.output}"

    def test_issue_get_help(self):
        self._run_help(_issue_mod.cli, ['get', '--help'])

    def test_issue_update_help(self):
        self._run_help(_issue_mod.cli, ['update', '--help'])

    def test_search_query_help(self):
        self._run_help(_search_mod.cli, ['query', '--help'])

    def test_worklog_add_help(self):
        self._run_help(_worklog_mod.cli, ['add', '--help'])

    def test_worklog_list_help(self):
        self._run_help(_worklog_mod.cli, ['list', '--help'])

    def test_create_issue_help(self):
        self._run_help(_create_mod.cli, ['issue', '--help'])

    def test_transition_list_help(self):
        self._run_help(_transition_mod.cli, ['list', '--help'])

    def test_transition_do_help(self):
        self._run_help(_transition_mod.cli, ['do', '--help'])

    def test_comment_add_help(self):
        self._run_help(_comment_mod.cli, ['add', '--help'])

    def test_comment_list_help(self):
        self._run_help(_comment_mod.cli, ['list', '--help'])

    def test_sprint_list_help(self):
        self._run_help(_sprint_mod.cli, ['list', '--help'])

    def test_sprint_issues_help(self):
        self._run_help(_sprint_mod.cli, ['issues', '--help'])

    def test_board_list_help(self):
        self._run_help(_board_mod.cli, ['list', '--help'])

    def test_board_issues_help(self):
        self._run_help(_board_mod.cli, ['issues', '--help'])

    def test_fields_search_help(self):
        self._run_help(_fields_mod.cli, ['search', '--help'])

    def test_fields_list_help(self):
        self._run_help(_fields_mod.cli, ['list', '--help'])

    def test_user_me_help(self):
        self._run_help(_user_mod.cli, ['me', '--help'])

    def test_user_get_help(self):
        self._run_help(_user_mod.cli, ['get', '--help'])

    def test_link_create_help(self):
        self._run_help(_link_mod.cli, ['create', '--help'])

    def test_link_list_types_help(self):
        self._run_help(_link_mod.cli, ['list-types', '--help'])


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Commands with mocked client produce expected output
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockedCommands:
    """CLI commands with mocked Jira client must produce correct output."""

    def _make_mock_client(self):
        return mock.Mock()

    def test_issue_get_json(self):
        """jira-issue --json get KEY must output JSON."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            'key': 'TEST-1',
            'fields': {'summary': 'Test issue', 'status': {'name': 'Open'}},
        }
        runner = click.testing.CliRunner()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ['--json', 'get', 'TEST-1'])
        assert result.exit_code == 0, result.output
        assert 'TEST-1' in result.output

    def test_search_query_quiet(self):
        """jira-search --quiet query JQL must output issue keys only."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {
            'issues': [{'key': 'A-1'}, {'key': 'A-2'}],
        }
        runner = click.testing.CliRunner()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            result = runner.invoke(_search_mod.cli, ['--quiet', 'query', 'project=A'])
        assert result.exit_code == 0, result.output
        assert 'A-1' in result.output
        assert 'A-2' in result.output

    def test_create_issue_dry_run(self):
        """jira-create issue with --dry-run must not call API."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            result = runner.invoke(_create_mod.cli, [
                'issue', 'PROJ', 'Test summary', '--type', 'Task', '--dry-run'
            ])
        assert result.exit_code == 0, result.output
        assert 'DRY RUN' in result.output
        mock_client.create_issue.assert_not_called()

    def test_transition_do_dry_run(self):
        """jira-transition do with --dry-run must not call API."""
        mock_client = self._make_mock_client()
        mock_client.get_issue_transitions.return_value = [
            {'name': 'In Progress', 'to': {'name': 'In Progress'}}
        ]
        runner = click.testing.CliRunner()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            result = runner.invoke(_transition_mod.cli, [
                'do', 'TEST-1', 'In Progress', '--dry-run'
            ])
        assert result.exit_code == 0, result.output
        assert 'DRY RUN' in result.output
        mock_client.set_issue_status.assert_not_called()

    def test_link_create_dry_run(self):
        """jira-link create with --dry-run must not call API."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            result = runner.invoke(_link_mod.cli, [
                'create', 'A-1', 'A-2', '--type', 'Blocks', '--dry-run'
            ])
        assert result.exit_code == 0, result.output
        assert 'DRY RUN' in result.output
        mock_client.create_issue_link.assert_not_called()

    def test_user_me_json(self):
        """jira-user --json me must output user info as JSON."""
        mock_client = self._make_mock_client()
        mock_client.myself.return_value = {
            'displayName': 'John Doe',
            'emailAddress': 'john@example.com',
            'accountId': '12345',
        }
        runner = click.testing.CliRunner()
        with mock.patch('lib.client.get_jira_client', return_value=mock_client):
            result = runner.invoke(_user_mod.cli, ['--json', 'me'])
        assert result.exit_code == 0, result.output
        assert 'John Doe' in result.output
