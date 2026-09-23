"""The strikethrough grammar, checked against recorded Jira output.

Two fixtures, both recorded from a live Jira Server 9.12 wiki renderer:

* ``strikethrough_oracle.json`` - the curated cases, WITH their rendered HTML.
  These are the ones to read to understand the rule; the span-body assertions
  run against them.
* ``strikethrough_corpus.json`` - the generated bulk, produced by
  ``scripts/generate-strikethrough-corpus.py``, recorded as a struck/not-struck
  flag. This is what turns "I thought of the cases" into "the suite found them".

The contract is deliberately asymmetric, and that is the point:

* **No false negatives.** Every ``<del>`` the renderer produced must be
  covered by a predicted span - except a pinned list of shapes that glue a URL
  or link macro directly to another one, which prose does not do.
* **False positives are allowed and pinned.** Predicting a span Jira would not
  draw costs one redundant ``\\-``, which prints as a plain hyphen. Missing one
  mangles the text. The model is a superset on purpose, and the exact set of
  over-predictions is pinned so it cannot grow unnoticed.

Two hand-derived versions of this rule were wrong before this suite existed.
The first claimed ``journalctl -b -p crit`` was a matched pair (it is not). The
second was pinned to 168 hand-picked cases and still claimed a span body could
not contain a dash - ``-b -p crit ... zu-`` disproves it, and only an
end-to-end sentence that happened to combine both shapes found it. A later
review found three more classes the alphabet did not cover at all: non-ASCII
symbols, U+00A0, and the escaped bracket. Hence the generator, and hence its
alphabet being the thing to extend when a new class turns up.
"""

import html
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts"))

from lib import markup  # noqa: E402
from lib.preview import RenderVerdict  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ORACLE = json.loads((FIXTURES / "strikethrough_oracle.json").read_text(encoding="utf-8"))
_CORPUS = json.loads((FIXTURES / "strikethrough_corpus.json").read_text(encoding="utf-8"))

CASES = _ORACLE["cases"]
# Jira draws a link to a RESOLVED issue with its key in <del> inside the anchor
# (`<a class="issue-link" data-issue-key="K"><del>K</del></a>`). That is
# issue-status styling, not a text-effect span, so it is removed before any
# assertion reads the rendered HTML. Duplicated from lib.preview on purpose,
# like _DEL_RE below: a bug in the production helper must not hide itself by
# being used on both sides of the assertion.
_RESOLVED_ISSUE_LINK_RE = re.compile(
    r"""(<a\b(?=[^>]*\bclass="issue-link")(?=[^>]*\bdata-issue-key="([^"]+)")[^>]*>)<del>\2</del></a>"""
)
for _case in CASES:
    _case["rendered"] = _RESOLVED_ISSUE_LINK_RE.sub(r"\1\2</a>", _case["rendered"])
# Two flat lists, not one list of objects: at ~9000 cases the per-object
# scaffolding was most of the file. Splitting them up front also means no test
# enters a case and returns without asserting, which reads as a pass.
STRUCK_CASES = _CORPUS["struck"]
CLEAN_CASES = _CORPUS["clean"]
CORPUS_CASES = STRUCK_CASES + CLEAN_CASES
KNOWN_OVER = set(_CORPUS["known_over_predictions"])
KNOWN_UNDER = set(_CORPUS["known_under_predictions"])

_DEL_RE = re.compile(r"<del>(.*?)</del>", re.S)
# Mirrors lib.markup._split_verbatim; duplicated on purpose so a bug in that
# helper cannot hide itself by being used on both sides of the assertion.
_VERBATIM_RE = re.compile(r"^\s*\{(code|noformat)(?::[^}\n]*)?\}\s*$")


