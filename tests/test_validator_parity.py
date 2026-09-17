"""Parity between the two implementations of the dash-strikethrough rule.

The rule lives twice: ``find_strikethrough_spans`` in
``skills/jira-communication/scripts/lib/markup.py`` (used by ``jira-comment.py``)
and an awk state machine in ``skills/jira-syntax/scripts/validate-jira-syntax.sh``.
They must agree, or a draft the standalone validator passes is rejected at post
time - or worse, the other way round.

The case list is no longer hand-picked: both implementations are run over every
prose case in ``tests/fixtures/strikethrough_oracle.json``, recorded from a live
renderer. A hand-picked list is exactly how the previous version of this file
stayed green while asserting that ``journalctl -b -p crit`` is struck through,
which Jira does not do.

What this file asserts is that the two implementations agree with EACH OTHER on
every one of those cases. Whether they agree with Jira is asserted separately,
in ``tests/test_strikethrough.py``, against the generated corpus - and
deliberately asymmetrically, because the model is a superset. Keeping the two
questions apart matters: an exemption granted for the Jira contract must not
silently become an excuse for the two implementations to drift.

The trap it still pins is locale: POSIX ``[[:alnum:]]`` is locale-dependent, so
an ASCII-only awk class silently diverges on non-ASCII prose. The validator is
therefore run under both ``C`` and a UTF-8 locale.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts/lib"))

from markup import find_strikethrough_spans, lint_wiki_markup  # noqa: E402

VALIDATOR = Path(__file__).resolve().parents[1] / "skills/jira-syntax/scripts/validate-jira-syntax.sh"
FIXTURE = Path(__file__).resolve().parent / "fixtures/strikethrough_oracle.json"


def _utf8_locale() -> str | None:
    """A UTF-8 locale that exists on this machine, or None.

    CI runners routinely ship only `C`/`POSIX`, and forcing `LC_ALL` to an
    absent locale makes the shell abort rather than run the validator - which
    is what turned this file red on its first push.
    """
    try:
        out = subprocess.run(["locale", "-a"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return None
    for name in out.split():
        if name.lower().replace("-", "").endswith("utf8"):
            return name
    return None


_UTF8 = _utf8_locale()
LOCALES = ["C"] + ([_UTF8] if _UTF8 else [])


def test_a_utf8_locale_is_available():
    """Fail loudly when the UTF-8 arm silently disappears.

    The parametrisation above shrinks to one arm on a machine with only
    C/POSIX, with no skip marker and nothing to notice - which is the shape
    that hid the original ASCII-only word-class bug. This is a warning, not a
    hard requirement, so it is skipped rather than failed; the skip is the
    signal.
    """
    if not _UTF8:
        pytest.skip("no UTF-8 locale on this machine - the UTF-8 parity arm did not run")


_ORACLE = json.loads(FIXTURE.read_text(encoding="utf-8"))

# Single-line prose only. The validator has its own opinions about multi-line
# fixtures (block tags, tables, fences) that would confound this comparison;
# block handling is covered by tests/test_strikethrough.py.
CASES = [
    c["markup"]
    for c in _ORACLE["cases"]
    if "\n" not in c["markup"] and not c["markup"].startswith(("|", "h2.", "h3.", "* ", "- "))
]

# A safety net for the selection above: if a filter change ever emptied one
# side, every parametrised test would pass vacuously.
assert sum(1 for t in CASES if find_strikethrough_spans(t)) >= 20, "corpus lost its positive cases"
assert sum(1 for t in CASES if not find_strikethrough_spans(t)) >= 20, "corpus lost its negative cases"


def _python_flags(text: str) -> bool:
    return bool(find_strikethrough_spans(text))


def _validator_flags(text: str, tmp_path: Path, locale: str) -> bool:
    # The validator treats a file with ``` fences as a hybrid template, so keep
    # the fixture fence-free; a bare h3. header keeps the rest of its checks quiet.
    f = tmp_path / "draft.txt"
    f.write_text(f"h3. Fixture\n\n{text}\n", encoding="utf-8")
    # JIRA_SYNTAX_SCAN_LOCALE pins the locale the validator scans in, so the
    # `C` arm really exercises the C-only fallback rather than the UTF-8 locale
    # the script would otherwise pick for itself.
    env = {**os.environ, "LC_ALL": locale, "LANG": locale, "JIRA_SYNTAX_SCAN_LOCALE": locale}
    r = subprocess.run(
        ["bash", str(VALIDATOR), str(f)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    # The validator exits non-zero only on ERRORs; a warning-only run exits 0.
    # Anything else means it did not run, and a silent "no match" would then be
    # read as agreement - fail loudly instead.
    assert r.returncode == 0, f"validator did not run under LC_ALL={locale}: {r.returncode} {r.stderr[:200]}"
    return "renders struck through" in r.stdout


@pytest.mark.parametrize("text", CASES, ids=CASES)
def test_lint_reports_exactly_what_the_tokenizer_finds(text):
    """No third opinion: the message the user reads comes from the model."""
    reported = any("renders struck through" in f for f in lint_wiki_markup(text))
    assert reported is _python_flags(text)


@pytest.mark.skipif(not VALIDATOR.exists(), reason="validator script not present")
@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("text", CASES, ids=CASES)
def test_validator_agrees_with_python(text, locale, tmp_path):
    """The shell validator must reach the same verdict as the Python tokenizer,
    in every locale available here - this is what the ASCII-only awk class broke."""
    assert _validator_flags(text, tmp_path, locale) is _python_flags(text)


@pytest.mark.skipif(not VALIDATOR.exists(), reason="validator script not present")
def test_validator_help_text_does_not_repeat_the_old_claim(tmp_path):
    """The message the user reads must not still say a lone flag is a span.

    The rule was wrong for months in prose as well as in code, and the prose is
    what a reader acts on.
    """
    source = VALIDATOR.read_text(encoding="utf-8")
    assert "single-dash option opens one too" not in source
    assert not re.search(r"journalctl -b -p crit.{0,40}matched pair", source, re.S)


# ─────────────────────────────────────────────────────────────────────────────
# The whole corpus, in one awk pass.
#
# The per-case test above runs the validator as a subprocess and is therefore
# limited to the ~200 curated cases; 8920 subprocesses would not be a test, it
# would be a coffee break. But the curated set does not contain the adversarial
# token combinations, so for a long time the shell side was simply never shown
# them - and it was silently missing spans Jira draws and this repo already had
# recorded verdicts for. A review found three that way.
#
# So the awk program is extracted from between the markers in the script and
# run once over every single-line case. One subprocess, under a second, and the
# two implementations are finally compared on the same evidence.
# ─────────────────────────────────────────────────────────────────────────────

_AWK_RE = re.compile(
    r"AWK-DASH-SCAN-BEGIN.*?dash_hits=\$\(LC_ALL=\"\$scan_locale\" awk '(?P<prog>.*?)' <<< \"\$content\"",
    re.S,
)
_CORPUS_FIXTURE = Path(__file__).resolve().parent / "fixtures/strikethrough_corpus.json"


def _awk_program() -> str:
    match = _AWK_RE.search(VALIDATOR.read_text(encoding="utf-8"))
    assert match, "could not extract the awk dash scan - did the markers move?"
    return match.group("prog")


@pytest.mark.skipif(not VALIDATOR.exists(), reason="validator script not present")
@pytest.mark.parametrize("locale", LOCALES)
def test_awk_agrees_with_python_over_the_whole_corpus(locale, tmp_path):
    corpus = json.loads(_CORPUS_FIXTURE.read_text(encoding="utf-8"))
    cases = [c for c in corpus["struck"] + corpus["clean"] if "\n" not in c]
    assert len(cases) > 5000, "corpus shrank - this test would pass on almost nothing"

    source = tmp_path / "corpus.txt"
    source.write_text("\n".join(cases) + "\n", encoding="utf-8")
    program = tmp_path / "scan.awk"
    program.write_text(_awk_program(), encoding="utf-8")

    result = subprocess.run(
        ["awk", "-f", str(program), str(source)],
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": locale, "LANG": locale},
        check=False,
    )
    assert result.returncode == 0, f"awk failed under {locale}: {result.stderr[:300]}"

    flagged_lines = {int(line.split(":", 1)[0]) for line in result.stdout.splitlines() if ":" in line}
    disagreements = [
        (n, case)
        for n, case in enumerate(cases, 1)
        for awk_says in [n in flagged_lines]
        if awk_says is not bool(find_strikethrough_spans(case))
    ]
    assert not disagreements, "awk and Python disagree on:\n" + "\n".join(
        f"  line {n}: awk={n in flagged_lines} python={bool(find_strikethrough_spans(c))} {c!r}"
        for n, c in disagreements[:10]
    )


@pytest.mark.skipif(not VALIDATOR.exists(), reason="validator script not present")
def test_a_dead_dash_scan_is_reported_not_swallowed(tmp_path):
    """A scan that did not run must not look like a draft with no findings.

    This is the shape the whole change exists to avoid, on the shell side: no
    hits is exactly what a clean draft produces. Two earlier attempts at this
    guard did not work and both looked like they did - first the pipe into
    `head` swallowed awk's status, then `set -e` aborted the script on the bare
    assignment before the check could run. The second one still exited
    non-zero, so a casual check ("it fails, good") passed while the ERROR never
    printed and the remaining files in a multi-file run were skipped.

    So this asserts all three: the message, the summary that follows it, and a
    non-zero exit.
    """
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    # Fails only for the dash scan, so the validator's other awk uses still work.
    (fakebin / "awk").write_text(
        '#!/bin/bash\nfor a in "$@"; do case "$a" in *"strikes("*) exit 3;; esac; done\nexec /usr/bin/awk "$@"\n',
        encoding="utf-8",
    )
    (fakebin / "awk").chmod(0o755)

    draft = tmp_path / "draft.txt"
    draft.write_text("h3. Fixture\n\nDie {{a}}-Extensions, jede zu- und abschaltbar\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(VALIDATOR), str(draft)],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"},
        check=False,
    )
    assert "did not run" in result.stdout, result.stdout[-500:]
    assert "Validation Summary" in result.stdout, "the run aborted instead of reporting"
    assert result.returncode != 0, "a draft that was never checked must not exit 0"
