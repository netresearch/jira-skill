# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Tests for the lint finding on references to another comment by position."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills/jira-communication/scripts"))

from lib.markup import lint_comment_references  # noqa: E402
from lib.markup_cli import check_markup  # noqa: E402

# The two comments that caused this check, verbatim (posted 2026-11-10).
REAL_CASES = [
    '(x) Correction to the comment above: the "Deploy (Update)" workflow does not '
    "recreate the Caddy container when nothing changed.",
    "because Caddy had no TLS certificate for the name yet (see the comments above).",
]

FLAGGED = [
    "As the comment below explains, the job was retried.",
    "The above comment is outdated.",
    "See the comments further up for the log.",
    "Wie im Kommentar oben beschrieben, wurde der Job neu gestartet.",
    "Siehe die Kommentare weiter unten.",
    "Der obige Kommentar ist veraltet.",
    "Laut dem oben stehenden Kommentar fehlt das Zertifikat.",
]

NOT_FLAGGED = [
    "See the previous comment for the log.",
    "see the earlier comment",
    "The next comment will carry the result.",
    "Siehe den vorherigen Kommentar.",
    "See [the deploy comment|https://jira.example.com/browse/OPS-1?focusedCommentId=12345"
    "&page=com.atlassian.jira.plugin.system.issuetabpanels:comment-tabpanel#comment-12345].",
    "The table above lists the hosts; the steps below fix it.",
    "See above.",
    "siehe oben",
    "The comment above the method in Foo.php is wrong.",
    "Ein Kommentar darüber, wie das geht, fehlt.",
]


@pytest.mark.parametrize("text", REAL_CASES)
def test_the_real_comments_are_flagged(text):
    findings = lint_comment_references(text)
    assert len(findings) == 1, findings
    assert "per-user setting" in findings[0]


@pytest.mark.parametrize("text", FLAGGED)
def test_position_references_are_flagged(text):
    assert lint_comment_references(text), text


@pytest.mark.parametrize("text", NOT_FLAGGED)
def test_time_words_permalinks_and_same_comment_references_pass(text):
    assert lint_comment_references(text) == [], text


def test_code_block_content_is_not_flagged():
    assert lint_comment_references("{code}\n# see the comment above\n{code}") == []


def test_finding_names_the_line():
    findings = lint_comment_references("h3. Result\n\n" + REAL_CASES[1])
    assert findings[0].startswith("line 3: 'comments above'")


def test_check_markup_aborts_on_a_position_reference(capsys):
    with pytest.raises(SystemExit) as exc:
        check_markup(REAL_CASES[0], force=False, label="comment")
    assert exc.value.code == 1
    assert "reference: line 1: 'comment above'" in capsys.readouterr().err


def test_check_markup_force_posts_with_a_warning(capsys):
    check_markup(REAL_CASES[1], force=True, label="comment")
    assert "reference: line 1: 'comments above'" in capsys.readouterr().err
