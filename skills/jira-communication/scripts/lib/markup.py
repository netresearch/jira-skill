"""Jira wiki-markup lint helpers.

Catches the most damaging authoring mistakes before text is sent to Jira:

- Block-markup tags ({code}, {noformat}, {quote}, {panel}) used inline.
  These are block-level macros; an unescaped tag with other text on the
  same line opens a real block mid-prose and swallows the rest of the
  line. Literal mentions must be escaped as \\{code\\}.
- Unbalanced block tags (odd occurrence count), which leave an unclosed
  block that swallows everything after it.
- Table data rows containing an unescaped ``||`` inside a cell. In a table
  ``|`` is the cell and ``||`` the header-cell delimiter, so a ``||`` in a
  normal ``|`` row (typically a Composer constraint like ``^12.4 || ^13.4``)
  splits the row and shifts every following column. An escaped ``\\|`` is a
  literal pipe and is left alone. Rewrite the cell without unescaped pipes.
- Inline emphasis (``_italic_``, ``*bold*``) glued to the middle of a word.
  Jira only opens emphasis at a word boundary, so ``Konzept_qualität_`` is
  rendered with literal underscores rather than italics. Only the clearly
  broken shape is flagged (a marker preceded by a word char whose matching
  closer lands on a clause boundary - space, sentence punctuation, a closing
  bracket or quote, or line end - not before a connector like % or /); the body
  must be non-empty, so
  symmetric double-marker tokens (``__LINE__``, ``**bold**``) and snake_case
  identifiers such as ``be_acl`` or ``sys_file_reference`` are left alone.
  Content inside ``{{monospace}}`` and ``[links]`` is ignored. Known blind spot:
  a bare trailing-underscore prefix (``tx_news_``) is flagged like broken
  emphasis - wrap identifiers in ``{{monospace}}`` to silence it.
- Flag-like tokens (``--strict``) outside code blocks. Jira parses
  ``-text-`` as strikethrough; the opening ``-`` needs only whitespace (or a
  ``{{`` monospace opener - text effects apply INSIDE ``{{...}}``, verified
  against Jira Server 9.12) before it and a non-space after it, so a pair of
  CLI flags strikes through everything between them. Escaped dashes (``\\-``)
  are literal and pass; em/en-dash typography (``---``, ``--`` before a
  non-letter) never matches.

Escaped tags (\\{code\\}), inline-monospace lookalikes ({{code}}) and
*other* tags inside an open block are ignored. An occurrence of the
*same* tag inside an open block closes it — exactly what the Jira
renderer does (verified against Jira Server 9.12: a mid-line {code}
inside a code block terminates the block there).
"""

import re
import unicodedata

BLOCK_TAGS = ("code", "noformat", "quote", "panel")

# Unescaped block tag, optionally with parameters ({code:bash}, {panel:title=x}).
# (?<!\{) keeps {{code}} / {{panel}} (inline monospace content) out of scope.
_TAG_RE = re.compile(r"(?<!\\)(?<!\{)\{(code|noformat|quote|panel)(?::[^}\n]*)?\}")

# Spans where markers are literal, blanked before the emphasis scan so their
# content ({{sys_file_reference}}, [foo_bar_|url]) never trips the check.
_INLINE_SPAN_RE = re.compile(r"\{\{.*?\}\}|\[[^\]\n]*\]")

# The closer must sit before a real clause boundary: whitespace, sentence
# punctuation, a closing bracket, a closing quote, or line end - NOT before a
# connector like % $ / @, which would wrongly match a format-string or path
# segment (%d_%m_%Y, some_dir_/f). Closing quotes are included because German
# prose quotes UI/field labels; `/` and dashes stay excluded on purpose to keep
# paths/format strings clean. The quote codepoints (ASCII " ', curly quotes,
# guillemets) are built via chr() so this source stays ASCII-only.
_CLOSE_QUOTES = "".join(map(chr, (0x22, 0x27, 0x2018, 0x2019, 0x201C, 0x201D, 0xAB, 0xBB)))
_EMPH_CLOSE = "(?=[\\s.,;:!?)\\]}" + _CLOSE_QUOTES + "]|$)"