def _spans_in(source: str) -> list[tuple[str, tuple[int, int]]]:
    """Every predicted span in ``source``, as (line, span), skipping verbatim blocks.

    The parameter is ``source`` rather than ``markup`` on purpose: this module
    imports ``lib.markup`` under that name, and a parameter shadowing it makes
    every call inside this function resolve against a string.
    """
    found: list[tuple[str, tuple[int, int]]] = []
    open_tag = None
    for line in source.split("\n"):
        match = _VERBATIM_RE.match(line)
        if open_tag is not None:
            if match is not None and match.group(1) == open_tag:
                open_tag = None
            continue
        if match is not None:
            open_tag = match.group(1)
            continue
        found += [(line, span) for span in markup.find_strikethrough_spans(line)]
    return found


def _ids(cases):
    return [c["markup"] for c in cases]


class TestFixturesAreIntact:
    """Guards everything below: a truncated fixture makes every case vacuous."""

    def test_curated_oracle(self):
        assert len(CASES) >= 200
        assert any("<del>" in c["rendered"] for c in CASES)
        assert any("<del>" not in c["rendered"] for c in CASES)

    def test_generated_corpus(self):
        assert len(CORPUS_CASES) >= 5000
        assert not (set(STRUCK_CASES) & set(CLEAN_CASES)), "a case is in both lists"
        assert len(STRUCK_CASES) >= 100, f"corpus is one-sided: {len(STRUCK_CASES)} struck"
        assert len(CLEAN_CASES) >= 100, f"corpus is one-sided: {len(CLEAN_CASES)} clean"


class TestNoFalseNegatives:
    """The load-bearing half: Jira struck it, so the model must have seen it."""

    @pytest.mark.parametrize("case", STRUCK_CASES, ids=STRUCK_CASES)
    def test_every_rendered_del_is_predicted(self, case):
        predicted = bool(_spans_in(case))
        if case in KNOWN_UNDER:
            assert not predicted, "known miss started passing - drop it from known_under_predictions"
            return
        assert predicted

    def test_known_misses_all_glue_two_regions_together(self):
        """The pinned misses must stay the shape they were accepted as.

        Every one of them puts two macro-shaped tokens - a link, a bare URL, an
        image, or a backslash-escaped bracket - on the same run of
        non-whitespace, and that is the whole reason they are exempt: Jira
        resolves the first and leaves the second as literal text, dashes and
        all, which written prose never does. If a miss is ever pinned that does
        NOT look like that, this fails and the exemption has to be argued
        rather than inherited.

        The token literals come from the generator, not from the production
        regex - an exemption that used the code under test to justify itself
        would hold whatever that code happens to do.
        """
        tokens = (
            "[t|https://x.de/a/-/b]",
            "https://x.de/a/-/b",
            "https://x.de/a\u00a0/-/b",
            "!i.png!",
            "!-x\u00a0y!",
            "\\[",
        )
        for case in KNOWN_UNDER:
            spans = sorted((m.start(), m.end()) for token in tokens for m in re.finditer(re.escape(token), case))
            glued = any(
                not re.search(r"\s", case[first_end:second_start])
                for (_, first_end), (second_start, _) in zip(spans, spans[1:], strict=False)
            )
            assert glued, f"pinned miss is not a glued-regions shape: {case!r}"
        # The cap is a smell alarm, not a limit with meaning. Two NBSP-carrying
        # tokens entering the alphabet once took the pinned list from 11 to 58,
        # which is what prompted measuring that `!` blocks a bare URL from
        # autolinking - that one rule brought it back to 15. A jump like that is
        # to be looked at, not absorbed by raising the number.
        assert len(KNOWN_UNDER) <= 25


class TestOverPredictionsArePinned:
    """False positives are acceptable, but only the ones already accounted for."""

    @pytest.mark.parametrize("case", CLEAN_CASES, ids=CLEAN_CASES)
    def test_no_unexpected_over_prediction(self, case):
        if not _spans_in(case):
            return
        assert case in KNOWN_OVER, "new over-prediction; safe, but add it to known_over_predictions deliberately"

    def test_pinned_over_predictions_still_over_predict(self):
        """The symmetric staleness check KNOWN_UNDER already had.

        A pinned over-prediction that the model stopped making has to be
        removed deliberately, or the list slowly becomes a list of things
        nobody has checked.
        """
        for case in KNOWN_OVER:
            assert _spans_in(case), f"no longer over-predicted - drop it from known_over_predictions: {case!r}"

    def test_the_documented_quirk_is_the_reason_for_most_of_them(self):
        # Jira abandons an opener whose body starts with one character followed
        # by a dash: `a -a-b- z` renders literally while `a -ab-cd- z` is
        # struck. Not modelled - the cost of predicting it is one redundant
        # escape, and a rule nobody can explain is a worse liability.
        assert markup.find_strikethrough_spans("a -a-b- z")
        assert markup.find_strikethrough_spans("a -ab-cd- z")


