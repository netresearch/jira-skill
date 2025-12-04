---
name: jira-integration
description: "Comprehensive Jira integration through lightweight Python scripts. Use when searching issues (JQL), getting/updating issue details, creating issues, transitioning status, adding comments, logging worklogs, managing sprints and boards, creating issue links, or formatting Jira wiki markup. Supports both Jira Cloud and Server/Data Center with automatic authentication detection. By Netresearch."
---

# Jira Integration Skill

Comprehensive Jira integration through lightweight Python CLI scripts.

## When to Use This Skill

Use when:
- Searching Jira issues with JQL queries
- Getting or updating issue details
- Creating new issues (bugs, features, tasks)
- Transitioning issue status (To Do → In Progress → Done)
- Adding comments to issues
- Logging work time (worklogs)
- Managing sprints and boards
- Creating or listing issue links
- Writing Jira wiki markup (NOT Markdown)

## Sub-Skills

This plugin contains two specialized skills:

| Skill | Purpose |
|-------|---------|
| `jira-communication` | API operations via Python CLI scripts |
| `jira-syntax` | Wiki markup syntax, templates, validation |

## Quick Start

```bash
# Install uv (Python package runner)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Configure credentials in ~/.env.jira
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-api-token

# Validate setup
uv run scripts/core/jira-validate.py --verbose
```

## Common Operations

```bash
# Search issues
uv run scripts/core/jira-search.py query "project = PROJ AND status = 'In Progress'"

# Get issue details
uv run scripts/core/jira-issue.py get PROJ-123

# Add worklog
uv run scripts/core/jira-worklog.py add PROJ-123 "2h 30m" -c "Code review"

# Create issue
uv run scripts/workflow/jira-create.py issue PROJ "Fix bug" --type Bug --priority High

# Transition issue
uv run scripts/workflow/jira-transition.py PROJ-123 "In Progress"
```

## Features

- **Zero MCP overhead** - Scripts invoked via Bash, no tool descriptions loaded
- **Fast execution** - No Docker container spin-up
- **Full API coverage** - All common Jira operations supported
- **Jira Server/DC + Cloud** - Works with both deployment types
- **Automatic auth detection** - API token, PAT, or basic auth

## Documentation

- **README.md** - Installation and usage guide
- **MIGRATION.md** - Migration from older versions
- **CHANGELOG.md** - Version history
- **skills/jira-communication/SKILL.md** - API operations
- **skills/jira-syntax/SKILL.md** - Wiki markup and templates

## Scripts Reference

### Core Operations
| Script | Purpose |
|--------|---------|
| `jira-validate.py` | Verify connection and credentials |
| `jira-issue.py` | Get or update issue details |
| `jira-search.py` | Search with JQL queries |
| `jira-worklog.py` | Time tracking entries |
| `jira-comment.py` | Add/list comments |

### Workflow Operations
| Script | Purpose |
|--------|---------|
| `jira-create.py` | Create new issues |
| `jira-transition.py` | Change issue status |
| `jira-link.py` | Create/list issue links |
| `jira-sprint.py` | Sprint management |
| `jira-board.py` | Board operations |

## Jira Syntax Quick Reference

**Important**: Jira uses wiki markup, NOT Markdown.

| Jira Syntax | Purpose |
|-------------|---------|
| `h2. Title` | Heading (NOT `## Title`) |
| `*bold*` | Bold (NOT `**bold**`) |
| `{code:java}...{code}` | Code block (NOT triple backticks) |
| `[text\|url]` | Link |
| `[PROJ-123]` | Issue link |

See `skills/jira-syntax/SKILL.md` for complete syntax guide.
