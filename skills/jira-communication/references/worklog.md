# Worklogs — Advanced Logging and Cross-Cutting Queries

## When to load

Load this reference whenever the user wants to log work with a custom start date/time, undo a worklog, or query worklogs across multiple issues by date range, user, project, epic or sprint.

## Before booking: is Jira the system of record?

Check this once per team, before the first `add`. Where a separate time tracker syncs its entries into Jira, that tracker owns time and a direct `jira-worklog.py add` **double-books** — your entry plus the one the tracker syncs in later. The duplicate is easy to miss afterwards, because a synced entry is indistinguishable from a hand-written one on the issue.

The team convention belongs in an `AGENTS.md` or a team runbook, not in this skill — it cannot know your setup. If Jira *is* the system of record, `add` is correct and the rest of this section applies.

## `jira-worklog.py add` — advanced flags

```bash
# Simplest — logs "now" against your account
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"

# Explicit start time
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 1h30m \
    --started "2026-04-20T14:00:00" --comment "Research session"
```

Time strings accept `Nw Nd Nh Nm Ns` combinations (Jira semantics, 8h workday).

## `jira-worklog.py delete` — undo a booking

Every `add` prints the new `Worklog ID`, and `list` shows the id of each entry — that id is the handle for `delete`. Use it to undo a booking made against the wrong issue, the wrong duration, or the wrong system (see above).

```bash
# See which entries exist, with their ids
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py list PROJ-123
#   [2026-08-06] Jane Doe: 45m  (id 409062)

# Preview — shows the entry that would go away, deletes nothing
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py delete PROJ-123 409062 --dry-run

# Delete it
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py delete PROJ-123 409062
```

`delete` fetches the entry first and echoes its date, author and duration, so a mistyped id surfaces before anything is removed rather than after. Deleting your own worklog needs the "Delete Own Worklogs" permission; someone else's needs "Delete All Worklogs".

## `jira-worklog-query.py` — cross-cutting query

```bash
# Default: my worklogs for the current week
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py

# By project with per-entry detail
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py --project PROJ --detail

# By date range, JSON output
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py \
    --from 2026-03-01 --to 2026-03-31 --json

# By epic or sprint
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py --epic PROJ-1940
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py --sprint 916
```

`--detail` shows individual worklog entries grouped by issue. Default output groups by issue with per-issue and grand totals. `--json` emits the raw worklog list — pipe to `jq` for custom reports.

## By Tempo account (customer worked-time)

To get the worked time booked to a **Tempo account** (a customer) for a month — across *all* workers, not just yourself — use `--tempo-account`:

```bash
# Total worked time for a customer account in a month (all workers)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py \
    --tempo-account ACME --from 2026-06-01 --to 2026-06-30 --detail
```

`--tempo-account` forces the Tempo backend and ignores `--user`/`--issue`/`--epic`/`--sprint`/`--project` (the account *is* the filter). Accepts a comma-separated list of account keys.

> **Requires Tempo Timesheets on Jira Server/DC** — the whole Tempo backend (`--tempo-account`, `--backend tempo`, and `--backend auto`'s detection) talks to `/rest/tempo-timesheets/4`. Tempo **Cloud** exposes a different API (`api.tempo.io`) and is **not** supported: `--tempo-account`/`--backend tempo` fail with a clear message, and `--backend auto` falls back to the JQL backend.

Why this exists: the plain worklog query (JQL or the Tempo `/worklogs` endpoint) can only filter by **worker**, issue, project or date — **not by Tempo account**. Time a customer books via a standby/support package is often logged by someone else on an issue you wouldn't guess, so a per-issue or per-user query silently returns nothing. Under the hood `--tempo-account` calls `POST /rest/tempo-timesheets/4/worklogs/search` with an `accountKey` array — the only endpoint that resolves a whole account. When a wrapper flag is missing, reach for the underlying REST before concluding the data is unreachable:

```bash
set -a; source ~/.env.jira; set +a
curl -sS -H "Authorization: Bearer $JIRA_PERSONAL_TOKEN" -H "Content-Type: application/json" \
  -X POST "${JIRA_URL%/}/rest/tempo-timesheets/4/worklogs/search" \
  -d '{"from":"2026-06-01","to":"2026-06-30","accountKey":["ACME"]}'
# account lookup (key/name/lead): GET /rest/tempo-accounts/1/account/<id>
```

## Relative dates

`--from` and `--to` accept plain `YYYY-MM-DD`. For rolling queries, compute the dates in the shell:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py \
    --from "$(date -d 'monday last week' -I)" --to "$(date -I)"
```
