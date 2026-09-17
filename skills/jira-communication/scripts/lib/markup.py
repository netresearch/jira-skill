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
- Dashes that Jira renders as a strikethrough span, outside code blocks.
  ``find_strikethrough_spans`` below implements the ``-text-`` grammar as
  measured against a live Jira Server 9.12 wiki renderer - not as a heuristic,
  and not as a guess, but as a deliberate SUPERSET of it: it may report a span
  the renderer would not draw, and aims never to miss one it would. Two classes
  of miss are known and pinned rather than fixed - autolinked issue keys, which
  are instance state (see ``find_strikethrough_spans``), and two macro-shaped
  tokens written against each other with nothing between them, which prose does
  not produce (see ``_mask_protected`` and the pinned list in
  ``tests/fixtures/strikethrough_corpus.json``).
  ``escape_strikethrough`` repairs the spans it does find, so callers can fix
  rather than bounce.

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

# ─────────────────────────────────────────────────────────────────────────────
# Strikethrough (`-text-`) — the grammar, measured rather than guessed
#
# Every rule below is pinned by two fixtures recorded from the live Jira
# Server 9.12 wiki renderer (POST /rest/api/1.0/render):
# tests/fixtures/strikethrough_oracle.json (curated cases with their HTML) and
# tests/fixtures/strikethrough_corpus.json (the generated bulk). Exact counts
# live in those files rather than here, where re-recording would leave them
# quietly false.
# `scripts/verify-render-oracle.py --live` re-records the first and
# `scripts/generate-strikethrough-corpus.py` the second, so "verified against
# 9.12" is a command, not a sentence. The generator exists because the two
# previous hand-derived versions of this rule were both wrong, and the second
# was wrong while passing 168 hand-picked cases.
#
# The predecessor of this code was a single regex that flagged any
# whitespace-preceded dash run followed by a word character. It was wrong in
# both directions, which is why Jira kept mangling text that had passed the
# lint while the lint kept bouncing text Jira renders fine:
#
#   * FALSE POSITIVE, the common case: `journalctl -b -p crit` renders
#     literally. A dash that LEADS a word can never close a span (a closer
#     needs a non-space before it), so two flags cannot pair with each other.
#     They are NOT harmless in general: add a trailing-dash word later on the
#     same line and `-b ... zu-` is struck end to end.
#   * FALSE NEGATIVE, the damaging case: `{{nr-pforum}}-Extensions ... zu- und`
#     is struck through end to end (issue #226). Any inline element's closing
#     punctuation - `}}`, `*`, `_`, `]`, `!`, `{color}` - is a non-word
#     character and therefore a valid opener boundary, and a German elliptical
#     compound (`zu- und`) is a valid closer.
# ─────────────────────────────────────────────────────────────────────────────


def _is_escaped(line: str, pos: int) -> bool:
    """True when the character at ``pos`` is neutralised by a preceding backslash.

    Backslash parity is deliberately ignored: Jira treats the dash as literal
    in both ``\\-`` and ``\\\\-`` (the latter because ``\\\\`` is its
    forced-line-break macro), and over-reading an escape can only ever cost a
    redundant escape, never a missed span.
    """
    return pos > 0 and line[pos - 1] == "\\"


def _is_delimiter_space(ch: str) -> bool:
    """Whitespace for the purpose of the dash delimiters - ASCII only.

    ``str.isspace()`` is wrong here and wrong in the direction that mangles
    text: it counts U+00A0, and Jira does not. Measured, ``a -x\u00a0- y``
    comes back struck through, so a non-breaking space before the closing dash
    does NOT disqualify it - while a plain space does (``a -x - y`` is clean).
    NBSP arrives routinely in text pasted out of Word or Outlook.

    This is NOT the same class as the ``\\s`` in ``_PROTECTED_RE``, and making
    the two agree would be a regression. Jira's URL autolinker DOES stop at
    U+00A0 (``https://h/a\u00a0/-/b`` links only ``https://h/a``), so ``\\s``
    is correct there and ASCII-only is correct here. A review proposed
    unifying them; the renderer says they are two different rules.
    """
    return ch in " \t\x0b\x0c\r"


