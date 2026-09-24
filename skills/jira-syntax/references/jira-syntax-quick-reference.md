# Jira Wiki Markup Syntax - Quick Reference

Complete reference for Jira's wiki markup syntax to ensure proper formatting in tickets, comments, and descriptions.

## Table of Contents

- [Text Formatting](#text-formatting)
- [Headings](#headings)
- [Lists](#lists)
- [Links](#links)
- [Code Blocks](#code-blocks)
- [Tables](#tables)
- [Panels and Quotes](#panels-and-quotes)
- [Colors](#colors)
- [Special Blocks](#special-blocks)
- [Line Breaks and Horizontal Rules](#line-breaks-and-horizontal-rules)
- [Special Characters](#special-characters)
- [Checklist Markers](#checklist-markers)
- [Validation Checklist](../SKILL.md#validation-checklist)
- [Common Mistakes](../SKILL.md#common-mistakes)

## Text Formatting

| Syntax | Output | Use Case |
|--------|--------|----------|
| `*text*` | **text** | Bold/strong emphasis |
| `_text_` | *text* | Italic/emphasis |
| `{{text}}` | `text` | Monospace for code/paths |
| `-text-` | ~~text~~ | Strikethrough |
| `+text+` | <u>text</u> | Underline/inserted text |
| `^text^` | text^superscript^ | Superscript |
| `~text~` | text~subscript~ | Subscript |
| `??text??` | text (citation) | Citation format |

## Headings

```
h1. Heading Level 1 (largest)
h2. Heading Level 2
h3. Heading Level 3
h4. Heading Level 4
h5. Heading Level 5
h6. Heading Level 6 (smallest)
```

Space required after the period (`h2. Title`, not `h2.Title`).

## Lists

### Bulleted Lists
```
* Level 1 item
** Level 2 nested item
*** Level 3 nested item
* Another level 1 item
```

### Numbered Lists
```
# First item
## Nested item
## Another nested item
# Second item
```

### Mixed Lists
```
# Numbered item
#* Nested bullet
#* Another bullet
# Another numbered item
```

**Rules:**
- Space after `*` or `#`
- Nesting uses additional symbols (`**`, `##`), not indentation
- Can mix list types with combined syntax (`#*`)

## Links

| Type | Syntax | Example |
|------|--------|---------|
| Issue Link | `[KEY-123]` | `[PROJ-456]` |
| User Mention | `[~username]` | `[~john.doe]` |
| External URL | `[http://url]` | `[http://example.com]` |
| Labeled Link | `[Label\|url]` | `[Google\|http://google.com]` |
| Attachment | `[^filename]` | `[^screenshot.png]` |
| Email | `[mailto:email]` | `[mailto:team@example.com]` |
| Anchor | `{anchor:name}` + `[#name]` | `{anchor:intro}` → `[#intro]` |

## Code Blocks

### Inline Code
Use `{{text}}` for inline monospace text.

### Code Blocks with Syntax Highlighting
```
{code:java}
System.out.println("Hello, World!");
{code}
```

**Supported Languages (Jira Server / Data Center):**

The Jira Server source-code formatter accepts ONLY this fixed list. Using any other identifier (e.g. `typoscript`, `rust`, `typescript`, `yml`, `shell`) produces:

> Unable to find source-code formatter for language: `<name>`. Available languages are: ...

| Group | Identifiers |
|-------|-------------|
| General-purpose | `actionscript`, `ada`, `applescript`, `c`, `c#`, `c++`, `cpp`, `erlang`, `go`, `groovy`, `haskell`, `java`, `javascript`, `js`, `lua`, `objc`, `perl`, `php`, `python`, `r`, `ruby`, `scala`, `swift`, `visualbasic` |
| Shell / scripting | `bash`, `sh` |
| Data / markup | `css`, `html`, `json`, `sql`, `xml`, `yaml` |
| Special | `none` (no highlighting), `nyan`, `rainbow` |

**Notes:**
- Use `c#` / `c++` literally, not `csharp` / `cplusplus` (though `cpp` is also accepted).
- There is no `typescript`, `rust`, `kotlin`, `dart`, `powershell`, `shell`, `yml`, `dockerfile`, `terraform`, or `typoscript` formatter.
- For unsupported languages, fall back to `{code:none}` (or `{noformat}`) to preserve the block without highlighting.

```
{code:none}
[request && request.getNormalizedParams().getHttpHost() == "backend.example.de"]
page.meta.robots = noindex,noarchive
[END]
{code}
```

### Preformatted Text (No Highlighting)
```
{noformat}
Plain text without syntax highlighting
Preserves whitespace and formatting
{noformat}
```

### Block Tags Are Never Inline

`{code}`, `{noformat}`, `{quote}` and `{panel}` are **block-level** macros: the tag must stand alone on its own line. An unescaped tag inside a prose sentence opens a real block mid-line and swallows the rest of the line — the classic failure is writing *about* code blocks.

Broken — renders everything after "in" as an opened code block:

```
All commands are documented in {code} blocks with output.
```

Correct — renders the literal text `{code}`:

```
All commands are documented in \{code\} blocks with output.
```

Escape literal mentions of any block tag with backslashes: `\{code\}`, `\{noformat\}`, `\{quote\}`, `\{panel\}`. For inline monospace use `{{...}}`, never an inline `{code}` pair — even `{code}one-liner{code}` renders as a block, not inline.

`scripts/validate-jira-syntax.sh` flags inline block tags and unbalanced tag counts; run it on composed text before submitting to Jira.

## Tables

### Basic Table
```
||Header 1||Header 2||Header 3||
|Cell A1|Cell A2|Cell A3|
|Cell B1|Cell B2|Cell B3|
```

**Rules:**
- `||` for header cells (double pipe)
- `|` for regular cells (single pipe)
- Rows must have same number of cells
- No trailing pipe at end of row

## Panels and Quotes

### Panel with Title and Background
```
{panel:title=Important Information|bgColor=#FFFFCE}
Content inside the panel
{panel}
```

**Panel Parameters:**
- `title=text` - Panel heading
- `bgColor=#HEXCODE` - Background color
- `borderStyle=solid|dashed` - Border style
- `borderColor=#HEXCODE` - Border color
- `titleBGColor=#HEXCODE` - Title background

### Quote Block
```
{quote}
Multi-line quoted text
Can span multiple paragraphs
{quote}
```

### Single Line Quote
```
bq. This is a block quote on one line
```

## Colors

```
{color:red}Red text{color}
{color:blue}Blue text{color}
{color:green}Green text{color}
{color:#FF0000}Hex color text{color}
```

Named colors (`red`, `blue`, `green`, `yellow`, `orange`, `purple`, `black`, `white`, `gray`/`grey`) or any hex code work as the macro parameter.

## Special Blocks

### Expand/Collapse Section
```
{expand:title=Click to expand}
Hidden content that can be toggled
{expand}
```

## Line Breaks and Horizontal Rules

```
Line 1\\
Line 2 (line break with \\)

First paragraph

Second paragraph (blank line creates new paragraph)

----
Horizontal rule (4 dashes)
```

## Special Characters

```
--- (em-dash: —)
-- (en-dash: –)
\\ (line break)
\{escaped brace\}
```

To escape special characters, use backslash: `\*`, `\{`, `\[`.

- **Only escape characters Jira actually parses as markup** — `*`, `_`, `-`, `+`, `^`, `~`, `{`, `[`, `|`, `\`. Do **not** escape plain punctuation such as `.`, `,`, or `:` — `\.` renders the backslash literally and produces the wrong output.
- **Never escape inline monospace** — `{{text}}` is not a macro, so `\{\{text\}\}` is wrong. Only escape the opening brace of a *macro name* shown as prose (e.g. `\{code\}`).
- **Preserve existing backslash escapes** — a source `\*`, `\_`, or `\{` already suppresses Markdown markup; keep it as-is, because Jira uses the same `\` escape mechanism for the same characters.

### Common gotcha: macro names in prose

Writing a macro name literally in prose (e.g. *"commands wrapped in \{code\} blocks"*) without escaping breaks rendering — Jira parses the literal as the *start* of a code-block macro and either consumes the rest of the comment or pairs with the next unrelated occurrence it finds. The same trap applies to any macro that opens and closes with the same token: `{noformat}…{noformat}`, `{quote}…{quote}`, `{color}…{color}`, `{panel}…{panel}`, `{anchor}…{anchor}`, and so on.

Three ways to write the literal token safely, in order of preference:

| Approach | Example | When to use |
|----------|---------|-------------|
| Rephrase to avoid the token | `commands shown as code blocks` | First choice — readers don't need the macro name to understand the prose |
| Backslash-escape | `\{code\}` | When you genuinely need to show the macro name |
| Wrap in a code span | `` `{{code}}` `` | Last resort — some style guides ban inline `{{monospace}}` in favour of bold `*term*` for technical terms |

The backslash escape is the official Jira mechanism; the rephrase is editorial; the `{{monospace}}` wrap renders fine but is disliked by teams that reserve monospace for actual code spans rather than inline references.

### Common gotcha: prose struck through by `-text-`

`-text-` is strikethrough. The grammar below is measured against a live Jira Server 9.12 wiki renderer, and the recorded cases are kept in the source repo (netresearch/jira-skill), not in the standalone skill package; it is not a rule of thumb, and an earlier version of this section stated it wrongly in both directions.

> **opener** — an unescaped `-` at line start or after a **non-word character**, followed by neither whitespace nor another dash
> **closer** — the next *valid* closer: an unescaped `-` that is not preceded by whitespace and is followed by a non-word character or line end; a dash failing either condition is skipped over, not fatal
> **body** — anything in between; a dash that fails the closer conditions is skipped over, not fatal

Two consequences are worth stating on their own, because both are the opposite of what the shape suggests.

**A pair of CLI flags is not a span — on its own.** `journalctl -b -p crit` renders literally, and so do `--strict ... -v` and `offset by -5 seconds`, because a dash that *leads* a word can never close a span, so flags cannot pair with each other. They are not immune, though: put a trailing-dash word anywhere later on the same line and the flag becomes the opener — `journalctl -b -p crit zeigt die Fehler; das Modul ist zu- und abschaltbar.` is struck from `-b` to `zu-`.

**The real trap is a dash after an inline element, closed by a trailing-dash word.** Any inline element's closing punctuation — `}}`, `*`, `_`, `]`, `!`, `{color}` — is a non-word character, so `{{nr-pforum}}-Extensions` opens a span; a German elliptical compound (`zu- und abschaltbar`) or any other word ending in a dash then closes it, and everything between renders struck through. German prose produces this shape routinely. A single flag also becomes dangerous once such a closer appears later on the same line: `with -v and a trailing word- here`.

Exempt, and not to be escaped: a dash inside a word (`Round-1`, `2026-09-04`, `Größe-x`), a leading dash with no closer anywhere on the line, em/en-dash typography (`---`, `--`), list bullets (`- item`), Unicode dashes (`–`, `—`), and anything inside `{code}`/`{noformat}`. `{quote}` and `{panel}` are **not** exempt — Jira parses text effects inside them.

The fix is to backslash-escape the whole dash run that opens the span: `{{nr-pforum}}\-Extensions`. A `\-` reaches the rendered HTML as `&#45;` and prints as a plain hyphen, so the reader sees no difference. Escaping only part of a run does not work: in `{{--strict}}` the opener is the *second* dash, and neutralising just that one promotes the first — write `{{\-\-strict}}`. Putting the command in a `{code}` block avoids the question entirely.

You normally do not have to do any of this by hand. Every `jira-communication` option that writes wiki markup — `jira-comment.py add`/`edit`, `jira-transition.py do --comment`, `jira-transition.py path --comment`, `jira-worklog.py add --comment`, and the `--description` of `jira-create.py issue` and `jira-issue.py update` — escapes these spans automatically before posting and report on stderr which lines they changed (`--no-auto-escape` keeps the markup verbatim; posting a deliberate span needs `--no-auto-escape --force`, because the lint and the render check each still refuse it). For a draft that does not go through those scripts, run `skills/jira-syntax/scripts/validate-jira-syntax.sh <file>` on it (from the repo root). The script verifies that the six paired macros (`code`, `panel`, `color`, `noformat`, `quote`, `anchor`) are balanced — every opener matches a closer, even with a language tag like `{code:bash}` — and catches Markdown leakage (` ``` ` fences, `[text](url)` links, `` `code` `` spans), language declarations Jira Server does not recognise, malformed table headers, and dash pairs outside code blocks that would render struck through.

## Checklist Markers

`(/)` and `(x)` are the conventional checklist markers: `(/)` for a completed
item, `(x)` for an open one. Use them only with that meaning.

- Do not put `(/)` on items that are merely proposed or not yet implemented.
  It renders as a green check and reads as "done".
- `( )` (empty parentheses) is **not** a macro. It renders literally as two
  parentheses, so it conveys nothing. For an open item use `(x)`, or a plain
  bullet when no status is intended.

```
* (/) Migration script written and tested
* (x) Rollback procedure documented
```

What each marker draws, from the render endpoint of Jira Server 9.12:

| Markup | Icon | Reads as |
| --- | --- | --- |
| `(/)` | green check (`check.png`) | done |
| `(x)` | red cross (`error.png`) | failed, or open in a plain checklist |
| `(!)` | warning triangle (`warning.png`) | needs attention |
| `(i)` | blue info (`information.png`) | note |
| `(?)` | question mark (`help_16.png`) | unclear |
| `(off)` | grey light bulb (`lightbulb.png`) | not applicable, inactive |
| `(-)` | red no-entry sign (`forbidden.png`) | forbidden |

In a review or QA comment, `(x)` already means a blocking failure, so it cannot also
mean "not done yet". Mark a step that is still pending with `(i)` and the word
"pending", or with a plain bullet. Never use `(-)` for it: the red no-entry sign
reads as "must not be done". Three of seven tickets in one maintenance window marked
pending steps that way.

```
* (/) Service updated to 19.4.1
* (i) pending: runner manager, after the service is verified
```

## Ask the renderer instead of reasoning about it

Jira renders wiki markup server-side, and it will tell you what it is going to do — for any markup, before anything is posted:

```bash
curl -s -H "Authorization: Bearer $JIRA_PERSONAL_TOKEN" -H 'Content-Type: application/json' \
  -X POST "$JIRA_URL/rest/api/1.0/render" \
  -d '{"rendererType":"atlassian-wiki-renderer","unrenderedMarkup":"Die {{a}}-Extensions, jede zu- und abschaltbar","issueKey":null}'
```

This is the endpoint behind Jira's own preview button. It is Server/DC only (Cloud uses ADF and has no equivalent), it needs no issue, and it writes nothing. It rate-limits with HTTP 429 above roughly three to eight parallel requests, so a batch run needs backoff.

**It is the same renderer that stores a comment.** Verified by rendering the full 1185-character source of an existing comment and diffing against that comment's stored `renderedBody` (`GET /rest/api/2/issue/<KEY>/comment/<id>?expand=renderedBody`) — byte-identical. So the preview is proof, not an approximation.

Use it whenever a claim about Jira markup is about to be written down — in a lint, a ticket, a reference page like this one. It costs one call and it settles the question. Two successive hand-derived versions of the strikethrough rule in this repo were wrong in opposite directions, and the second passed 168 hand-picked cases while still being wrong; a generated corpus rendered through this endpoint found the defect in minutes. Two runners built on it — one to re-record the curated cases, one to generate and record a corpus — live in the source repo (netresearch/jira-skill), not in the standalone skill package; the curl above is the whole technique and needs neither.

Two things it cannot settle, because they are not in the markup:

- **Instance state.** Jira substitutes autolinked issue keys before text effects run, so `OPS-899-x ... zu-` renders struck through where OPS-899 exists and literally where it does not. Render against the instance you will post to.
- **What the markup was meant to say.** The renderer answers "what will this look like", never "is this what you wanted".

## Validation is a gate, not a formality

`scripts/validate-jira-syntax.sh` only helps if its **result** is read before
the content is posted. Run it as its own step:

```bash
validate-jira-syntax.sh comment.txt   # read the result
# only then:
jira-comment.py add PROJ-123 -        # body piped from the same file
```

Never chain it with the posting command. With `;` the comment posts even
though validation failed; with `&&` the report scrolls past unread. Either way
the broken comment is already on the ticket and needs a follow-up edit —
visible to everyone watching it.

### Frequent catch: braces inside a monospace span

`${VAR}` (or any `{`/`}`) inside `{{...}}` breaks the span — the Jira parser
renders it as raw text:

```
{{traefik.http.middlewares.office-allow-${ENVIRONMENT}.ipallowlist.sourcerange}}
```

The validator reports:

```
ERROR: Found unescaped { or } inside {{...}} monospace block — Jira parser
will render it as raw text. Escape as \{ \} or split the reference.
```

Escape the braces as `\{ \}`, split the reference, or move the whole line into
a `{code}` block — a `{code}` block is usually the most readable for anything
command-shaped.
