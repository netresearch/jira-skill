# QA Gather

## When to load

Load this reference when reviewing a ticket transitioned to *QA* / *In Review* / *Ready for Review*, or when the user asks for "QA review", "peer review", "review and resolve", or pulls a ticket from a team-review queue. Also when a peer-review style runbook (e.g. [`peer-qa-review`](https://github.com/netresearch/peer-qa-review-skill)) needs single-call context discovery for Stage 0 of its lifecycle.

The script gives you everything a reviewer typically chases across 4–5 separate calls — issue + description + comments + worklog + structured issue links + web/remote links + URLs scraped from prose (MR/PR/pipeline/commit/tag/release) + sibling tickets — in one shot. The description and every comment body are part of the text output, so no follow-up `jira-issue.py work KEY` is needed to read the ticket.

## Command

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-qa-gather.py PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-qa-gather.py PROJ-123 --no-body   # metadata only
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-qa-gather.py PROJ-123 --json
```

Read-only. No `--dry-run` needed.

## Options

| Flag | Default | Effect |
|------|---------|--------|
| `--json` | off | Emit a single JSON object with everything (machine-readable, full bundle). Default is human-readable summary. |
| `--quiet`, `-q` | off | Print only the issue key after a successful fetch (validates connectivity/permissions/existence first). |
| `--no-siblings` | off | Skip the sibling-ticket JQL search. |
| `--no-body` | off | Omit the description and the comment bodies from the text output (metadata-only shape; the comment count and URL extraction still cover every comment). No effect on `--json`. |
| `--sibling-window DAYS` | 60 | Sibling search looks at tickets `updated >= -<DAYS>d`. Min: 1. |
| `--max-siblings N` | 5 | Cap on sibling tickets returned. Min: 1. |
| `--profile`, `--env-file`, `--debug` | — | Standard global flags (see `multi-profile.md` for `--profile`). |

## Output (default mode)

Human-readable sections, in order:

1. Issue key + summary
2. Status, **current assignee** (or `Unassigned`), comment count, worklog count + total minutes
3. `Description:` — the full description, indented (omitted when empty, or with `--no-body`)
4. Structured issue links (`<type> → <key>: <summary>` for outward, `←` for inward), or `Issue links: none`
5. Web/remote links (`title: url`), or `Web/remote links: none`

Sections 4 and 5 always print, including when empty. "None" is a reviewable fact — a related ticket mentioned in prose but never linked, or a merged MR with no web link, is a finding in its own right — whereas an omitted section reads as "not checked" and invites the reader to assume the links exist.

The assignee is section 2 because claiming a ticket off a team queue depends on it: unassigned means claimable, someone else means it is already in flight, and yourself means you may be about to review your own work.
6. URLs extracted from prose, grouped by category: `merge_request`, `pull_request`, `pipeline`, `commit`, `tag`, `release`, `issue_link`
7. Sibling tickets in the same project, sorted by `updated DESC`
8. `COMMENTS (N total — chronological)` — every comment as `--- [YYYY-MM-DD HH:MM] Display Name (username) ---` followed by its body, the same rendering as `jira-issue.py work` (omitted when there are none, or with `--no-body`)

Comments come last so the metadata stays at the top of the screen; the section is the full, paginated set (Jira's embedded block stops at 50 on Server/DC).

## JSON shape (with `--json`)

Top-level keys (stable):

- `issue_key` — string, the requested key
- `issue` — full Jira issue dict from `client.issue()` with `expand=renderedFields`
- `description` — raw `fields.description` (string on Server/DC, ADF dict on Cloud), `null` when empty — same shape as `jira-issue.py work --json`
- `comments` — list of comment dicts, all pages (falls back to the embedded block from the issue payload if the paginated fetch fails, with a warning)
- `worklogs` — list of worklog dicts
- `worklog_total_seconds` — int
- `assignee` — string account name, or `null` when unassigned (`null` is meaningful: an unclaimed queue ticket)
- `assignee_display` — string display name, or `null`
- `issue_links` — list (raw `issuelinks` from the issue)
- `web_links` — list (from `get_issue_remote_links`)
- `extracted_urls` — `{category: [url, ...]}` deduplicated, order-preserved
- `siblings` — list of issue dicts (summary + status + resolutiondate + updated)

## Sibling-search semantics

Same project, summary-token overlap (case-insensitive heuristic, 4-char minimum, stop-list filtered, max 5 keywords from the source ticket's summary), `updated >= -<window>d`, ordered by `updated DESC`. Includes both resolved *and* still-open tickets — open sibling work is often the most relevant for QA. Project and issue keys are quoted in the JQL string to handle keys with special characters.

## Failure modes

- Issue fetch fails → script exits non-zero with a sanitized error.
- Worklog / web-links / sibling-search failures → warning to stderr, the corresponding JSON field is empty/`[]`, the script continues. The first (issue) fetch is the only hard dependency.
- Paginated comment fetch fails → warning to stderr, the comments embedded in the issue payload (capped at 50) are used instead.
- Exception messages are passed through `_sanitize_error()` to redact tokens / passwords / api keys before being printed.

## Companion runbook

The [`peer-qa-review`](https://github.com/netresearch/peer-qa-review-skill) skill provides the *what to check / how to format the QA comment* layer; this script provides the *fetch the data* layer. They compose: peer-qa-review's Stage 0 is "run jira-qa-gather; structure the rest of the review around the bundle."

If you have peer-qa-review loaded, prefer to follow its lifecycle (Claim → Discover → Formal → Functional+Inventory → Docs+Rollback+Comm → Verdict). If not, this script's output is still self-contained enough for a manual review pass.
