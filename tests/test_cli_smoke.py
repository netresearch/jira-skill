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
_worklog_query_mod = _load_script("jira-worklog-query", "utility")
_weblink_mod = _load_script("jira-weblink", "utility")
_watchers_mod = _load_script("jira-watchers", "utility")
_version_mod = _load_script("jira-version", "workflow")
_qa_gather_mod = _load_script("jira-qa-gather", "utility")
_move_mod = _load_script("jira-move", "workflow")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: --help exits cleanly for all CLI scripts
# ═══════════════════════════════════════════════════════════════════════════════


class TestHelpOutput:
    """Every CLI script must respond to --help with exit code 0."""

    def _run_help(self, cli):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0, f"--help failed: {result.output}"
        return result.output

    def test_issue_help(self):
        output = self._run_help(_issue_mod.cli)
        assert "issue" in output.lower()

    def test_search_help(self):
        output = self._run_help(_search_mod.cli)
        assert "search" in output.lower() or "query" in output.lower()

    def test_worklog_help(self):
        output = self._run_help(_worklog_mod.cli)
        assert "worklog" in output.lower()

    def test_create_help(self):
        output = self._run_help(_create_mod.cli)
        assert "create" in output.lower() or "issue" in output.lower()

    def test_transition_help(self):
        output = self._run_help(_transition_mod.cli)
        assert "transition" in output.lower()

    def test_comment_help(self):
        output = self._run_help(_comment_mod.cli)
        assert "comment" in output.lower()

    def test_sprint_help(self):
        output = self._run_help(_sprint_mod.cli)
        assert "sprint" in output.lower()

    def test_board_help(self):
        output = self._run_help(_board_mod.cli)
        assert "board" in output.lower()

    def test_fields_help(self):
        output = self._run_help(_fields_mod.cli)
        assert "field" in output.lower()

    def test_user_help(self):
        output = self._run_help(_user_mod.cli)
        assert "user" in output.lower()

    def test_link_help(self):
        output = self._run_help(_link_mod.cli)
        assert "link" in output.lower()

    def test_worklog_query_help(self):
        output = self._run_help(_worklog_query_mod.cli)
        assert "worklog" in output.lower() or "query" in output.lower()

    def test_weblink_help(self):
        output = self._run_help(_weblink_mod.cli)
        assert "web link" in output.lower() or "remote link" in output.lower()

    def test_watchers_help(self):
        output = self._run_help(_watchers_mod.cli)
        assert "watcher" in output.lower()

    def test_version_help(self):
        output = self._run_help(_version_mod.cli)
        assert "version" in output.lower()

    def test_qa_gather_help(self):
        output = self._run_help(_qa_gather_mod.cli)
        assert "qa" in output.lower() or "review" in output.lower() or "gather" in output.lower()

    def test_qa_gather_rejects_zero_window(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_qa_gather_mod.cli, ["TEST-1", "--sibling-window", "0"])
        assert result.exit_code != 0, "expected non-zero exit for --sibling-window=0"

    def test_qa_gather_rejects_negative_max(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_qa_gather_mod.cli, ["TEST-1", "--max-siblings", "-1"])
        assert result.exit_code != 0, "expected non-zero exit for --max-siblings=-1"


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
        self._run_help(_issue_mod.cli, ["get", "--help"])

    def test_issue_update_help(self):
        self._run_help(_issue_mod.cli, ["update", "--help"])

    def test_search_query_help(self):
        self._run_help(_search_mod.cli, ["query", "--help"])

    def test_worklog_add_help(self):
        self._run_help(_worklog_mod.cli, ["add", "--help"])

    def test_worklog_list_help(self):
        self._run_help(_worklog_mod.cli, ["list", "--help"])

    def test_create_issue_help(self):
        self._run_help(_create_mod.cli, ["issue", "--help"])

    def test_transition_list_help(self):
        self._run_help(_transition_mod.cli, ["list", "--help"])

    def test_transition_do_help(self):
        self._run_help(_transition_mod.cli, ["do", "--help"])

    def test_comment_add_help(self):
        self._run_help(_comment_mod.cli, ["add", "--help"])

    def test_comment_list_help(self):
        self._run_help(_comment_mod.cli, ["list", "--help"])

    def test_comment_edit_help(self):
        self._run_help(_comment_mod.cli, ["edit", "--help"])

    def test_comment_delete_help(self):
        self._run_help(_comment_mod.cli, ["delete", "--help"])

    def test_sprint_list_help(self):
        self._run_help(_sprint_mod.cli, ["list", "--help"])

    def test_sprint_issues_help(self):
        self._run_help(_sprint_mod.cli, ["issues", "--help"])

    def test_board_list_help(self):
        self._run_help(_board_mod.cli, ["list", "--help"])

    def test_board_issues_help(self):
        self._run_help(_board_mod.cli, ["issues", "--help"])

    def test_fields_search_help(self):
        self._run_help(_fields_mod.cli, ["search", "--help"])

    def test_fields_list_help(self):
        self._run_help(_fields_mod.cli, ["list", "--help"])

    def test_user_me_help(self):
        self._run_help(_user_mod.cli, ["me", "--help"])

    def test_user_get_help(self):
        self._run_help(_user_mod.cli, ["get", "--help"])

    def test_link_create_help(self):
        self._run_help(_link_mod.cli, ["create", "--help"])

    def test_link_list_types_help(self):
        self._run_help(_link_mod.cli, ["list-types", "--help"])

    def test_link_bulk_create_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_link_mod.cli, ["bulk-create", "--help"])
        assert result.exit_code == 0, result.output
        assert "--from-csv" in result.output
        assert "--skip-existing" in result.output

    def test_link_bulk_delete_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_link_mod.cli, ["bulk-delete", "--help"])
        assert result.exit_code == 0, result.output
        assert "--ids" in result.output
        assert "--ids-file" in result.output

    def test_link_invert_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_link_mod.cli, ["invert", "--help"])
        assert result.exit_code == 0, result.output
        assert "--id" in result.output
        assert "--dry-run" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Commands with mocked client produce expected output
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockedCommands:
    """CLI commands with mocked Jira client must produce correct output."""

    def _make_mock_client(self):
        client = mock.Mock()
        # Default to Server/DC: LazyJiraClient.jql() override uses is_cloud_url(client.url)
        # to choose between delegating to client.jql() (Server/DC) and calling the new
        # /rest/api/3/search/jql endpoint (Cloud). A bare Mock makes 'url' a Mock object,
        # which would crash urlparse(); pin it to a Server URL so the smokes exercise
        # the delegation path the existing test assertions expect.
        client.url = "https://jira.example.com"
        return client

    def test_issue_get_json(self):
        """jira-issue --json get KEY must output JSON."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "key": "TEST-1",
            "fields": {"summary": "Test issue", "status": {"name": "Open"}},
        }
        mock_client.get_issue_remote_links.return_value = []
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["--json", "get", "TEST-1"])
        assert result.exit_code == 0, result.output
        assert "TEST-1" in result.output

    def test_search_query_quiet(self):
        """jira-search --quiet query JQL must output issue keys only."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {
            "issues": [{"key": "A-1"}, {"key": "A-2"}],
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_search_mod.cli, ["--quiet", "query", "project=A"])
        assert result.exit_code == 0, result.output
        assert "A-1" in result.output
        assert "A-2" in result.output

    def test_search_query_start_at_forwarded(self):
        """jira-search --start-at must be forwarded to client.jql(start=...)."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {
            "issues": [{"key": "A-51"}, {"key": "A-52"}],
            "total": 234,
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _search_mod.cli,
                ["query", "project=A", "--start-at", "50", "--max-results", "50"],
            )
        assert result.exit_code == 0, result.output
        # Verify the pagination kwarg was forwarded to jql()
        mock_client.jql.assert_called_once()
        _, kwargs = mock_client.jql.call_args
        assert kwargs.get("start") == 50
        assert kwargs.get("limit") == 50
        # Verify the pagination range is rendered in the output
        assert "showing 51-52 of 234" in result.output

    def test_search_query_start_at_rejects_negative(self):
        """jira-search --start-at must reject negative values via click.IntRange."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _search_mod.cli,
                ["query", "project=A", "--start-at", "-1"],
            )
        assert result.exit_code != 0
        # click.IntRange rejection happens before the API is hit
        mock_client.jql.assert_not_called()

    def test_search_query_singular_pluralization(self):
        """jira-search must say '1 issue' (singular) when total == 1."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {
            "issues": [{"key": "A-1", "fields": {"summary": "only"}}],
            "total": 1,
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_search_mod.cli, ["query", "project=A"])
        assert result.exit_code == 0, result.output
        assert "of 1 issue)" in result.output
        assert "of 1 issues)" not in result.output

    def test_search_query_empty_page_shows_total(self):
        """Empty issues + total > 0 must hint about --start-at, not 'No issues found'."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {"issues": [], "total": 234}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _search_mod.cli,
                ["query", "project=A", "--start-at", "500"],
            )
        assert result.exit_code == 0, result.output
        assert "No issues on this page" in result.output
        assert "total: 234" in result.output
        assert "--start-at" in result.output

    def test_search_query_warns_when_capped_and_more_pages_exist(self):
        """If server caps page size below requested and more results exist, warn on stderr."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {
            "issues": [{"key": "A-1"}],
            "total": 100,
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_search_mod.cli, ["query", "project=A", "--max-results", "50", "--start-at", "0"])
        assert result.exit_code == 0, result.output
        assert "Server capped results" in result.output

    def test_search_query_does_not_warn_on_final_page(self):
        """Don't warn when fewer results is explained by being on the final page."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {
            "issues": [{"key": "A-99"}],
            "total": 100,
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_search_mod.cli, ["query", "project=A", "--max-results", "50", "--start-at", "99"])
        assert result.exit_code == 0, result.output
        assert "Server capped results" not in result.output

    def test_search_query_order_by_appends_to_jql(self):
        """--order-by must append a single ORDER BY clause to the JQL string."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {"issues": [], "total": 0}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _search_mod.cli,
                ["query", "project = PROJ", "--order-by", "updated DESC"],
            )
        assert result.exit_code == 0, result.output
        mock_client.jql.assert_called_once()
        called_jql = mock_client.jql.call_args[0][0]
        assert called_jql == "project = PROJ ORDER BY updated DESC"

    def test_search_query_order_by_multi_repeats_join_with_comma(self):
        """Multiple --order-by flags must produce one comma-separated ORDER BY."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {"issues": [], "total": 0}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _search_mod.cli,
                [
                    "query",
                    "project = PROJ",
                    "--order-by",
                    "priority DESC",
                    "--order-by",
                    "created ASC",
                ],
            )
        assert result.exit_code == 0, result.output
        called_jql = mock_client.jql.call_args[0][0]
        assert called_jql == "project = PROJ ORDER BY priority DESC, created ASC"

    def test_search_query_order_by_rejects_when_jql_already_orders(self):
        """If JQL already contains ORDER BY, --order-by must error (no jql() call)."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _search_mod.cli,
                [
                    "query",
                    "project = PROJ ORDER BY key",
                    "--order-by",
                    "updated DESC",
                ],
            )
        assert result.exit_code == 2
        assert "ORDER BY" in result.output
        # Tip about the embedded form must surface
        assert "Tip" in result.output
        mock_client.jql.assert_not_called()

    def test_search_query_order_by_ignores_quoted_order_by(self):
        """--order-by must not be rejected when 'order by' appears inside a quoted string literal."""
        mock_client = self._make_mock_client()
        mock_client.jql.return_value = {"issues": [], "total": 0}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            # 'order by' inside a single-quoted value must NOT trip the detector
            result = runner.invoke(
                _search_mod.cli,
                ["query", "summary ~ 'order by'", "--order-by", "updated DESC"],
            )
        assert result.exit_code == 0, result.output
        called_jql = mock_client.jql.call_args[0][0]
        assert "ORDER BY updated DESC" in called_jql

    def test_create_issue_dry_run(self):
        """jira-create issue with --dry-run must not call API."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_create_mod.cli, ["issue", "PROJ", "Test summary", "--type", "Task", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.create_issue.assert_not_called()

    def test_transition_do_dry_run(self):
        """jira-transition do with --dry-run must not call API."""
        mock_client = self._make_mock_client()
        mock_client.get_issue_transitions.return_value = [{"name": "In Progress", "to": {"name": "In Progress"}}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_transition_mod.cli, ["do", "TEST-1", "In Progress", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        mock_client.set_issue_status.assert_not_called()

    def test_link_create_dry_run(self):
        """jira-link create with --dry-run must not call API."""
        mock_client = self._make_mock_client()
        # Dry-run still resolves the link type so the preview can use the
        # outward verb — give it a minimal table to look up.
        mock_client.get_issue_link_types.return_value = [
            {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_link_mod.cli, ["create", "A-1", "A-2", "--type", "Blocks", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        # Direction: A-2 is the active actor, A-1 is the recipient
        assert "A-2 blocks A-1" in result.output
        mock_client.create_issue_link.assert_not_called()

    def test_link_invert_dry_run(self):
        """jira-link invert with --dry-run must not modify Jira."""
        mock_client = self._make_mock_client()
        mock_client.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Cause", "outward": "causes", "inward": "is caused by"},
            "inwardIssue": {"key": "EFFECT-1"},
            "outwardIssue": {"key": "ROOT-2"},
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_link_mod.cli, ["invert", "--id", "42", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would invert: EFFECT-1 causes ROOT-2 → ROOT-2 causes EFFECT-1" in result.output
        mock_client.remove_issue_link.assert_not_called()
        mock_client.create_issue_link.assert_not_called()

    def _run_comment_cmd(self, args, mock_client=None, **invoke_kwargs):
        """Run a jira-comment CLI command with a mocked LazyJiraClient."""
        if mock_client is None:
            mock_client = self._make_mock_client()
        mock_client.with_context = mock.Mock()
        runner = click.testing.CliRunner()
        # Patch on the already-imported module so the constructor is intercepted
        with mock.patch.object(_comment_mod, "LazyJiraClient", return_value=mock_client):
            result = runner.invoke(_comment_mod.cli, args, **invoke_kwargs)
        return result, mock_client

    def test_comment_add_stdin(self):
        """jira-comment add PROJ-123 - must read comment from stdin."""
        mc = self._make_mock_client()
        mc.issue_add_comment.return_value = {"id": "99999"}
        result, mc = self._run_comment_cmd(["add", "PROJ-123", "-"], mock_client=mc, input="h2. Test\n\nBody text")
        assert result.exit_code == 0, result.output
        assert "99999" in result.output
        mc.issue_add_comment.assert_called_once()
        actual_body = mc.issue_add_comment.call_args[0][1]
        assert "h2. Test" in actual_body
        assert "\n\n" in actual_body
        assert "Body text" in actual_body

    def test_comment_add_stdin_preserves_whitespace(self):
        """stdin input must preserve leading whitespace and internal structure."""
        mc = self._make_mock_client()
        mc.issue_add_comment.return_value = {"id": "99998"}
        body = "  indented line\n\n  another indented"
        result, mc = self._run_comment_cmd(["add", "PROJ-123", "-"], mock_client=mc, input=body)
        assert result.exit_code == 0, result.output
        actual_body = mc.issue_add_comment.call_args[0][1]
        assert actual_body == "  indented line\n\n  another indented"

    def test_comment_add_stdin_strips_trailing_newlines_only(self):
        """Trailing newlines stripped; leading whitespace and internal newlines preserved."""
        mc = self._make_mock_client()
        mc.issue_add_comment.return_value = {"id": "100"}
        result, mc = self._run_comment_cmd(["add", "PROJ-123", "-"], mock_client=mc, input="  leading\nline2\n\n")
        assert result.exit_code == 0, result.output
        actual = mc.issue_add_comment.call_args[0][1]
        assert actual == "  leading\nline2"

    def test_comment_add_stdin_empty_fails(self):
        """jira-comment add PROJ-123 - with empty stdin must fail."""
        result, _ = self._run_comment_cmd(["add", "PROJ-123", "-"], input="")
        assert result.exit_code == 1
        assert "stdin" in result.output.lower()

    def test_comment_add_stdin_whitespace_only_fails(self):
        """jira-comment add PROJ-123 - with whitespace-only stdin must fail."""
        result, _ = self._run_comment_cmd(["add", "PROJ-123", "-"], input="   \n\n  ")
        assert result.exit_code == 1
        assert "stdin" in result.output.lower()

    def test_comment_add_stdin_tty_guard_exists(self):
        """The add command must check sys.stdin.isatty() before reading stdin.

        Click's CliRunner replaces sys.stdin during invoke(), making it impossible
        to test the isatty guard through the CLI. We verify at the source level
        that the guard exists and is correctly placed before the stdin read
        (read_stdin_utf8 — see lib/input.py).
        """
        import inspect

        source = inspect.getsource(_comment_mod.add.callback)
        isatty_pos = source.find("isatty()")
        read_pos = source.find("read_stdin_utf8(")
        assert isatty_pos != -1, "isatty() guard missing from add command"
        assert read_pos != -1, "read_stdin_utf8() missing from add command"
        assert isatty_pos < read_pos, "isatty() guard must come before read_stdin_utf8()"

    def test_comment_list_rejects_negative_limit(self):
        """jira-comment list --limit -1 must be rejected by Click before API calls."""
        mc = self._make_mock_client()
        mc.issue = mock.Mock()
        result, mc = self._run_comment_cmd(["list", "PROJ-123", "--limit", "-1"], mock_client=mc)
        assert result.exit_code != 0
        mc.issue.assert_not_called()

    def test_comment_list_header_shows_total_when_limited(self):
        """jira-comment list must show 'N of M' when Jira reports more than shown."""
        mc = self._make_mock_client()
        mc.issue.return_value = {
            "fields": {
                "comment": {
                    "comments": [
                        {
                            "id": "1",
                            "author": {"displayName": "A"},
                            "created": "2026-01-01T00:00:00.000+0000",
                            "body": "a",
                        },
                        {
                            "id": "2",
                            "author": {"displayName": "B"},
                            "created": "2026-01-02T00:00:00.000+0000",
                            "body": "b",
                        },
                    ],
                    "total": 5,
                }
            }
        }
        result, mc = self._run_comment_cmd(["list", "PROJ-123", "--limit", "2"], mock_client=mc)
        assert result.exit_code == 0, result.output
        assert "2 of 5 shown" in result.output

    def test_comment_list_limit_zero_uses_paginated_endpoint(self):
        """jira-comment list --limit 0 should paginate via /issue/{key}/comment."""
        mc = self._make_mock_client()
        mc.issue = mock.Mock()
        mc.get = mock.Mock()
        mc.get.side_effect = [
            {"comments": [{"id": "1"}, {"id": "2"}], "total": 3},
            {"comments": [{"id": "3"}], "total": 3},
        ]
        result, mc = self._run_comment_cmd(["--json", "list", "PROJ-123", "--limit", "0"], mock_client=mc)
        assert result.exit_code == 0, result.output
        # issue endpoint should not be used in this mode
        mc.issue.assert_not_called()
        assert mc.get.call_count == 2
        first_call = mc.get.call_args_list[0]
        assert "rest/api/2/issue/PROJ-123/comment" in first_call.args[0]

    def test_comment_add_stdin_oversized_fails(self):
        """stdin input exceeding size limit must fail."""
        big_input = "x" * (256 * 1024 + 100)
        result, _ = self._run_comment_cmd(["add", "PROJ-123", "-"], input=big_input)
        assert result.exit_code == 1
        assert "size" in result.output.lower()

    def test_comment_add_stdin_quiet(self):
        """jira-comment --quiet add PROJ-123 - must output only the comment ID."""
        mc = self._make_mock_client()
        mc.issue_add_comment.return_value = {"id": "88888"}
        result, mc = self._run_comment_cmd(["--quiet", "add", "PROJ-123", "-"], mock_client=mc, input="text")
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "88888"

    def test_comment_add_literal_text(self):
        """jira-comment add PROJ-123 'text' must pass text directly, not read stdin."""
        mc = self._make_mock_client()
        mc.issue_add_comment.return_value = {"id": "99997"}
        result, mc = self._run_comment_cmd(["add", "PROJ-123", "literal text"], mock_client=mc)
        assert result.exit_code == 0, result.output
        mc.issue_add_comment.assert_called_once_with("PROJ-123", "literal text")

    def test_user_me_json(self):
        """jira-user --json me must output user info as JSON."""
        mock_client = self._make_mock_client()
        mock_client.myself.return_value = {
            "displayName": "John Doe",
            "emailAddress": "john@example.com",
            "accountId": "12345",
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_user_mod.cli, ["--json", "me"])
        assert result.exit_code == 0, result.output
        assert "John Doe" in result.output

    def test_board_list_name_filter_passed_to_api(self):
        """jira-board list --name PATTERN must forward pattern as server-side filter.

        The Jira agile API does partial-match filtering server-side when
        `name` is passed; we must not fall back to client-side filtering,
        otherwise instances with 3000+ boards waste a round trip.
        """
        mock_client = self._make_mock_client()
        mock_client.get.return_value = {"values": []}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_board_mod.cli, ["list", "--name", "Lithium"])
        assert result.exit_code == 0, result.output
        mock_client.get.assert_called_once()
        _, kwargs = mock_client.get.call_args
        params = kwargs.get("params", {})
        assert params.get("name") == "Lithium"

    def test_board_list_paginates_until_last_page(self):
        """jira-board list must follow agile pagination when isLast is false."""
        mock_client = self._make_mock_client()
        mock_client.get.side_effect = [
            {"values": [{"id": 1, "name": "A", "type": "scrum", "location": {"projectKey": "P"}}], "isLast": False},
            {"values": [{"id": 2, "name": "B", "type": "kanban", "location": {"projectKey": "P"}}], "isLast": True},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_board_mod.cli, ["list"])
        assert result.exit_code == 0, result.output
        assert mock_client.get.call_count == 2
        starts = [call.kwargs.get("params", {}).get("startAt") for call in mock_client.get.call_args_list]
        assert starts == [0, 1]

    def test_sprint_list_paginates_until_last_page(self):
        """jira-sprint list must follow agile pagination when isLast is false."""
        mock_client = self._make_mock_client()
        mock_client.get.side_effect = [
            {"values": [{"id": 10, "name": "S1", "state": "closed"}], "isLast": False},
            {"values": [{"id": 11, "name": "S2", "state": "active"}], "isLast": True},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_sprint_mod.cli, ["list", "42"])
        assert result.exit_code == 0, result.output
        assert mock_client.get.call_count == 2
        paths = [call.args[0] for call in mock_client.get.call_args_list]
        assert all("rest/agile/1.0/board/42/sprint" in p for p in paths)
        starts = [call.kwargs.get("params", {}).get("startAt") for call in mock_client.get.call_args_list]
        assert starts == [0, 1]

    def test_issue_update_add_labels_splits_commas_and_dedupes_casefold(self):
        """--add-label should accept comma-separated tokens and avoid case-duplicates."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {"fields": {"labels": ["Foo", "bar"]}}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _issue_mod.cli,
                ["update", "TEST-1", "--add-label", "foo,Baz", "--add-label", "baz"],
            )
        assert result.exit_code == 0, result.output
        mock_client.update_issue_field.assert_called_once()
        args, _kwargs = mock_client.update_issue_field.call_args
        assert args[0] == "TEST-1"
        payload = args[1]
        assert payload["labels"] == ["bar", "Baz", "Foo"]

    def test_issue_update_remove_labels_matches_case_insensitively(self):
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {"fields": {"labels": ["Foo", "BAR"]}}
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["update", "TEST-1", "--remove-label", "foo,bar"])
        assert result.exit_code == 0, result.output
        mock_client.update_issue_field.assert_called_once()
        args, _kwargs = mock_client.update_issue_field.call_args
        assert args[1]["labels"] == []

    def test_issue_update_rejects_labels_with_incremental_flags(self):
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _issue_mod.cli,
                ["update", "TEST-1", "--labels", "a,b", "--add-label", "c"],
            )
        assert result.exit_code != 0
        mock_client.issue.assert_not_called()
        mock_client.update_issue_field.assert_not_called()

    def test_issue_update_description_typed_flag(self):
        """--description should set the description field on update."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _issue_mod.cli,
                ["update", "TEST-1", "--description", "New body"],
            )
        assert result.exit_code == 0, result.output
        mock_client.update_issue_field.assert_called_once()
        args, _kwargs = mock_client.update_issue_field.call_args
        assert args[0] == "TEST-1"
        assert args[1] == {"description": "New body"}

    def test_issue_update_description_from_stdin_strips_trailing_newline(self):
        """--description - should read from stdin and rstrip trailing newlines."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _issue_mod.cli,
                ["update", "TEST-1", "--description", "-"],
                input="Body from heredoc\n",
            )
        assert result.exit_code == 0, result.output
        args, _kwargs = mock_client.update_issue_field.call_args
        assert args[1] == {"description": "Body from heredoc"}

    def test_issue_update_description_empty_string_is_set(self):
        """Empty --description still issues an update (clears the field)."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _issue_mod.cli,
                ["update", "TEST-1", "--description", ""],
            )
        assert result.exit_code == 0, result.output
        args, _kwargs = mock_client.update_issue_field.call_args
        assert args[1] == {"description": ""}

    def test_issue_update_description_combines_with_other_flags(self):
        """--description should compose with other typed flags."""
        mock_client = self._make_mock_client()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(
                _issue_mod.cli,
                ["update", "TEST-1", "--description", "x", "--priority", "High"],
            )
        assert result.exit_code == 0, result.output
        args, _kwargs = mock_client.update_issue_field.call_args
        assert args[1] == {"description": "x", "priority": {"name": "High"}}

    def test_move_issue_cross_project_refused_even_for_dry_run(self):
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "fields": {
                "summary": "Hi",
                "issuetype": {"name": "Task"},
                "status": {"name": "Open"},
                "project": {"key": "SRC"},
            }
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_move_mod.cli, ["issue", "SRC-1", "DST", "--dry-run"])
        assert result.exit_code != 0
        mock_client.issue.assert_called_once()
        mock_client._session.put.assert_not_called()

    def test_issue_get_json_compact_by_default(self):
        """jira-issue --json get must strip null/empty fields by default."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "key": "TEST-1",
            "id": "10001",
            "fields": {
                "summary": "Test",
                "status": {"name": "Open"},
                "assignee": None,
                "labels": [],
                "customfield_99999": None,
            },
        }
        mock_client.get_issue_remote_links.return_value = []
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["--json", "get", "TEST-1"])
        assert result.exit_code == 0, result.output
        assert "customfield_99999" not in result.output
        assert "assignee" not in result.output
        assert "TEST-1" in result.output

    def test_issue_get_json_raw_preserves_nulls(self):
        """jira-issue --json get --raw must keep null/empty fields."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "key": "TEST-1",
            "fields": {"summary": "Test", "customfield_99999": None},
        }
        mock_client.get_issue_remote_links.return_value = []
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["--json", "get", "TEST-1", "--raw"])
        assert result.exit_code == 0, result.output
        assert "customfield_99999" in result.output

    def test_issue_time_in_status_help(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_issue_mod.cli, ["time-in-status", "--help"])
        assert result.exit_code == 0, result.output
        assert "time" in result.output.lower()

    def test_issue_time_in_status_fetches_changelog_and_prints_summary(self):
        """time-in-status must request changelog expansion and show per-status durations."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "key": "TEST-1",
            "fields": {
                "summary": "Test",
                "status": {"name": "Done"},
                "created": "2024-01-01T00:00:00.000+0000",
            },
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-03T00:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "Open", "toString": "In Progress"}],
                    },
                    {
                        "created": "2024-01-10T00:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "In Progress", "toString": "Done"}],
                    },
                ]
            },
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["time-in-status", "TEST-1"])
        assert result.exit_code == 0, result.output
        # Must pass expand=changelog to Jira
        _, kwargs = mock_client.issue.call_args
        assert "changelog" in kwargs.get("expand", "")
        # Output mentions each status
        assert "Open" in result.output
        assert "In Progress" in result.output
        assert "Done" in result.output

    def test_issue_time_in_status_filter_resolves_status_name(self):
        """--status 'progress' should resolve to 'In Progress' via resolve_status()."""
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "key": "TEST-1",
            "fields": {
                "summary": "Test",
                "status": {"name": "Done"},
                "created": "2024-01-01T00:00:00.000+0000",
            },
            "changelog": {
                "histories": [
                    {
                        "created": "2024-01-03T00:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "Open", "toString": "In Progress"}],
                    },
                    {
                        "created": "2024-01-10T00:00:00.000+0000",
                        "items": [{"field": "status", "fromString": "In Progress", "toString": "Done"}],
                    },
                ]
            },
        }
        # resolve_status will call client.get("rest/api/2/status")
        mock_client.get.return_value = [
            {"name": "Open"},
            {"name": "In Progress"},
            {"name": "Done"},
        ]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["time-in-status", "TEST-1", "--status", "progress"])
        assert result.exit_code == 0, result.output
        assert "In Progress" in result.output

    def test_issue_time_in_status_json(self):
        mock_client = self._make_mock_client()
        mock_client.issue.return_value = {
            "key": "TEST-1",
            "fields": {
                "summary": "Test",
                "status": {"name": "Open"},
                "created": "2024-01-01T00:00:00.000+0000",
            },
            "changelog": {"histories": []},
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_issue_mod.cli, ["--json", "time-in-status", "TEST-1"])
        assert result.exit_code == 0, result.output
        # JSON payload must include the key and a status breakdown
        import json as _json

        payload = _json.loads(result.output)
        assert payload["key"] == "TEST-1"
        assert payload["current_status"] == "Open"
        assert "Open" in payload["time_in_status"]

    def test_worklog_list_renders_adf_comment(self):
        """jira-worklog list must render extracted text from ADF comments (Cloud), not the raw dict."""
        adf_comment = {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Implemented retry logic"}]}],
        }
        mock_client = self._make_mock_client()
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [
                {
                    "id": "1",
                    "author": {"displayName": "Alice"},
                    "timeSpent": "2h",
                    "started": "2026-04-30T08:00:00.000+0000",
                    "comment": adf_comment,
                }
            ]
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_worklog_mod.cli, ["list", "TEST-1"])
        assert result.exit_code == 0, result.output
        assert "Implemented retry logic" in result.output
        # Regression guard: a raw ADF dict would render as repr() starting with "{'type'"
        assert "{'type'" not in result.output

    def test_worklog_list_truncate_does_not_raise_on_adf(self):
        """--truncate must not raise TypeError when comment is an ADF dict (Cloud regression)."""
        adf_comment = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "A long worklog comment that exceeds twenty characters"}],
                }
            ],
        }
        mock_client = self._make_mock_client()
        mock_client.issue_get_worklog.return_value = {
            "worklogs": [
                {
                    "id": "1",
                    "author": {"displayName": "Alice"},
                    "timeSpent": "1h",
                    "started": "2026-04-30T08:00:00.000+0000",
                    "comment": adf_comment,
                }
            ]
        }
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=mock_client):
            result = runner.invoke(_worklog_mod.cli, ["list", "TEST-1", "--truncate", "20"])
        # Pre-fix this raised TypeError ("unhashable type: 'slice'"-style on dict slicing).
        assert result.exit_code == 0, result.output
        assert "..." in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: jira-issue intent verbs (work / qa / qa-fail / act)
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntentVerbs:
    """Smoke tests for the four single-call intent verbs added in this PR."""

    def _mock_client_for_intents(self, comments=None, transitions=None, status_name="QA", changelog=None):
        client = mock.Mock()
        client.issue.return_value = {
            "key": "TEST-1",
            "fields": {
                "summary": "Test ticket",
                "status": {"name": status_name},
                "assignee": {"displayName": "Test User"},
                "description": "Body",
                "attachment": [],
                "issuelinks": [],
            },
            "changelog": {"histories": changelog or []},
        }
        client.get.return_value = {"comments": comments or [], "total": len(comments or [])}
        client.get_issue_remote_links.return_value = []
        client.get_issue_transitions.return_value = transitions or []
        return client

    def test_work_help_lists_truncate(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_issue_mod.cli, ["work", "--help"])
        assert result.exit_code == 0
        assert "--truncate" in result.output

    def test_qa_help_lists_truncate(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_issue_mod.cli, ["qa", "--help"])
        assert result.exit_code == 0
        assert "--truncate" in result.output

    def test_act_help_has_no_truncate(self):
        """`act` has no body content — `--truncate` should NOT be exposed."""
        runner = click.testing.CliRunner()
        result = runner.invoke(_issue_mod.cli, ["act", "--help"])
        assert result.exit_code == 0
        assert "--truncate" not in result.output

    def test_work_json_includes_attachments_and_links(self):
        """`work --json` must include attachments, issueLinks, webLinks in payload."""
        client = self._mock_client_for_intents(comments=[])
        client.issue.return_value["fields"]["attachment"] = [{"filename": "x.log"}]
        client.issue.return_value["fields"]["issuelinks"] = [{"type": {"name": "Blocks"}}]
        client.get_issue_remote_links.return_value = [{"object": {"url": "https://x"}}]
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=client):
            result = runner.invoke(_issue_mod.cli, ["--json", "work", "TEST-1"])
        assert result.exit_code == 0, result.output
        import json as _json

        data = _json.loads(result.output)
        assert data["attachments"] == [{"filename": "x.log"}]
        assert data["issueLinks"] == [{"type": {"name": "Blocks"}}]
        assert data["webLinks"] == [{"object": {"url": "https://x"}}]

    def test_work_quiet_skips_remote_link_fetch(self):
        """`work --quiet` must not hit the remote-link endpoint."""
        client = self._mock_client_for_intents()
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=client):
            result = runner.invoke(_issue_mod.cli, ["--quiet", "work", "TEST-1"])
        assert result.exit_code == 0, result.output
        assert "TEST-1" in result.output
        client.get_issue_remote_links.assert_not_called()

    def test_work_paginates_comments(self):
        """`work` must call the paginated comment endpoint (not the embedded payload)."""
        comments = [
            {"id": str(i), "created": f"2026-05-10T08:00:0{i}.000+0000", "author": {"displayName": "U"}, "body": "x"}
            for i in range(3)
        ]
        client = self._mock_client_for_intents(comments=comments)
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=client):
            result = runner.invoke(_issue_mod.cli, ["--json", "work", "TEST-1"])
        assert result.exit_code == 0, result.output
        client.get.assert_any_call("rest/api/2/issue/TEST-1/comment", params={"startAt": 0, "maxResults": 100})

    def test_qa_fallback_when_no_into_qa_transition(self):
        """`qa` falls back to last 5 comments when no INTO_QA transition is in the changelog."""
        comments = [
            {"id": str(i), "created": f"2026-05-10T08:00:0{i}.000+0000", "author": {"displayName": "U"}, "body": "x"}
            for i in range(3)
        ]
        client = self._mock_client_for_intents(comments=comments, changelog=[])
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=client):
            result = runner.invoke(_issue_mod.cli, ["qa", "TEST-1"])
        assert result.exit_code == 0, result.output
        assert "falling back to last 5 comments" in result.output

    def test_act_surfaces_transition_fetch_failure(self):
        """`act` must exit non-zero (outside debug) if the transitions endpoint fails."""
        client = self._mock_client_for_intents()
        client.get_issue_transitions.side_effect = RuntimeError("boom")
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=client):
            result = runner.invoke(_issue_mod.cli, ["act", "TEST-1"])
        assert result.exit_code != 0
        assert "boom" in result.output or "act context" in result.output

    def test_act_lists_transitions_in_text_mode(self):
        client = self._mock_client_for_intents(
            transitions=[{"id": "11", "name": "Start work"}, {"id": "31", "name": "Resolve"}]
        )
        runner = click.testing.CliRunner()
        with mock.patch("lib.client.get_jira_client", return_value=client):
            result = runner.invoke(_issue_mod.cli, ["act", "TEST-1"])
        assert result.exit_code == 0, result.output
        assert "Start work" in result.output
        assert "Resolve" in result.output
