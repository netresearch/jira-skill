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

Deleting someone else's comment requires the Delete All Comments permission.

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

`add` and `edit` lint the body before posting: inline block tags (`{code}`, `{noformat}`, `{quote}`, `{panel}` are block-level — a tag with other text on the same line opens a block mid-prose) and unbalanced tag counts abort with an error. Escape literal mentions as `\{code\}`. Override with `--force` (findings are then printed as warnings).

## Comment verbosity: depth for the failing path only

Working-path checks get ONE summary line at most; the non-working path gets the depth; obvious/derivable steps are cut entirely. A human reader cannot filter long tables that mostly say "this works" — verbose investigation comments cause overload and force the reader to re-derive what mattered.

## Consolidate progress updates — edit, don't append

When iterative work on one issue produces multiple status updates, edit the prior comment instead of adding a new one. Watchers and QA reviewers are notified per comment and must wade through progress chatter to find the current state. Reserve new comments for genuinely separate story beats that build on (not restate) earlier ones.
