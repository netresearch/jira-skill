---
name: jira-communication
description: "Use when handling Jira issues, sprints, boards, links, fields, worklogs, attachments, or users, or on any Jira intent without a key (\"create/find a ticket\", \"pick a project\"). Auto-triggers on Jira URLs and issue keys (PROJ-123). Also use when MCP Atlassian tools fail or are unavailable for Jira Server/DC."
license: "(MIT AND CC-BY-SA-4.0). See LICENSE-MIT and LICENSE-CC-BY-SA-4.0"
compatibility: "Requires python 3.10+, uv. Jira Server/DC or Cloud instance with API access."
metadata:
  author: Netresearch DTT GmbH
  version: "3.31.3"
  repository: https://github.com/netresearch/jira-skill
allowed-tools: Bash(uv run ${CLAUDE_SKILL_DIR}/scripts/*) Bash(${CLAUDE_SKILL_DIR}/scripts/*) Read Write
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

Auth issues → `jira-setup.py`. **Anti-pattern:** `get` + `comment list` — use the matching verb.

## Scripts

Under `${CLAUDE_SKILL_DIR}/scripts/{core,workflow,utility}/`.

**Core**: `jira-issue.py`, `jira-search.py`, `jira-worklog.py`, `jira-attachment.py`, `jira-setup.py`, `jira-validate.py`
**Workflow**: `jira-create.py`, `jira-transition.py`, `jira-comment.py`, `jira-move.py`, `jira-sprint.py`, `jira-board.py`, `jira-version.py`, `tempo-account.py`
**Utility**: `jira-user.py`, `jira-fields.py`, `jira-link.py`, `jira-weblink.py`, `jira-worklog-query.py`, `jira-watchers.py`, `jira-qa-gather.py`

## Execution Style

Run directly. Scripts report `✓`/`✗`. Destructive ops: `--dry-run`. Global flags before subcommand: `jira-issue.py --json get PROJ-123`.

## Posting wiki markup rewrites and checks it first

Every `--comment` and `--description` option that writes wiki markup does two things before the write, both on by default, because text that renders wrong is silent — the API returns 2xx either way. That is all seven: `jira-comment.py add`/`edit`, `jira-transition.py do --comment`, `jira-transition.py path --comment`, `jira-worklog.py add --comment`, and the `--description` of `jira-create.py issue` and `jira-issue.py update`. A body smuggled in through `--fields-json` is not gated — that option writes raw fields by design.

1. **Dashes that Jira would render as strikethrough are escaped.** `\-` prints as a plain hyphen, so the posted text reads as written; stderr names how many lines changed and shows the first five. (The one shape where the escape is visible is two macros written against each other with no space — the dash can land inside a link target. Ordinary prose does not reach it.) `--no-auto-escape` keeps the markup verbatim — but on its own it does not post a deliberate `-strikethrough-`: the lint and the render check each still refuse the span. Use `--no-auto-escape --force` for that.
2. **The text is rendered by the instance and refused if it comes back struck through.** This costs one API call per post and catches what no local check can — an autolinked issue key creates a boundary that exists only on an instance where that key resolves. `--no-preflight` skips it; an unreachable renderer warns once and posts anyway.

`--force` posts despite either finding. The three flags are spelled the same on each. See `references/comments.md` for the details.

## Basic Usage

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py get PROJ-123
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-search.py query "assignee = currentUser() AND status != Closed" -n 5 -f key,summary,status
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --assignee me --priority Critical
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py add PROJ-123 "Comment text"
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-comment.py add PROJ-123 "Comment text" --no-auto-escape --force  # deliberate -strikethrough-
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-transition.py do PROJ-123 "In Progress"
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-create.py issue PROJ "Summary" --type Task
```

> **Transitions**: `list` shows each transition's id and what its screen requires; pass the **id** to `do` — a name or
> a target status is not always unique, and an ambiguous one is refused rather than guessed.
> **Terminal transitions**: pass `--resolution <value>` (`Done`, `Won't do`); if rejected ("cannot be set"),
> retry without it — `references/intent-verbs.md`. **Versions**: read `references/versions.md` before `jira-version.py`.
> **Mentions**: posting commands verify `[~username]` (miss → suggestions); `get`/`work` print usernames (`references/fields-and-users.md`).

## Related Skills

**jira-syntax**: descriptions/comments use Jira wiki markup, not Markdown.

## No editorializing

State what happened, not how good it is — `references/no-editorializing.md`.

## References

- `references/jql-quick-reference.md`, `references/jql-cookbook.md`
- `references/multi-profile.md` — `--profile`
- `references/troubleshooting.md` — auth, 401/403
- `references/issue-editing.md` — edit, delete, clear fields, `--fields-json`
- `references/creation.md` — create, `--parent`, fields, admin-scope (`project`, `tempo-account.py`)
- `references/comments.md` — edit, delete, lint, body via `-`
- `references/worklog.md` — `--started`, ranges, `--tempo-account`, `delete`
- `references/attachments.md` — upload, download
- `references/links.md` — links
- `references/agile.md` — sprints/boards
- `references/no-editorializing.md` — no self-praise
- `references/fields-and-users.md` — custom field IDs, users, issue types
- `references/watchers.md` — watch, subscribe, list watchers
- `references/versions.md` — fix/affects versions, releases, version CRUD
- `references/qa-gather.md` — audit bundle (siblings, prose URLs)
- `references/intent-verbs.md` — `work / qa / qa-fail / act`, exact transition names

## Authentication

Cloud: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`. Server/DC: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`. Config via `~/.env.jira` or `~/.jira/profiles.json`.
