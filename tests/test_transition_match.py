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


def _tf(tid: str, name: str, to: str, required=(), optional=()):
    """A transition as the API returns it with ``expand=transitions.fields``."""
    fields = {k: {"required": True} for k in required}
    fields.update({k: {"required": False} for k in optional})
    return {"id": tid, "name": name, "to": to, "fields": fields}


class TestAmbiguousSelectors:
    """Two transitions that a name or a target cannot tell apart.

    Both shapes are real, from one Jira DC instance: `✅ QA → Resolved` beside
    `❌ QA → Reopened` (same label up to an emoji, opposite outcomes), and
    `✅ Done → Closed` beside `✖ Close → Closed` (same target, different
    requirements). Returning the first match silently sent a ticket to the wrong
    place; the resolver must refuse and hand back the candidates instead.
    """

    QA_PAIR = [
        _tf("121", "✅ QA", "Resolved"),
        _tf("281", "❌ QA", "Reopened"),
    ]
    CLOSED_PAIR = [
        _tf("381", "✅ Done", "Closed"),
        _tf("341", "✖ Close", "Closed", required=("resolution",)),
    ]

    def test_same_label_up_to_emoji_is_refused(self):
        match, ambiguous = _mod.find_matching_transition(self.QA_PAIR, "QA")
        assert match is None
        assert {t["id"] for t in ambiguous} == {"121", "281"}

    def test_shared_target_status_is_refused(self):
        match, ambiguous = _mod.find_matching_transition(self.CLOSED_PAIR, "Closed")
        assert match is None
        assert {t["id"] for t in ambiguous} == {"381", "341"}

    def test_id_selects_unambiguously(self):
        match, ambiguous = _mod.find_matching_transition(self.QA_PAIR, "121")
        assert match["name"] == "✅ QA"
        assert ambiguous == []

    def test_id_wins_over_a_name_that_would_be_ambiguous(self):
        match, _ = _mod.find_matching_transition(self.CLOSED_PAIR, "341")
        assert match["name"] == "✖ Close"

    def test_unambiguous_name_still_resolves(self):
        match, ambiguous = _mod.find_matching_transition(self.CLOSED_PAIR, "Done")
        assert match["id"] == "381"
        assert ambiguous == []


class TestFieldSpec:
    def test_required_fields_read_from_the_screen(self):
        t = _tf("341", "✖ Close", "Closed", required=("resolution",), optional=("worklog",))
        assert _mod.required_fields(t) == ["resolution"]
        assert _mod.settable_fields(t) == ["resolution", "worklog"]

    def test_a_transition_declaring_nothing_requires_nothing(self):
        assert _mod.required_fields(_tf("381", "✅ Done", "Closed")) == []

    def test_unexpanded_transition_reports_no_requirements(self):
        """An unexpanded listing cannot express requiredness — it must not pretend to."""
        assert _mod.required_fields({"id": "1", "name": "x", "to": "y"}) == []

    def test_ambiguity_notes_name_both_candidates(self):
        notes = _mod._ambiguous_selectors(TestAmbiguousSelectors.CLOSED_PAIR)
        assert any("381" in n and "341" in n for n in notes)


class TestReviewFindings:
    """Two defects the review caught in the first version of this change."""

    def test_an_empty_expanded_list_is_an_answer_not_a_miss(self):
        """`{"transitions": []}` means the issue offers none — do not ask again."""
        calls = {"full": 0, "legacy": 0}

        class Client:
            def get_issue_transitions_full(self, key, expand=None):
                calls["full"] += 1
                return {"transitions": []}

            def get_issue_transitions(self, key):
                calls["legacy"] += 1
                raise AssertionError("must not fall back on a valid empty answer")

        assert _mod.fetch_transitions(Client(), "X-1") == []
        assert calls == {"full": 1, "legacy": 0}

    def test_a_missing_transitions_key_still_falls_back(self):
        class Client:
            def get_issue_transitions_full(self, key, expand=None):
                return {"expand": "transitions"}

            def get_issue_transitions(self, key):
                return [{"id": "1", "name": "Go", "to": "Done"}]

        assert _mod.fetch_transitions(Client(), "X-1")[0]["id"] == "1"

    def test_ambiguity_notes_normalize_the_target_like_the_matcher(self):
        """`✅ Closed` and `✖ Closed`: `do` refuses them, so `list` must say why."""
        ts = [
            _tf("381", "Done", "✅ Closed"),
            _tf("341", "Close", "✖ Closed", required=("resolution",)),
        ]
        match, ambiguous = _mod.find_matching_transition(ts, "Closed")
        assert match is None and len(ambiguous) == 2

        notes = _mod._ambiguous_selectors(ts)
        assert any("381" in n and "341" in n for n in notes), "list must flag what do refuses"


class TestSecondRoundFindings:
    def test_unknown_requirements_are_not_reported_as_none(self):
        """An unexpanded transition has no screen — that is not 'requires nothing'."""
        unexpanded = {"id": "1", "name": "Go", "to": "Done"}
        assert "fields" not in unexpanded
        expanded = _tf("2", "Close", "Closed", required=("resolution",))
        assert _mod.required_fields(expanded) == ["resolution"]

    def test_missing_hint_offers_the_flag_only_for_resolution(self):
        hint = _mod._missing_hint(["resolution"])
        assert "--resolution" in hint

    def test_missing_hint_does_not_point_at_a_flag_that_cannot_help(self):
        hint = _mod._missing_hint(["assignee", "customfield_10881"])
        assert "--resolution" not in hint
        assert "assignee" in hint and "customfield_10881" in hint

    def test_missing_hint_covers_a_mixed_set(self):
        hint = _mod._missing_hint(["resolution", "assignee"])
        assert "--resolution" in hint and "assignee" in hint


class TestUnknownSpecInDo:
    """`do` must not claim a check it could not perform.

    `list` renders `?` where the screen was not returned. `do` printed `-` and
    silently skipped the required-field pre-check — the same conflation of
    "requires nothing" with "nobody asked", one command over.
    """

    def test_required_fields_cannot_speak_for_an_unexpanded_transition(self):
        unexpanded = {"id": "1", "name": "Go", "to": "Done"}
        assert "fields" not in unexpanded
        assert _mod.required_fields(unexpanded) == []

    def test_an_expanded_transition_without_requirements_is_a_real_answer(self):
        assert "fields" in _tf("2", "Done", "Closed")
        assert _mod.required_fields(_tf("2", "Done", "Closed")) == []


class TestMalformedExpandedResponse:
    def test_a_non_dict_entry_falls_back_instead_of_raising(self):
        """Every caller does t.get(...), so a null member must not reach them."""

        class Client:
            def get_issue_transitions_full(self, key, expand=None):
                return {"transitions": [None]}

            def get_issue_transitions(self, key):
                return [{"id": "1", "name": "Go", "to": "Done"}]

        got = _mod.fetch_transitions(Client(), "X-1")
        assert got == [{"id": "1", "name": "Go", "to": "Done"}]

    def test_a_well_formed_list_is_still_returned_as_is(self):
        class Client:
            def get_issue_transitions_full(self, key, expand=None):
                return {"transitions": [{"id": "9", "name": "Ok", "to": "Done"}]}

            def get_issue_transitions(self, key):
                raise AssertionError("must not fall back on a well-formed answer")

        assert _mod.fetch_transitions(Client(), "X-1")[0]["id"] == "9"
