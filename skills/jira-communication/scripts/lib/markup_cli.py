"""The three markup gates every wiki-markup write goes through, as CLI helpers.

``lib/markup.py`` holds the grammar and knows nothing about the terminal;
``lib/preview.py`` asks the instance. This module is the part that talks to the
user: it repairs, it reports, and it decides when to abort. Same split as
``lib/users.py``, where ``check_mentions_cli`` wraps the mention lookup.

It exists because these three lived in ``jira-comment.py`` and therefore ran on
exactly two of the six surfaces that post wiki markup. The other four - a
worklog comment, a transition comment, and the description of ``jira-create
issue`` and ``jira-issue update`` - render the same markup through the same
renderer and mangled it the same way. The mention gate had already been spread
across all six; this follows it.

The order is fixed and matters:

1. ``repair_markup`` escapes what can be escaped. A strikethrough span is not a
   judgement call, it is a mechanical defect with a mechanical repair.
2. ``check_markup`` reports what cannot: block tags used inline, unbalanced
   tags, and anything the escaper left behind.
3. ``check_rendering`` asks the instance, which is the only way to see what no
   source-level model can - an autolinked issue key creates a boundary that
   exists only where that key resolves.
"""

import sys

from lib.markup import escape_strikethrough, lint_ticket_language, lint_wiki_markup
from lib.output import error, warning
from lib.preview import preflight_render

# What the three gates are called on the command line. Kept here so a caller
# adding them does not invent a fourth spelling.
FORCE_HELP = "Post despite wiki-markup lint findings or a struck-through render preview"
NO_AUTO_ESCAPE_HELP = "Do not escape dashes Jira would render as strikethrough; add --force to actually post the span"
NO_PREFLIGHT_HELP = "Skip the render-preview check against the Jira instance before posting"


def repair_markup(text: str, auto_escape: bool, *, label: str = "text") -> str:
    """Escape dashes Jira would render as strikethrough, and say what changed.

    ``\\-`` prints as a plain hyphen, so the posted text reads exactly as
    written. Reporting the repair on stderr is deliberate - a silent rewrite of
    the user's text would be worse than the bug.

    ``--no-auto-escape`` turns it off, but not on its own: ``check_markup`` and
    ``check_rendering`` each refuse the surviving span independently, so a
    deliberate strikethrough needs ``--no-auto-escape --force``.
    """
    if not auto_escape:
        return text
    repaired = escape_strikethrough(text)
    if repaired == text:
        return text
    changed = [
        (n, after)
        for n, (before, after) in enumerate(zip(text.split("\n"), repaired.split("\n"), strict=True), 1)
        if before != after
    ]
    warning(
        f"auto-escaped {len(changed)} line(s) of the {label} that Jira would have rendered struck "
        f"through (\\- prints as a plain hyphen; use --no-auto-escape to keep the markup as written)"
    )
    for n, after in changed[:5]:
        warning(f"  line {n}: {after.strip()[:100]!r}")
    return repaired


def check_markup(text: str, force: bool, issue_key: str | None = None, *, label: str = "text") -> None:
    """Lint wiki markup and ticket language; abort on findings unless forced.

    The two kinds are labelled and explained separately: a language-only
    finding reported as a markup problem, with a suggestion about block tags,
    sends the reader looking for the wrong defect.
    """
    markup_findings = lint_wiki_markup(text)
    language_findings = lint_ticket_language(text, issue_key)
    if not markup_findings and not language_findings:
        return

    if force:
        for finding in markup_findings:
            warning(f"markup: {finding}")
        for finding in language_findings:
            warning(f"language: {finding}")
        return

    labelled = [f"markup: {f}" for f in markup_findings] + [f"language: {f}" for f in language_findings]
    hints = []
    if markup_findings:
        hints.append("Block tags are never inline; escape literal mentions as \\{code\\}.")
    if language_findings:
        hints.append("Re-resolve the language for this ticket; quoted user content stays verbatim.")
    hints.append("Re-run with --force to post anyway.")

    error(f"Lint found problems in the {label}:\n  " + "\n  ".join(labelled), suggestion=" ".join(hints))
    sys.exit(1)


def check_rendering(
    text: str,
    force: bool,
    issue_key: str | None,
    enabled: bool,
    env_file: str | None = None,
    profile: str | None = None,
    *,
    label: str = "text",
) -> None:
    """Ask the instance how it will render this text, and refuse a mangled write.

    The lexical repair handles what a model of the grammar CAN handle. This
    handles what it cannot, and the gap is not academic: Jira substitutes
    autolinked issue keys before text effects run, so
    ``{{OPS-899-Divergenzanalyse.pdf}}`` comes back with the key struck through
    on an instance where OPS-899 exists and clean on one where it does not.
    Escaping the dash does not help - measured - because the opener is
    positioned relative to the substituted link, not the source text.

    Advisory by construction. An unreachable, slow or absent renderer (the
    endpoint is Server/DC only) prints one warning and gets out of the way; it
    must never stop somebody writing to Jira.
    """
    if not enabled:
        return

    verdict = preflight_render(text, issue_key=issue_key, env_file=env_file, profile=profile)
    if not verdict.available:
        warning(f"render preview unavailable ({verdict.reason}) - relying on the local markup lint alone")
        return
    if not verdict.struck:
        return

    struck = "; ".join(repr(s[:80]) for s in verdict.struck[:3])
    if force:
        warning(f"rendering: Jira strikes through {struck}")
        return

    error(
        f"Jira renders part of this {label} struck through: {struck}",
        suggestion=(
            "The local escape could not fix it - this usually means an autolinked issue key "
            "(a dash right after PROJ-123) or another macro creating the boundary. Rephrase, "
            "put the token in a {code} block, or re-run with --force to write it anyway."
        ),
    )
    sys.exit(1)


def guard_wiki_markup(
    text: str,
    *,
    force: bool,
    auto_escape: bool,
    preflight: bool,
    issue_key: str | None = None,
    env_file: str | None = None,
    profile: str | None = None,
    label: str = "text",
) -> str:
    """Run all three gates in order and return the text to write.

    One call so a caller cannot wire up two of the three and believe it is
    covered - which is how the description paths went unguarded while the
    comment path had the full treatment.
    """
    text = repair_markup(text, auto_escape, label=label)
    check_markup(text, force, issue_key, label=label)
    check_rendering(text, force, issue_key, preflight, env_file, profile, label=label)
    return text
