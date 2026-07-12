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

A quick sanity check before posting: run `skills/jira-syntax/scripts/validate-jira-syntax.sh <file>` on your draft (from the repo root). The script verifies that the six paired macros (`code`, `panel`, `color`, `noformat`, `quote`, `anchor`) are balanced — every opener matches a closer, even with a language tag like `{code:bash}` — and catches Markdown leakage (` ``` ` fences, `[text](url)` links, `` `code` `` spans), language declarations Jira Server does not recognise, and malformed table headers.

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
