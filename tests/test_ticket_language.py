"""Tests for the IT-project language guard in lib.markup."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills/jira-communication/scripts"))

from lib.markup import is_english_only_project, lint_ticket_language, looks_german  # noqa: E402

GERMAN = (
    "h3. Ergebnis\n\n"
    "Der Runner wurde neu gestartet und zieht das Image jetzt ohne Fehler. "
    "Die Pipeline ist gruen, aber der Cache wird noch nicht verwendet.\n"
)
ENGLISH = (
    "h3. Result\n\n"
    "The runner was restarted and now pulls the image without an error. "
    "The pipeline is green, but the cache is not used yet.\n"
)


class TestProjectClassification:
    def test_exact_it_projects(self):
        for key in ("NRS-4625", "NRT-4583", "LIC-7", "PO-12"):
            assert is_english_only_project(key), key

    def test_prefix_it_projects(self):
        for key in ("SRVGL-255", "SRVC-117", "IOS-385", "IOT-397"):
            assert is_english_only_project(key), key

    def test_other_projects_are_not_covered(self):
        for key in ("NRNR-1590", "OPSFX-362", "HSM-1", "DEV-9"):
            assert not is_english_only_project(key), key

    def test_lowercase_key_is_normalised(self):
        assert is_english_only_project("nrs-4625")


class TestGermanDetection:
    def test_german_prose_is_detected(self):
        german, hits = looks_german(GERMAN)
        assert german
        assert len(hits) >= 5

    def test_english_prose_is_not_flagged(self):
        german, _ = looks_german(ENGLISH)
        assert not german

    def test_single_german_word_is_not_enough(self):
        # A loanword or one quoted term must not trip the threshold.
        german, _ = looks_german("The Abnahme is pending and the runner is green.")
        assert not german

    def test_english_lookalikes_do_not_accumulate(self):
        # `die`, `war`, `hat`, `also`, `fast`, `man`, `so`, `an`, `in` are English
        # words too and are deliberately absent from the marker list.
        german, hits = looks_german("In a war the die is cast, so a man had a hat, and also ran fast in an hour.")
        assert not german, hits


class TestLint:
    def test_german_on_it_project_is_flagged(self):
        findings = lint_ticket_language(GERMAN, "NRS-4625")
        assert len(findings) == 1
        assert "English by convention" in findings[0]
        assert "NRS" in findings[0]

    def test_english_on_it_project_is_clean(self):
        assert lint_ticket_language(ENGLISH, "NRS-4625") == []

    def test_german_on_a_non_it_project_is_clean(self):
        # NRNR and the customer projects are legitimately German.
        assert lint_ticket_language(GERMAN, "NRNR-1590") == []

    def test_missing_key_is_clean(self):
        assert lint_ticket_language(GERMAN, None) == []
