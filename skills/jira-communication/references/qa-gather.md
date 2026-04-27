# QA Gather

## When to load

Load this reference when reviewing a ticket transitioned to *QA* / *In Review* / *Ready for Review*, or when the user asks for "QA review", "peer review", "review and resolve", or pulls a ticket from a team-review queue. Also when a peer-review style runbook (e.g. [`peer-qa-review`](https://github.com/netresearch/peer-qa-review-skill)) needs single-call context discovery for Stage 0 of its lifecycle.

The script gives you everything a reviewer typically chases across 4–5 separate calls — issue + description + comments + worklog + structured issue links + web/remote links + URLs scraped from prose (MR/PR/pipeline/commit/tag/release) + sibling tickets — in one shot.

## Command

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-qa-gather.py PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-qa-gather.py PROJ-123 --json
```

Read-only. No `--dry-run` needed.

## Options

| Flag | Default | Effect |
|------|---------|--------|
| `--json` | off | Emit a single JSON object with everything (machine-readable, full bundle). Default is human-readable summary. |
| `--quiet`, `-q` | off | Print only the issue key after a successful fetch (validates connectivity/permissions/existence first). |
| `--no-siblings` | off | Skip the sibling-ticket JQL search. |
| `--sibling-window DAYS` | 60 | Sibling search looks at tickets `updated >= -<DAYS>d`. Min: 1. |
| `--max-siblings N` | 5 | Cap on sibling tickets returned. Min: 1. |
| `--profile`, `--env-file`, `--debug` | — | Standard global flags (see `multi-profile.md` for `--profile`). |

## Output (default mode)

Human-readable sections, in order:

1. Issue key + summary
2. Status, comment count, worklog count + total minutes
3. Structured issue links (`<type> → <key>: <summary>` for outward, `←` for inward)
4. Web/remote links (`title: url`)
5. URLs extracted from prose, grouped by category: `merge_request`, `pull_request`, `pipeline`, `commit`, `tag`, `release`, `issue_link`
6. Sibling tickets in the same project, sorted by `updated DESC`

## JSON shape (with `--json`)

Top-level keys (stable):

- `issue_key` — string, the requested key
- `issue` — full Jira issue dict from `client.issue()` with `expand=renderedFields`
- `comments` — list of comment dicts (extracted from the issue payload, no second API call)
- `worklogs` — list of worklog dicts
- `worklog_total_seconds` — int
- `issue_links` — list (raw `issuelinks` from the issue)
- `web_links` — list (from `get_issue_remote_links`)
- `extracted_urls` — `{category: [url, ...]}` deduplicated, order-preserved
- `siblings` — list of issue dicts (summary + status + resolutiondate + updated)

## Sibling-search semantics

Same project, summary-token overlap (case-insensitive heuristic, 4-char minimum, stop-list filtered, max 5 keywords from the source ticket's summary), `updated >= -<window>d`, ordered by `updated DESC`. Includes both resolved *and* still-open tickets — open sibling work is often the most relevant for QA. Project and issue keys are quoted in the JQL string to handle keys with special characters.

## Failure modes

- Issue fetch fails → script exits non-zero with a sanitized error.
- Worklog / web-links / sibling-search failures → warning to stderr, the corresponding JSON field is empty/`[]`, the script continues. The first (issue) fetch is the only hard dependency.
- Exception messages are passed through `_sanitize_error()` to redact tokens / passwords / api keys before being printed.

## Companion runbook

The [`peer-qa-review`](https://github.com/netresearch/peer-qa-review-skill) skill provides the *what to check / how to format the QA comment* layer; this script provides the *fetch the data* layer. They compose: peer-qa-review's Stage 0 is "run jira-qa-gather; structure the rest of the review around the bundle."

If you have peer-qa-review loaded, prefer to follow its lifecycle (Claim → Discover → Formal → Functional+Inventory → Docs+Rollback+Comm → Verdict). If not, this script's output is still self-contained enough for a manual review pass.