# The curated oracle needs its own pins. Its cases are almost disjoint from the
# generated corpus, so the corpus assertions say nothing about them, and the
# body-text test below skips any case whose span count does not line up - which
# is exactly where a miss would hide. Both directions are therefore listed by
# name here and asserted to be complete.
ORACLE_KNOWN_MISSES = {
    # An autolinked issue key: Jira substitutes OPS-899 before text effects
    # run, so the boundary after it exists only on an instance where that key
    # resolves. No source-level model can see it - lib/preview.py is the answer.
    # The other OPS-899 cases in the oracle render the key in <del> only
    # because the issue is resolved; that styling is removed at load (above),
    # so they are clean rather than misses.
    "OPS-899-x und zu- und",
}


class TestCuratedOracleIsPinnedBothWays:
    """Without this, an oracle-only miss passes silently (review finding)."""

    def test_misses_are_exactly_the_autolink_cases(self):
        misses = {c["markup"] for c in CASES if "<del>" in c["rendered"] and not _spans_in(c["markup"])}
        assert misses == ORACLE_KNOWN_MISSES

    def test_every_over_prediction_is_the_documented_quirk(self):
        """Each one must be an opener whose body is one character then a dash.

        Asserting the shape rather than a literal list: it is the property the
        exemption rests on, so a new over-prediction of a DIFFERENT shape fails
        here instead of being waved through.
        """
        for case in CASES:
            if "<del>" in case["rendered"]:
                continue
            for line, (opener, _closer) in _spans_in(case["markup"]):
                assert line[opener + 2 : opener + 3] == "-", (
                    f"over-prediction that is not the one-char quirk: {case['markup']!r}"
                )


class TestAgainstCuratedOracle:
    @pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
    def test_span_text_matches_rendered_del_body(self, case):
        spans = _spans_in(case["markup"])
        bodies = _DEL_RE.findall(case["rendered"])
        if len(spans) != len(bodies):
            # Count mismatches are pinned by TestCuratedOracleIsPinnedBothWays;
            # the interesting check here is the exact text, which only lines up
            # one-to-one.
            return
        for (line, (opener, closer)), body in zip(spans, bodies, strict=True):
            if "<" in body:
                continue
            # Jira emits an escaped dash as &#45;, so compare against source.
            assert html.unescape(body) == line[opener + 1 : closer].replace("\\-", "-")

    @pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
    def test_escaper_removes_every_span(self, case):
        assert _spans_in(markup.escape_strikethrough(case["markup"])) == []


class TestEscaperClearsTheWholeCorpus:
    @pytest.mark.parametrize("case", CORPUS_CASES, ids=CORPUS_CASES)
    def test_no_span_survives_the_repair(self, case):
        assert _spans_in(markup.escape_strikethrough(case)) == []


