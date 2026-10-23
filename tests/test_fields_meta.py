# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for ``jira-fields.py meta``: create and edit screen metadata."""

import json

from conftest import load_script, make_mock_client, run_cli

_fields_mod = load_script("jira-fields", "utility")

_TYPES = {"issueTypes": [{"id": "11002", "name": "Domain"}, {"id": "3", "name": "Task"}]}

_SUMMARY = {"fieldId": "summary", "name": "Summary", "required": True, "schema": {"type": "string"}}
_RESPONSIBLE = {"fieldId": "customfield_12608", "name": "Responsible", "required": False, "schema": {"type": "user"}}
_PRIORITY = {
    "fieldId": "priority",
    "name": "Priority",
    "required": False,
    "schema": {"type": "priority"},
    "allowedValues": [{"name": n} for n in ["Blocker", "Critical", "Major", "Minor", "Trivial", "Low"]],
}


def _client_with_pages(*pages):
    mc = make_mock_client()
    mc.project.return_value = _TYPES
    mc.get.side_effect = list(pages)
    return mc


def test_create_meta_resolves_type_by_name_and_follows_pagination():
    mc = _client_with_pages(
        {"startAt": 0, "total": 3, "isLast": False, "values": [_SUMMARY, _PRIORITY]},
        {"startAt": 2, "total": 3, "isLast": True, "values": [_RESPONSIBLE]},
    )
    result, mc = run_cli(_fields_mod, ["--quiet", "meta", "PROJ", "domain"], mc)
    assert result.exit_code == 0, result.output
    assert result.output.split() == ["summary", "priority", "customfield_12608"]
    first, second = mc.get.call_args_list
    assert first.args[0] == "rest/api/2/issue/createmeta/PROJ/issuetypes/11002"
    assert second.kwargs["params"]["startAt"] == 2


def test_create_meta_accepts_type_id_and_cloud_fields_key():
    mc = _client_with_pages({"startAt": 0, "total": 1, "fields": [_RESPONSIBLE]})
    result, mc = run_cli(_fields_mod, ["--json", "meta", "PROJ", "3"], mc)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)[0]["fieldId"] == "customfield_12608"
    assert mc.get.call_args.args[0].endswith("/issuetypes/3")


def test_create_meta_pages_by_total_when_cloud_sends_no_is_last():
    mc = _client_with_pages(
        {"startAt": 0, "total": 2, "fields": [_SUMMARY]},
        {"startAt": 1, "total": 2, "fields": [_RESPONSIBLE]},
    )
    result, mc = run_cli(_fields_mod, ["--quiet", "meta", "PROJ", "Task"], mc)
    assert result.exit_code == 0, result.output
    assert result.output.split() == ["summary", "customfield_12608"]
    assert mc.get.call_count == 2


def test_table_lists_required_first_and_truncates_allowed_values():
    mc = _client_with_pages({"startAt": 0, "total": 3, "isLast": True, "values": [_RESPONSIBLE, _PRIORITY, _SUMMARY]})
    result, _ = run_cli(_fields_mod, ["meta", "PROJ", "Domain"], mc)
    assert result.exit_code == 0, result.output
    rows = [line for line in result.output.splitlines() if "|" in line][1:]
    assert rows[0].startswith("summary")
    assert "Blocker, Critical, Major, Minor, Trivial (+1)" in result.output


def test_edit_meta_reads_issue_editmeta():
    mc = make_mock_client()
    mc.get.return_value = {"fields": {"summary": {"name": "Summary", "required": True}}}
    result, mc = run_cli(_fields_mod, ["--quiet", "meta", "--edit", "PROJ-41"], mc)
    assert result.exit_code == 0, result.output
    assert result.output.split() == ["summary"]
    mc.get.assert_called_once_with("rest/api/2/issue/PROJ-41/editmeta")
    mc.project.assert_not_called()


def test_unknown_issue_type_lists_available_types():
    mc = _client_with_pages()
    result, mc = run_cli(_fields_mod, ["meta", "PROJ", "Nope"], mc)
    assert result.exit_code == 1
    assert "Available: Domain, Task" in result.output
    mc.get.assert_not_called()


def test_missing_arguments_without_edit_exits_2():
    result, _ = run_cli(_fields_mod, ["meta", "PROJ"])
    assert result.exit_code == 2
