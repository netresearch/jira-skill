---
name: jira-communication
description: >
  Jira API operations via Python CLI scripts. Triggers on: worklog logging ("log 2h on PROJ-123"),
  issue get/update ("show me PROJ-123", "update priority"), JQL search ("find issues in sprint"),
  environment validation ("validate jira setup"). Zero MCP overhead - scripts invoked via uv run.
---

# Jira Communication Skill

Script-based Jira API operations using `uv run` with `atlassian-python-api`.

## Quick Reference

### Prerequisites

1. **uv installed**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **Credentials configured**: Create `~/.env.jira` with one of:

   **For Jira Cloud:**
   ```
   JIRA_URL=https://your-company.atlassian.net
   JIRA_USERNAME=your-email@example.com
   JIRA_API_TOKEN=your-api-token
   ```

   **For Jira Server/Data Center:**
   ```
   JIRA_URL=https://jira.your-company.com
   JIRA_PERSONAL_TOKEN=your-personal-access-token
   ```

### Validate Setup

```bash
uv run scripts/core/jira-validate.py --verbose
```

## Core Operations (P0)

### Worklog Management (22.8% of usage)

```bash
# Add worklog entry
uv run scripts/core/jira-worklog.py add PROJ-123 "2h 30m" -c "Code review"

# List worklogs
uv run scripts/core/jira-worklog.py list PROJ-123 --limit 10
```

**Time format**: Passed directly to Jira API (e.g., `2h`, `2h 30m`, `1d`, `30m`)

### Issue Operations (26.7% of usage)

```bash
# Get issue details
uv run scripts/core/jira-issue.py get PROJ-123
uv run scripts/core/jira-issue.py get PROJ-123 --fields summary,status,assignee

# Update issue
uv run scripts/core/jira-issue.py update PROJ-123 --priority High --labels backend,urgent
uv run scripts/core/jira-issue.py update PROJ-123 --summary "New title" --dry-run
```

### JQL Search (10.7% of usage)

```bash
# Search with JQL
uv run scripts/core/jira-search.py query "project = PROJ AND status = 'In Progress'"
uv run scripts/core/jira-search.py query "assignee = currentUser()" --output keys
uv run scripts/core/jira-search.py query "updated >= -7d" --output json
```

**Common JQL patterns**:
- `project = PROJ` - Issues in project
- `assignee = currentUser()` - My issues
- `status = "In Progress"` - By status
- `updated >= -7d` - Updated last 7 days
- `sprint in openSprints()` - Current sprint

## Output Formats

All scripts support:
- **Default**: Human-readable formatted output
- `--json`: Machine-readable JSON
- `--quiet` / `-q`: Minimal output (keys only)

## Error Handling

Scripts provide actionable error messages:
```
✗ Configuration error: Missing authentication credentials. Provide either:
    - JIRA_USERNAME + JIRA_API_TOKEN (for Cloud)
    - JIRA_PERSONAL_TOKEN (for Server/DC)
```

Use `--debug` for verbose error output with stack traces.

## Architecture

```
scripts/
├── lib/                    # Shared utilities
│   ├── client.py          # Jira client initialization
│   ├── config.py          # Environment handling
│   └── output.py          # Formatting helpers
├── core/                   # P0 - Must have (68% coverage)
│   ├── jira-validate.py   # Environment validation
│   ├── jira-worklog.py    # Worklog operations
│   ├── jira-issue.py      # Issue get/update
│   └── jira-search.py     # JQL search
├── workflow/               # P1 - Phase 2
└── utility/                # P2 - Phase 3
```

## References

- [JQL Syntax Reference](references/jql-reference.md)
- [atlassian-python-api Docs](https://atlassian-python-api.readthedocs.io/)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
