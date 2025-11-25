# Migration Guide: From MCP to Script-Based Jira Skill

This guide helps you migrate from the old `jira-mcp` skill (v2.x) that used the `mcp-atlassian` Docker MCP server to the new `jira-communication` skill (v3.x) that uses lightweight Python scripts.

## Why Migrate?

| Aspect | Old (v2.x) | New (v3.x) |
|--------|-----------|-----------|
| Context tokens | ~8,000-12,000 | ~500 |
| Startup time | 3-5s (Docker) | <1s |
| Dependencies | Docker + MCP | uv only |
| Offline capability | No | Validation only |

## Prerequisites

### 1. Install uv

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pip
pip install uv
```

### 2. Verify Environment File

Ensure `~/.env.jira` exists with:

```
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-api-token
```

For Jira Server/DC with Personal Access Token:

```
JIRA_URL=https://jira.yourcompany.com
JIRA_PERSONAL_TOKEN=your-personal-access-token
```

### 3. Validate Setup

```bash
cd skills/jira-communication
uv run scripts/core/jira-validate.py --verbose
```

## Command Migration Reference

### Issue Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_get_issue PROJ-123` | `uv run scripts/core/jira-issue.py get PROJ-123` |
| `mcp__jira_update_issue PROJ-123 ...` | `uv run scripts/core/jira-issue.py update PROJ-123 ...` |
| `mcp__jira_create_issue ...` | `uv run scripts/workflow/jira-create.py issue ...` |

### Search Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_search "project = PROJ"` | `uv run scripts/core/jira-search.py query "project = PROJ"` |

### Worklog Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_add_worklog PROJ-123 "2h"` | `uv run scripts/core/jira-worklog.py add PROJ-123 "2h"` |
| `mcp__jira_get_worklog PROJ-123` | `uv run scripts/core/jira-worklog.py list PROJ-123` |

### Transition Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_get_transitions PROJ-123` | `uv run scripts/workflow/jira-transition.py list PROJ-123` |
| `mcp__jira_transition_issue ...` | `uv run scripts/workflow/jira-transition.py do ...` |

### Comment Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_add_comment PROJ-123 "text"` | `uv run scripts/workflow/jira-comment.py add PROJ-123 "text"` |

### Agile Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_get_agile_boards` | `uv run scripts/workflow/jira-board.py list` |
| `mcp__jira_get_board_issues 42` | `uv run scripts/workflow/jira-board.py issues 42` |
| `mcp__jira_get_sprints_from_board 42` | `uv run scripts/workflow/jira-sprint.py list 42` |
| `mcp__jira_get_sprint_issues 123` | `uv run scripts/workflow/jira-sprint.py issues 123` |

### Field Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_search_fields "sprint"` | `uv run scripts/utility/jira-fields.py search sprint` |

### User Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_get_user_profile "me"` | `uv run scripts/utility/jira-user.py me` |

### Link Operations

| Old (MCP) | New (Script) |
|-----------|-------------|
| `mcp__jira_get_link_types` | `uv run scripts/utility/jira-link.py list-types` |
| `mcp__jira_create_issue_link ...` | `uv run scripts/utility/jira-link.py create ...` |

## Output Format Migration

### JSON Output

Old: JSON was default
New: Human-readable is default, use `--json` for JSON

```bash
# Get JSON output
uv run scripts/core/jira-issue.py get PROJ-123 --json
```

### Quiet Mode

New feature for scripting:

```bash
# Just get the issue key
uv run scripts/core/jira-search.py query "project = PROJ" --output keys
```

## New Features

### Dry-Run Mode

Test write operations without making changes:

```bash
uv run scripts/workflow/jira-create.py issue PROJ "Test" --type Task --dry-run
uv run scripts/workflow/jira-transition.py do PROJ-123 "Done" --dry-run
uv run scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type "Blocks" --dry-run
```

### Validation Script

Pre-flight checks for your environment:

```bash
uv run scripts/core/jira-validate.py --verbose --project PROJ
```

### Server/DC Support

Full support for Jira Server and Data Center using Personal Access Tokens:

```bash
# Set JIRA_PERSONAL_TOKEN in ~/.env.jira
# The scripts auto-detect the authentication mode
```

## Troubleshooting

### "uv not found"

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### "Environment file not found"

Create `~/.env.jira` with your credentials.

### "Authentication failed"

1. Verify JIRA_URL is correct
2. For Cloud: JIRA_USERNAME is your email
3. For Server/DC: Use JIRA_PERSONAL_TOKEN instead
4. Regenerate your API token if expired

### Import errors

Run scripts from the skill directory:
```bash
cd skills/jira-communication
uv run scripts/core/jira-issue.py get PROJ-123
```

## Rollback

If you need to temporarily use the old MCP-based approach:

1. Check out a previous version from git history (pre-v3.0.0)
2. Re-add the MCP server configuration to your setup
3. Note: This is not recommended for long-term use
