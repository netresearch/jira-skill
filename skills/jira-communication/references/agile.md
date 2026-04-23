# Agile — Sprints and Boards

## When to load

Load this reference whenever the user wants to list sprints, list boards, move issues between sprints, or identify the active sprint for a board.

## Boards

```bash
# All boards visible to the authenticated user
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py list

# Filter by project
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py list --project PROJ

# Show only Scrum or Kanban
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py list --type scrum
```

## Sprints

```bash
# Sprints for a specific board
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-sprint.py list --board 119

# Active sprint only
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-sprint.py list --board 119 --state active

# Details on a single sprint (goal, dates, issues)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-sprint.py get 916
```

## Assigning an issue to a sprint

The Sprint custom field takes the sprint's integer ID (not its name). Resolve the field's `id` via `jira-fields.py search "sprint"` on your instance; it's typically `customfield_<N>`.

```bash
# Substitute the real custom-field id from `jira-fields.py search "sprint"`
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 \
    --fields-json '{"customfield_SPRINT": 916}'
```

See `issue-editing.md` for more on `--fields-json`, and `fields-and-users.md` for looking up the sprint custom-field ID on other instances.

## Scrum vs Kanban

- **Scrum boards** own named sprints; issues have a Sprint field with an integer ID.
- **Kanban boards** have no sprints — the Sprint field is always empty; `jira-sprint.py list --board <kanban>` returns an empty array, not an error.
