# MCP Atlassian Tools Guide

Complete reference for all mcp-atlassian Jira MCP tools.

## Tool Naming Convention

All tools use the prefix: `mcp__mcp-atlassian__jira_*`

## Read Operations

### jira_get_issue
Get detailed information about a specific issue.

**Parameters:**
- `issue_key` (string, required): Issue key (e.g., "PROJ-123")
- `expand` (array, optional): Fields to expand (e.g., ["changelog", "renderedFields"])

**Returns:** Complete issue object with all fields

**Example:**
```
mcp__mcp-atlassian__jira_get_issue
  issue_key: "PROJ-123"
  expand: ["changelog"]
```

---

### jira_search
Search for issues using JQL.

**Parameters:**
- `jql` (string, required): JQL query string
- `max_results` (integer, optional): Maximum results to return (default: 50)
- `start_at` (integer, optional): Pagination offset (default: 0)
- `fields` (array, optional): Specific fields to retrieve

**Returns:** Array of matching issues

**Example:**
```
mcp__mcp-atlassian__jira_search
  jql: "project = PROJ AND status = 'In Progress'"
  max_results: 100
  fields: ["summary", "status", "assignee"]
```

---

### jira_get_transitions
Get available workflow transitions for an issue.

**Parameters:**
- `issue_key` (string, required): Issue key

**Returns:** Array of available transitions with IDs and names

**Example:**
```
mcp__mcp-atlassian__jira_get_transitions
  issue_key: "PROJ-123"
```

---

### jira_get_worklog
Retrieve worklog entries for an issue.

**Parameters:**
- `issue_key` (string, required): Issue key

**Returns:** Array of worklog entries

---

### jira_download_attachments
Download attachments from an issue.

**Parameters:**
- `issue_key` (string, required): Issue key
- `output_dir` (string, optional): Directory to save attachments

**Returns:** List of downloaded file paths

---

## Write Operations

### jira_create_issue
Create a new Jira issue.

**Parameters:**
- `project_key` (string, required): Project key (e.g., "PROJ")
- `summary` (string, required): Issue title
- `issue_type` (string, required): Type (e.g., "Bug", "Task", "Story")
- `description` (string, optional): Issue description (use Jira wiki markup)
- `priority` (string, optional): Priority name (e.g., "High", "Medium")
- `labels` (array, optional): Array of label strings
- `assignee` (string, optional): Username or email
- `reporter` (string, optional): Username or email
- `components` (array, optional): Component names
- `fix_versions` (array, optional): Fix version names
- `custom_fields` (object, optional): Custom field values

**Returns:** Created issue object with key

**Example:**
```
mcp__mcp-atlassian__jira_create_issue
  project_key: "PROJ"
  summary: "Login fails with timeout"
  issue_type: "Bug"
  description: "h2. Problem\n\nUsers cannot log in after 30 seconds."
  priority: "High"
  labels: ["backend", "urgent"]
  assignee: "john.doe@example.com"
```

---

### jira_batch_create_issues
Create multiple issues in a single operation.

**Parameters:**
- `issues` (array, required): Array of issue objects (same fields as jira_create_issue)

**Returns:** Array of created issues

**Example:**
```
mcp__mcp-atlassian__jira_batch_create_issues
  issues: [
    {
      "project_key": "PROJ",
      "summary": "Task 1",
      "issue_type": "Task",
      "description": "h2. Details\n..."
    },
    {
      "project_key": "PROJ",
      "summary": "Task 2",
      "issue_type": "Task"
    }
  ]
```

---

### jira_update_issue
Update an existing issue's fields.

**Parameters:**
- `issue_key` (string, required): Issue key
- `fields` (object, required): Fields to update

**Example:**
```
mcp__mcp-atlassian__jira_update_issue
  issue_key: "PROJ-123"
  fields: {
    "summary": "Updated title",
    "description": "h2. New Description",
    "priority": {"name": "High"},
    "labels": ["backend", "critical"]
  }
```

---

### jira_add_comment
Add a comment to an issue.

**Parameters:**
- `issue_key` (string, required): Issue key
- `comment` (string, required): Comment body (use Jira wiki markup)

**Example:**
```
mcp__mcp-atlassian__jira_add_comment
  issue_key: "PROJ-123"
  comment: "h3. Update\n\nFixed the issue in commit abc123."
```

---

### jira_add_worklog
Log work time on an issue.

**Parameters:**
- `issue_key` (string, required): Issue key
- `time_spent` (string, required): Time in Jira format (e.g., "2h 30m", "1d 4h")
- `comment` (string, optional): Worklog comment
- `started` (string, optional): Start date/time (ISO 8601)

**Example:**
```
mcp__mcp-atlassian__jira_add_worklog
  issue_key: "PROJ-123"
  time_spent: "3h 15m"
  comment: "Implemented authentication fix"
```

---

### jira_transition_issue
Transition an issue to a new status.

**Parameters:**
- `issue_key` (string, required): Issue key
- `transition_id` (string, required): Transition ID (from jira_get_transitions)
- `comment` (string, optional): Transition comment
- `fields` (object, optional): Fields to update during transition

**Example:**
```
mcp__mcp-atlassian__jira_transition_issue
  issue_key: "PROJ-123"
  transition_id: "31"
  comment: "h3. Testing Complete\n\nAll tests passed."
```

---

## Link Operations

### jira_create_issue_link
Create a link between two issues.

**Parameters:**
- `link_type` (string, required): Link type (e.g., "Blocks", "Relates", "Duplicates")
- `inward_issue_key` (string, required): Source issue
- `outward_issue_key` (string, required): Target issue
- `comment` (string, optional): Link comment

**Example:**
```
mcp__mcp-atlassian__jira_create_issue_link
  link_type: "Blocks"
  inward_issue_key: "PROJ-123"
  outward_issue_key: "PROJ-456"
  comment: "Must complete PROJ-123 first"
```

---

### jira_link_to_epic
Link an issue to an epic.

**Parameters:**
- `issue_key` (string, required): Issue to link
- `epic_key` (string, required): Epic key

---

### jira_get_link_types
Get available link types.

**Returns:** Array of link type objects

---

## Best Practices

### Error Handling
Always check for errors in responses:
- Authentication failures
- Permission denied
- Invalid field values
- Required fields missing

### Field Validation
Before creating/updating:
1. Verify project exists and is accessible
2. Check required fields for issue type
3. Validate custom field IDs
4. Ensure status transitions are valid

### Performance
1. Use `fields` parameter to request only needed data
2. Batch operations when creating multiple issues
3. Use pagination for large result sets (`start_at`, `max_results`)
4. Cache project and field metadata

### Content Format
1. Always use Jira wiki markup (not Markdown)
2. Validate syntax with jira-syntax skill
3. Test complex formatting in Jira UI first
4. Include language in code blocks: `{code:java}`

## Common Workflows

See `workflow-patterns.md` for detailed multi-step operation examples.

## References

- [mcp-atlassian Documentation](https://github.com/sooperset/mcp-atlassian)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
