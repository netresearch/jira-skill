<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# QA Gather

## When to load

Load this reference when reviewing a ticket transitioned to *QA* / *In Review* / *Ready for Review*, or when the user asks for "QA review", "peer review", "review and resolve", or pulls a ticket from a team-review queue. Also when a peer-review style runbook (e.g. [`peer-qa-review`](https://github.com/netresearch/peer-qa-review-skill)) needs single-call context discovery for Stage 0 of its lifecycle.

The script gives you everything a reviewer typically chases across 4–5 separate calls — issue + description + comments + worklog + structured issue links + web/remote links + URLs scraped from prose (MR/PR/pipeline/commit/tag/release) + sibling tickets + a self-review check — in one shot. The description and every comment body are part of the text output, so no follow-up `jira-issue.py work KEY` is needed to read the ticket.

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
3. `Self-review check: <self|other|unknown> (<reason>)` — see [Self-review check](#self-review-check); a `WARNING:` line follows when the verdict is `self`
4. `Description:` — the full description, indented (omitted when empty, or with `--no-body`)
5. Structured issue links (`<type> → <key>: <summary>` for outward, `←` for inward), or `Issue links: none`
6. Web/remote links (`title: url`), or `Web/remote links: none`
7. URLs extracted from prose, grouped by category: `merge_request`, `pull_request`, `pipeline`, `commit`, `tag`, `release`, `issue_link`
8. Sibling tickets in the same project, sorted by `updated DESC`
9. `COMMENTS (N total — chronological)` — every comment as `--- [YYYY-MM-DD HH:MM] Display Name (username) ---` followed by its body, the same rendering as `jira-issue.py work` (omitted when there are none, or with `--no-body`)

Sections 5 and 6 always print, including when empty. "None" is a reviewable fact — a related ticket mentioned in prose but never linked, or a merged MR with no web link, is a finding in its own right — whereas an omitted section reads as "not checked" and invites the reader to assume the links exist.

The assignee says whether a ticket is claimed: unassigned means claimable, someone else means it is already in flight. It does not say who did the work. Workflows that unassign a ticket on its move into QA leave every QA ticket `Unassigned`, so "the assignee is me" never fires there. The self-review check answers that question from the changelog and the worklog instead.

Comments come last so the metadata stays at the top of the screen; the section is the full, paginated set (Jira's embedded block stops at 50 on Server/DC).

## Self-review check

The check compares you (the authenticated user, `GET /rest/api/2/myself`: `name` on Server/DC, `accountId` on Cloud) with three implementation signals. Every round in the changelog counts, not only the latest: a reviewer who implemented a round that QA rejected, after which someone else took the ticket over, is still reviewing their own work.

| Signal | Source |
|--------|--------|
| Handovers into QA | Authors of every changelog entry that moved the status from a non-QA status into a QA status. The most recent one is shown as `implementer` — the same handover the `jira-issue.py qa` verb uses (see `intent-verbs.md`); a match on it is named `implementer`, a match on an earlier one `earlier_handover` |
| `worklog_authors` | Distinct authors of the issue's worklog entries |
| Moves into In Progress | Authors of every move into a status whose category is In Progress (`statusCategory.key == "indeterminate"`), excluding moves into or out of a QA status — many instances put QA in that category too, and a QA reject back to In Progress is the reviewer's verdict, not implementation work. The most recent one is shown as `in_progress_by`; a match on it is named `in_progress_by`, a match on an earlier one `earlier_in_progress`. A move into a status id the status list does not contain (a deleted status), or into a status listed without a category, has no known category: the signal counts as unread, the moves into known statuses still match, `reason` names `status category of a move`, and the text marks both lines `incomplete: a status category is unknown` |

Verdict:

- `self` — you match at least one signal; `matched` names which, and `matched_events` (one indented text line each) gives the date and statuses of every matching changelog entry.
- `other` — no signal matches, a handover into QA exists, and every input could be read: you, the full worklog, the status categories, the full changelog and the author of the latest handover.
- `unknown` — no transition into a QA status is in the changelog, or one of those inputs could not be read: a failed fetch, a worklog response that carries no `worklogs` list (empty body, error object) or fewer entries than its `total`, a changelog whose `total` exceeds the embedded entries (Cloud caps it), a latest handover entry without an author (deleted or anonymous user, post-function), or a move into a status the status list does not contain. `reason` names which. None of these counts as "not you".

The creator and the reporter are printed for information only. Opening a ticket is not implementing it, so neither is a signal.

Known limitations:

- Any worklog entry counts. A reviewer who logged time for an earlier review round of the same ticket gets `self` on the next round; the text line says `worklog_author`, so check whose entry it is before handing the review off.
- Moves into QA count from every round. A reviewer who once moved a ticket into QA on someone else's behalf gets `self` (`earlier_handover`); the event line shows when, so check it before handing the review off.
- Jira returns no worklog entries when the Log Work field is hidden for the project, and that response looks the same as an empty worklog. On such a project the worklog signal cannot fire; the changelog signals still apply.

The section also carries two facts reviewers otherwise look up by hand: `resolution` (its name, or none) and `worklog_empty` (yes/no; unknown when the worklog could not be read).

The changelog comes embedded in the issue payload (`expand=changelog`), the same source the `qa` verb reads. With `--json` it is therefore part of the `issue` object, which grows with the ticket's history.

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
- `self_review` — object:
  - `verdict` — `"self"`, `"other"` or `"unknown"`; `reason` — one line saying why; `matched` — list of the matching signals (`implementer`, `earlier_handover`, `worklog_author`, `in_progress_by`, `earlier_in_progress`); `matched_events` — `{signal, created, from, to}` for each matching changelog entry
  - `reviewer` — your account name / accountId, `null` if `myself` failed
  - `implementer`, `implementer_display` — author of the handover into QA, `null` when there is none; `handover` — `{created, from, to}` of that transition, or `null`; `handover_authors` — every handover author in changelog order
  - `in_progress_by` — author of the most recent move into In Progress, or `null`; `in_progress_authors` — every such author in changelog order; `in_progress_complete` — `false` when the status categories could not be read or a move went to a status without a known category
  - `worklog_authors` — sorted list of account names, `null` if the worklog could not be read
  - `worklog_empty` — bool, `null` if the worklog could not be read
  - `resolution` — resolution name, or `null`
  - `creator`, `reporter` — `"Display Name (name)"`, information only

## Sibling-search semantics

Same project, summary-token overlap (case-insensitive heuristic, 4-char minimum, stop-list filtered, max 5 keywords from the source ticket's summary), `updated >= -<window>d`, ordered by `updated DESC`. Includes both resolved *and* still-open tickets — open sibling work is often the most relevant for QA. Project and issue keys are quoted in the JQL string to handle keys with special characters.

## Failure modes

- Issue fetch fails → script exits non-zero with a sanitized error.
- Worklog / web-links / sibling-search failures → warning to stderr, the corresponding JSON field is empty/`[]`, the script continues.
- `myself` / status-list failures → warning to stderr; `self_review.reviewer` or `in_progress_by` stays `null` and a verdict that would have been `other` becomes `unknown`. The first (issue) fetch is the only hard dependency.
- A response that arrives but cannot be used — a worklog without a `worklogs` list, a status list that is not a list, a `myself` without `name` or `accountId` — prints no warning; it shows only as `unknown` with the input named in `self_review.reason`.
- Paginated comment fetch fails → warning to stderr, the comments embedded in the issue payload (capped at 50) are used instead.
- Exception messages are passed through `_sanitize_error()` to redact tokens / passwords / api keys before being printed.

## Companion runbook

The [`peer-qa-review`](https://github.com/netresearch/peer-qa-review-skill) skill provides the *what to check / how to format the QA comment* layer; this script provides the *fetch the data* layer. They compose: peer-qa-review's Stage 0 is "run jira-qa-gather; structure the rest of the review around the bundle."

If you have peer-qa-review loaded, prefer to follow its lifecycle (Claim → Discover → Formal → Functional+Inventory → Docs+Rollback+Comm → Verdict). If not, this script's output is still self-contained enough for a manual review pass.
