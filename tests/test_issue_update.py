"""Tests for jira-issue.py `update` read-after-write verification (#115).

Jira's PUT /issue/{key} silently ignores some issuetype/project changes on
Server/DC — it returns success while leaving the field untouched. The `update`
command must re-fetch those fields and fail loudly instead of reporting a
false-positive success.
"""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import click.testing

_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script(name: str = "jira-issue", subdir: str = "core"):
    path = _scripts_path / subdir / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_script()


def _make_mock_client(url: str = "https://jira.example.com"):
    mc = mock.Mock()
    mc.with_context = mock.Mock()
    mc.url = url
    return mc


def _run(args, mock_client=None):
    if mock_client is None:
        mock_client = _make_mock_client()
    runner = click.testing.CliRunner()
    with mock.patch.object(_mod, "LazyJiraClient", return_value=mock_client):
        result = runner.invoke(_mod.cli, args)
    return result, mock_client


def _issue(issuetype: dict | None = None, project: dict | None = None) -> dict:
    fields: dict = {}
    if issuetype is not None:
        fields["issuetype"] = issuetype
    if project is not None:
        fields["project"] = project
    return {"key": "FX-1095", "fields": fields}


class TestReferenceMismatch:
    """Unit tests for the comparison helper, independent of the CLI."""

    def test_matches_on_id(self):
        assert _mod._reference_mismatch({"id": "7"}, {"id": "7", "name": "Sub: Bug"}) is None

    def test_matches_on_name(self):
        assert _mod._reference_mismatch({"name": "Sub: Bug"}, {"id": "7", "name": "Sub: Bug"}) is None

    def test_mismatch_on_id_returns_labels(self):
        result = _mod._reference_mismatch({"id": "7"}, {"id": "5", "name": "Sub: Task"})
        assert result == ("7", "Sub: Task")

    def test_mismatch_on_name_returns_labels(self):
        result = _mod._reference_mismatch({"name": "Sub: Bug"}, {"id": "5", "name": "Sub: Task"})
        assert result == ("Sub: Bug", "Sub: Task")

    def test_unknown_shape_is_not_a_false_alarm(self):
        assert _mod._reference_mismatch("Bug", {"name": "Task"}) is None
        assert _mod._reference_mismatch({"id": "7"}, None) is None

    def test_missing_identifier_in_actual_skips_quietly(self):
        # requested by id, but the refreshed value only exposes name → no comparison
        assert _mod._reference_mismatch({"id": "7"}, {"name": "Sub: Bug"}) is None

    def test_project_key_matches_case_insensitively(self):
        # Jira canonicalizes project keys to uppercase; a lowercase request that
        # was applied correctly must not be reported as a mismatch.
        assert _mod._reference_mismatch({"key": "fx"}, {"id": "10000", "key": "FX"}) is None

    def test_issue_type_name_matches_case_insensitively(self):
        assert _mod._reference_mismatch({"name": "bug"}, {"id": "1", "name": "Bug"}) is None

    def test_id_is_compared_exactly(self):
        # ids are opaque — different ids are a genuine mismatch even if numeric-ish.
        assert _mod._reference_mismatch({"id": "7"}, {"id": "70", "name": "X"}) == ("7", "X")


class TestUpdateVerification:
    def test_silently_ignored_issuetype_change_fails(self):
        """The #115 scenario: 204 success but the type never changed."""
        mc = _make_mock_client()
        mc.issue.return_value = _issue(issuetype={"id": "1", "name": "Sub: Task"})
        result, _ = _run(["update", "FX-1095", "--fields-json", '{"issuetype":{"id":"7"}}'], mc)
        assert result.exit_code == 1, result.output
        assert "issuetype change was not applied" in result.output
        assert "jira-move issue" in result.output
        # It re-fetched to verify.
        mc.issue.assert_called_once()
        assert "issuetype" in mc.issue.call_args.kwargs.get("fields", "")

    def test_applied_issuetype_change_succeeds(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue(issuetype={"id": "7", "name": "Sub: Bug"})
        result, _ = _run(["update", "FX-1095", "--fields-json", '{"issuetype":{"id":"7"}}'], mc)
        assert result.exit_code == 0, result.output
        assert "Updated FX-1095" in result.output

    def test_silently_ignored_project_change_fails(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue(project={"id": "10000", "key": "FX"})
        result, _ = _run(["update", "FX-1095", "--fields-json", '{"project":{"key":"OTHER"}}'], mc)
        assert result.exit_code == 1, result.output
        assert "project change was not applied" in result.output
        assert "Move action" in result.output

    def test_non_verified_field_skips_readback(self):
        """Updating only summary must NOT trigger a verification re-fetch."""
        mc = _make_mock_client()
        result, _ = _run(["update", "FX-1095", "--summary", "New title"], mc)
        assert result.exit_code == 0, result.output
        assert "Updated FX-1095" in result.output
        mc.issue.assert_not_called()

    def test_json_output_on_verified_change(self):
        mc = _make_mock_client()
        mc.issue.return_value = _issue(issuetype={"id": "7", "name": "Sub: Bug"})
        result, _ = _run(["--json", "update", "FX-1095", "--fields-json", '{"issuetype":{"id":"7"}}'], mc)
        assert result.exit_code == 0, result.output
        assert '"issuetype"' in result.output
