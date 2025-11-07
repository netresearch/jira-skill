---
version: "2.0.0"
mcp_servers:
  - name: "mcp-atlassian"
    description: "Jira REST API integration via MCP"
    required: true
---

# Jira MCP Communication Skill

## When to Use This Skill

Invoke this skill when performing Jira API operations via the mcp-atlassian MCP server:

**File/Command Patterns:**
- Using MCP tools: `mcp__mcp-atlassian__jira_*`
- Working with issue keys: PROJECT-123 format
- JQL (Jira Query Language) queries
- Files ending in `.jql`

**Keywords/Commands:**
- "jira search", "jql query"
- "create issue", "update issue"
- "add comment", "log work"
- "transition issue", "link issue"
- "get issue", "fetch issue"
- "batch operations"

**Tasks:**
- Search for issues using JQL queries
- Create/update Jira issues via API
- Add comments or worklog entries
- Transition issues through workflow states
- Link related issues
- Download/upload attachments
- Batch create/update multiple issues
- Retrieve issue details and metadata

## MCP Server Configuration

This skill requires the mcp-atlassian MCP server to be configured in Claude Code's MCP settings (`~/.config/claude-code/mcp.json` or `.claude/settings.local.json`):

```json
{
  "mcp-atlassian": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "--pull=always", "--env-file", "${HOME}/.env.jira",
             "ghcr.io/sooperset/mcp-atlassian:latest"]
  }
}
```

**User Setup:** Create `~/.env.jira` with:
```
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=your.email@example.com
JIRA_API_TOKEN=your_api_token_here
```

## Workflow

### 1. Issue Search and Retrieval

Use JQL for powerful searching:

```
# Find all open bugs in a project
mcp__mcp-atlassian__jira_search
  jql: "project = PROJ AND issuetype = Bug AND status != Closed"
  max_results: 50

# Get recent issues assigned to current user
mcp__mcp-atlassian__jira_search
  jql: "assignee = currentUser() AND updated >= -7d"

# Find issues in current sprint
mcp__mcp-atlassian__jira_search
  jql: "sprint in openSprints() AND project = PROJ"

# Get specific issue with all fields
mcp__mcp-atlassian__jira_get_issue
  issue_key: "PROJ-123"
  expand: ["changelog", "renderedFields"]
```

### 2. Issue Creation

Create issues with proper formatting (use jira-syntax skill for validation):

```
mcp__mcp-atlassian__jira_create_issue
  project_key: "PROJ"
  summary: "Brief, descriptive title"
  issue_type: "Task"
  description: "
h2. Problem Description

The current implementation has performance issues when processing large datasets.

h3. Steps to Reproduce
# Navigate to data import page
# Upload file larger than 10MB
# Click *Process Data* button
# Observe timeout after 30 seconds

h3. Expected Behavior
- File should process within 5 seconds
- Progress indicator should show upload status
- No timeout errors

h3. Technical Details
{code:java}
public void processData(File file) {
    // Current implementation
    largeDataProcessor.process(file);
}
{code}

*Priority:* High
*Affects Version:* 2.1.0
"
  priority: "High"
  labels: ["performance", "backend"]
  assignee: "john.doe@example.com"
```

### 3. Issue Updates

```
mcp__mcp-atlassian__jira_update_issue
  issue_key: "PROJ-123"
  fields: {
    "summary": "Updated title",
    "description": "h2. Updated Description\n\nNew content with proper formatting",
    "priority": {"name": "High"},
    "labels": ["backend", "urgent"]
  }
```

### 4. Adding Comments

Always use Jira wiki markup in comments (validate with jira-syntax skill):

```
mcp__mcp-atlassian__jira_add_comment
  issue_key: "PROJ-123"
  comment: "
h3. Investigation Results

I've investigated this issue and found the following:

* Root cause is in the {{DataProcessor}} class
* Occurs only with files over *10MB*
* Memory usage spikes to ~2GB during processing

h4. Proposed Solution
{code:java}
// Use streaming approach instead of loading entire file
public void processData(File file) {
    try (Stream<String> lines = Files.lines(file.toPath())) {
        lines.forEach(this::processLine);
    }
}
{code}

This should reduce memory usage to ~200MB and improve processing time.

[~john.doe] Please review this approach.
"
```

### 5. Work Logging

```
mcp__mcp-atlassian__jira_add_worklog
  issue_key: "PROJ-123"
  time_spent: "2h 30m"
  comment: "
h3. Work Completed
* Implemented streaming data processor
* Added unit tests for large file handling
* Updated documentation

h3. Next Steps
* Deploy to staging for testing
* Monitor memory usage metrics
"
```

### 6. Issue Transitions

```
# Get available transitions
mcp__mcp-atlassian__jira_get_transitions
  issue_key: "PROJ-123"

# Transition to new status
mcp__mcp-atlassian__jira_transition_issue
  issue_key: "PROJ-123"
  transition_id: "31"
  comment: "
h3. Testing Complete

All test cases passed successfully:
* Unit tests: {color:green}✓ Passed{color}
* Integration tests: {color:green}✓ Passed{color}
* Performance tests: {color:green}✓ Passed{color}

Ready for production deployment.
"
```

### 7. Issue Linking

```
mcp__mcp-atlassian__jira_create_issue_link
  link_type: "Blocks"
  inward_issue_key: "PROJ-123"
  outward_issue_key: "PROJ-456"
  comment: "This issue must be completed before PROJ-456 can proceed."

# Link to epic
mcp__mcp-atlassian__jira_link_to_epic
  issue_key: "PROJ-123"
  epic_key: "PROJ-100"
```

