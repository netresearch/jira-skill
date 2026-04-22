---
name: jira-communication
description: "Use when interacting with Jira issues - searching, creating, updating, moving, transitioning, commenting, logging work, downloading attachments, managing sprints, boards, issue links, web links, fields, or users. Auto-triggers on Jira URLs and issue keys (PROJ-123). Also use when MCP Atlassian tools fail or are unavailable for Jira Server/DC."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python 3.10+, uv, curl. Jira Server/DC or Cloud instance with API access."
metadata:
  author: Netresearch DTT GmbH
  version: "3.11.0"
  repository: https://github.com/netresearch/jira-skill
allowed-tools: Bash(python:*) Bash(uv:*) Bash(curl:*) Read Write
---

# Jira Communication

CLI scripts via `uv run`. All support `--help`, `--json`, `--quiet`, `--debug`.

## Auto-Trigger

On Jira URL or issue key (PROJ-123) → run `jira-issue.py get`. Auth issues → `jira-setup.py`.

## Scripts

**Core**: `jira-issue.py` (get/update/delete), `jira-search.py` (JQL), `jira-worklog.py`, `jira-attachment.py` (add/download), `jira-setup.py`, `jira-validate.py`
**Workflow**: `jira-create.py`, `jira-transition.py`, `jira-comment.py` (add/edit/delete/list), `jira-move.py`, `jira-sprint.py`, `jira-board.py`
**Utility**: `jira-user.py` (get/search/me), `jira-fields.py` (search/types), `jira-link.py`, `jira-weblink.py` (web link CRUD), `jira-worklog-query.py`

Scripts in `${CLAUDE_SKILL_DIR}/scripts/` under `core/`, `workflow/`, or `utility/`.


## Execution Style

**Be direct.** Run the command — scripts confirm success (`✓`) or errors (`✗`). Destructive operations support `--dry-run`.

Global flags go **before** the subcommand:
```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py --json get PROJ-123
```

## Common Tasks

```bash
# Read / search (--json is compact by default; --raw for full payload)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py get PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py get PROJ-123 --expand changelog,transitions
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py time-in-status PROJ-123 [--status Review]
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py query "assignee = currentUser() AND status != Closed" -n 5 -f key,summary,status

# Update / assign (--fields-json for description and custom fields)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --assignee me --priority Critical
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --fields-json '{"description": "New desc"}'

# Delete (--delete-subtasks for parents)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py delete PROJ-123 --dry-run

# Comment (--json list for IDs)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py add PROJ-123 "Comment text"
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py --json list PROJ-123

# Transition
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-transition.py do PROJ-123 "In Progress"

# Log / query worklogs
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-worklog-query.py --project HMKG --detail

# Create (--type auto-resolves to subtask when --parent given)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Summary" --type Task --reporter jane.doe
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Summary" --type Bug --parent PROJ-100

# User lookup
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py get john.doe
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py me

# Move / link / web links (link scripts: create/list/delete)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-move.py issue NRS-100 SRVUC
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type Blocks
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-weblink.py delete PROJ-123 --id 42

uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py types PROJ

# Board discovery (server-side name match)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-board.py list --name Lithium

# Attachments
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 screenshot.png
```

`--assignee me` resolves to the authenticated user.

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, not Markdown.

## References

- `references/jql-quick-reference.md` - JQL syntax
- `references/jql-cookbook.md` - Natural-language → JQL
- `references/multi-profile.md` - Multi-profile and auto-resolution
- `references/troubleshooting.md` - Setup and auth

## Authentication

Cloud: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`. Server/DC: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`. Config via `~/.env.jira` or `~/.jira/profiles.json`.
