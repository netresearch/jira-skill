"""Tests for jira-issue.py `_print_issue` comment/parent/subtasks rendering (#127).

The default human-readable formatter used to ignore `-f comment` (and
`parent`/`subtasks`) silently: no output, no error, no "0 comments" notice. An
empty result then reads as "this issue has no comments" when it has many. These
tests pin the fix: an always-on comment count, parent/subtask metadata, and a
safety net so an explicitly requested field never renders nothing.
"""

from conftest import load_script

_mod = load_script("jira-issue", "core")


def _issue(fields: dict) -> dict:
    return {"key": "FX-1", "fields": fields}


def test_comment_count_and_pointer_when_requested(capsys):
    """`-f ...,comment` surfaces the count plus a pointer instead of nothing."""
    _mod._print_issue(
        _issue({"summary": "S", "comment": {"total": 9, "comments": []}}),
        requested_fields={"summary", "comment"},
    )
    out = capsys.readouterr().out
    assert "Comments: 9" in out
    assert "jira-issue.py work FX-1" in out
    assert "jira-comment.py list FX-1" in out


def test_comment_count_shown_on_default_view(capsys):
    """A default `get` (no field filter) always surfaces the comment count."""
    _mod._print_issue(_issue({"summary": "S", "comment": {"total": 3, "comments": []}}))
    out = capsys.readouterr().out
    assert "Comments: 3" in out


def test_zero_comments_renders_explicit_zero(capsys):
    """Zero comments is stated explicitly, never left blank."""
    _mod._print_issue(
        _issue({"summary": "S", "comment": {"total": 0, "comments": []}}),
        requested_fields={"summary", "comment"},
    )
    out = capsys.readouterr().out
    assert "Comments: 0" in out


def test_comment_total_falls_back_to_array_length(capsys):
    """When `total` is absent, the rendered count falls back to the array length."""
    _mod._print_issue(
        _issue({"summary": "S", "comment": {"comments": [{"id": "1"}, {"id": "2"}]}}),
        requested_fields={"comment"},
    )
    out = capsys.readouterr().out
    assert "Comments: 2" in out


def test_comment_total_explicit_null_falls_back_to_array_length(capsys):
    """An explicit `total: null` must not leak through; fall back to the array length."""
    _mod._print_issue(
        _issue({"summary": "S", "comment": {"total": None, "comments": [{"id": "1"}]}}),
        requested_fields={"comment"},
    )
    out = capsys.readouterr().out
    assert "Comments: 1" in out


def test_comment_array_explicit_null_renders_zero(capsys):
    """An explicit `comments: null` with no total must not raise; render zero."""
    _mod._print_issue(
        _issue({"summary": "S", "comment": {"comments": None}}),
        requested_fields={"comment"},
    )
    out = capsys.readouterr().out
    assert "Comments: 0" in out


def test_subtask_null_summary_does_not_print_none(capsys):
    """A subtask with an explicit `summary: null` must not print the literal 'None'."""
    _mod._print_issue(_issue({"summary": "S", "subtasks": [{"key": "SUB-1", "fields": {"summary": None}}]}))
    out = capsys.readouterr().out
    assert "Subtasks (1):" in out
    assert "SUB-1:" in out
    assert "None" not in out


def test_no_comment_line_when_field_absent(capsys):
    """A restricted `-f` that omits comment fetches no comment field, so no line."""
    _mod._print_issue(
        _issue({"summary": "S", "status": {"name": "Open"}}),
        requested_fields={"summary", "status"},
    )
    out = capsys.readouterr().out
    assert "Comments:" not in out


def test_parent_and_subtasks_rendered(capsys):
    """Parent and subtasks surface as cheap metadata in the default view."""
    _mod._print_issue(
        _issue(
            {
                "summary": "S",
                "parent": {"key": "EP-1", "fields": {"summary": "Epic"}},
                "subtasks": [{"key": "SUB-1", "fields": {"summary": "Do thing", "status": {"name": "Open"}}}],
            }
        )
    )
    out = capsys.readouterr().out
    assert "Parent: EP-1: Epic" in out
    assert "Subtasks (1):" in out
    assert "SUB-1: Do thing [Open]" in out


def test_requested_field_without_renderer_gets_notice(capsys):
    """An explicitly requested field with no renderer emits a pointer, not silence."""
    _mod._print_issue(
        _issue({"summary": "S", "customfield_10071": "some value"}),
        requested_fields={"summary", "customfield_10071"},
    )
    out = capsys.readouterr().out
    assert "customfield_10071: present in the response but not rendered here" in out


def test_no_safety_net_notice_on_default_view(capsys):
    """The safety net only fires for explicit `-f` requests, not the default view."""
    _mod._print_issue(_issue({"summary": "S", "customfield_10071": "some value"}))
    out = capsys.readouterr().out
    assert "customfield_10071" not in out
