"""Tests for jira-watchers.py — list/add/remove issue watchers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import click.testing
import pytest

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str, subdir: str = "utility"):
    """Load a hyphenated CLI script via importlib."""
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_watchers_mod = _load_script("jira-watchers", "utility")


def _make_mock_client(cloud: bool = False):
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    # Explicit attribute — LazyJiraClient exposes .cloud via atlassian.Jira
    object.__setattr__(mc, "cloud", cloud)
    return mc


def _run(args, mock_client=None):
    """Run jira-watchers CLI with a mocked LazyJiraClient."""
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_watchers_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_watchers_mod.cli, args)
    return result, mock_client


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: help / subcommand registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersHelp:
    def test_cli_help_shows_subcommands(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_watchers_mod.cli, ["--help"])
        assert result.exit_code == 0, result.output
        assert "list" in result.output
        assert "add" in result.output
        assert "remove" in result.output


def _watcher(name="jdoe", display="John Doe", account_id=None):
    """Build a watcher dict matching the Jira API shape."""
    w = {"name": name, "displayName": display, "active": True}
    if account_id is not None:
        w["accountId"] = account_id
    return w


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: list subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersList:
    def test_list_text_output(self):
        mc = _make_mock_client()
        mc.issue_get_watchers.return_value = {
            "watchCount": 2,
            "isWatching": False,
            "watchers": [
                _watcher("jdoe", "John Doe"),
                _watcher("asmith", "Alice Smith"),
            ],
        }
        result, _ = _run(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "TEST-1" in result.output
        assert "jdoe" in result.output
        assert "John Doe" in result.output
        assert "asmith" in result.output
        assert "Alice Smith" in result.output
        mc.issue_get_watchers.assert_called_once_with("TEST-1")

    def test_list_empty(self):
        mc = _make_mock_client()
        mc.issue_get_watchers.return_value = {
            "watchCount": 0, "isWatching": False, "watchers": [],
        }
        result, _ = _run(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "(no watchers)" in result.output
        assert "TEST-1" in result.output

    def test_list_json_output(self):
        mc = _make_mock_client()
        payload = {
            "watchCount": 1,
            "isWatching": True,
            "watchers": [_watcher("jdoe", "John Doe")],
        }
        mc.issue_get_watchers.return_value = payload
        result, _ = _run(["--json", "list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["watchCount"] == 1
        assert data["isWatching"] is True
        assert data["watchers"][0]["name"] == "jdoe"

    def test_list_quiet_cloud_prints_account_ids(self):
        mc = _make_mock_client(cloud=True)
        mc.issue_get_watchers.return_value = {
            "watchCount": 2,
            "isWatching": False,
            "watchers": [
                _watcher("a", "A", account_id="557058:aaa"),
                _watcher("b", "B", account_id="557058:bbb"),
            ],
        }
        result, _ = _run(["--quiet", "list", "TEST-1"], mc)
        assert result.exit_code == 0
        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        assert lines == ["557058:aaa", "557058:bbb"]

    def test_list_quiet_dc_prints_usernames(self):
        mc = _make_mock_client(cloud=False)
        mc.issue_get_watchers.return_value = {
            "watchCount": 2,
            "isWatching": False,
            "watchers": [_watcher("jdoe", "J"), _watcher("asmith", "A")],
        }
        result, _ = _run(["--quiet", "list", "TEST-1"], mc)
        assert result.exit_code == 0
        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        assert lines == ["jdoe", "asmith"]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: add subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWatchersAdd:
    def test_add_self_default(self):
        mc = _make_mock_client()
        # Default --user is "me", resolve_assignee calls client.myself()
        mc.myself.return_value = {"name": "bwilson", "displayName": "Bob Wilson"}
        mc.issue_add_watcher.return_value = None  # 204 No Content
        result, _ = _run(["add", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "Added watcher" in result.output
        assert "TEST-1" in result.output
        assert "bwilson" in result.output
        # Raw string identifier, not a dict — Jira's watchers POST body is
        # a JSON-encoded string; atlassian-python-api passes this straight
        # through as the request body.
        mc.issue_add_watcher.assert_called_once_with("TEST-1", "bwilson")

    def test_add_user_by_username_dc(self):
        mc = _make_mock_client(cloud=False)
        mc.user_find_by_user_string.return_value = [
            {"name": "asmith", "displayName": "Alice Smith"}
        ]
        result, _ = _run(["add", "TEST-1", "--user", "asmith"], mc)
        assert result.exit_code == 0, result.output
        assert "asmith" in result.output
        assert "(you)" not in result.output
        mc.issue_add_watcher.assert_called_once_with("TEST-1", "asmith")

    def test_add_user_by_account_id_cloud(self):
        """An account-id-shaped identifier bypasses user search."""
        mc = _make_mock_client(cloud=True)
        acct = "557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a"
        result, _ = _run(["add", "TEST-1", "--user", acct], mc)
        assert result.exit_code == 0, result.output
        mc.user_find_by_user_string.assert_not_called()
        mc.issue_add_watcher.assert_called_once_with("TEST-1", acct)

    def test_add_json_output(self):
        mc = _make_mock_client()
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["--json", "add", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data == {"key": "TEST-1", "user": "bwilson", "added": True}

    def test_add_quiet_output(self):
        mc = _make_mock_client()
        mc.myself.return_value = {"name": "bwilson"}
        result, _ = _run(["--quiet", "add", "TEST-1"], mc)
        assert result.exit_code == 0
        assert result.output.strip() == "ok"
