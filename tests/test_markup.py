"""Tests for ``lib.markup.lint_wiki_markup`` — the wiki-markup linter."""

import sys
from pathlib import Path

# Add scripts to path for lib imports (mirrors tests/test_input.py).
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))

from lib.markup import lint_wiki_markup


class TestClean:
    """Inputs that must produce no findings."""

    def test_plain_prose(self):
        assert lint_wiki_markup("Just a sentence with *bold* and {{mono}}.") == []

    def test_clean_code_block(self):
        assert lint_wiki_markup("{code:bash}\nls -l\n{code}") == []

    def test_clean_quote_block(self):
        assert lint_wiki_markup("{quote}\ncited text\n{quote}") == []

    def test_escaped_literal_in_prose(self):
        assert lint_wiki_markup("escape literal mentions as \\{code\\} in prose") == []

    def test_inline_monospace_lookalike(self):
        # {{code}} / {{panel}} are inline monospace, not block tags.
        assert lint_wiki_markup("Use {{code}} for inline monospace and {{panel}} too") == []

    def test_other_tags_inside_open_block_ignored(self):
        assert lint_wiki_markup("{code}\nexample shows {noformat} inside code\n{code}") == []

    def test_tag_with_params(self):
        assert lint_wiki_markup("{panel:title=Note}\ncontent\n{panel}") == []


class TestInline:
    """Block tags used inline must be flagged."""

    def test_tag_in_prose(self):
        findings = lint_wiki_markup("(/) icons, {code} blocks together")
        assert any("used inline" in f for f in findings)

    def test_one_line_pair(self):
        findings = lint_wiki_markup("bad {code}one-liner{code} inline")
        assert any("used inline" in f for f in findings)

    def test_two_tags_whitespace_separated(self):
        # Several tags on one line are inline usage even when the
        # remainder is whitespace (review finding on this PR).
        findings = lint_wiki_markup("{code} {panel}")
        assert any("used inline" in f for f in findings)


class TestBalance:
    """Unbalanced or unclosed blocks must be flagged."""

    def test_odd_tag_count(self):
        findings = lint_wiki_markup("text with {code} blocks\n{code}\nls\n{code}")
        assert any("unbalanced {code}" in f for f in findings)

    def test_unclosed_block(self):
        findings = lint_wiki_markup("{noformat}\nstuff")
        assert any("unclosed {noformat}" in f for f in findings)


class TestRendererSemantics:
    """Same-tag occurrences inside an open block close it — matching the
    Jira Server 9.12 renderer (verified via /rest/api/1.0/render)."""

    def test_text_after_closing_tag(self):
        findings = lint_wiki_markup("{code}\nfoo {code} bar\nnext\n{code}\n{code}")
        assert any("text after closing {code}" in f for f in findings)

    def test_closing_tag_alone_is_fine(self):
        assert lint_wiki_markup("{code}\nfoo\n{code}") == []


class TestTablePipes:
    """`||` inside a normal `|` table row splits the row and must be flagged."""

    def test_header_row_is_clean(self):
        assert lint_wiki_markup("|| Paket || Constraint || PT ||") == []

    def test_plain_data_row_is_clean(self):
        assert lint_wiki_markup("| news | ^13.1 | 1 |") == []

    def test_double_pipe_in_data_cell_flagged(self):
        findings = lint_wiki_markup("| luxletter | 29.0.1, ^12.4 || ^13.4 | 2 |")
        assert any("splits the row" in f for f in findings)

    def test_double_pipe_in_prose_is_not_a_table(self):
        # A line that does not start with `|` is prose, not a table row.
        assert lint_wiki_markup("supports ^12.4 || ^13.4 in composer.json") == []

    def test_escaped_double_pipe_in_data_cell_is_clean(self):
        # A cell may hold a literal `||` written as the escaped `\|\|`.
        assert lint_wiki_markup(r"| luxletter | 29.0.1, ^12.4 \|\| ^13.4 | 2 |") == []

    def test_escaped_pipe_before_delimiter_is_clean(self):
        # `\|` is a literal pipe; `\||` is literal-pipe + delimiter, not broken.
        assert lint_wiki_markup(r"| a\|| b |") == []

    def test_escaped_backslash_before_double_pipe_flagged(self):
        # `\\` is a literal backslash, so the following `||` is unescaped.
        findings = lint_wiki_markup(r"| luxletter | 29.0.1, ^12.4 \\|| ^13.4 | 2 |")
        assert any("splits the row" in f for f in findings)
