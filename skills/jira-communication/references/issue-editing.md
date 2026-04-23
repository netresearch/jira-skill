# Issue Editing — Advanced

## When to load

Load this reference whenever the user wants to set `--fields-json`, set a custom `--reporter`, delete an issue (especially with sub-tasks), move an issue between projects, or change any field that is not assignee, priority, or labels.

## `--fields-json` for description and custom fields

`jira-issue.py update` accepts a raw JSON object to set any field the Jira REST API exposes:

```bash
# Plain description edit
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --fields-json '{"description": "Rewritten description"}'

# Custom fields (Sprint ID as integer, Epic Link as issue key)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --fields-json '{"customfield_SPRINT": 916, "customfield_EPIC": "PROJ-1940"}'

# Combine with typed flags — typed flags win on conflict
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --priority Critical \
    --fields-json '{"labels": ["review", "urgent"]}'
```

Look up custom field IDs with `jira-fields.py` — see `fields-and-users.md`.

## Setting a custom reporter

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --reporter jane.doe
```

On Cloud the value is the accountId; on Server/DC it is the username.

## Deleting issues

```bash
# Always preview first
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py delete PROJ-123 --dry-run

# Real delete
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py delete PROJ-123

# Parent with sub-tasks — the API rejects it unless you opt in
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py delete PROJ-100 --delete-subtasks
```

`--delete-subtasks` cascades the delete. The script refuses without it when sub-tasks exist.

## Moving an issue between projects

```bash
# Preview the move (destination project must accept the issue type)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-move.py issue PROJ-100 TARGET --dry-run

# Execute the move
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-move.py issue PROJ-100 TARGET
```

The issue key changes after the move; the script prints the new key.
