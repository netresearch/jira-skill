# Worklogs — Advanced Logging and Cross-Cutting Queries

## When to load

Load this reference whenever the user wants to log work with a custom start date/time, or query worklogs across multiple issues by date range, user, project, epic or sprint.

## `jira-worklog.py add` — advanced flags

```bash
# Simplest — logs "now" against your account
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"

# Explicit start time
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 1h30m \
    --started "2026-04-20T14:00:00" --comment "Research session"
```

Time strings accept `Nw Nd Nh Nm Ns` combinations (Jira semantics, 8h workday).

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


## TimeTracker (tt.netresearch.de) vs Jira Tempo — "TT" means TimeTracker

At Netresearch **"TT" / "via TT" means TimeTracker** (https://tt.netresearch.de),
a system **separate from** Jira Tempo. `jira-worklog.py add` writes to **Jira
Tempo**, which does **not** appear in TimeTracker. TimeTracker **auto-syncs its
own entries into Jira Tempo**, so:

- If the user asks to book "via TT", book in **TimeTracker**, not with
  `jira-worklog.py` — a direct Tempo entry is invisible in TT and **double-books**
  (it duplicates the entry TimeTracker later syncs in).
- The existing Tempo worklogs you see on an issue usually originated in
  TimeTracker and synced across.

### Booking in TimeTracker (MCP)

TimeTracker exposes an MCP endpoint. Token in `~/.secrets/tt` (starts `tt_p…`).

```bash
TOK=$(tr -d '\r\n' < ~/.secrets/tt); BASE=https://tt.netresearch.de/mcp
# handshake: initialize -> capture the mcp-session-id header -> notifications/initialized
# then tools/call. Responses are plain JSON: .result.content[0].text holds a JSON string.
```

Key tools: `log_time` (project + activity **required**; ticket, date, start/end or
durationMinutes, description), `get_day`, `list_recent_entries`, `list_activities`,
`list_projects`, `update_entry`, `delete_entry`.

- **NRS tickets** (jira.netresearch.de `NRS-*`): project **948** "Netresearch IT
  Support/Help Desk", activity **1 = Entwicklung** (19 = Analyse, 4 = Dokumentation,
  2 = QA). Booking under project 25 (F+E) fails with *"Given ticket does not have a
  valid prefix"* — F+E's ticket system does not include the NRS prefix. Match how the
  same ticket class was booked before via `list_recent_entries`.
- Pass explicit `start`/`end` so the 09:00 default does not overlap existing entries.
- **ADR-025 agent model**: `log_time` also accepts `agentWalltimeMinutes` +
  `humanMinutes` + `touchpoints` to dual-write an AI-agent + delegated-human entry —
  the honest representation for agent-assisted work; ask which the user wants.

To fix a mistaken direct-Tempo booking, delete the Jira worklog with the client lib:
`client.delete(f"rest/api/2/issue/KEY/worklog/{id}")` (jira-worklog.py has no delete).
