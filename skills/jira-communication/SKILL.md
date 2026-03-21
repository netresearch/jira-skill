---
name: jira-communication
description: "Use when interacting with Jira issues - searching, creating, updating, moving, transitioning, commenting, logging work, downloading attachments, managing sprints, boards, issue links, fields, or users. Auto-triggers on Jira URLs and issue keys (PROJ-123). Also use when MCP Atlassian tools fail or are unavailable for Jira Server/DC."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python 3.10+, uv, curl. Jira Server/DC or Cloud instance with API access."
metadata:
  author: Netresearch DTT GmbH
  version: "3.5.0"
  repository: https://github.com/netresearch/jira-skill
allowed-tools: Bash(python:*) Bash(uv:*) Bash(curl:*) Read Write
---

# Jira Communication

CLI scripts for Jira operations via `uv run`. All scripts support `--help`, `--json`, `--quiet`, `--debug`.

**Paths** are relative to `skills/jira-communication/`.

## Auto-Trigger

On Jira URL or issue key (PROJ-123) → `jira-issue.py get PROJ-123`. Auth failure → `jira-setup.py`.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/core/jira-setup.py` | Interactive credential config |
| `scripts/core/jira-validate.py` | Verify connection |
| `scripts/core/jira-issue.py` | Get/update issue details |
| `scripts/core/jira-search.py` | Search with JQL |
| `scripts/core/jira-worklog.py` | Time tracking |
| `scripts/core/jira-attachment.py` | Download attachments |
| `scripts/workflow/jira-create.py` | Create issues |
| `scripts/workflow/jira-move.py` | Move issues between projects |
| `scripts/workflow/jira-transition.py` | Change status |
| `scripts/workflow/jira-comment.py` | Add/edit/list comments |
| `scripts/workflow/jira-sprint.py` | List sprints |
| `scripts/workflow/jira-board.py` | List boards |
| `scripts/utility/jira-user.py` | User info |
| `scripts/utility/jira-fields.py` | Search fields, list issue types |
| `scripts/utility/jira-link.py` | Issue links |


## Execution Style

**Be direct.** Run the command — scripts confirm success (`✓`) or report errors (`✗`). No need to dry-run or verify after.

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

# Update fields / assign
uv run scripts/core/jira-issue.py update PROJ-123 --assignee me
uv run scripts/core/jira-issue.py update PROJ-123 --priority Critical

# Comment
uv run scripts/workflow/jira-comment.py add PROJ-123 "Comment text"

# Transition (use "list" to see available transitions)
uv run scripts/workflow/jira-transition.py list PROJ-123
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress"

# Log work
uv run scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"

# Create (--type auto-resolves to subtask type when --parent given)
uv run scripts/workflow/jira-create.py issue PROJ "Summary" --type Task
uv run scripts/workflow/jira-create.py issue PROJ "Summary" --type Bug --parent PROJ-100 --assignee me

# Move / link / types
uv run scripts/workflow/jira-move.py issue NRS-100 SRVUC
uv run scripts/utility/jira-link.py add PROJ-123 "blocks" PROJ-456
uv run scripts/utility/jira-fields.py types PROJ
```

`--assignee me` resolves to the authenticated user on any script.

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, NOT Markdown.

## References

- `references/jql-quick-reference.md` - JQL syntax
- `references/troubleshooting.md` - Setup and auth issues

## Authentication

Cloud: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`. Server/DC: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`. Config via `~/.env.jira` or `~/.jira/profiles.json` (auto-resolves from issue key).
