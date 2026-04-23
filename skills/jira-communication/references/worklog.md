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

## Relative dates

`--from` and `--to` accept plain `YYYY-MM-DD`. For rolling queries, compute the dates in the shell:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py \
    --from "$(date -d 'monday last week' -I)" --to "$(date -I)"
```

