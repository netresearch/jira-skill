---
name: jira-communication
description: "Use when interacting with Jira issues - searching, creating, updating, moving, transitioning, commenting, logging work, downloading attachments, managing sprints, boards, issue links, fields, or users. Auto-triggers on Jira URLs and issue keys (PROJ-123). Also use when MCP Atlassian tools fail or are unavailable for Jira Server/DC."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python 3.10+, uv, curl. Jira Server/DC or Cloud instance with API access."
metadata:
  author: Netresearch DTT GmbH
  version: "3.7.0"
  repository: https://github.com/netresearch/jira-skill
allowed-tools: Bash(python:*) Bash(uv:*) Bash(curl:*) Read Write
---

# Jira Communication

CLI scripts via `uv run`. All support `--help`, `--json`, `--quiet`, `--debug`.

**Paths** are relative to `skills/jira-communication/`.

## Auto-Trigger

On Jira URL or issue key (PROJ-123) → `jira-issue.py get PROJ-123`. Auth issues → `jira-setup.py`.

## Scripts

**Core**: `jira-issue.py` (get/update/delete), `jira-search.py` (JQL), `jira-worklog.py`, `jira-attachment.py`, `jira-setup.py`, `jira-validate.py`
**Workflow**: `jira-create.py`, `jira-transition.py`, `jira-comment.py` (add/edit/delete/list), `jira-move.py`, `jira-sprint.py`, `jira-board.py`
**Utility**: `jira-user.py`, `jira-fields.py` (search/types), `jira-link.py`

All in `scripts/core/`, `scripts/workflow/`, or `scripts/utility/`.


## Execution Style

**Be direct.** Run the command — scripts confirm success (`✓`) or errors (`✗`). Destructive operations support `--dry-run`.

Global flags go **before** the subcommand:
```bash
uv run scripts/core/jira-issue.py --json get PROJ-123
```

## Common Tasks

```bash
# Read issue
uv run scripts/core/jira-issue.py get PROJ-123
uv run scripts/core/jira-issue.py --json get PROJ-123

# Search (use -f for fields, -n for limit)
uv run scripts/core/jira-search.py query "assignee = currentUser() AND status != Closed"
uv run scripts/core/jira-search.py query "project = PROJ ORDER BY updated DESC" -n 5 -f key,summary,status,priority

# Update fields / assign (--fields-json for description and custom fields)
uv run scripts/core/jira-issue.py update PROJ-123 --assignee me
uv run scripts/core/jira-issue.py update PROJ-123 --priority Critical --summary "New title"
uv run scripts/core/jira-issue.py update PROJ-123 --fields-json '{"description": "New desc"}'

# Delete issue (use --dry-run to preview, --delete-subtasks for parent issues)
uv run scripts/core/jira-issue.py delete PROJ-123 --dry-run
uv run scripts/core/jira-issue.py delete PROJ-123

# Comment (add/edit/list — use --json list to get IDs for edit/delete)
uv run scripts/workflow/jira-comment.py add PROJ-123 "Comment text"
cat comment.txt | uv run scripts/workflow/jira-comment.py add PROJ-123 -
uv run scripts/workflow/jira-comment.py --json list PROJ-123
uv run scripts/workflow/jira-comment.py edit PROJ-123 COMMENT_ID "Updated text"
uv run scripts/workflow/jira-comment.py delete PROJ-123 COMMENT_ID --dry-run

# Transition (use "list" to see available transitions)
uv run scripts/workflow/jira-transition.py list PROJ-123
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress"

# Log work
uv run scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"

# Create (--type auto-resolves to subtask when --parent given)
uv run scripts/workflow/jira-create.py issue PROJ "Summary" --type Task
uv run scripts/workflow/jira-create.py issue PROJ "Summary" --type Bug --parent PROJ-100

# Move / change type / link
uv run scripts/workflow/jira-move.py issue NRS-100 SRVUC
uv run scripts/workflow/jira-move.py issue NRS-100 NRS --issue-type Task
uv run scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type "Blocks"
uv run scripts/utility/jira-fields.py types PROJ
```

`--assignee me` resolves to the authenticated user.

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, not Markdown.

## References

- `references/jql-quick-reference.md` - JQL syntax
- `references/multi-profile.md` - Multi-profile and auto-resolution
- `references/troubleshooting.md` - Setup and auth

## Authentication

Cloud: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`. Server/DC: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`. Config via `~/.env.jira` or `~/.jira/profiles.json`.
