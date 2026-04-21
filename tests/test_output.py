"""Tests for output.py — extract_adf_text() function."""

import sys
from pathlib import Path

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.output import compact_json, extract_adf_text

# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_adf_text()
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractAdfText:
    """extract_adf_text() must extract plain text from Atlassian Document Format."""

    def test_paragraph_with_text(self):
        adf = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}]}
        assert extract_adf_text(adf) == "Hello world"

    def test_multiple_paragraphs(self):
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
            ],
        }
        assert extract_adf_text(adf) == "First Second"

    def test_text_block(self):
        adf = {"type": "doc", "content": [{"type": "text", "text": "Direct text"}]}
        assert extract_adf_text(adf) == "Direct text"

    def test_empty_content(self):
        adf = {"type": "doc", "content": []}
        assert extract_adf_text(adf) == ""

    def test_non_dict_returns_string(self):
        assert extract_adf_text("plain string") == "plain string"

    def test_no_content_key(self):
        adf = {"type": "doc"}
        assert extract_adf_text(adf) == ""

    def test_heading_extracted(self):
        """Headings must be included in extracted text (F9)."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "My Heading"}]}
            ],
        }
        assert "My Heading" in extract_adf_text(adf)

    def test_bullet_list_extracted(self):
        """Bullet list items must be included in extracted text (F9)."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item one"}]}],
                        },
                        {
                            "type": "listItem",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Item two"}]}],
                        },
                    ],
                }
            ],
        }
        result = extract_adf_text(adf)
        assert "Item one" in result
        assert "Item two" in result

    def test_code_block_extracted(self):
        """Code block content must be included in extracted text (F9)."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": 'print("hello")'}],
                }
            ],
        }
        assert 'print("hello")' in extract_adf_text(adf)

    def test_blockquote_extracted(self):
        """Blockquote content must be included in extracted text (F9)."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Quoted text"}]}],
                }
            ],
        }
        assert "Quoted text" in extract_adf_text(adf)

    def test_nested_structure_extracted(self):
        """Deeply nested ADF structures must be fully traversed (F9)."""
        adf = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Intro"}]},
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Step 1"}]}],
                        }
                    ],
                },
                {"type": "heading", "content": [{"type": "text", "text": "Summary"}]},
            ],
        }
        result = extract_adf_text(adf)
        assert "Intro" in result
        assert "Step 1" in result
        assert "Summary" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: compact_json()
# ═══════════════════════════════════════════════════════════════════════════════


class TestCompactJson:
    """compact_json() must strip null / empty-list values recursively."""

    def test_strips_none_values(self):
        assert compact_json({"a": 1, "b": None, "c": "x"}) == {"a": 1, "c": "x"}

    def test_strips_empty_lists(self):
        assert compact_json({"a": [], "b": [1, 2]}) == {"b": [1, 2]}

    def test_preserves_false_and_zero(self):
        """Falsy values that aren't None/[] must be preserved."""
        data = {"truthy": 1, "zero": 0, "false": False, "empty_str": ""}
        assert compact_json(data) == {"truthy": 1, "zero": 0, "false": False, "empty_str": ""}

    def test_recursive_into_nested_dict(self):
        data = {"outer": {"inner": None, "kept": "x"}}
        assert compact_json(data) == {"outer": {"kept": "x"}}

    def test_recursive_into_list_of_dicts(self):
        data = {"items": [{"a": None, "b": 1}, {"a": 2, "b": None}]}
        assert compact_json(data) == {"items": [{"b": 1}, {"a": 2}]}

    def test_jira_issue_shape_drops_null_customfields(self):
        """The real-world case from issue #72."""
        issue = {
            "key": "PROJ-1",
            "id": "10001",
            "self": "https://jira.example.com/rest/api/2/issue/10001",
            "fields": {
                "summary": "Bug",
                "status": {"name": "Open"},
                "assignee": None,
                "labels": [],
                "customfield_18111": None,
                "customfield_18112": None,
                "customfield_18113": [],
                "priority": {"name": "High"},
            },
        }
        result = compact_json(issue)
        assert result["key"] == "PROJ-1"
        assert result["id"] == "10001"
        assert "customfield_18111" not in result["fields"]
        assert "customfield_18112" not in result["fields"]
        assert "customfield_18113" not in result["fields"]
        assert "assignee" not in result["fields"]
        assert "labels" not in result["fields"]
        assert result["fields"]["summary"] == "Bug"
        assert result["fields"]["status"] == {"name": "Open"}

    def test_does_not_mutate_input(self):
        original = {"a": None, "b": 1}
        compact_json(original)
        assert "a" in original  # input untouched

    def test_non_dict_non_list_passthrough(self):
        assert compact_json("hello") == "hello"
        assert compact_json(42) == 42
        assert compact_json(None) is None
