"""Tests for jira-transition.py `find_matching_transition` — tolerant name resolver.

Jira transitions are often labelled with emoji prefixes (e.g. "✅ Resolve"), so
exact-equality matching forces the caller to reproduce the emoji. The resolver
adds emoji-tolerant and unique-substring fallbacks on top of exact matching.
"""

from conftest import load_script

_mod = load_script("jira-transition", "workflow")


def _t(name: str, to: str):
    return {"id": name, "name": name, "to": to}


class TestFindMatchingTransition:
    def test_exact_case_insensitive_name(self):
        ts = [_t("Start work", "In Progress"), _t("Resolve", "Resolved")]
        match, ambiguous = _mod.find_matching_transition(ts, "resolve")
        assert match["name"] == "Resolve"
        assert ambiguous == []

    def test_exact_on_target_status(self):
        ts = [_t("Done it", "Resolved")]
        match, _ = _mod.find_matching_transition(ts, "Resolved")
        assert match["name"] == "Done it"

    def test_emoji_prefixed_name_matched_by_plain_name(self):
        """The regression: '✅ Resolve' must match a plain 'Resolve'."""
        ts = [_t("▶ Start work", "In Progress"), _t("✅ Resolve", "Resolved"), _t("⏳️ Waiting", "Waiting")]
        match, ambiguous = _mod.find_matching_transition(ts, "Resolve")
        assert match["name"] == "✅ Resolve"
        assert ambiguous == []

    def test_unique_substring_match(self):
        ts = [_t("Start work", "In Progress"), _t("Send to QA review", "QA")]
        match, _ = _mod.find_matching_transition(ts, "QA review")
        assert match["name"] == "Send to QA review"

    def test_ambiguous_substring_returns_candidates(self):
        ts = [_t("Resolve as fixed", "Resolved"), _t("Resolve as duplicate", "Resolved")]
        match, ambiguous = _mod.find_matching_transition(ts, "resolve as")
        assert match is None
        assert {t["name"] for t in ambiguous} == {"Resolve as fixed", "Resolve as duplicate"}

    def test_no_match_returns_empty(self):
        ts = [_t("Start work", "In Progress")]
        match, ambiguous = _mod.find_matching_transition(ts, "Resolve")
        assert match is None
        assert ambiguous == []

    def test_exact_wins_over_substring(self):
        """An exact name must win even when it is a substring of another transition."""
        ts = [_t("Review", "In Review"), _t("Review and approve", "Approved")]
        match, ambiguous = _mod.find_matching_transition(ts, "Review")
        assert match["name"] == "Review"
        assert ambiguous == []

    def test_non_latin_name_not_stripped_to_empty(self):
        """Localized (non-ASCII) transition names must survive normalization.

        Regression: an ASCII-only strip class would reduce a fully-Cyrillic name
        to '' and break matching. '\\W'-based stripping keeps Unicode letters.
        """
        ts = [_t("✅ Решить", "Решено"), _t("▶ Начать", "В работе")]
        match, ambiguous = _mod.find_matching_transition(ts, "Решить")
        assert match["name"] == "✅ Решить"
        assert ambiguous == []

    def test_unicode_casefold_equality(self):
        """German ß should casefold-match 'ss' (Unicode-correct comparison)."""
        ts = [_t("Abschließen", "Done")]
        match, _ = _mod.find_matching_transition(ts, "ABSCHLIESSEN")
        assert match["name"] == "Abschließen"
