"""Jira wiki-markup lint helpers.

Catches the most damaging authoring mistakes before text is sent to Jira:

- Block-markup tags ({code}, {noformat}, {quote}, {panel}) used inline.
  These are block-level macros; an unescaped tag with other text on the
  same line opens a real block mid-prose and swallows the rest of the
  line. Literal mentions must be escaped as \\{code\\}.
- Unbalanced block tags (odd occurrence count), which leave an unclosed
  block that swallows everything after it.

Escaped tags (\\{code\\}), inline-monospace lookalikes ({{code}}) and
*other* tags inside an open block are ignored. An occurrence of the
*same* tag inside an open block closes it — exactly what the Jira
renderer does (verified against Jira Server 9.12: a mid-line {code}
inside a code block terminates the block there).
"""

import re

BLOCK_TAGS = ("code", "noformat", "quote", "panel")

# Unescaped block tag, optionally with parameters ({code:bash}, {panel:title=x}).
# (?<!\{) keeps {{code}} / {{panel}} (inline monospace content) out of scope.
_TAG_RE = re.compile(r"(?<!\\)(?<!\{)\{(code|noformat|quote|panel)(?::[^}\n]*)?\}")


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
