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

Under `${CLAUDE_SKILL_DIR}/scripts/{core,workflow,utility}/`.

**Core**: `jira-issue.py`, `jira-search.py`, `jira-worklog.py`, `jira-attachment.py`, `jira-setup.py`, `jira-validate.py`
**Workflow**: `jira-create.py`, `jira-transition.py`, `jira-comment.py`, `jira-move.py`, `jira-sprint.py`, `jira-board.py`
**Utility**: `jira-user.py`, `jira-fields.py`, `jira-link.py`, `jira-weblink.py`, `jira-worklog-query.py`, `jira-watchers.py`

## Execution Style

Run directly. Scripts report `✓`/`✗`. Destructive ops: `--dry-run`. Global flags before subcommand: `jira-issue.py --json get PROJ-123`.

## Basic Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py get PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py query "assignee = currentUser() AND status != Closed" -n 5 -f key,summary,status
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --assignee me --priority Critical
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py add PROJ-123 "Comment text"
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-transition.py do PROJ-123 "In Progress"
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Summary" --type Task
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-attachment.py add PROJ-123 screenshot.png
```

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, not Markdown.

## References

- `references/jql-quick-reference.md` — when JQL goes beyond simple filters
- `references/jql-cookbook.md` — when translating natural-language requests into JQL
- `references/multi-profile.md` — when using multiple Jira instances or `--profile`
- `references/troubleshooting.md` — when hitting auth, SSL, 401, 403, or connection failures
- `references/issue-editing.md` — when using `--fields-json`, reporter changes, deletes, or moves
- `references/creation.md` — when creating with `--parent`, reporter, components, or custom fields
- `references/comments.md` — when editing, deleting, or listing comments
- `references/worklog.md` — when using `--started`, date ranges, or `jira-worklog-query.py`
- `references/attachments.md` — when uploading, downloading, or inspecting attachments
- `references/links.md` — when working with issue or web links
- `references/agile.md` — when working with sprints, boards, or `board --name`
- `references/fields-and-users.md` — when looking up custom field IDs, users, or issue types
- `references/watchers.md` — when the user asks to watch, subscribe, notify on, or list watchers of an issue

## Authentication

Cloud: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`. Server/DC: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`. Config via `~/.env.jira` or `~/.jira/profiles.json`.
