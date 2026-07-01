# No editorializing — inform, don't sell (tone, not wordlist)

Applies to every written artifact: commit messages, PR/MR descriptions, review
comments, issue/ticket text, chat — and code comments, docstrings,
documentation, README and changelog files.

Editorializing is a matter of **tone and intent, not specific words** — no
banned-word list catches it, and the same word can be fine or not depending on
whether it carries a fact. The failure is writing about *how good, clean, or
careful the work is* instead of *what it does*. The reader has the diff and the
artifact; anything that only flatters the work or reassures them adds nothing,
and to a reviewer it reads as salesmanship — it provokes a counter-reaction
before they reach the substance.

Apply three tests before a sentence stays:

1. **Deletion** — remove the phrase. Did the reader lose a fact? If not, cut it.
2. **Subject** — is the sentence about the change, or about *you / your work*
   (its quality, your diligence)? The latter goes.
3. **Voice** — would a terse maintainer write this, or does it read like a
   cover letter?

Two recurring failure modes:

- **Announcing the expected.** Passing tests, clean linters, "documented", "no
  regressions", "works as expected" are the baseline — do not narrate them.
  State a check's status only to flag an *exception* (something knowingly
  failing or skipped). In a test/verification list, say what was *added or
  covered*, not that it is green.

- **Self-praise and reassurance.** Grading your own output ("clean", "robust",
  "elegant", "foolproof", "tidy", "genuinely new", "production-ready"); framings
  that reassure ("the honest breaking change", "deliberately scoped, not
  hidden", "where it belongs"); and the diligence humble-brag ("I carefully…",
  "I made sure to…", "thoroughly tested"). These describe the author, not the
  change. Show the fact; drop the framing. (The words are only symptoms — judge
  by the three tests above, not by the word.)

Use plain labels, not graded ones: "Breaking change", "Tests", "Limitations" —
not "Tests (all green)" or "Breaking change (honest)". If a limitation's cause
matters, it is already stated in the item.
