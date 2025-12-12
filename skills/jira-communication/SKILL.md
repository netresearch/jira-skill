---
name: jira-communication
description: >
  Jira API operations via Python CLI scripts. Use when Claude needs to:
  (1) Search issues with JQL queries, (2) Get or update issue details,
  (3) Create new issues, (4) Transition issue status (e.g., "To Do" → "Done"),
  (5) Add comments, (6) Log work time (worklogs), (7) List sprints and sprint issues,
  (8) List boards and board issues, (9) Create or list issue links,
  (10) Discover available Jira fields, (11) Get user profile information,
  (12) Download attachments from issues.
  Supports both Jira Cloud and Server/Data Center with automatic auth detection.
---

# Jira Communication

Standalone CLI scripts for Jira operations using `uv run`.

## Instructions

- **Default to `--json` flag** when processing data programmatically
- **Don't read scripts** - use `<script>.py --help` to understand options
- **Validate first**: Run `jira-validate.py` before other operations
- **Dry-run writes**: Use `--dry-run` for create/update/transition operations
- **Credentials**: Via `~/.env.jira` file or environment variables (see Authentication)
- **Content formatting**: Use **jira-syntax** skill for descriptions/comments (Jira wiki markup, NOT Markdown)

## Available Scripts

### Core Operations

#### `scripts/core/jira-validate.py`
**When to use:** Verify Jira connection and credentials

#### `scripts/core/jira-issue.py`
**When to use:** Get or update issue details

#### `scripts/core/jira-search.py`
**When to use:** Search issues with JQL queries

#### `scripts/core/jira-worklog.py`
**When to use:** Add or list time tracking entries

#### `scripts/core/jira-attachment.py`
**When to use:** Download attachments from Jira issues

### Workflow Operations

#### `scripts/workflow/jira-create.py`
**When to use:** Create new issues (use **jira-syntax** skill for description content)

#### `scripts/workflow/jira-transition.py`
**When to use:** Change issue status (e.g., "In Progress" → "Done")

#### `scripts/workflow/jira-comment.py`
**When to use:** Add comments to issues (use **jira-syntax** skill for formatting)

#### `scripts/workflow/jira-sprint.py`
**When to use:** List sprints or sprint issues

#### `scripts/workflow/jira-board.py`
**When to use:** List boards or board issues

### Utility Operations

#### `scripts/utility/jira-user.py`
**When to use:** Get user profile information

#### `scripts/utility/jira-fields.py`
**When to use:** Search available Jira fields

#### `scripts/utility/jira-link.py`
**When to use:** Create or list issue links

## ⚠️ Flag Ordering (Critical)

Global flags **MUST** come **before** the subcommand:

```bash
# ✓ Correct
uv run scripts/core/jira-issue.py --json get PROJ-123

# ✗ Wrong - fails with "No such option"
uv run scripts/core/jira-issue.py get PROJ-123 --json
```

## Quick Start

All scripts support `--help`, `--json`, `--quiet`, and `--debug`.

```bash
# Validate setup first
uv run scripts/core/jira-validate.py --verbose

# Search issues
uv run scripts/core/jira-search.py query "project = PROJ AND status = Open"

# Get issue details
uv run scripts/core/jira-issue.py get PROJ-123

# Transition with dry-run
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress" --dry-run
```

## Common Workflows

### Find my open issues and get details
```bash
uv run scripts/core/jira-search.py --json query "assignee = currentUser() AND status != Done"
```

### Log 2 hours of work
```bash
uv run scripts/core/jira-worklog.py add PROJ-123 2h --comment "Implemented feature X"
```

### Create and transition an issue
```bash
uv run scripts/workflow/jira-create.py issue PROJ "Fix login bug" --type Bug
uv run scripts/workflow/jira-transition.py do PROJ-124 "In Progress"
```

### Download an attachment
```bash
# Get issue with attachments listed
uv run scripts/core/jira-issue.py get PROJ-123

# Download attachment using URL from issue output
uv run scripts/core/jira-attachment.py download /rest/api/2/attachment/content/12345 ./file.pdf
```

## Related Skills

**jira-syntax**: Use for formatting descriptions and comments. Jira uses wiki markup, NOT Markdown.
- `*bold*` not `**bold**`
- `h2. Heading` not `## Heading`
- `{code:python}...{code}` not triple backticks

## References

- **JQL syntax**: See [references/jql-quick-reference.md](references/jql-quick-reference.md)
- **Troubleshooting**: See [references/troubleshooting.md](references/troubleshooting.md)

## Authentication

Configuration loaded in priority order:
1. `~/.env.jira` file (if exists)
2. Environment variables (fallback for missing values)

**Jira Cloud**: `JIRA_URL` + `JIRA_USERNAME` + `JIRA_API_TOKEN`
**Jira Server/DC**: `JIRA_URL` + `JIRA_PERSONAL_TOKEN`

Run `jira-validate.py --verbose` to verify setup. See [references/troubleshooting.md](references/troubleshooting.md) for detailed setup.
