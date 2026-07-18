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


class TestInlineEmphasis:
    """Emphasis markers glued mid-word render literally and must be flagged,
    while snake_case identifiers and boundary-correct emphasis stay clean."""

    def test_underscore_midword_flagged(self):
        findings = lint_wiki_markup("§4.1 bewertet die Konzept_qualität_, nicht den Preis.")
        assert any("starts mid-word" in f for f in findings)

    def test_star_midword_flagged(self):
        findings = lint_wiki_markup("das ist Fett*wort* im Satz")
        assert any("starts mid-word" in f for f in findings)

    def test_boundary_italic_is_clean(self):
        assert lint_wiki_markup("das ist _wichtig_ und bleibt sauber") == []

    def test_boundary_bold_is_clean(self):
        assert lint_wiki_markup("das ist *fett* und bleibt sauber") == []

    def test_snake_case_identifiers_are_clean(self):
        # be_acl, sys_file_reference, sf_event_mgt: no closer lands on a boundary.
        assert lint_wiki_markup("Extensions be_acl, sys_file_reference und sf_event_mgt bleiben.") == []

    def test_trailing_underscore_identifier_is_clean(self):
        assert lint_wiki_markup("wir nutzen leuphana_solr am Ende.") == []

    def test_emphasis_after_hyphen_is_clean(self):
        # `-` is a non-word boundary, so AG-_Entscheidung_ opens correctly.
        assert lint_wiki_markup("die AG-_Entscheidung_ war eindeutig") == []

    def test_underscores_in_monospace_are_clean(self):
        assert lint_wiki_markup("siehe {{Prefix_Wort_}} im Backend") == []

    def test_underscores_in_link_are_clean(self):
        assert lint_wiki_markup("[Prefix_Wort_|https://example.com/x] ansehen") == []

    def test_php_magic_constants_are_clean(self):
        # Symmetric double-marker tokens must not match (non-empty body required).
        assert lint_wiki_markup("__LINE__, __FILE__, __CLASS__ und __init__ bleiben.") == []

    def test_markdown_double_marker_is_clean(self):
        # Carried-over Markdown bold **x** / __x__ must not be flagged.
        assert lint_wiki_markup("Text **bold** und __kursiv__ sowie foo**bar** bleiben.") == []

    def test_format_string_and_path_segments_are_clean(self):
        # An inner _seg_/…*seg* whose next segment starts with a connector
        # (% $ /) is a format string / path, not a clause-boundary closer.
        assert lint_wiki_markup("Ordner %d_%m_%Y, Zeit %H_%M_%S und path/to/some_dir_/file.") == []
        assert lint_wiki_markup("Key user_$id_$tenant lesen.") == []

    def test_nfd_combining_accent_before_marker_flagged(self):
        # "café_wert_" in decomposed form (e + U+0301) must still be caught;
        # the scan NFC-normalises so the accented letter counts as a word char.
        assert any("starts mid-word" in f for f in lint_wiki_markup("café_wert_ Ende."))

    def test_broken_emphasis_before_closing_quote_flagged(self):
        # Quoted UI/field labels with a glued marker: the closer sits before
        # a quote, a real clause boundary (common in German prose).
        assert any("starts mid-word" in f for f in lint_wiki_markup('Das Label "Konzept_qualitaet_" ist falsch.'))
        german = "Im Feld " + chr(0x201E) + "Anmelden_jetzt_" + chr(0x201C) + " fehlt."
        assert any("starts mid-word" in f for f in lint_wiki_markup(german))