def _is_word_char(ch: str) -> bool:
    """Jira's word class for text effects: Unicode letters and digits only.

    Measured, because this is where a regex ``\\w`` would be wrong in both
    directions: ``Gr(oe)sse-x- y`` and ``a(ae)-x- y`` stay literal (a non-ASCII
    letter IS a word character), while ``a_-x- y`` opens a span (``_`` is NOT).
    """
    return ch.isalnum()


# Regions Jira resolves into a single element BEFORE text effects run, so a
# dash inside them is never a delimiter. Measured: the `/-/` in a GitLab URL is
# inert inside `[MR|https://host/g/p/-/merge_requests/5]` and in the same URL
# written bare, and in `!-x.png!` - but the SAME `/-/` in plain prose
# (`a /-/ zu- b`) does open a span. Escaping a dash inside a URL would break
# the link, so these must be masked out before scanning.
#
# `{{monospace}}` is deliberately NOT in this list: text effects do apply
# inside it (`{{-x-}}` comes back struck), which is the one place the old
# implementation was right.
# A bare URL runs to whitespace or to the next `{`, `}`, `]` or `|` - measured:
# `https://h/a/-/b{{m}}` links only up to the brace, while `...b*b*` links the
# lot. Stopping too late is the dangerous direction, because the mask then
# swallows real markup and hides the dashes in it.
#
# A bare URL after a pipe or an exclamation mark is NOT autolinked - Jira expects that shape inside
# [text|url], so standalone it stays literal and its dashes stay live
# (`x a|https://h/a/-/b zu- y` and `x !https://h/a/-/b zu- y` both come back
# struck, while `]`, `}` and `*` before the same URL leave it linked).
# A backslash-escaped bracket
# or bang is not a macro either, so its content is ordinary prose.
#
# A region only resolves at a boundary, and one that does NOT resolve leaves
# its dashes live - masking it anyway would be a false negative, the direction
# that mangles text. The boundary class is ASCII alphanumerics, measured:
# `x ahttp://…/-/b- y` comes back struck (not autolinked, so `/-/` is prose),
# while `x _http://…/-/b- y` and `x ähttp://…/-/b- y` are clean (autolinked).
_PROTECTED_RE = re.compile(
    r"""
    (?<!\\)
    (?:
      \[[^\]\n]*\]                              # a square-bracketed link
    | (?<![A-Za-z0-9|!])(?:https?|ftp)://[^\s{}\]|]+  # bare URL - needs a boundary
    | (?<![A-Za-z0-9|!])mailto:[^\s{}\]|]+
    | (?<![A-Za-z0-9])![^\s!]+!                  # image or attachment
    )
    """,
    re.VERBOSE,
)

_MASK = "\x01"  # not a word character, so a masked region still ends a boundary
# (\x01 rather than NUL: the awk mirror in validate-jira-syntax.sh cannot carry
# a NUL through a string, and the two implementations are pinned to each other.)


def _mask_protected(line: str) -> str:
    """Blank out protected regions, preserving length so indices stay valid.

    Two regions written back to back do not both resolve - Jira renders the
    first and leaves the second as literal text, dashes and all
    (`[t|https://h/a/-/b][t|https://h/a/-/b]` comes back with the second one
    struck through). So a match that begins exactly where the previous one
    ended is skipped rather than masked.

    Only the immediately following region is skipped, not a whole run: in
    `[a][b][c]` the third is masked again. Whether Jira resolves that third one
    is not measured. The awk mirror implements the same rule, and the
    whole-corpus parity test holds it to that on every recorded case - which is
    how a divergence here was caught once already: awk used to resume INSIDE
    the skipped region and mask a shorter one nested in it. The glued-region
    shapes this still gets wrong are pinned in the corpus fixture as known
    under-predictions.
    """
    out = list(line)
    previous_end = -1
    for match in _PROTECTED_RE.finditer(line):
        if match.start() == previous_end:
            continue
        out[match.start() : match.end()] = _MASK * (match.end() - match.start())
        previous_end = match.end()
    return "".join(out)


