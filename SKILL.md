---
name: jira-integration
description: "Agent Skill: Comprehensive Jira integration through lightweight Python scripts. AUTOMATICALLY TRIGGER when user mentions Jira URLs like 'https://jira.*/browse/*', 'https://*.atlassian.net/browse/*', or issue keys like 'PROJ-123'. Use when searching issues (JQL), getting/updating issue details, creating issues, transitioning status, adding comments, logging worklogs, managing sprints and boards, creating issue links, or formatting Jira wiki markup. If authentication fails, offer to configure credentials interactively. Supports both Jira Cloud and Server/Data Center with automatic authentication detection. By Netresearch."
---

# Jira Integration Skill

Comprehensive Jira integration through lightweight Python CLI scripts.

## Auto-Trigger Patterns

**AUTOMATICALLY ACTIVATE** when user mentions:
- **Jira URLs**: `https://jira.*/browse/*`, `https://*.atlassian.net/browse/*`, `https://*/jira/browse/*`
- **Issue keys**: Pattern like `PROJ-123`, `NRS-4167`, `ABC-1` (uppercase letters + hyphen + numbers)
- **Keywords**: "Jira issue", "Jira ticket", "search Jira", "open this ticket"

**Example triggers:**
- "I want to work on https://jira.netresearch.de/browse/NRS-4167" → Extract NRS-4167, fetch issue
- "What's the status of PROJ-123?" → Fetch issue PROJ-123
- "Search Jira for my open issues" → Run JQL search

## Authentication Failure Handling

**CRITICAL**: When authentication fails, DO NOT just display the error. Instead:

1. **Detect failure** - Look for "Missing required variable", "Configuration errors", or 401/403 responses
2. **Offer help** - Ask: "Jira credentials aren't configured. Would you like me to help set them up?"
3. **Run interactive setup** - Execute: `uv run skills/jira-communication/scripts/core/jira-setup.py`
4. **The script will**:
   - Prompt for Jira URL
   - Auto-detect Cloud vs Server/DC
   - Ask for credentials (API token or Personal Access Token)
   - Validate credentials before saving
   - Create `~/.env.jira` with secure permissions (600)

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

## Sub-Skill Documentation

- **skills/jira-communication/SKILL.md** - API operations (scripts, JQL, worklogs)
- **skills/jira-syntax/SKILL.md** - Wiki markup syntax, templates, validation

## Scripts Reference

### Core Operations
| Script | Purpose |
|--------|---------|
| `jira-setup.py` | **Interactive credential setup** (run when auth fails) |
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

---

> **Contributing:** Improvements to this skill should be submitted to the source repository:
> https://github.com/netresearch/jira-skill