class TestTheVisibleEscapeExceptionIsBounded:
    """The superset's cost claim, made checkable instead of asserted in prose.

    ``find_strikethrough_spans`` documents the cost of an over-prediction as
    "one redundant ``\\-``, invisible in prose", with one exception: where two
    macros are written against each other the escape can land inside a link
    target, where a reader sees it. That sentence has now been wrong twice -
    once with invented counts, once with an example shape that does not
    reproduce - so it is pinned here rather than re-verified by hand each time.
    """

    URL_ESCAPE_RE = re.compile(r"https?://[^\s]*\\-")

    def _newly_escaped_inside_a_url(self):
        """Clean cases where the ESCAPER introduces a ``\\-`` into a URL.

        The filter matters: counting every clean case whose output matches the
        pattern gives 139, because many carry ``\\-`` in a URL already. Only a
        NEW one is a cost the escaper imposed.
        """
        hits = []
        for case in CLEAN_CASES:
            repaired = markup.escape_strikethrough(case)
            if repaired == case:
                continue
            if len(self.URL_ESCAPE_RE.findall(repaired)) > len(self.URL_ESCAPE_RE.findall(case)):
                hits.append(case)
        return hits

    def test_the_exception_is_exactly_three_pinned_cases(self):
        hits = self._newly_escaped_inside_a_url()
        assert len(hits) == 3, [markup.escape_strikethrough(h) for h in hits]
        assert set(hits) <= KNOWN_OVER, "a visible escape that is not a pinned over-prediction"

    def test_the_documented_example_reproduces(self):
        assert (
            markup.escape_strikethrough("x !i.png![t|https://x.de/a/-/b]- y") == "x !i.png![t|https://x.de/a/\\-/b]- y"
        )

    def test_prose_that_separates_its_macros_is_untouched(self):
        for text in (
            "Siehe [MR|https://git.netresearch.de/g/p/-/merge_requests/5] und zu- und abschaltbar",
            "Siehe https://git.netresearch.de/g/p/-/merge_requests/5 und zu- und abschaltbar",
        ):
            assert markup.escape_strikethrough(text) == text


class TestRegressionsFromIssue226:
    """The shapes reported in netresearch/jira-skill#226, verbatim."""

    OPS_899 = (
        "Die nr-pforum-*Extensions waren als unabhängig dranstöpselbare "
        "Erweiterungen gedacht, jede für sich zu- und abschaltbar."
    )
    MONOSPACE = "Die {{nr-pforum-*}}-Extensions waren gedacht, jede für sich zu- und abschaltbar."

    def test_plain_prose_is_not_flagged(self):
        # Jira renders this one literally (recorded), so a finding here would be
        # the false positive that made the old lint unusable on German prose.
        assert markup.find_strikethrough_spans(self.OPS_899) == []

    def test_monospace_boundary_opens_a_span(self):
        # `}}` is a non-word character, so the dash after it opens; `zu-` closes.
        assert len(markup.find_strikethrough_spans(self.MONOSPACE)) == 1
        assert any("renders struck through" in f for f in markup.lint_wiki_markup(self.MONOSPACE))

    def test_escaper_fixes_the_monospace_case(self):
        fixed = markup.escape_strikethrough(self.MONOSPACE)
        assert fixed == "Die {{nr-pforum-*}}\\-Extensions waren gedacht, jede für sich zu- und abschaltbar."
        assert markup.lint_wiki_markup(fixed) == []


