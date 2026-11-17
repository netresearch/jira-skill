# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""validate-jira-syntax.sh warns on a nested bullet that continues no list.

Each case was rendered through Jira Server's ``POST /rest/api/1.0/render``.
When the line above a ``** item`` is blank, a heading or a plain paragraph, Jira
opens a new list and renders an empty level-1 bullet with the item nested under
it. A non-blank line inside a list continues the item above it, so a ``**``
line after such a continuation still nests correctly.
"""

import subprocess
from pathlib import Path

import pytest

VALIDATOR = Path(__file__).resolve().parents[1] / "skills/jira-syntax/scripts/validate-jira-syntax.sh"
MESSAGE = "Nested bullet without a list item above"


def _warned_lines(text: str, tmp_path: Path) -> list[str]:
    draft = tmp_path / "draft.txt"
    draft.write_text(text, encoding="utf-8")
    result = subprocess.run(["bash", str(VALIDATOR), str(draft)], capture_output=True, text=True, check=False)
    out = result.stdout.splitlines()
    for i, line in enumerate(out):
        if MESSAGE in line:
            assert "WARNING" in line, line
            hits = []
            for follow in out[i + 1 :]:
                if follow.startswith("   Lines with issue:"):
                    continue
                if not follow[:1].isdigit():
                    break
                hits.append(follow.split(":", 1)[0])
            return hits
    return []


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        # rendered: <ul><li>parent<ul><li>child</li></ul></li></ul>
        ("* parent\n** child\n", []),
        # rendered: <ul><li>parent<br/>plain<ul><li>child</li></ul></li></ul>
        ("* parent\nplain\n** child\n", []),
        # rendered: <ul><li>parent</li></ul><ul><li><ul><li>child</li></ul></li></ul>
        ("* parent\n\n** child\n", ["3"]),
        # rendered: <p>Text line</p><ul><li><ul><li>child</li></ul></li></ul>
        ("Text line\n** child\n", ["2"]),
        # rendered: <ul><li><ul><li>child only</li></ul></li></ul>
        ("** child only\n", ["1"]),
        # rendered: <h2>Title</h2><ul><li><ul><li>child</li></ul></li></ul>
        ("h2. Title\n** child\n", ["2"]),
        # rendered: the second ** after the blank line gets an empty parent
        ("* a\n** b\n\n** c\n", ["4"]),
        # verbatim: not markup inside {code}/{noformat}
        ("{code}\n** not a list\n{code}\n", []),
        ("{noformat}\n\n** not a list\n{noformat}\n", []),
        # a different block tag inside a verbatim block is literal content
        ("{noformat}\n{code}\n** literal\n{noformat}\n** orphan\n", ["5"]),
    ],
)
def test_nested_bullet_needs_a_list_item_above(text, lines, tmp_path):
    assert _warned_lines(text, tmp_path) == lines