def find_strikethrough_spans(line: str) -> list[tuple[int, int]]:
    """Return ``(opener, closer)`` index pairs Jira renders struck through.

    One line at a time - a span never crosses a newline. The caller is
    responsible for skipping ``{code}``/``{noformat}`` content, where dashes
    are literal.

    The grammar, measured against Jira Server 9.12:

    * **Opener** - an unescaped ``-`` at line start or after a non-word
      character, followed by a character that is neither whitespace nor another
      dash. The boundary is why ``{{mono}}-Extensions`` opens a span and
      ``Round-1`` does not: ``}`` is a non-word character, ``d`` is not.
    * **Closer** - the first *valid* closer after it: an unescaped ``-`` not
      preceded by whitespace and followed by a non-word character or line end.
      A dash that fails those conditions is skipped, not fatal - which is why
      ``journalctl -b -p crit … zu-`` IS struck end to end while
      ``journalctl -b -p crit`` on its own is not: a dash that leads a word can
      never close, so flags alone have no closer at all.

    In a dash run the opener is the last dash and the closer the first, so
    ``a --foo-- b`` strikes ``foo`` and leaves the outer dashes literal.

    Whitespace here is ASCII only: Jira treats U+00A0 as an ordinary character,
    so a non-breaking space before the closing dash does not disqualify it.

    **This is a superset, on purpose.** Jira abandons an opener whose body
    begins with a single character followed by a dash (``a -a-b- z`` renders
    literally, while ``a -ab-cd- z`` is struck); that quirk is recorded in the
    fixture but not modelled, because the only cost of predicting a span Jira
    would not draw is one redundant ``\\-``, which renders as a plain hyphen,
    whereas the cost of missing one is mangled text. ``tests/test_strikethrough.py``
    pins both directions: zero UNLISTED false negatives against the recorded
    corpus - eleven are listed - and the list of known over-predictions, so
    neither can grow unnoticed.

    **It is not exact, and cannot be.** Jira substitutes autolinked issue keys
    before text effects run, so ``OPS-899-x … zu-`` is struck on an instance
    where OPS-899 exists and clean on one where it does not - the same string,
    two renderings. No source-level model can decide that. The pre-flight
    render check in ``jira-comment.py`` is what covers it.
    """
    spans: list[tuple[int, int]] = []
    scan = _mask_protected(line)
    n = len(scan)
    i = 0
    while i < n:
        if scan[i] != "-" or _is_escaped(scan, i):
            i += 1
            continue
        # Opener: boundary before, and neither whitespace nor a dash after.
        if i > 0 and _is_word_char(scan[i - 1]):
            i += 1
            continue
        if i + 1 >= n or _is_delimiter_space(scan[i + 1]) or scan[i + 1] == "-":
            i += 1
            continue

        closer = _find_closer(scan, i)
        if closer is None:
            i += 1
            continue
        spans.append((i, closer))
        i = closer + 1
    return spans


def _find_closer(scan: str, opener: int) -> int | None:
    """First index after ``opener`` holding a dash that can close a span."""
    n = len(scan)
    for j in range(opener + 2, n):
        if scan[j] != "-" or _is_escaped(scan, j):
            continue
        if _is_delimiter_space(scan[j - 1]):
            continue
        if j + 1 < n and _is_word_char(scan[j + 1]):
            continue
        return j
    return None


def _escape_dash_run(line: str, opener: int) -> str:
    """Backslash-escape the whole dash run that ``opener`` belongs to.

    Escaping the opener alone is not enough, and the gap is easy to miss: in
    ``{{--strict}} foo bar-`` the opener is the SECOND dash, and neutralising
    just that one promotes the first to opener - the span survives, measured.
    Escaping the run closes it. ``\\-`` renders as a plain hyphen, so the
    repair is invisible to the reader.
    """
    start = opener
    while start > 0 and line[start - 1] == "-" and not _is_escaped(line, start - 1):
        start -= 1
    end = opener
    while end + 1 < len(line) and line[end + 1] == "-":
        end += 1
    run = line[start : end + 1].replace("-", "\\-")
    return line[:start] + run + line[end + 1 :]


