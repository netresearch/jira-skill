# Fields and Users — Reference Data Lookup

## When to load

Load this reference whenever the user needs to: look up a custom field ID, list issue types for a project, search for a Jira user, or resolve a username/accountId for use as a reporter, assignee, or watcher value.

## Users

```bash
# Resolve a specific identifier — prints the canonical record
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py get john.doe

# Free-text search (by display name or email fragment)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py search "doreen"

# The current authenticated user (what `--assignee me` resolves to)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py me
```

Useful when `--assignee`, `--reporter`, or `--user` rejects a value: search returns the canonical username (Server/DC) or accountId (Cloud) the API expects.

## Custom fields

```bash
# Search field metadata by name fragment
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py search "sprint"
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py search "epic"

# Dump all fields as JSON (for grep/jq pipelines)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py --json search ""
```

The key you need for `--fields-json` is the `id` (e.g. `customfield_<N>`) — not the human name.

## Issue types per project

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py types PROJ
```

Prints every issue type the project accepts, including sub-task types. Issue type names are **case-sensitive** on create (`jira-create.py --type`).

## Common custom-field shapes (IDs vary per instance)

| Field | Type | Notes |
|---|---|---|
| Sprint | integer | Sprint ID, not name |
| Epic Link | string | Epic issue key, e.g. `"PROJ-1940"` |
| UAT / Test instructions | text | QA hand-off notes |

Always confirm the `id` with `jira-fields.py search` on the target instance — custom-field numbering is not portable.
