"""Tests for jira-weblink.py CRUD subcommands and jira-issue.py link output."""

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


def _load_script(name: str, subdir: str = "core"):
    """Load a hyphenated CLI script via importlib."""
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_weblink_mod = _load_script("jira-weblink", "utility")
_issue_mod = _load_script("jira-issue", "core")


def _make_mock_client():
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    return mc


def _run_weblink(args, mock_client=None):
    """Run jira-weblink CLI with a mocked LazyJiraClient."""
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_weblink_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_weblink_mod.cli, args)
    return result, mock_client


def _run_issue(args, mock_client=None):
    """Run jira-issue CLI with a mocked LazyJiraClient."""
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_issue_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_issue_mod.cli, args)
    return result, mock_client


def _link(link_id=42, url="https://example.com", title="Example"):
    """Build a remote link dict matching the Jira API shape."""
    return {"id": link_id, "object": {"url": url, "title": title}}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: weblink help
# ═══════════════════════════════════════════════════════════════════════════════


class TestWeblinkHelp:
    """Subcommands must respond to --help with exit code 0."""

    @pytest.mark.parametrize("subcmd", ["add", "list", "update", "delete"])
    def test_subcommand_help(self, subcmd):
        runner = click.testing.CliRunner()
        result = runner.invoke(_weblink_mod.cli, [subcmd, "--help"])
        assert result.exit_code == 0, result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: add subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWeblinkAdd:
    def test_add_text_output(self):
        mc = _make_mock_client()
        mc.create_or_update_issue_remote_links.return_value = {"id": 99}
        result, _ = _run_weblink(
            ["add", "TEST-1", "--url", "https://example.com", "--title", "My Link"],
            mc,
        )
        assert result.exit_code == 0, result.output
        assert "Added web link" in result.output
        assert "TEST-1" in result.output
        mc.create_or_update_issue_remote_links.assert_called_once_with("TEST-1", "https://example.com", "My Link")

    def test_add_json_output(self):
        mc = _make_mock_client()
        mc.create_or_update_issue_remote_links.return_value = {"id": 99}
        result, _ = _run_weblink(
            ["--json", "add", "TEST-1", "--url", "https://example.com", "--title", "Doc"],
            mc,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["key"] == "TEST-1"
        assert data["url"] == "https://example.com"
        assert data["title"] == "Doc"
        assert data["created"] is True
        assert data["id"] == 99

    def test_add_quiet_output(self):
        mc = _make_mock_client()
        mc.create_or_update_issue_remote_links.return_value = {"id": 1}
        result, _ = _run_weblink(
            ["--quiet", "add", "TEST-1", "--url", "https://x.com", "--title", "X"],
            mc,
        )
        assert result.exit_code == 0
        assert result.output.strip() == "ok"

    def test_add_dry_run(self):
        mc = _make_mock_client()
        result, _ = _run_weblink(
            ["add", "TEST-1", "--url", "https://x.com", "--title", "X", "--dry-run"],
            mc,
        )
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would add" in result.output
        mc.create_or_update_issue_remote_links.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: list subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWeblinkList:
    def test_list_text_output(self):
        mc = _make_mock_client()
        url_a = "https://a.com"
        url_b = "https://b.com"
        mc.get_issue_remote_links.return_value = [
            _link(1, url_a, "Link A"),
            _link(2, url_b, "Link B"),
        ]
        result, _ = _run_weblink(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "Web links for TEST-1" in result.output
        assert "[1]" in result.output
        assert "Link A" in result.output
        assert url_a in result.output
        assert "[2]" in result.output

    def test_list_json_output(self):
        mc = _make_mock_client()
        links = [_link(10, "https://x.com", "X")]
        mc.get_issue_remote_links.return_value = links
        result, _ = _run_weblink(["--json", "list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == 10

    def test_list_empty(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = []
        result, _ = _run_weblink(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "No web links found" in result.output

    def test_list_quiet(self):
        mc = _make_mock_client()
        url_q = "https://q.com"
        mc.get_issue_remote_links.return_value = [
            _link(5, url_q, "Q"),
        ]
        result, _ = _run_weblink(["--quiet", "list", "TEST-1"], mc)
        assert result.exit_code == 0
        assert f"5 {url_q}" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: update subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWeblinkUpdate:
    def test_update_by_id(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://old.com", "Old")
        result, _ = _run_weblink(
            ["update", "TEST-1", "--id", "42", "--title", "New Title"],
            mc,
        )
        assert result.exit_code == 0, result.output
        assert "Updated web link" in result.output
        mc.update_issue_remote_link_by_id.assert_called_once_with("TEST-1", 42, "https://old.com", "New Title")

    def test_update_by_url(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [_link(7, "https://target.com", "T")]
        mc.get_issue_remote_link_by_id.return_value = _link(7, "https://target.com", "T")
        result, _ = _run_weblink(
            ["update", "TEST-1", "--url", "https://target.com", "--new-url", "https://new.com"],
            mc,
        )
        assert result.exit_code == 0, result.output
        mc.update_issue_remote_link_by_id.assert_called_once_with("TEST-1", 7, "https://new.com", "T")

    def test_update_missing_id_and_url(self):
        result, mc = _run_weblink(["update", "TEST-1", "--title", "X"])
        assert result.exit_code == 1
        assert "--id" in result.output or "--url" in result.output

    def test_update_missing_title_and_new_url(self):
        result, mc = _run_weblink(["update", "TEST-1", "--id", "42"])
        assert result.exit_code == 1
        assert "--title" in result.output or "--new-url" in result.output

    def test_update_json_output(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://x.com", "X")
        result, _ = _run_weblink(
            ["--json", "update", "TEST-1", "--id", "42", "--title", "Y"],
            mc,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["updated"] is True
        assert data["id"] == 42

    def test_update_quiet_output(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://x.com", "X")
        result, _ = _run_weblink(
            ["--quiet", "update", "TEST-1", "--id", "42", "--title", "Y"],
            mc,
        )
        assert result.exit_code == 0
        assert result.output.strip() == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: delete subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestWeblinkDelete:
    def test_delete_by_id(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://x.com", "X")
        result, _ = _run_weblink(["delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        assert "Deleted web link" in result.output
        mc.delete_issue_remote_link_by_id.assert_called_once_with("TEST-1", 42)

    def test_delete_by_url(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [_link(9, "https://del.com", "Del")]
        mc.get_issue_remote_link_by_id.return_value = _link(9, "https://del.com", "Del")
        result, _ = _run_weblink(["delete", "TEST-1", "--url", "https://del.com"], mc)
        assert result.exit_code == 0, result.output
        mc.delete_issue_remote_link_by_id.assert_called_once_with("TEST-1", 9)

    def test_delete_dry_run(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://x.com", "X")
        result, _ = _run_weblink(["delete", "TEST-1", "--id", "42", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would delete" in result.output
        mc.delete_issue_remote_link_by_id.assert_not_called()

    def test_delete_missing_id_and_url(self):
        result, _ = _run_weblink(["delete", "TEST-1"])
        assert result.exit_code == 1
        assert "--id" in result.output or "--url" in result.output

    def test_delete_json_output(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://x.com", "X")
        result, _ = _run_weblink(["--json", "delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["deleted"] is True
        assert data["id"] == 42

    def test_delete_quiet_output(self):
        mc = _make_mock_client()
        mc.get_issue_remote_link_by_id.return_value = _link(42, "https://x.com", "X")
        result, _ = _run_weblink(["--quiet", "delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0
        assert result.output.strip() == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: URL-based lookup logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestUrlLookup:
    def test_no_match_errors(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [
            _link(1, "https://other.com", "Other"),
        ]
        result, _ = _run_weblink(["delete", "TEST-1", "--url", "https://missing.com"], mc)
        assert result.exit_code == 1
        assert "No web link found" in result.output

    def test_multiple_matches_errors(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [
            _link(1, "https://dup.com", "Dup A"),
            _link(2, "https://dup.com", "Dup B"),
        ]
        result, _ = _run_weblink(["delete", "TEST-1", "--url", "https://dup.com"], mc)
        assert result.exit_code == 1
        assert "Multiple web links" in result.output
        assert "--id" in result.output

    def test_single_match_succeeds(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [
            _link(1, "https://other.com", "Other"),
            _link(5, "https://target.com", "Target"),
        ]
        mc.get_issue_remote_link_by_id.return_value = _link(5, "https://target.com", "Target")
        result, _ = _run_weblink(["delete", "TEST-1", "--url", "https://target.com"], mc)
        assert result.exit_code == 0, result.output
        mc.delete_issue_remote_link_by_id.assert_called_once_with("TEST-1", 5)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: issue get — issue links and web links output
# ═══════════════════════════════════════════════════════════════════════════════


def _make_issue(key="TEST-1", issue_links=None):
    """Build a minimal issue dict with optional links."""
    fields = {
        "summary": "Test issue",
        "status": {"name": "Open"},
        "issuelinks": issue_links or [],
    }
    return {"key": key, "fields": fields}


class TestIssueGetLinks:
    def test_outward_issue_link_arrow(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue(
            issue_links=[
                {
                    "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
                    "outwardIssue": {"key": "TEST-456", "fields": {"summary": "Blocked task"}},
                }
            ]
        )
        mc.get_issue_remote_links.return_value = []
        result, _ = _run_issue(["get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "ISSUE LINKS" in result.output
        assert "blocks" in result.output
        assert "\u2192" in result.output  # → arrow
        assert "TEST-456" in result.output

    def test_inward_issue_link_arrow(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue(
            issue_links=[
                {
                    "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
                    "inwardIssue": {"key": "TEST-789", "fields": {"summary": "Blocker"}},
                }
            ]
        )
        mc.get_issue_remote_links.return_value = []
        result, _ = _run_issue(["get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "is blocked by" in result.output
        assert "\u2190" in result.output  # ← arrow
        assert "TEST-789" in result.output

    def test_web_links_displayed(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        mc.get_issue_remote_links.return_value = [
            _link(10, docs_url := "https://docs.example.com", "Design Doc"),
            _link(20, "https://ci.example.com", "CI Build"),
        ]
        result, _ = _run_issue(["get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "WEB LINKS" in result.output
        assert "[10]" in result.output
        assert "Design Doc" in result.output
        assert docs_url in result.output
        assert "[20]" in result.output

    def test_empty_issue_links_not_shown(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue(issue_links=[])
        mc.get_issue_remote_links.return_value = []
        result, _ = _run_issue(["get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "ISSUE LINKS" not in result.output

    def test_empty_web_links_not_shown(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        mc.get_issue_remote_links.return_value = []
        result, _ = _run_issue(["get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "WEB LINKS" not in result.output

    def test_json_output_includes_web_links_key(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        links = [_link(10, "https://x.com", "X")]
        mc.get_issue_remote_links.return_value = links
        result, _ = _run_issue(["--json", "get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "webLinks" in data
        assert len(data["webLinks"]) == 1
        assert data["webLinks"][0]["id"] == 10

    def test_json_output_empty_web_links(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        mc.get_issue_remote_links.return_value = []
        result, _ = _run_issue(["--json", "get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["webLinks"] == []

    def test_quiet_does_not_fetch_web_links(self):
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        result, _ = _run_issue(["--quiet", "get", "TEST-1"], mc)
        assert result.exit_code == 0
        assert result.output.strip() == "TEST-1"
        mc.get_issue_remote_links.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: edge cases — missing fields in link dicts
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_link_missing_object(self):
        """A link dict with no 'object' key should not crash."""
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [{"id": 1}]
        result, _ = _run_weblink(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "[1]" in result.output

    def test_link_missing_title(self):
        mc = _make_mock_client()
        mc.get_issue_remote_links.return_value = [{"id": 3, "object": {"url": "https://no-title.com"}}]
        result, _ = _run_weblink(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "(untitled)" in result.output

    def test_add_result_not_dict(self):
        """API returning non-dict (e.g. string) should not crash."""
        mc = _make_mock_client()
        mc.create_or_update_issue_remote_links.return_value = "ok"
        result, _ = _run_weblink(["add", "TEST-1", "--url", "https://x.com", "--title", "X"], mc)
        assert result.exit_code == 0, result.output

    def test_web_link_fetch_failure_in_issue_get(self):
        """If web link fetch fails, issue get should still succeed (non-debug)."""
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        mc.get_issue_remote_links.side_effect = Exception("API error")
        result, _ = _run_issue(["get", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "WEB LINKS" not in result.output

    def test_fields_filter_suppresses_issue_links(self):
        """--fields summary should suppress the ISSUE LINKS section."""
        mc = _make_mock_client()
        issue = _make_issue(
            issue_links=[
                {
                    "type": {"name": "Blocks", "outward": "blocks"},
                    "outwardIssue": {"key": "TEST-2", "fields": {"summary": "Other"}},
                }
            ]
        )
        mc.issue.return_value = issue
        result, _ = _run_issue(["get", "TEST-1", "--fields", "summary"], mc)
        assert result.exit_code == 0, result.output
        assert "ISSUE LINKS" not in result.output
        assert "WEB LINKS" not in result.output
        mc.get_issue_remote_links.assert_not_called()

    def test_fields_weblinks_only(self):
        """--fields weblinks should fetch web links but not crash on missing fields."""
        mc = _make_mock_client()
        mc.issue.return_value = _make_issue()
        links = [_link(10, "https://x.com", "X")]
        mc.get_issue_remote_links.return_value = links
        result, _ = _run_issue(["get", "TEST-1", "--fields", "weblinks"], mc)
        assert result.exit_code == 0, result.output
        assert "WEB LINKS" in result.output
        mc.get_issue_remote_links.assert_called_once()

    def test_add_api_exception_shows_error(self):
        """API failure in add should exit 1 with error message."""
        mc = _make_mock_client()
        mc.create_or_update_issue_remote_links.side_effect = Exception("403 Forbidden")
        result, _ = _run_weblink(["add", "TEST-1", "--url", "https://x.com", "--title", "X"], mc)
        assert result.exit_code == 1
        assert "Failed to add web link" in result.output