# Only these two render their content verbatim. {quote} and {panel} still parse
# text effects (measured: `{panel}\na {{m}}-x- b\n{panel}` comes back with a
# <del>), so a dash inside them is exactly as dangerous as one in bare prose.
_VERBATIM_TAGS = ("code", "noformat")
_VERBATIM_RE = re.compile(r"^\s*(?<!\\)\{(" + "|".join(_VERBATIM_TAGS) + r")(?::[^}\n]*)?\}\s*$")


def _split_verbatim(text: str):
    """Yield ``(line, is_verbatim)`` for every line, tracking {code}/{noformat}.

    A tag line is itself reported as verbatim: it is markup, not prose, and
    neither the dash scan nor the escaper has any business rewriting it.
    """
    open_tag: str | None = None
    for line in text.split("\n"):
        m = _VERBATIM_RE.match(line)
        if open_tag is not None:
            yield line, True
            if m is not None and m.group(1) == open_tag:
                open_tag = None
        elif m is not None:
            open_tag = m.group(1)
            yield line, True
        else:
            yield line, False


def escape_strikethrough(text: str) -> str:
    """Neutralise every dash Jira would read as a strikethrough opener.

    Returns text that renders identically to what the author meant: ``\\-`` is
    a plain hyphen on the page. Content inside ``{code}``/``{noformat}`` is
    left untouched, where a dash is literal already.

    Escaping is iterated to a fixed point per line, because repairing one span
    can expose the next: in ``a -x- -y- b`` the second pair only becomes
    reachable once the first stops consuming its dashes.

    The loop stops if an iteration fails to change the line. Every escape
    strictly reduces the number of unescaped dashes, so that cannot happen
    today - but this runs in the posting path, where a future edit that made
    the repair a no-op would otherwise hang the caller rather than fail it.
    (Not hypothetical: neutering ``_escape_dash_run`` in a mutation run hung
    the whole test suite.) A line the repair cannot converge on is left as it
    is and reported by ``lint_wiki_markup``, which callers run afterwards.
    """
    out: list[str] = []
    for line, verbatim in _split_verbatim(text):
        if not verbatim:
            while spans := find_strikethrough_spans(line):
                repaired = _escape_dash_run(line, spans[0][0])
                if repaired == line:
                    break
                line = repaired
        out.append(line)
    return "\n".join(out)


def lint_wiki_markup(text: str) -> list[str]:
    """Return a list of human-readable lint findings (empty = clean)."""
    findings: list[str] = []
    counts = dict.fromkeys(BLOCK_TAGS, 0)
    in_block: str | None = None

    # Verbatim tracking is separate from the block-balance state machine below:
    # that one guards all four tags, while only {code}/{noformat} suppress text
    # effects. Inside a {quote} or {panel} a dash still strikes through.
    verbatim_flags = [v for _, v in _split_verbatim(text)]

    for lineno, line in enumerate(text.split("\n"), 1):
        matches = list(_TAG_RE.finditer(line))

        # Runs before the in_block short-circuit: {quote}/{panel} content is
        # skipped by that state machine but is NOT verbatim to Jira.
        if not verbatim_flags[lineno - 1]:
            for opener, closer in find_strikethrough_spans(line):
                findings.append(
                    f"line {lineno}: {line[opener : closer + 1]!r} renders struck through - "
                    f"Jira reads a dash after a non-word character as a strikethrough "
                    f"opener (an inline element's closing {{{{}}}}, *, _, ] or ! counts) "
                    f"and a dash before one as the closer; escape it as \\- (a "
                    f"backslash-escaped dash still prints as a plain hyphen)"
                )

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