# A marker preceded by a word char whose matching closer sits at a clause boundary
# is broken-but-intended emphasis (Konzept_qualität_). The body is NON-EMPTY
# ([^\s<m>]+): an empty body would make the trailing pair of every symmetric
# double-marker token match, false-flagging PHP magic constants / dunders
# (__LINE__, __CLASS__, __init__) and Markdown bold (**x**, __x__) - all common in
# TYPO3/dev text. The body also cannot span another marker, so snake_case
# identifiers (be_acl, sf_event_mgt), whose closer never lands on a boundary, do
# not match. Known blind spot: a bare trailing-underscore prefix (tx_news_) is
# structurally identical to broken emphasis and is still flagged - wrap identifiers
# in {{monospace}} (good Jira practice) to silence it.
_MIDWORD_EMPHASIS_RES = {
    "_": re.compile(r"(?<=\w)_[^\s_]+_" + _EMPH_CLOSE),
    "*": re.compile(r"(?<=\w)\*[^\s*]+\*" + _EMPH_CLOSE),
}

# Flag-like token Jira strikes through. Scanned on the RAW line (not the
# monospace-blanked copy): text effects apply INSIDE {{...}}, so {{--strict}}
# is just as broken as bare --strict. The caller strips \- escapes before
# matching (an escaped dash is a literal); requiring a letter after the second
# dash keeps em/en-dash typography (---, `-- `) out of scope.
_FLAG_DASH_RE = re.compile(r"(?:^|\s|\{\{)--[A-Za-z]")


def lint_wiki_markup(text: str) -> list[str]:
    """Return a list of human-readable lint findings (empty = clean)."""
    findings: list[str] = []
    counts = dict.fromkeys(BLOCK_TAGS, 0)
    in_block: str | None = None

    for lineno, line in enumerate(text.split("\n"), 1):
        matches = list(_TAG_RE.finditer(line))

        if in_block is not None:
            # Inside a block, only the matching closing tag is markup;
            # everything else on the line is verbatim content.
            closing = next((m for m in matches if m.group(1) == in_block), None)
            if closing is not None:
                counts[in_block] += 1
                if line[closing.end() :].strip():
                    findings.append(
                        f"line {lineno}: text after closing {{{in_block}}} tag - "
                        f"block tags must stand alone on their own line"
                    )
                in_block = None
            continue

        # Table data row (starts with a single `|`) must not contain an
        # unescaped `||`: `||` is the header-cell delimiter and splits the row
        # mid-cell. An escaped `\|` is a literal pipe, so ignore it.
        stripped = line.strip()
        if stripped.startswith("|") and not stripped.startswith("||") and re.search(r"(?<!\\)(?:\\\\)*\|\|", stripped):
            findings.append(
                f"line {lineno}: table data row contains an unescaped '||' inside "
                f"a cell (e.g. a Composer constraint '^12.4 || ^13.4') - '|' is the "
                f"cell delimiter, so this splits the row; rewrite the cell without "
                f"unescaped pipes: {stripped[:80]!r}"
            )

        # Inline emphasis glued mid-word renders as a literal marker. NFC-normalise
        # first so a word ending in a decomposed accent (NFD "e"+combining acute)
        # still presents a word char before the marker, then blank out {{monospace}}
        # and [link] spans, where the markers are literal.
        scan = _INLINE_SPAN_RE.sub(" ", unicodedata.normalize("NFC", line))
        for marker, emphasis_re in _MIDWORD_EMPHASIS_RES.items():
            if emphasis_re.search(scan):
                findings.append(
                    f"line {lineno}: inline '{marker}' emphasis starts mid-word - "
                    f"Jira only renders {marker}text{marker} at a word boundary, so "
                    f"this shows the literal marker; emphasize the whole token at a "
                    f"boundary (e.g. '{marker}Wort{marker}', not "
                    f"'Prefix{marker}Wort{marker}'): {stripped[:80]!r}"
                )

        # CLI flags render struck through, even inside {{monospace}} - scan the
        # raw line with \- escapes removed (an escaped dash is a literal).
        if _FLAG_DASH_RE.search(line.replace("\\-", "")):
            findings.append(
                f"line {lineno}: flag-like token (--foo) - Jira parses -text- as "
                f"strikethrough, even inside {{{{...}}}} monospace, so a pair of "
                f"flags strikes through everything between them; escape every "
                f"dash as \\-\\-foo (e.g. {{{{\\-\\-strict}}}}): {stripped[:80]!r}"
            )

        if not matches:
            continue

        for m in matches:
            counts[m.group(1)] += 1

        # A clean block-tag line contains nothing but a single tag; several
        # tags on one line ({code} {panel}) are inline usage even when the
        # remainder is whitespace.
        if _TAG_RE.sub("", line).strip() or len(matches) > 1:
            findings.append(
                f"line {lineno}: block tag used inline - {{code}}/{{noformat}}/"
                f"{{quote}}/{{panel}} are block markup and never inline; escape "
                f"literal mentions as \\{{code\\}}: {line.strip()[:80]!r}"
            )
        elif len(matches) == 1:
            # Only a clean, solitary tag opens a block for lint purposes;
            # an inline tag is already flagged and would corrupt the state.
            in_block = matches[0].group(1)

    if in_block is not None:
        findings.append(f"unclosed {{{in_block}}} block - everything after the opening tag is swallowed")

    for tag, n in counts.items():
        if n % 2:
            findings.append(
                f"unbalanced {{{tag}}} tags: {n} unescaped occurrence(s), expected "
                f"pairs - escape literal mentions as \\{{{tag}\\}}"
            )

    return findings


