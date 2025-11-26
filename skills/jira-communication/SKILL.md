---
name: jira-communication
description: Jira API operations via Python CLI scripts. Use when working with Jira issues, worklogs, sprints, transitions, comments, or searching with JQL. Supports both Jira Cloud and Server/Data Center.
---

# Jira Communication

Standalone CLI scripts for Jira operations using `uv run`.

## Instructions

- **Default to `--json` flag** when processing data programmatically
- **Don't read scripts** - use `<script>.py --help` to understand options
- **Validate first**: Run `jira-validate.py` before other operations
- **Dry-run writes**: Use `--dry-run` for create/update/transition operations
- Requires `~/.env.jira` with credentials (see `jira-validate.py --help`)

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

### Workflow Operations

#### `scripts/workflow/jira-create.py`
**When to use:** Create new issues

#### `scripts/workflow/jira-transition.py`
**When to use:** Change issue status (e.g., "In Progress" → "Done")

#### `scripts/workflow/jira-comment.py`
**When to use:** Add comments to issues

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

## Quick Start

All scripts support `--help`, `--json`, and `--quiet`.

**Important:** Global flags (`--json`, `--quiet`, `--debug`) must be placed **before** the subcommand:

```bash
# Correct flag placement
uv run scripts/core/jira-issue.py --help
uv run scripts/core/jira-issue.py --json get PROJ-123
uv run scripts/core/jira-search.py --quiet query "project = PROJ"

# Wrong - will fail with "No such option"
# uv run scripts/core/jira-issue.py get PROJ-123 --json
```

## Authentication

Requires `~/.env.jira` - run `jira-validate.py --help` for setup details.
