---
name: jira-communication
description: "Use when interacting with Jira issues - searching, creating, updating, moving, transitioning, commenting, logging work, downloading attachments, managing sprints, boards, issue links, web links, fields, or users. Auto-triggers on Jira URLs and issue keys (PROJ-123). Also use when MCP Atlassian tools fail or are unavailable for Jira Server/DC."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python 3.10+, uv. Jira Server/DC or Cloud instance with API access."
metadata:
  author: Netresearch DTT GmbH
  version: "3.18.1"
  repository: https://github.com/netresearch/jira-skill
allowed-tools: Bash(python:*) Bash(uv:*) Read Write
---

# Jira Communication

CLI scripts via `uv run`, all supporting `--help`, `--json`, `--quiet`, `--debug`.

## Auto-Trigger

On Jira URL or issue key (PROJ-123), pick by **intent** — each is one call:

| Intent | Tool |
|---|---|
| triage / work on ticket | `jira-issue.py work KEY` |
| start QA review | `jira-issue.py qa KEY` |
| QA-fail follow-up | `jira-issue.py qa-fail KEY` |
| field-only lookup | `jira-issue.py get KEY --fields ...` |
| change status | `jira-issue.py act KEY` → `jira-transition.py do` |
| audit / sibling discovery | `jira-qa-gather.py KEY` |

Auth issues → `jira-setup.py`. **Anti-pattern:** `get` + `comment list` on one key — use the matching verb. See `references/intent-verbs.md`.

## Scripts

Under `${CLAUDE_SKILL_DIR}/scripts/{core,workflow,utility}/`.

**Core**: `jira-issue.py`, `jira-search.py`, `jira-worklog.py`, `jira-attachment.py`, `jira-setup.py`, `jira-validate.py`
**Workflow**: `jira-create.py`, `jira-transition.py`, `jira-comment.py`, `jira-move.py`, `jira-sprint.py`, `jira-board.py`, `jira-version.py`
**Utility**: `jira-user.py`, `jira-fields.py`, `jira-link.py`, `jira-weblink.py`, `jira-worklog-query.py`, `jira-watchers.py`, `jira-qa-gather.py`

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

> **Terminal transitions**: always pass `--resolution <value>` (e.g. `Done`, `Won't do`, `Duplicate`) or the
> resolution field stays empty and the ticket appears unresolved. See `references/intent-verbs.md`.

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, not Markdown.

## References

- `references/jql-quick-reference.md`, `references/jql-cookbook.md` — JQL beyond simple filters
- `references/multi-profile.md` — multiple Jira instances, `--profile`
- `references/troubleshooting.md` — auth, SSL, 401, 403, connection
- `references/issue-editing.md` — `--description`, `--fields-json`, reporter, deletes, moves
- `references/creation.md` — `--parent`, components, custom fields
- `references/comments.md` — edit, delete, list, markup lint / `--force`
- `references/worklog.md` — `--started`, date ranges, `jira-worklog-query.py`
- `references/attachments.md` — upload, download (cwd-only), inspect
- `references/links.md` — issue/web links, instance-specific link types
- `references/agile.md` — sprints, boards, `board --name`
- `references/fields-and-users.md` — custom field IDs, users, issue types
- `references/watchers.md` — watch, subscribe, list watchers
- `references/versions.md` — fix/affects versions, releases, version CRUD
- `references/qa-gather.md` — comprehensive audit bundle (siblings, prose URLs)
- `references/intent-verbs.md` — `work / qa / qa-fail / act`, exact transition names

## Authentication

Cloud: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`. Server/DC: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`. Config via `~/.env.jira` or `~/.jira/profiles.json`.
