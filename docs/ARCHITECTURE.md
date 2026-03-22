# Architecture

## System Overview

The jira-skill plugin provides two Claude Code skills for Jira integration: `jira-communication` (API operations via Python CLI scripts) and `jira-syntax` (wiki markup syntax, templates, validation).

## Components

### jira-communication Skill (`skills/jira-communication/`)

Python CLI scripts organized into three tiers:

- **Core** (`scripts/core/`): Fundamental operations -- issue get/update, JQL search, worklog, attachments, setup, and validation.
- **Workflow** (`scripts/workflow/`): Higher-level operations -- issue creation, transitions, comments, sprints, boards.
- **Utility** (`scripts/utility/`): Support tools -- field search, user info, issue linking.

All scripts use `uv` for dependency management and share a common base for authentication, output formatting, and error handling.

### jira-syntax Skill (`skills/jira-syntax/`)

Reference material and templates for Jira wiki markup syntax. Loaded on-demand by Claude Code when wiki markup formatting is needed.

### Plugin Metadata (`.claude-plugin/plugin.json`)

Declares the plugin's skills, version, and entry points for Claude Code discovery.

## Data Flow

```
User prompt (e.g., "search Jira for open bugs")
  -> Claude Code activates jira-communication skill
  -> Skill instructs agent to run appropriate Python script
  -> Script reads credentials from ~/.env.jira
  -> Script calls Jira REST API
  -> Structured output returned to agent
```

## Key Design Decisions

- **Zero MCP overhead**: Scripts invoked via Bash, no tool descriptions loaded into context.
- **uv for dependency management**: Fast, reproducible Python environments without Docker.
- **Dual deployment support**: Works with both Jira Server/DC and Jira Cloud via environment-based configuration.
