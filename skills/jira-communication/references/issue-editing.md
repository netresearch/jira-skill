# Issue Editing — Advanced

## When to load

Load this reference whenever the user wants to set `--fields-json`, set a custom `--reporter`, delete an issue (especially with sub-tasks), attempt an unsupported cross-project move via CLI (see below), or change any field that is not assignee, priority, or labels.

## `--fields-json` for description and custom fields

`jira-issue.py update` accepts a raw JSON object to set any field the Jira REST API exposes:

```bash
# Plain description edit
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --fields-json '{"description": "Rewritten description"}'

# Custom fields (Sprint ID as integer, Epic Link as issue key)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --fields-json '{"customfield_SPRINT": 916, "customfield_EPIC": "PROJ-1940"}'

# Combine with typed flags — `--fields-json` wins on conflict
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --priority Critical \
    --fields-json '{"labels": ["review", "urgent"]}'
```

The script merges `--fields-json` onto the typed-flag payload (`update_fields.update(extra_fields)`), so any key present in both is taken from `--fields-json`. Use typed flags for fields the CLI exposes directly, and reach for `--fields-json` only for the long tail.

Look up custom field IDs with `jira-fields.py` — see `fields-and-users.md`.

## Labels: replace vs incremental updates

`jira-issue.py update` supports three modes:

- `--labels a,b,c` replaces the full label set.
- `--add-label` / `--remove-label` incrementally update labels without wiping unrelated tags.
- Do **not** combine `--labels` with `--add-label` / `--remove-label` in one invocation.

Each `--add-label` / `--remove-label` may be repeated and may contain comma-separated values. Matching for removals is **case-insensitive**, and additions **dedupe case-insensitively** while preserving the casing already stored in Jira when possible.

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
  --add-label backend --add-label urgent,frontend --remove-label stale
```

## Setting a custom reporter

`jira-issue.py update` has no `--reporter` flag; the reporter on an existing issue is changed through `--fields-json`:

```bash
# Cloud (accountId) or Server/DC (name) — both go through --fields-json
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --fields-json '{"reporter": {"name": "jane.doe"}}'
```

On Jira Cloud, use `{"reporter": {"accountId": "..."}}` instead. The create-time shortcut is the typed `--reporter` flag on `jira-create.py` — see `creation.md`.

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

Cross-project moves are **not implemented** in `jira-move.py` because some Jira Server/DC versions accept `project` edits via the standard issue endpoint without actually moving the issue (silent partial updates / corruption risk). The command **refuses** cross-project targets for both real execution and `--dry-run`.

Use the Jira UI **Move** action (or a bulk-move workflow your admins provide) for cross-project relocation.

Within the **same** project, `jira-move.py` can change issue type:

```bash
# Preview a same-project type change
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-move.py issue PROJ-100 PROJ --issue-type Task --dry-run

# Execute the type change (issue key stays the same)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-move.py issue PROJ-100 PROJ --issue-type Task
```
