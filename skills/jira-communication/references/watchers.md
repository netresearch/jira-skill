# Watchers

## When to load

Load this reference whenever the user asks about watchers — listing, adding,
removing, or auto-subscribing themselves or a stakeholder when an issue
changes state. Watchers are not exposed anywhere else in the skill, so any
"watch", "subscribe", "notify me on", "unsubscribe", or "who is watching"
request should land here.

## Commands

All commands are subcommands of `jira-watchers.py`. Global flags (`--json`,
`--quiet`, `--profile`, `--env-file`, `--debug`) go **before** the subcommand.

### list

```bash
# Default — header with count, one row per watcher
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py list PROJ-123

# JSON — raw Jira response ({"watchCount", "isWatching", "watchers": [...]})
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py --json list PROJ-123

# Quiet — one identifier per line
# DC prints usernames; Cloud prints accountIds (pipeline-friendly)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py --quiet list PROJ-123
```

### add

```bash
# Self-subscribe (default — requires only Browse Projects)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py add PROJ-123

# Subscribe someone else (requires Manage Watchers permission)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py add PROJ-123 --user product.owner

# Cloud: pass an accountId directly to skip user-search
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py add PROJ-123 --user 557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a

# JSON output → {"key": "PROJ-123", "user": "asmith", "added": true}
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py --json add PROJ-123
```

### remove

```bash
# Un-watch yourself
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py remove PROJ-123

# Remove someone else (requires Manage Watchers)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py remove PROJ-123 --user asmith

# Preview without calling the API
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py remove PROJ-123 --user asmith --dry-run

# JSON output → {"key": "PROJ-123", "user": "asmith", "removed": true}
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py --json remove PROJ-123
```

### Bulk patterns (no server-side bulk endpoint)

```bash
# Watch every child of an epic
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py --json query '"Epic Link" = PROJ-789' \
  | jq -r '.issues[].key' \
  | xargs -I{} uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-watchers.py add {}
```

## Gotchas

- **DC vs Cloud identity.** DC uses usernames (`jdoe`); Cloud uses accountIds
  (`557058:...`). The script auto-detects via `client.cloud` and `resolve_assignee()` —
  pass whatever identifier you have; account-id-shaped strings bypass user search.
- **`issue_delete_watcher` library kwargs differ from raw REST params.**
  In `atlassian-python-api`, call `issue_delete_watcher(..., username=...)` on DC
  and `issue_delete_watcher(..., account_id=...)` on Cloud; the script chooses the
  correct kwarg based on deployment/identifier shape. If you ever drop to raw
  REST, the query parameter names are `?username=` (DC) and `?accountId=` (Cloud).
- **Self-watch is idempotent.** Adding yourself when already watching returns
  HTTP 204, not an error — the script treats repeated self-adds as success.
- **403 on someone-else add/remove.** Non-self watcher changes require the
  Manage Watchers project permission. A 403 is surfaced verbatim as the
  error message — do not silently swallow.
- **404 on remove-non-watcher.** Removing a user who is not currently watching
  returns HTTP 404 on both DC and Cloud. The script surfaces this as a clean
  error (exit code 1), not a silent success.

## See also

`docs/plans/2026-04-20-watchers-design.md` for the full design trail
(REST shapes, DC vs Cloud matrix, out-of-scope items).
