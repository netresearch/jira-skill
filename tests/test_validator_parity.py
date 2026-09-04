"""Parity between the two implementations of the dash-strikethrough rule.

The rule lives twice: `_FLAG_DASH_RE` in `skills/jira-communication/scripts/lib/markup.py`
(used by `jira-comment.py add`) and an awk pattern in
`skills/jira-syntax/scripts/validate-jira-syntax.sh`. They must agree, or a draft
that the standalone validator passes is rejected at post time — or worse, the
other way round.

The trap this pins is locale: POSIX `[[:alnum:]]` is locale-dependent, so under
`LC_ALL=C` an ASCII-only awk class silently diverges from Python's Unicode-aware
`\\w`. The validator is therefore run under both `C` and a UTF-8 locale.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts/lib"))

from markup import lint_wiki_markup  # noqa: E402

VALIDATOR = Path(__file__).resolve().parents[1] / "skills/jira-syntax/scripts/validate-jira-syntax.sh"

# (text, expected_flagged). Each is prose, so nothing here is inside {code}.
CASES = [
    ("checked with --strict and --no-global", True),
    ("green under {{--strict}} today", True),
    ("an empty {{journalctl -b -p crit}}", True),
    ("run it with -v for verbose output", True),
    ("offset by -5 seconds", True),
    ("use -é as the flag", True),  # non-ASCII word char after the dash
    ("green under {{\\-\\-strict}} today", False),
    ("compare {{uptime \\-s}} against the mtime", False),
    ("a --- b and c -- d stay prose", False),
    ("- first item", False),
    ("the Round-1 review on 2026-09-04 stays prose", False),
    ("the range a--b stays prose", False),
]


def _python_flags(text: str) -> bool:
    return any("strikethrough span" in f for f in lint_wiki_markup(text))


def _validator_flags(text: str, tmp_path: Path, locale: str) -> bool:
    # The validator treats a file with ``` fences as a hybrid template, so keep
    # the fixture fence-free; a bare h3. header keeps the rest of its checks quiet.
    f = tmp_path / "draft.txt"
    f.write_text(f"h3. Fixture\n\n{text}\n", encoding="utf-8")
    r = subprocess.run(
        ["bash", str(VALIDATOR), str(f)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "LC_ALL": locale},
        check=False,
    )
    return "opens a strikethrough span" in r.stdout


@pytest.mark.parametrize("text,expected", CASES)
def test_python_matches_expectation(text, expected):
    assert _python_flags(text) is expected


@pytest.mark.skipif(not VALIDATOR.exists(), reason="validator script not present")
@pytest.mark.parametrize("locale", ["C", "en_US.UTF-8"])
@pytest.mark.parametrize("text,expected", CASES)
def test_validator_agrees_with_python(text, expected, locale, tmp_path):
    """The shell validator must reach the same verdict as the Python lint, in
    every locale — this is what the ASCII-only awk class used to break."""
    assert _validator_flags(text, tmp_path, locale) is expected
    assert _validator_flags(text, tmp_path, locale) is _python_flags(text)