class TestCliFlagsAlone:
    """A flag with no closer on the line is safe; with one, it is not.

    Both halves matter. Asserting only that flags are clean would be satisfied
    by a model that never reports anything.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "journalctl -b -p crit zeigt die Fehler",
            "run -v then -x done",
            "run --v then --x done",
            "Ein Test mit --strict und danach noch -v am Ende",
            "start -word end -word2 tail",
            "offset by -5 seconds",
        ],
    )
    def test_no_closer_means_no_finding(self, text):
        assert markup.find_strikethrough_spans(text) == []
        assert markup.lint_wiki_markup(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "a paragraph with -v and a trailing word- here",
            "journalctl -b -p crit zeigt die Fehler; das Modul ist zu- und abschaltbar.",
        ],
    )
    def test_a_trailing_dash_later_on_the_line_does(self, text):
        assert markup.find_strikethrough_spans(text)


class TestProtectedRegions:
    """A dash inside a link, URL or image is inert - escaping it breaks the link.

    This is the regression the whole masking layer exists for: GitLab merge
    request URLs carry a literal `/-/`, and this team pastes them into Jira
    comments constantly.
    """

    GITLAB = "[MR|https://git.netresearch.de/g/p/-/merge_requests/5] ist zu- und abschaltbar"

    def test_link_body_is_not_a_span(self):
        assert markup.find_strikethrough_spans(self.GITLAB) == []

    def test_link_body_is_not_escaped(self):
        assert markup.escape_strikethrough(self.GITLAB) == self.GITLAB

    def test_bare_url_is_protected(self):
        text = "Siehe https://x.de/a/-/b und das Modul zu- und abschaltbar"
        assert markup.find_strikethrough_spans(text) == []
        assert markup.escape_strikethrough(text) == text

    def test_image_macro_is_protected(self):
        assert markup.find_strikethrough_spans("!-x.png! zu- foo") == []

    def test_dash_in_link_text_is_protected(self):
        assert markup.find_strikethrough_spans("[Text mit -x|https://x.de] und zu- foo") == []

    def test_the_same_slash_dash_slash_in_prose_is_not(self):
        # Without the URL around it, `/-/` is an ordinary opener - measured.
        assert markup.find_strikethrough_spans("a /-/ zu- b")

    def test_url_glued_to_a_word_is_not_autolinked_and_stays_live(self):
        # Jira does not autolink `ahttp://...`, so its dashes are prose.
        assert markup.find_strikethrough_spans("x ahttp://x.de/a/-/b- y")

    def test_monospace_is_not_protected(self):
        # The one place the old implementation was right: text effects DO
        # apply inside {{...}}.
        assert markup.find_strikethrough_spans("{{-x-}} y")
        assert markup.find_strikethrough_spans("{{--strict}} foo bar- z")


class TestGrammarClauses:
    """One test per clause, so a regression names which rule broke."""

    def test_opener_needs_a_non_word_boundary(self):
        assert markup.find_strikethrough_spans("word-x- y") == []
        assert markup.find_strikethrough_spans("pre1-x- y") == []
        assert markup.find_strikethrough_spans("a_-x- y") == [(2, 4)]

    def test_non_ascii_letters_are_word_characters(self):
        assert markup.find_strikethrough_spans("Größe-x- y") == []
        assert markup.find_strikethrough_spans("a -x-ä y") == []

    def test_closer_needs_a_non_space_before_it(self):
        assert markup.find_strikethrough_spans("a -x - y") == []

    def test_closer_needs_a_non_word_after_it(self):
        assert markup.find_strikethrough_spans("pre -x-y z") == []
        assert markup.find_strikethrough_spans("pre -x- y") == [(4, 6)]

    def test_an_invalid_closer_is_skipped_not_fatal(self):
        # The defect the 168-case fixture missed: `-p` cannot close (space
        # before it), so the scan must carry on to `zu-` rather than give up.
        assert markup.find_strikethrough_spans("a -b -p crit zu- z") == [(2, 15)]

    def test_escaped_dash_in_the_body_does_not_break_the_span(self):
        assert len(markup.find_strikethrough_spans("a -x \\- y- b")) == 1

    def test_end_of_line_closes_a_span(self):
        assert markup.find_strikethrough_spans("a -x-") == [(2, 4)]

    def test_in_a_run_the_last_dash_opens_and_the_first_closes(self):
        assert markup.find_strikethrough_spans("a --foo-- b") == [(3, 7)]

    def test_escaped_dashes_are_literal(self):
        assert markup.find_strikethrough_spans("a \\-x- b") == []

    def test_unicode_dashes_are_inert(self):
        assert markup.find_strikethrough_spans("a –x– b") == []
        assert markup.find_strikethrough_spans("a —x— b") == []


class TestEscaperMechanics:
    def test_whole_dash_run_is_escaped(self):
        # Escaping only the opener would promote the first dash of the run to
        # opener and leave the span alive - measured, see _escape_dash_run.
        assert markup.escape_strikethrough("{{--strict}} foo bar- z") == "{{\\-\\-strict}} foo bar- z"

    def test_repeated_spans_all_get_fixed(self):
        assert markup.escape_strikethrough("a -x- and -y- b") == "a \\-x- and \\-y- b"

    def test_clean_text_is_returned_unchanged(self):
        for case in CASES:
            if not _spans_in(case["markup"]):
                assert markup.escape_strikethrough(case["markup"]) == case["markup"]

    def test_verbatim_blocks_are_left_alone(self):
        text = "{code}\na -x- b\n{code}"
        assert markup.escape_strikethrough(text) == text

    def test_quote_and_panel_are_not_verbatim(self):
        # Jira parses text effects inside {quote}/{panel} (recorded), so the
        # escaper must reach into them.
        assert markup.escape_strikethrough("{panel}\na {{m}}-x- b\n{panel}") == "{panel}\na {{m}}\\-x- b\n{panel}"


class TestEscaperTerminates:
    """The repair runs in the posting path; it must fail, never hang.

    Neutering _escape_dash_run during a mutation run hung the whole suite -
    the fixed-point loop had no progress guard. This pins the guard by making
    the repair a no-op and asserting the call still returns.
    """

    def test_a_non_progressing_repair_does_not_loop(self, monkeypatch):
        monkeypatch.setattr(markup, "_escape_dash_run", lambda line, opener: line)
        text = "Die {{a}}-Extensions, jede zu- und abschaltbar"
        assert markup.escape_strikethrough(text) == text
        # The span survives, so the lint must still report it - a repair that
        # cannot converge has to stay visible, not be swallowed.
        assert any("renders struck through" in f for f in markup.lint_wiki_markup(text))


class TestCommentCliWiring:
    """The repair must reach the POSTED text, not merely be importable.

    The previous version of this class called ``_repair_markup`` directly and
    called that "wiring". Deleting the call from ``add`` and ``edit`` reddened
    nothing — a review checked. These drive the real Click command and assert
    on the argument the client was handed, once per command, because ``edit``
    is the one a refactor drops silently.
    """

    @staticmethod
    def _module():
        import importlib.util

        path = Path(__file__).resolve().parents[1] / "skills/jira-communication/scripts/workflow/jira-comment.py"
        spec = importlib.util.spec_from_file_location("jira_comment_wiring_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run(self, args):
        from unittest import mock

        import click.testing

        module = self._module()
        client = mock.MagicMock()
        client.with_context = mock.Mock()
        client.issue_add_comment.return_value = {"id": "1"}
        client.issue_edit_comment.return_value = {"id": "1"}
        with (
            mock.patch.object(module, "LazyJiraClient", return_value=client),
            # Patched where it is USED, not where the command lives: the three
            # gates moved to lib.markup_cli so all seven wiki-markup surfaces
            # share one implementation.
            mock.patch("lib.markup_cli.preflight_render", return_value=RenderVerdict(True, [])),
            mock.patch.object(module, "check_mentions_cli", return_value=None),
        ):
            result = click.testing.CliRunner().invoke(module.cli, args)
        return result, client

    RAW = "Die {{a}}-Extensions, jede zu- und abschaltbar"
    REPAIRED = "Die {{a}}\\-Extensions, jede zu- und abschaltbar"

    def test_add_posts_the_repaired_text(self):
        result, client = self._run(["add", "PROJ-123", self.RAW])
        assert result.exit_code == 0, result.output
        client.issue_add_comment.assert_called_once_with("PROJ-123", self.REPAIRED)

    def test_edit_posts_the_repaired_text(self):
        result, client = self._run(["edit", "PROJ-123", "42", self.RAW])
        assert result.exit_code == 0, result.output
        client.issue_edit_comment.assert_called_once_with("PROJ-123", "42", self.REPAIRED)

    def test_no_auto_escape_posts_the_text_verbatim(self):
        # --force is needed too: the lint refuses the surviving span on its own.
        result, client = self._run(["add", "PROJ-123", self.RAW, "--no-auto-escape", "--force"])
        assert result.exit_code == 0, result.output
        client.issue_add_comment.assert_called_once_with("PROJ-123", self.RAW)

    def test_clean_text_is_posted_unchanged(self):
        text = "journalctl -b -p crit zeigt die Fehler"
        result, client = self._run(["add", "PROJ-123", text])
        assert result.exit_code == 0, result.output
        client.issue_add_comment.assert_called_once_with("PROJ-123", text)
