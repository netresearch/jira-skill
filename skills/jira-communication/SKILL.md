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

Activate when user mentions:
- **Jira URLs**: `https://jira.*/browse/*`, `https://*.atlassian.net/browse/*`
- **Issue keys**: `PROJ-123`, `NRS-4167`

On URL trigger → extract key → `jira-issue.py get PROJ-123`

## Auth Failure Handling

When auth fails, offer: `uv run scripts/core/jira-setup.py` (interactive credential setup)

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

## Common Tasks — Copy These Directly

```bash
# Get issue
uv run scripts/core/jira-issue.py get PROJ-123

# Assign to me
uv run scripts/core/jira-issue.py update PROJ-123 --assignee me

# Create subtask (--type auto-resolves to subtask type when --parent given)
uv run scripts/workflow/jira-create.py issue PROJ "Summary" --type Task --parent PROJ-100

# Create and assign to me
uv run scripts/workflow/jira-create.py issue PROJ "Summary" --type Bug --parent PROJ-100 --assignee me

# Transition
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress"

# Search
uv run scripts/core/jira-search.py query "assignee = currentUser() AND status != Closed"

# Log work
uv run scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"

# List issue types for a project
uv run scripts/utility/jira-fields.py types PROJ

# Move issue
uv run scripts/workflow/jira-move.py issue NRS-100 SRVUC
```

`--assignee me` works on any script — resolves to the authenticated user automatically.

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, NOT Markdown.

## References

- `references/jql-quick-reference.md` - JQL syntax
- `references/troubleshooting.md` - Setup and auth issues

## Authentication

**Cloud**: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`
**Server/DC**: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`

Config via `~/.env.jira` or env vars. Multiple instances via `~/.jira/profiles.json` (auto-resolves from issue key/URL or `--profile NAME`).
