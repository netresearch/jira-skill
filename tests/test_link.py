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

    @pytest.mark.parametrize(
        "subcmd", ["create", "list", "list-types", "delete", "bulk-create", "bulk-delete", "invert"]
    )
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
        # get_issue_link returns a global link view with BOTH endpoints.
        # issue_key matches outwardIssue.key so verbiage comes from the
        # outward label.
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "TEST-1", "fields": {"summary": "Src", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "TEST-2", "fields": {"summary": "Blocked", "status": {"name": "Open"}}},
        }
        result, _ = _run_link(["delete", "TEST-2", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        assert "Deleted link" in result.output
        # issue_key=TEST-2 matches outwardIssue, so display uses outward verbiage
        assert "blocks" in result.output
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
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "TEST-1", "fields": {"summary": "X", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "TEST-2", "fields": {"summary": "Y", "status": {"name": "Open"}}},
        }
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
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "TEST-1", "fields": {"summary": "X", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "TEST-2", "fields": {"summary": "Y", "status": {"name": "Open"}}},
        }
        result, _ = _run_link(["--json", "delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["deleted"] is True
        assert data["id"] == "42"
        assert data["key"] == "TEST-1"

    def test_delete_quiet_output(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "TEST-1", "fields": {"summary": "X", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "TEST-2", "fields": {"summary": "Y", "status": {"name": "Open"}}},
        }
        result, _ = _run_link(["--quiet", "delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 0
        assert result.output.strip() == "ok"

    def test_delete_api_exception_shows_error(self):
        mc = _make_mock_client()
        # Link has TEST-1 as inward so delete against TEST-1 resolves correctly.
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "TEST-1", "fields": {"summary": "X", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "TEST-2", "fields": {"summary": "Y", "status": {"name": "Open"}}},
        }
        mc.remove_issue_link.side_effect = Exception("403 Forbidden")
        result, _ = _run_link(["delete", "TEST-1", "--id", "42"], mc)
        assert result.exit_code == 1
        assert "Failed to delete issue link" in result.output

    def test_delete_by_id_wrong_issue_key(self):
        """Reject delete when the link id is not associated with issue_key."""
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "OTHER-A", "fields": {"summary": "A", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "OTHER-B", "fields": {"summary": "B", "status": {"name": "Open"}}},
        }
        result, _ = _run_link(["delete", "UNRELATED-1", "--id", "42"], mc)
        assert result.exit_code == 1
        assert "not associated" in result.output
        mc.remove_issue_link.assert_not_called()

    def test_delete_by_id_context_chooses_inward_direction(self):
        """When issue_key is the inward side, verbiage uses the inward label."""
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "PROJ-B", "fields": {"summary": "B", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "PROJ-A", "fields": {"summary": "A", "status": {"name": "Open"}}},
        }
        result, _ = _run_link(["delete", "PROJ-B", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        assert "is blocked by PROJ-A" in result.output
        assert "blocks PROJ-A" not in result.output

    def test_delete_by_to_lowercase(self):
        """--to PROJ-2 should match even when Jira returns TEST-2 (case-insensitive)."""
        mc = _make_mock_client()
        mc.issue.return_value = _issue_with_links(
            "TEST-1",
            [_issue_link("7", "Blocks", "outward", "TEST-2", "X")],
        )
        result, _ = _run_link(
            ["delete", "TEST-1", "--to", "test-2", "--type", "blocks"],
            mc,
        )
        assert result.exit_code == 0, result.output
        mc.remove_issue_link.assert_called_once_with("7")

    def test_delete_by_id_context_key_case_insensitive(self):
        """Display direction must remain correct when ISSUE_KEY case differs from Jira's canonical case.

        Regression: without casefold the context match fell through to the
        generic outward branch and displayed "blocks PROJ-A" even when the
        user's issue was on the outward side (correct: "blocks PROJ-B").
        """
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "42",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "inwardIssue": {"key": "PROJ-B", "fields": {"summary": "B", "status": {"name": "Open"}}},
            "outwardIssue": {"key": "PROJ-A", "fields": {"summary": "A", "status": {"name": "Open"}}},
        }
        result, _ = _run_link(["delete", "proj-a", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        # proj-a matches outward (PROJ-A), so display should use outward verb + inward key
        assert "blocks PROJ-B" in result.output
        assert "is blocked by" not in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: create subcommand (success message direction, --source/--target, dry-run)
# ═══════════════════════════════════════════════════════════════════════════════


_LINK_TYPES = [
    {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
    {"name": "Cause", "outward": "causes", "inward": "is caused by"},
    {"name": "Side effect", "outward": "affects", "inward": "is affected by"},
]


def _client_with_link_types():
    mc = _make_mock_client()
    mc.get_issue_link_types.return_value = _LINK_TYPES
    mc.create_issue_link.return_value = None
    return mc


class TestLinkCreate:
    def test_create_success_uses_outward_sentence(self):
        """create FROM TO --type Cause prints 'TO causes FROM'."""
        mc = _client_with_link_types()
        result, _ = _run_link(["create", "EFFECT-1", "ROOT-2", "--type", "Cause"], mc)
        assert result.exit_code == 0, result.output
        assert "Created: ROOT-2 causes EFFECT-1" in result.output
        assert "link-type: Cause" in result.output
        # Must NOT use the legacy misleading arrow
        assert "-->" not in result.output
        # Verify the API payload preserves the outward/inward direction.
        mc.create_issue_link.assert_called_once_with(
            {
                "type": {"name": "Cause"},
                "inwardIssue": {"key": "ROOT-2"},
                "outwardIssue": {"key": "EFFECT-1"},
            }
        )

    def test_create_dry_run_prints_sentence(self):
        mc = _client_with_link_types()
        result, _ = _run_link(["create", "FRONTEND-12", "INFRA-99", "--type", "Blocks", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would create: INFRA-99 blocks FRONTEND-12" in result.output
        mc.create_issue_link.assert_not_called()

    def test_create_dry_run_unknown_type_errors(self):
        mc = _client_with_link_types()
        result, _ = _run_link(["create", "A-1", "B-2", "--type", "Bogus", "--dry-run"], mc)
        assert result.exit_code == 1
        assert "Unknown link type" in result.output
        mc.create_issue_link.assert_not_called()

    def test_create_named_aliases_equivalent_to_swapped_positional(self):
        """--source S --target T must POST {outward: T, inward: S}."""
        mc = _client_with_link_types()
        result, _ = _run_link(
            ["create", "--source", "INFRA-99", "--target", "FRONTEND-12", "--type", "Blocks"],
            mc,
        )
        assert result.exit_code == 0, result.output
        assert "Created: INFRA-99 blocks FRONTEND-12" in result.output
        mc.create_issue_link.assert_called_once_with(
            {
                "type": {"name": "Blocks"},
                "inwardIssue": {"key": "INFRA-99"},
                "outwardIssue": {"key": "FRONTEND-12"},
            }
        )

    def test_create_rejects_mixed_positional_and_named(self):
        mc = _client_with_link_types()
        result, _ = _run_link(
            [
                "create",
                "EFFECT-1",
                "ROOT-2",
                "--source",
                "X",
                "--target",
                "Y",
                "--type",
                "Cause",
            ],
            mc,
        )
        assert result.exit_code == 1
        assert "not both" in result.output or "either" in result.output

    def test_create_named_requires_both_source_and_target(self):
        mc = _client_with_link_types()
        result, _ = _run_link(["create", "--source", "ONLY-1", "--type", "Cause"], mc)
        assert result.exit_code == 1
        assert "--source" in result.output and "--target" in result.output

    def test_create_case_insensitive_type_matches_canonical_name(self):
        """User passes --type 'cause'; script normalizes to 'Cause' for the API."""
        mc = _client_with_link_types()
        result, _ = _run_link(["create", "EFFECT-1", "ROOT-2", "--type", "cause"], mc)
        assert result.exit_code == 0, result.output
        mc.create_issue_link.assert_called_once()
        payload = mc.create_issue_link.call_args[0][0]
        assert payload["type"]["name"] == "Cause"

    def test_create_json_output_includes_sentence(self):
        mc = _client_with_link_types()
        result, _ = _run_link(["--json", "create", "EFFECT-1", "ROOT-2", "--type", "Cause"], mc)
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["created"] is True
        assert data["sentence"] == "ROOT-2 causes EFFECT-1"
        assert data["source"] == "ROOT-2"
        assert data["target"] == "EFFECT-1"
        assert data["outward"] == "causes"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: bulk-create subcommand
# ═══════════════════════════════════════════════════════════════════════════════


def _write_csv(tmp_path, content: str):
    """Helper: write a CSV string to tmp_path/'links.csv' and return the path."""
    p = tmp_path / "links.csv"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _bulk_client():
    """Mock client preloaded with link types covering every type used in bulk tests."""
    mc = _make_mock_client()
    mc.get_issue_link_types.return_value = [
        {"name": "Cause", "outward": "causes", "inward": "is caused by"},
        {"name": "Deploy", "outward": "deploys", "inward": "is deployed by"},
        {"name": "Side effect", "outward": "affects", "inward": "is affected by"},
        {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
    ]
    mc.create_issue_link.return_value = None
    # No existing links by default
    mc.issue.return_value = _issue_with_links("DEFAULT-1", [])
    return mc


class TestBulkCreate:
    def test_happy_path_three_rows_three_types(self, tmp_path):
        csv_text = "from,to,type\nIOS-18,NRS-878,Cause\nIOS-18,NRT-4388,Deploy\nIOS-18,NRS-3106,Side effect\n"
        csv_path = _write_csv(tmp_path, csv_text)
        mc = _bulk_client()

        result, _ = _run_link(["bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 0, result.output
        assert "[1/3] NRS-878 causes IOS-18 (link-type: Cause)" in result.output
        assert "[2/3] NRT-4388 deploys IOS-18 (link-type: Deploy)" in result.output
        assert "[3/3] NRS-3106 affects IOS-18 (link-type: Side effect)" in result.output
        assert "created: 3, skipped: 0, failed: 0" in result.output
        assert mc.create_issue_link.call_count == 3
        # Verify direction of the first call: TO is the inward side, FROM is outward.
        first_call = mc.create_issue_link.call_args_list[0][0][0]
        assert first_call == {
            "type": {"name": "Cause"},
            "inwardIssue": {"key": "NRS-878"},
            "outwardIssue": {"key": "IOS-18"},
        }
        # get_issue_link_types should be called exactly once (cache).
        assert mc.get_issue_link_types.call_count == 1

    def test_dry_run_does_not_call_api(self, tmp_path):
        csv_path = _write_csv(tmp_path, "from,to,type\nA-1,B-2,Blocks\n")
        mc = _bulk_client()
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path, "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "[1/1] Would create: B-2 blocks A-1 (link-type: Blocks)" in result.output
        mc.create_issue_link.assert_not_called()

    def test_csv_header_is_case_and_whitespace_insensitive(self, tmp_path):
        # Mixed case + spaces in header — must still extract correctly
        csv_path = _write_csv(tmp_path, " From, TO ,Type\nIOS-18,NRS-878,cause\n")
        mc = _bulk_client()
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 0, result.output
        assert "[1/1] NRS-878 causes IOS-18" in result.output
        first_call = mc.create_issue_link.call_args_list[0][0][0]
        assert first_call == {
            "type": {"name": "Cause"},
            "inwardIssue": {"key": "NRS-878"},
            "outwardIssue": {"key": "IOS-18"},
        }

    def test_skip_existing_caches_per_from_key(self, tmp_path):
        # Three rows all share the same FROM — `client.issue()` should be
        # called exactly once, not three times. (Regression: N+1 fix)
        csv_path = _write_csv(
            tmp_path,
            "from,to,type\nIOS-18,NRS-1,Cause\nIOS-18,NRS-2,Cause\nIOS-18,NRS-3,Cause\n",
        )
        mc = _bulk_client()

        def issue_side_effect(key, fields=None):
            return _issue_with_links(key, [])

        mc.issue.side_effect = issue_side_effect
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path, "--skip-existing"], mc)
        assert result.exit_code == 0, result.output
        assert mc.issue.call_count == 1, f"expected 1 fetch (cached), got {mc.issue.call_count}"
        assert mc.create_issue_link.call_count == 3

    def test_skip_existing_skips_matching_link(self, tmp_path):
        csv_path = _write_csv(tmp_path, "from,to,type\nIOS-18,NRS-878,Cause\nIOS-18,NRS-879,Cause\n")
        mc = _bulk_client()
        # First row's FROM (IOS-18) already has a Cause link to NRS-878 → skip.
        # Second row's FROM (IOS-18) has no Cause link to NRS-879 → create.
        # Mock issue() per row by inspecting the fields-fetch.
        existing_link = _issue_link("999", "Cause", "outward", "NRS-878", "Existing")

        def issue_side_effect(key, fields=None):
            return _issue_with_links(key, [existing_link])

        mc.issue.side_effect = issue_side_effect
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path, "--skip-existing"], mc)
        assert result.exit_code == 0, result.output
        assert "[1/2] SKIP existing: IOS-18 ↔ NRS-878 (Cause)" in result.output
        assert "[2/2] NRS-879 causes IOS-18" in result.output
        assert "created: 1, skipped: 1, failed: 0" in result.output
        # Only ONE create call (row 2), since row 1 was skipped.
        assert mc.create_issue_link.call_count == 1

    def test_abort_on_error_halts_on_row_2(self, tmp_path):
        csv_text = "from,to,type\nA-1,B-2,Cause\nA-1,B-3,Cause\nA-1,B-4,Cause\n"
        csv_path = _write_csv(tmp_path, csv_text)
        mc = _bulk_client()
        # First call succeeds, second raises — abort default → no third call.
        mc.create_issue_link.side_effect = [None, Exception("500 Server Error"), None]
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 1
        assert "[1/3] B-2 causes A-1" in result.output
        assert "[2/3] FAIL" in result.output
        assert "[3/3]" not in result.output
        assert mc.create_issue_link.call_count == 2
        assert "created: 1, skipped: 0, failed: 1" in result.output

    def test_continue_on_error_records_failures_and_continues(self, tmp_path):
        csv_text = "from,to,type\nA-1,B-2,Cause\nA-1,B-3,Cause\nA-1,B-4,Cause\n"
        csv_path = _write_csv(tmp_path, csv_text)
        mc = _bulk_client()
        mc.create_issue_link.side_effect = [None, Exception("500 Server Error"), None]
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path, "--continue-on-error"], mc)
        # continue-on-error means we keep going AND exit 0 even with failures
        # (per spec: it "logs and keeps going").
        assert result.exit_code == 0, result.output
        assert mc.create_issue_link.call_count == 3
        assert "created: 2, skipped: 0, failed: 1" in result.output

    def test_empty_csv_exits_zero(self, tmp_path):
        csv_path = _write_csv(tmp_path, "")
        mc = _bulk_client()
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 0, result.output
        assert "created: 0" in result.output

    def test_malformed_csv_missing_column_exits_2(self, tmp_path):
        csv_path = _write_csv(tmp_path, "from,to\nA-1,B-2\n")
        mc = _bulk_client()
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 2
        assert "type" in result.output

    def test_unknown_link_type_emits_failure(self, tmp_path):
        csv_path = _write_csv(tmp_path, "from,to,type\nA-1,B-2,Bogus\n")
        mc = _bulk_client()
        # Default = abort; one bad row → exit 1.
        result, _ = _run_link(["bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 1
        assert "Unknown link type" in result.output
        mc.create_issue_link.assert_not_called()

    def test_json_emits_jsonl_with_summary(self, tmp_path):
        csv_path = _write_csv(tmp_path, "from,to,type\nA-1,B-2,Cause\n")
        mc = _bulk_client()
        result, _ = _run_link(["--json", "bulk-create", "--from-csv", csv_path], mc)
        assert result.exit_code == 0, result.output
        lines = [ln for ln in result.output.splitlines() if ln.strip()]
        assert len(lines) == 2
        row = json.loads(lines[0])
        summary = json.loads(lines[1])
        assert row["status"] == "created"
        assert row["sentence"] == "B-2 causes A-1"
        assert summary == {"summary": True, "created": 1, "skipped": 0, "failed": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: bulk-delete subcommand
# ═══════════════════════════════════════════════════════════════════════════════


class TestBulkDelete:
    def test_happy_path_by_ids(self):
        mc = _make_mock_client()
        mc.get_issue_link.side_effect = [
            {
                "id": "101",
                "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
                "outwardIssue": {"key": "TEST-2"},
                "inwardIssue": {"key": "TEST-1"},
            },
            {
                "id": "102",
                "type": {"name": "Cause", "outward": "causes", "inward": "is caused by"},
                "outwardIssue": {"key": "ROOT-2"},
                "inwardIssue": {"key": "EFFECT-1"},
            },
        ]
        mc.remove_issue_link.return_value = None
        result, _ = _run_link(["bulk-delete", "--ids", "101,102"], mc)
        assert result.exit_code == 0, result.output
        assert "[1/2] Deleted [101] TEST-2 ↔ TEST-1 (Blocks)" in result.output
        assert "[2/2] Deleted [102] ROOT-2 ↔ EFFECT-1 (Cause)" in result.output
        assert "deleted: 2, failed: 0" in result.output
        assert mc.remove_issue_link.call_count == 2
        mc.remove_issue_link.assert_any_call("101")
        mc.remove_issue_link.assert_any_call("102")

    def test_requires_exactly_one_of_ids_or_ids_file(self):
        result, _ = _run_link(["bulk-delete"])
        assert result.exit_code == 1
        assert "--ids" in result.output

    def test_empty_ids_file_emits_delete_summary_not_create(self, tmp_path):
        # Regression: empty input previously fell through to the bulk-create
        # summary emitter, printing 'created/skipped/failed' instead of
        # 'deleted/failed'. Schema must stay consistent across all bulk-delete
        # invocations.
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        result, _ = _run_link(["bulk-delete", "--ids-file", str(empty)])
        assert result.exit_code == 0, result.output
        assert "deleted: 0, failed: 0" in result.output
        assert "created" not in result.output
        assert "skipped" not in result.output

    def test_rejects_both_ids_and_ids_file(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("101\n", encoding="utf-8")
        result, _ = _run_link(["bulk-delete", "--ids", "1", "--ids-file", str(f)])
        assert result.exit_code == 1

    def test_dry_run_does_not_call_remove(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "101",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "outwardIssue": {"key": "TEST-2"},
            "inwardIssue": {"key": "TEST-1"},
        }
        result, _ = _run_link(["bulk-delete", "--ids", "101", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "Would delete [101]" in result.output
        mc.remove_issue_link.assert_not_called()

    def test_ids_file_reads_one_per_line(self, tmp_path):
        f = tmp_path / "ids.txt"
        f.write_text("101\n102\n\n", encoding="utf-8")
        mc = _make_mock_client()
        mc.get_issue_link.return_value = {
            "id": "?",
            "type": {"name": "Blocks", "outward": "blocks", "inward": "is blocked by"},
            "outwardIssue": {"key": "X"},
            "inwardIssue": {"key": "Y"},
        }
        mc.remove_issue_link.return_value = None
        result, _ = _run_link(["bulk-delete", "--ids-file", str(f)], mc)
        assert result.exit_code == 0, result.output
        assert "deleted: 2, failed: 0" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: invert subcommand
# ═══════════════════════════════════════════════════════════════════════════════


def _link_for_invert():
    """Sample link: 'EFFECT-1 causes ROOT-2' (inward=EFFECT-1, outward=ROOT-2)."""
    return {
        "id": "42",
        "type": {"name": "Cause", "outward": "causes", "inward": "is caused by"},
        "inwardIssue": {"key": "EFFECT-1"},
        "outwardIssue": {"key": "ROOT-2"},
    }


class TestInvert:
    def test_dry_run_shows_both_sentences(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _link_for_invert()
        result, _ = _run_link(["invert", "--id", "42", "--dry-run"], mc)
        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Would invert: EFFECT-1 causes ROOT-2 → ROOT-2 causes EFFECT-1" in result.output
        mc.remove_issue_link.assert_not_called()
        mc.create_issue_link.assert_not_called()

    def test_happy_path_deletes_then_creates_swapped(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _link_for_invert()
        mc.remove_issue_link.return_value = None
        mc.create_issue_link.return_value = None

        result, _ = _run_link(["invert", "--id", "42"], mc)
        assert result.exit_code == 0, result.output
        assert "Inverted: EFFECT-1 causes ROOT-2 → ROOT-2 causes EFFECT-1" in result.output
        mc.remove_issue_link.assert_called_once_with("42")
        mc.create_issue_link.assert_called_once_with(
            {
                "type": {"name": "Cause"},
                "inwardIssue": {"key": "ROOT-2"},
                "outwardIssue": {"key": "EFFECT-1"},
            }
        )

    def test_rollback_when_invert_create_fails(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _link_for_invert()
        mc.remove_issue_link.return_value = None
        # First create (inverted) raises; second create (rollback) succeeds.
        mc.create_issue_link.side_effect = [Exception("400 invalid"), None]
        result, _ = _run_link(["invert", "--id", "42"], mc)
        assert result.exit_code == 1
        assert "original link restored" in result.output
        # Both creates were attempted: the inverted, then the rollback.
        assert mc.create_issue_link.call_count == 2
        # Rollback payload matches the original direction.
        rollback_call = mc.create_issue_link.call_args_list[1][0][0]
        assert rollback_call == {
            "type": {"name": "Cause"},
            "inwardIssue": {"key": "EFFECT-1"},
            "outwardIssue": {"key": "ROOT-2"},
        }

    def test_inconsistent_state_when_rollback_also_fails(self):
        mc = _make_mock_client()
        mc.get_issue_link.return_value = _link_for_invert()
        mc.remove_issue_link.return_value = None
        mc.create_issue_link.side_effect = [Exception("first boom"), Exception("rollback boom")]
        result, _ = _run_link(["invert", "--id", "42"], mc)
        assert result.exit_code == 1
        assert "INCONSISTENT STATE" in result.output
        assert "42" in result.output
        # Both directions referenced in the error so the human can fix it.
        assert "EFFECT-1 causes ROOT-2" in result.output
        assert "ROOT-2 causes EFFECT-1" in result.output
