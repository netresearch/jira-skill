"""Tests for output.py — extract_adf_text() function."""

import sys
from pathlib import Path

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.output import extract_adf_text

# ═══════════════════════════════════════════════════════════════════════════════
# Tests: extract_adf_text()
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractAdfText:
    """extract_adf_text() must extract plain text from Atlassian Document Format."""

    def test_paragraph_with_text(self):
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'paragraph',
                    'content': [
                        {'type': 'text', 'text': 'Hello world'}
                    ]
                }
            ]
        }
        assert extract_adf_text(adf) == 'Hello world'

    def test_multiple_paragraphs(self):
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'First'}]
                },
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'Second'}]
                }
            ]
        }
        assert extract_adf_text(adf) == 'First Second'

    def test_text_block(self):
        adf = {
            'type': 'doc',
            'content': [
                {'type': 'text', 'text': 'Direct text'}
            ]
        }
        assert extract_adf_text(adf) == 'Direct text'

    def test_empty_content(self):
        adf = {'type': 'doc', 'content': []}
        assert extract_adf_text(adf) == ''

    def test_non_dict_returns_string(self):
        assert extract_adf_text('plain string') == 'plain string'

    def test_no_content_key(self):
        adf = {'type': 'doc'}
        assert extract_adf_text(adf) == ''

    def test_heading_extracted(self):
        """Headings must be included in extracted text (F9)."""
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'heading',
                    'attrs': {'level': 2},
                    'content': [{'type': 'text', 'text': 'My Heading'}]
                }
            ]
        }
        assert 'My Heading' in extract_adf_text(adf)

    def test_bullet_list_extracted(self):
        """Bullet list items must be included in extracted text (F9)."""
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'bulletList',
                    'content': [
                        {
                            'type': 'listItem',
                            'content': [
                                {
                                    'type': 'paragraph',
                                    'content': [{'type': 'text', 'text': 'Item one'}]
                                }
                            ]
                        },
                        {
                            'type': 'listItem',
                            'content': [
                                {
                                    'type': 'paragraph',
                                    'content': [{'type': 'text', 'text': 'Item two'}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = extract_adf_text(adf)
        assert 'Item one' in result
        assert 'Item two' in result

    def test_code_block_extracted(self):
        """Code block content must be included in extracted text (F9)."""
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'codeBlock',
                    'attrs': {'language': 'python'},
                    'content': [{'type': 'text', 'text': 'print("hello")'}]
                }
            ]
        }
        assert 'print("hello")' in extract_adf_text(adf)

    def test_blockquote_extracted(self):
        """Blockquote content must be included in extracted text (F9)."""
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'blockquote',
                    'content': [
                        {
                            'type': 'paragraph',
                            'content': [{'type': 'text', 'text': 'Quoted text'}]
                        }
                    ]
                }
            ]
        }
        assert 'Quoted text' in extract_adf_text(adf)

    def test_nested_structure_extracted(self):
        """Deeply nested ADF structures must be fully traversed (F9)."""
        adf = {
            'type': 'doc',
            'content': [
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'Intro'}]
                },
                {
                    'type': 'orderedList',
                    'content': [
                        {
                            'type': 'listItem',
                            'content': [
                                {
                                    'type': 'paragraph',
                                    'content': [{'type': 'text', 'text': 'Step 1'}]
                                }
                            ]
                        }
                    ]
                },
                {
                    'type': 'heading',
                    'content': [{'type': 'text', 'text': 'Summary'}]
                }
            ]
        }
        result = extract_adf_text(adf)
        assert 'Intro' in result
        assert 'Step 1' in result
        assert 'Summary' in result
