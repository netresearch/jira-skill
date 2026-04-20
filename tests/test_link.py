"""Tests for jira-link.py list + delete subcommands."""

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


_link_mod = _load_script("jira-link", "utility")


def _make_mock_client():
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    return mc


def _run_link(args, mock_client=None):
    """Run jira-link CLI with a mocked LazyJiraClient."""
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_link_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_link_mod.cli, args)
    return result, mock_client


def _issue_link(link_id="10042", type_name="Blocks", direction="outward", other_key="TEST-2", other_summary="Other"):
    """Build an issue link dict matching the Jira REST API shape.

    direction: 'outward' or 'inward'
    """
    type_obj = {
        "name": type_name,
        "outward": type_name.lower().rstrip("s") + "s" if type_name else "",
        "inward": "is " + (type_name.lower().rstrip("s") + "ed by") if type_name else "",
    }
    # Use canonical labels for Blocks so tests match reality
    if type_name == "Blocks":
        type_obj = {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"}
    elif type_name == "Relates":
        type_obj = {"name": "Relates", "outward": "relates to", "inward": "is related to"}

    other = {
        "key": other_key,
        "fields": {"summary": other_summary, "status": {"name": "Open"}},
    }
    link = {"id": str(link_id), "type": type_obj}
    if direction == "outward":
        link["outwardIssue"] = other
    else:
        link["inwardIssue"] = other
    return link


def _issue_with_links(key="TEST-1", links=None):
    return {"key": key, "fields": {"issuelinks": links or []}}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: help smoke
# ═══════════════════════════════════════════════════════════════════════════════


class TestLinkHelp:
    """Subcommands must respond to --help with exit code 0."""

    @pytest.mark.parametrize("subcmd", ["create", "list", "list-types", "delete"])
    def test_subcommand_help(self, subcmd):
        runner = click.testing.CliRunner()
        result = runner.invoke(_link_mod.cli, [subcmd, "--help"])
        assert result.exit_code == 0, result.output

    def test_list_help_shows_issue_key_arg(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_link_mod.cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "ISSUE_KEY" in result.output

    def test_delete_help_shows_id_and_to(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(_link_mod.cli, ["delete", "--help"])
        assert result.exit_code == 0
        assert "--id" in result.output
        assert "--to" in result.output
        assert "--type" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: list subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestLinkList:
    def test_list_text_output(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [
                _issue_link("101", "Blocks", "outward", "TEST-2", "Blocked task"),
                _issue_link("102", "Relates", "inward", "TEST-3", "Related"),
            ],
        )
        result, _ = _run_link(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "101" in result.output
        assert "Blocks" in result.output
        assert "TEST-2" in result.output
        assert "102" in result.output
        assert "TEST-3" in result.output

    def test_list_json_output(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [_issue_link("101", "Blocks", "outward", "TEST-2", "Blocked task")],
        )
        result, _ = _run_link(["--json", "list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "101"
        assert data[0]["type"] == "Blocks"
        assert data[0]["direction"] == "outward"
        assert data[0]["other_key"] == "TEST-2"

    def test_list_empty(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links("TEST-1", [])
        result, _ = _run_link(["list", "TEST-1"], mc)
        assert result.exit_code == 0, result.output
        assert "No issue links" in result.output

    def test_list_quiet(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [_issue_link("55", "Blocks", "outward", "TEST-2", "X")],
        )
        result, _ = _run_link(["--quiet", "list", "TEST-1"], mc)
        assert result.exit_code == 0
        assert "55" in result.output
        assert "Blocks" in result.output
        assert "TEST-2" in result.output

    def test_list_api_exception_shows_error(self):
        mc = _make_mock_client()
        mc.issue.side_effect = Exception("500 Server Error")
        result, _ = _run_link(["list", "TEST-1"], mc)
        assert result.exit_code == 1
        assert "Failed to list issue links" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: delete subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestLinkDelete:
    def test_delete_by_id(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _issue_link("42", "Blocks", "outward", "TEST-2", "Blocked")
        result, _ = _run_link(["delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        assert "Deleted link" in result.output
        mc.remove_issue_link.assert_called_once_with("42")

    def test_delete_by_to_and_type(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [
                _issue_link("7", "Blocks", "outward", "TEST-2", "B"),
                _issue_link("8", "Relates", "outward", "TEST-9", "R"),
            ],
        )
        result, _ = _run_link(
            ["delete", "TEST-1", "--to", "TEST-2", "--type", "Blocks"],
            mc,
        )
        assert result.exit_code == 0, result.output
        mc.remove_issue_link.assert_called_once_with("7")

    def test_delete_dry_run(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _issue_link("42", "Blocks", "outward", "TEST-2", "X")
        result, _ = _run_link(["delete", "TEST-1", "--id", "42", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would delete" in result.output
        mc.remove_issue_link.assert_not_called()

    def test_delete_missing_all_identifiers(self):
        result, _ = _run_link(["delete", "TEST-1"])
        assert result.exit_code == 1
        assert "--id" in result.output or "--to" in result.output

    def test_delete_conflicting_identifiers(self):
        result, _ = _run_link(
            ["delete", "TEST-1", "--id", "42", "--to", "TEST-2", "--type", "Blocks"],
        )
        assert result.exit_code == 1
        assert "OR" in result.output or "not both" in result.output

    def test_delete_to_without_type(self):
        result, _ = _run_link(["delete", "TEST-1", "--to", "TEST-2"])
        assert result.exit_code == 1

    def test_delete_type_without_to(self):
        result, _ = _run_link(["delete", "TEST-1", "--type", "Blocks"])
        assert result.exit_code == 1

    def test_delete_to_type_no_match(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [_issue_link("7", "Relates", "outward", "TEST-9", "R")],
        )
        result, _ = _run_link(
            ["delete", "TEST-1", "--to", "TEST-2", "--type", "Blocks"],
            mc,
        )
        assert result.exit_code == 1
        assert "No" in result.output

    def test_delete_to_type_multiple_matches(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [
                _issue_link("7", "Blocks", "outward", "TEST-2", "A"),
                _issue_link("8", "Blocks", "outward", "TEST-2", "B"),
            ],
        )
        result, _ = _run_link(
            ["delete", "TEST-1", "--to", "TEST-2", "--type", "Blocks"],
            mc,
        )
        assert result.exit_code == 1
        assert "Multiple" in result.output
        assert "7" in result.output
        assert "8" in result.output
        mc.remove_issue_link.assert_not_called()

    def test_delete_json_output(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _issue_link("42", "Blocks", "outward", "TEST-2", "X")
        result, _ = _run_link(["--json", "delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["deleted"] is True
        assert data["id"] == "42"
        assert data["key"] == "TEST-1"

    def test_delete_quiet_output(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _issue_link("42", "Blocks", "outward", "TEST-2", "X")
        result, _ = _run_link(["--quiet", "delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0
        assert result.output.strip() == "ok"

    def test_delete_api_exception_shows_error(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _issue_link("42", "Blocks", "outward", "TEST-2", "X")
        mc.remove_issue_link.side_effect = Exception("403 Forbidden")
        result, _ = _run_link(["delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 1
        assert "Failed to delete issue link" in result.output
