---
name: "jira-mcp"
description: "Jira REST API integration via mcp-atlassian MCP server for issue management, search, and automation. Use when: (1) Searching issues with JQL queries like 'project = X AND status = Open', (2) Creating or updating Jira issues via API, (3) Adding comments or worklog entries, (4) Transitioning issues through workflow states, (5) Linking related issues or epics, (6) Batch operations on multiple issues, (7) Using any mcp__mcp-atlassian__jira_* tool, (8) Working with issue keys in PROJECT-123 format, (9) Downloading/uploading attachments, (10) Sprint and board operations"
---

# Jira MCP Communication Skill

Handles all Jira API operations via the mcp-atlassian MCP server. For syntax validation and templates, use the **jira-syntax** skill.

## Prerequisites

Create `~/.env.jira` with credentials:
```
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=your.email@example.com
JIRA_API_TOKEN=your_api_token_here
```

## Core Operations

### Search Issues
```
jira_search
  jql: "project = PROJ AND status != Closed ORDER BY priority DESC"
  max_results: 50
```
See `references/jql-reference.md` for complete JQL syntax.

### Create Issue
```
jira_create_issue
  project_key: "PROJ"
  summary: "Brief, descriptive title"
  issue_type: "Task"
  description: "[Use Jira wiki markup - validate with jira-syntax skill]"
  priority: "High"
  labels: ["backend"]
```

### Update Issue
```
jira_update_issue
  issue_key: "PROJ-123"
  fields: {"summary": "New title", "priority": {"name": "High"}}
```

### Add Comment
```
jira_add_comment
  issue_key: "PROJ-123"
  comment: "h3. Update\n\nProgress on implementation..."
```

### Log Work
```
jira_add_worklog
  issue_key: "PROJ-123"
  time_spent: "2h 30m"
  comment: "Completed unit tests"
```

### Transition Issue
```
jira_get_transitions issue_key: "PROJ-123"  # Get available transitions first
jira_transition_issue issue_key: "PROJ-123" transition_id: "31"
```

### Link Issues
```
jira_create_issue_link
  link_type: "Blocks"
  inward_issue_key: "PROJ-123"
  outward_issue_key: "PROJ-456"

jira_link_to_epic issue_key: "PROJ-123" epic_key: "PROJ-100"
```

### Batch Create
```
jira_batch_create_issues
  issues: [
    {"project_key": "PROJ", "summary": "Task 1", "issue_type": "Task"},
    {"project_key": "PROJ", "summary": "Task 2", "issue_type": "Task"}
  ]
```

## MCP Tools Quick Reference

**Read**: `jira_get_issue`, `jira_search`, `jira_get_transitions`, `jira_get_worklog`, `jira_get_project_issues`, `jira_search_fields`, `jira_get_link_types`, `jira_download_attachments`

**Write**: `jira_create_issue`, `jira_batch_create_issues`, `jira_update_issue`, `jira_add_comment`, `jira_add_worklog`, `jira_transition_issue`, `jira_create_issue_link`, `jira_link_to_epic`, `jira_remove_issue_link`

**Agile**: `jira_get_agile_boards`, `jira_get_board_issues`, `jira_get_sprints_from_board`, `jira_get_sprint_issues`

See `references/mcp-tools-guide.md` for complete tool documentation.

## Integration with jira-syntax Skill

1. **jira-syntax**: Get templates, validate Jira wiki markup formatting
2. **jira-mcp**: Submit validated content to Jira via API

Always validate content with jira-syntax before submission to ensure proper rendering.

## Common Patterns

See `references/workflow-patterns.md` for:
- Sprint planning workflows
- Status report generation
- Bulk issue creation
- Workflow automation sequences

## Troubleshooting

**Authentication**: Verify `~/.env.jira` exists with valid JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

**Search returns nothing**: Test JQL in Jira UI first; check JIRA_PROJECTS_FILTER if set

**Update fails**: Use `jira_search_fields` to find correct field names; verify edit permissions

**MCP server issues**: Check Docker is running (`docker ps`); review container logs

## References

- `references/jql-reference.md` - JQL syntax and examples
- `references/mcp-tools-guide.md` - Complete MCP tool documentation
- `references/workflow-patterns.md` - Common operation sequences
- [mcp-atlassian GitHub](https://github.com/sooperset/mcp-atlassian)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