### 8. Batch Operations

```
mcp__mcp-atlassian__jira_batch_create_issues
  issues: [
    {
      "project_key": "PROJ",
      "summary": "Task 1: Database schema updates",
      "issue_type": "Task",
      "description": "h2. Requirements\n* Update user table\n* Add indexes"
    },
    {
      "project_key": "PROJ",
      "summary": "Task 2: API endpoint implementation",
      "issue_type": "Task",
      "description": "h2. Endpoints\n* {{GET /api/users}}\n* {{POST /api/users}}"
    }
  ]
```

### 9. Attachments

```
# Download attachments from an issue
mcp__mcp-atlassian__jira_download_attachments
  issue_key: "PROJ-123"
  output_dir: "./downloads"
```

## Integration with jira-syntax Skill

This skill works alongside the jira-syntax skill for validated content:

**Recommended Workflow:**
1. Use jira-syntax to get template and validate formatting
2. Use jira-mcp to submit validated content to Jira
3. Result: Properly formatted issues in Jira

**Example:**
```
User: "Create bug report for authentication failure"

1. jira-syntax provides template
2. User fills template
3. jira-syntax validates syntax
4. jira-mcp creates issue via MCP
5. ✅ PROJ-456 created with perfect formatting
```

## MCP Tool Reference

### Read Operations:
- `jira_get_user_profile` - Retrieve user information
- `jira_get_issue` - Get issue details with fields
- `jira_search` - JQL-based issue search
- `jira_search_fields` - Find custom fields
- `jira_get_project_issues` - All issues in project
- `jira_get_transitions` - Available status transitions
- `jira_get_worklog` - Worklog entries for issue
- `jira_download_attachments` - Download issue attachments
- `jira_get_link_types` - Available link types
- `jira_get_project_versions` - Get fix versions
- `jira_get_agile_boards` - List agile boards
- `jira_get_board_issues` - Issues on specific board
- `jira_get_sprints_from_board` - Sprints for board
- `jira_get_sprint_issues` - Issues in sprint

### Write Operations:
- `jira_create_issue` - Create new issue
- `jira_batch_create_issues` - Create multiple issues
- `jira_update_issue` - Update issue fields
- `jira_add_comment` - Add comment to issue
- `jira_add_worklog` - Log work time
- `jira_link_to_epic` - Link issue to epic
- `jira_create_issue_link` - Link two issues
- `jira_remove_issue_link` - Remove issue link
- `jira_transition_issue` - Change issue status

### Authentication:
1. MCP server reads credentials from `~/.env.jira`
2. Automatically authenticates with Jira API
3. Handles Jira Cloud vs Server/DC differences
4. Respects project filters (JIRA_PROJECTS_FILTER)

## Common Use Cases

### 1. Sprint Planning
```
# Search sprint items
mcp__mcp-atlassian__jira_search
  jql: "sprint = 'Sprint 42' AND project = PROJ ORDER BY priority DESC"

# Bulk update priorities, estimates, assignees
# Add sprint planning comments with tables showing capacity
```

### 2. Status Reports
```
# Generate report from JQL results
1. Count issues by status
2. List blockers with highlighting
3. Create summary table with progress
4. Add worklog summaries
```

### 3. Bulk Issue Creation
```
# Create multiple related issues
mcp__mcp-atlassian__jira_batch_create_issues with:
- Consistent formatting across batches
- Validated Jira syntax
- Proper linking between issues
```

### 4. Workflow Automation
```
# Automated status transitions based on conditions
1. Search for issues meeting criteria
2. Validate transition availability
3. Transition with appropriate comments
4. Link related issues as needed
```

## Best Practices

### Searching Issues:
1. Use specific JQL for precise results
2. Filter by project, sprint, assignee, status
3. Sort by priority, updated date, or created date
4. Limit results with pagination
5. Use field filters to reduce response size

### Batch Operations:
1. Group related issues for batch creation
2. Use consistent formatting across batches
3. Validate before executing batch operations
4. Monitor for errors in batch responses

### Performance:
1. Request only needed fields to reduce payload
2. Use pagination for large result sets
3. Cache frequently accessed project/field data
4. Batch operations when creating multiple issues

### Content Validation:
1. Always validate syntax with jira-syntax skill before submission
2. Test complex formatting in Jira UI first
3. Use templates for consistent structure
4. Verify required fields for issue type

## Troubleshooting

### Authentication Failures:
- Verify JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN set in `~/.env.jira`
- Check API token validity in Atlassian settings
- Ensure MCP server is running and accessible
- Verify Docker is installed and running

### Search Issues:
- Validate JQL syntax in Jira's search interface
- Check project filter configuration
- Verify field names are correct (use jira_search_fields)
- Ensure user has permission to view results

### Update Failures:
- Verify issue exists and is accessible
- Check required fields for issue type
- Ensure user has edit permissions
- Validate field values match Jira schema
- Confirm syntax is valid Jira wiki markup

### MCP Server Issues:
- Check Docker container is running: `docker ps`
- Verify env file exists: `ls -la ~/.env.jira`
- Test credentials in Jira web interface
- Review MCP server logs for errors

## References

- **JQL Reference**: `references/jql-reference.md` - Detailed JQL syntax and examples
- **MCP Tools Guide**: `references/mcp-tools-guide.md` - Complete tool documentation
- **Workflow Patterns**: `references/workflow-patterns.md` - Common operation sequences
- [mcp-atlassian GitHub](https://github.com/sooperset/mcp-atlassian) - MCP server documentation
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/) - Official API reference
- [JQL Documentation](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/) - JQL guide
