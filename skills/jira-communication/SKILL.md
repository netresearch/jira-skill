---
name: jira-communication
description: "Use when interacting with Jira issues - searching, creating, updating, transitioning, commenting, logging work, downloading attachments, managing sprints, boards, issue links, fields, or users. Auto-triggers on Jira URLs and issue keys (PROJ-123)."
allowed-tools: Bash(uv run scripts/*:*) Read
---

# Jira Communication

CLI scripts for Jira operations using `uv run`. All scripts support `--help`, `--json`, `--quiet`, `--debug`.

## Auto-Trigger

Trigger when user mentions:
- **Jira URLs**: `https://jira.*/browse/*`, `https://*.atlassian.net/browse/*`
- **Issue keys**: `PROJ-123`, `NRS-4167`

When triggered by URL → extract issue key → run `jira-issue.py get PROJ-123`

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
| `scripts/workflow/jira-transition.py` | Change status |
| `scripts/workflow/jira-comment.py` | Add comments |
| `scripts/workflow/jira-sprint.py` | List sprints |
| `scripts/workflow/jira-board.py` | List boards |
| `scripts/utility/jira-user.py` | User info |
| `scripts/utility/jira-fields.py` | Search fields |
| `scripts/utility/jira-link.py` | Issue links |

## Critical: Flag Ordering

Global flags **MUST** come **before** subcommand:
```bash
# Correct:  uv run scripts/core/jira-issue.py --json get PROJ-123
# Wrong:    uv run scripts/core/jira-issue.py get PROJ-123 --json
```

## Quick Examples

```bash
uv run scripts/core/jira-validate.py --verbose
uv run scripts/core/jira-search.py query "assignee = currentUser()"
uv run scripts/core/jira-issue.py get PROJ-123
uv run scripts/core/jira-worklog.py add PROJ-123 2h --comment "Work done"
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress" --dry-run
```

## Related Skills

**jira-syntax**: For descriptions/comments. Jira uses wiki markup, NOT Markdown.

## References

- `references/jql-quick-reference.md` - JQL syntax
- `references/troubleshooting.md` - Setup and auth issues

## Authentication

**Cloud**: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`
**Server/DC**: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`

Config via `~/.env.jira` or env vars. Run `jira-validate.py --verbose` to verify.

## Multi-Profile Support

When `~/.jira/profiles.json` exists, multiple Jira instances are supported.

**Profile resolution** (automatic, priority order):
1. `--env-file PATH` → legacy single-file behavior
2. `--profile NAME` flag → use named profile directly
3. Full Jira URL in input → match host to profile
4. Issue key (e.g., WEB-1381) → match project prefix to profile
5. `.jira-profile` file in working directory → use named profile
6. Default profile from profiles.json
7. Fallback to `~/.env.jira`

**When triggered by URL** → extract host → match profile automatically:
```bash
# User mentions https://jira.meine-krankenkasse.de/browse/WEB-1381
# Profile "mkk" is automatically resolved from URL host match
uv run scripts/core/jira-issue.py get WEB-1381
```

**When triggered by issue key only** → check project mapping automatically:
```bash
# WEB is mapped to "mkk" profile → automatically resolved
uv run scripts/core/jira-issue.py get WEB-1381
```

**If ambiguous** → ask user which profile to use.

**Profile management**:
```bash
uv run scripts/core/jira-setup.py --profile mkk                    # Create profile
uv run scripts/core/jira-validate.py --profile mkk --verbose        # Validate profile
uv run scripts/core/jira-validate.py --all-profiles                 # Validate all
uv run scripts/core/jira-setup.py --migrate                         # Migrate .env.jira
```
