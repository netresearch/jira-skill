# Comments — Edit, Delete, List

## When to load

Load this reference whenever the user wants to edit or delete an existing comment, list comments, or needs to get a comment ID for any reason.

## List and get IDs

```bash
# Pretty list (most recent last)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py list PROJ-123

# JSON list — use this to harvest comment IDs for edit/delete
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py --json list PROJ-123
```

The JSON output has a top-level `comments` array; each entry has `id`, `author.displayName`, `body`, and `updated`.

### `list` shows ten comments by default — pass `--limit 0` when you are reading, not harvesting

```bash
# The whole history, paginated for you
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py list PROJ-123 --limit 0
```

Ten is the right default for grabbing a recent comment ID. It is the wrong default for answering a question about what a ticket says, and the difference is invisible in the answer: a busy ticket carries its decisions in the middle of its history, and the last ten comments are the part that agreed with you. When the read informs a claim — a QA verdict, a status report, "nobody mentioned X" — use `--limit 0`.

A truncated read now says so on **stderr** as well as in the table, so the notice survives a pipe and appears under `--json` and `--quiet` too. If you see `⚠ PROJ-123: showing 10 of 163 comments`, the answer you are about to give is based on 10.

### Never put a line filter between `list` and your eyes

`| head`, `| tail`, `| grep`, `--max-count` — each of them cuts a comment body mid-sentence and drops whole comments silently, and what is left looks like a complete answer. "X does not appear in this ticket" after a truncated read is a statement about the cut, not about the ticket; it has been wrong in exactly that way, in a public comment that someone else had to correct.

Use the tool's own knobs instead, which cut where the data says to cut rather than where the terminal does:

```bash
# Shorten every body to N characters, keeping all comments and their metadata
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py list PROJ-123 --limit 0 --truncate 200

# Or select deliberately, in a structured way
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py --json list PROJ-123 --limit 0 \
  | jq -r '.[] | select(.author.name == "someone") | .body'
```

For a body too large to read in one go, write it to a file and read windows of it — the file keeps the whole thing while you look at part of it, which is the property a pipe destroys.

## Edit an existing comment

```bash
# Full replacement of the body — edits preserve created timestamp, update the "updated" timestamp
# (issue key, comment ID and text are positional arguments)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py edit PROJ-123 594276 "Corrected text"
```

Jira appends an "edited" marker in the UI automatically.

## Delete a comment

```bash
# Preview
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py delete PROJ-123 594276 --dry-run

# Real delete
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py delete PROJ-123 594276
```

Non-interactive: no confirmation prompt, no stdin — `--dry-run` is the preview, the real call deletes on the spot (no `echo y |` needed). Deleting someone else's comment requires the Delete All Comments permission.

## Multi-line comments

`jira-comment.py add` takes the body as a positional argument. Pass `-` to read the body from stdin, which pairs naturally with a HEREDOC or a file:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py add PROJ-123 - <<'EOF'
h3. Progress

Deployed to staging, see https://staging.example.com/.
EOF

# Or from a file
cat comment.txt | uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py add PROJ-123 -
```

Comments use Jira wiki markup — see the **jira-syntax** skill for formatting.

## Markup lint

`add` and `edit` lint the body before posting: inline block tags (`{code}`, `{noformat}`, `{quote}`, `{panel}` are block-level — a tag with other text on the same line opens a block mid-prose) and unbalanced tag counts abort with an error. Escape literal tag mentions as `\{code\}`. Override with `--force` (findings are then printed as warnings).

Dashes that Jira would render as a strikethrough span are **repaired rather than reported**: `add` and `edit` escape them before posting and print on stderr which lines they changed. `\-` prints as a plain hyphen, so the posted text reads as written. `--no-auto-escape` keeps the markup verbatim, but does not by itself post a comment with a live span — the lint and the render check each refuse it independently, so a deliberate strikethrough needs `--no-auto-escape --force`. The grammar is measured against a live Jira Server 9.12 renderer (`tests/fixtures/strikethrough_oracle.json`, re-recorded by `scripts/verify-render-oracle.py --live`), which matters because the shape is counter-intuitive in both directions: `journalctl -b -p crit` is safe (a dash leading a word cannot close a span), while `{{nr-pforum}}-Extensions ... zu- und abschaltbar` is struck through end to end. See the quick reference in the `jira-syntax` skill for the full rule.

The same lint carries a **ticket-language reminder**. Some projects are English-only by team convention (the rule and the project list live in the consuming team skill; the check ships with `NRS`, `NRT`, `SRV*`, `IO*`, `LIC`, `PO`), and language drift is invisible in review because such tickets often already contain German from quoted mails. When a comment on one of those keys reads as German prose — five or more distinct German function words, which a loanword or a short quoted fragment stays below — the lint says so and names the markers it found. The scan reads the whole body and cannot tell a quote from authored text, so a comment carrying a *substantial* German quote is reported too; `--force` is how you post it verbatim. Other projects, customer ones included, are never touched by this check.

Every command that posts mention-capable wiki markup runs the same mention gate: `jira-comment add`/`edit`, `jira-transition do --comment`, `jira-worklog add --comment`, and the `--description` of `jira-create issue` / `jira-issue update`. Each `[~username]` is verified against Jira before posting (an unverified mention renders as dead text and notifies nobody); an unknown username aborts with candidate suggestions rendered in the form that actually notifies (`[~name]` on Server/DC, `[~accountid:...]` on Cloud, where a plain `[~username]` can never notify and is always flagged). Mentions inside `{code}`/`{noformat}` blocks and backslash-escaped literals (`\[~...]`) are ignored — quoting a log line does not trip the gate. Auth or transport failures abort with the real error, never as "unknown user". Skip with `--no-verify-mentions`.

## Verify rendering after posting

A 2xx on `add`/`edit` proves the write landed, not that the markup renders as intended — Jira renders wiki markup server-side. The rendered HTML is the only proof:

```bash
curl -s -H "Authorization: Bearer $JIRA_PERSONAL_TOKEN" \
  "$JIRA_URL/rest/api/2/issue/<KEY>/comment/<id>?expand=renderedBody" | jq -r '.renderedBody'
```

Grep it for what you fear: `<del>` means something parsed as strikethrough (the dash trap — see the lint above), a literal `\` means a backslash escape reached the reader, and `&#45;` is a correctly escaped dash. Run this after editing any markup-sensitive comment; verified against Jira Server 9.12.

## Comment verbosity: depth for the failing path only

Working-path checks get ONE summary line at most; the non-working path gets the depth; obvious/derivable steps are cut entirely. A human reader cannot filter long tables that mostly say "this works" — verbose investigation comments cause overload and force the reader to re-derive what mattered.

## Consolidate progress updates — edit, don't append

When iterative work on one issue produces multiple status updates, edit the prior comment instead of adding a new one. Watchers and QA reviewers are notified per comment and must wade through progress chatter to find the current state. Reserve new comments for genuinely separate story beats that build on (not restate) earlier ones.
