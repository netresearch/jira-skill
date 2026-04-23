# Issue Creation — Advanced

## When to load

Load this reference whenever the user wants to create a sub-task (`--parent`), set a custom reporter, attach components, or pass custom-field values on create via `--fields-json`.

## Sub-tasks via `--parent`

```bash
# --type auto-resolves to the right sub-task issue type for the parent's project
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Fix flaky test" \
    --type Bug --parent PROJ-100
```

`jira-create.py` inspects the parent and picks the matching `Sub: <Type>` issue type where the project defines one, falling back to the project's declared sub-task type.

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

Typed flags (`--assignee`, `--priority`, `--labels`, `--reporter`, `--components`) win over `--fields-json` when the same field is set in both. Use `--fields-json` only for fields the CLI doesn't expose directly.
