# Issue Creation — Advanced

## When to load

Load this reference whenever the user wants to create a sub-task (`--parent`), set a custom reporter, attach components, or pass custom-field values on create via `--fields-json`.

## Sub-tasks via `--parent`

```bash
# --type auto-resolves to the right sub-task issue type for the parent's project
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Fix flaky test" \
    --type Bug --parent PROJ-100
```

When `--parent` is provided, `jira-create.py` resolves the sub-task issue type from the project's issue-type catalog (matching on name, case-insensitive). The parent issue itself is not fetched — resolution is project-scoped: an exact match on the requested type wins, otherwise a substring match against sub-task names (e.g., `Task` → `Sub: Task`), otherwise the sole sub-task type if only one exists.

## Custom reporter

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "User-reported bug" \
    --type Bug --reporter jane.doe
```

Value is the accountId on Cloud, the username on Server/DC. Resolve via `jira-user.py search` (see `fields-and-users.md`).

## Components

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Summary" \
    --type Task --components "Backend,API"
```

Components must already exist on the project.

## Custom fields on create

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Summary" \
    --type Task \
    --fields-json '{"customfield_SPRINT": 916, "customfield_EPIC": "PROJ-1940"}'
```

Sprint ID is an integer, not an array. Epic Link is the epic's issue key as a string.

## Combining flags

`--fields-json` wins over typed flags (`--assignee`, `--priority`, `--labels`, `--reporter`, `--components`) when the same field is set in both — the script merges the JSON payload onto the typed-flag payload (`fields.update(extra_fields)`). Use typed flags for the fields the CLI exposes directly, and reach for `--fields-json` only for the long tail.