# Projects whose agent-authored content is English by convention. Team rules
# live in the consuming skill (netresearch-jira, references/it/language.md);
# this list only decides where the reminder fires. Matched on the key's
# project part, `SRV`/`IO` as prefixes because of SRVGL, SRVC, IOS, IOT.
_ENGLISH_ONLY_EXACT = frozenset({"NRS", "NRT", "LIC", "PO"})
_ENGLISH_ONLY_PREFIXES = ("SRV", "IO")

# Function words that are common in German and rare-to-absent in English
# technical prose. Deliberately excludes look-alikes that are ordinary English
# words on their own (`die`, `war`, `hat`, `bald`, `also`, `fast`, `an`, `in`,
# `so`, `man`), so an English sentence cannot accumulate hits by accident.
_GERMAN_MARKERS = frozenset(
    """
    aber auch auf aus bei beim bereits bis dabei damit dann dass dem den denn der
    des deshalb durch ein eine einem einen einer eines erst falls für gegen ist
    jede jeden jetzt kann kein keine mit nach nicht noch nur oder ohne schon sein
    seine sich sind soll sollte über und unter vom von vor wenn werden wird wurde
    wurden während zum zur zwei
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")

# How many *distinct* markers must appear before the text is called German.
# Five effectively require German sentence structure, so a loanword or a short
# quoted fragment stays below it. The scan sees the whole body, quotes
# included: a substantial German quote does reach five markers and does
# produce a finding - that case is what --force is for.
_GERMAN_MARKER_THRESHOLD = 5


def looks_german(text: str) -> tuple[bool, list[str]]:
    """Heuristic: does this text read as German prose? Returns (verdict, markers)."""
    words = {w.lower() for w in _WORD_RE.findall(text)}
    hits = sorted(words & _GERMAN_MARKERS)
    return len(hits) >= _GERMAN_MARKER_THRESHOLD, hits


def is_english_only_project(issue_key: str) -> bool:
    """True when the key belongs to a project whose content is English by convention."""
    project = issue_key.split("-", 1)[0].upper()
    return project in _ENGLISH_ONLY_EXACT or project.startswith(_ENGLISH_ONLY_PREFIXES)


def lint_ticket_language(text: str, issue_key: str | None) -> list[str]:
    """Warn when German prose is about to be posted to an English-only project.

    The rule itself is a team convention (see the consuming team skill); what
    makes it worth a mechanical check is that prose alone has not held. Drift
    happens mid-session after a run of genuinely German tickets, and it is
    invisible in review because the ticket often already contains German from
    quoted mails.

    The scan reads the whole body, so a comment carrying a substantial German
    quote is reported like German prose - the check cannot tell a quote from
    authored text. That is the intended trade-off rather than a gap: posting
    quoted content verbatim is exactly what the caller's --force is for.
    """
    if not issue_key or not is_english_only_project(issue_key):
        return []
    german, hits = looks_german(text)
    if not german:
        return []
    project = issue_key.split("-", 1)[0].upper()
    sample = ", ".join(hits[:6])
    return [
        f"text looks German ({sample}...) but {project} content is English by "
        f"convention - re-resolve the language per ticket; quoted user content "
        f"stays verbatim, so re-run with --force if that is what this is"
    ]
