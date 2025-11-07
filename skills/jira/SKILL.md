
# Jira Integration Skill

## When to Use This Skill

Invoke this skill when working with Jira through the mcp-atlassian MCP server:

**File/Command Patterns:**
- Any mention of "Jira", "issue", "ticket", "JIRA"
- Using MCP tools: `mcp__mcp-atlassian__jira_*`
- Working with issue keys: PROJECT-123 format
- JQL (Jira Query Language) queries

**Keywords/Commands:**
- Creating/updating Jira issues
- Searching tickets with JQL
- Managing projects and sprints
- Adding comments or worklog entries
- Assigning issues to users
- Transitioning issue status
- Linking related issues
- Downloading/uploading attachments
- Batch operations on issues

**Tasks:**
- Create properly formatted Jira tickets with wiki markup
- Search for issues using JQL queries
- Update issue fields (summary, description, assignee, priority)
- Add comments with correct Jira formatting
- Log work time on issues
- Transition issues through workflow states
- Link related issues (blocks, relates to, duplicates)
- Generate reports from Jira data
- Batch create/update multiple issues
- Enforce Jira wiki syntax in all descriptions and comments

## Workflow

### 1. Issue Search and Retrieval

Use JQL for powerful searching:

```
# Find all open bugs in a project
mcp__mcp-atlassian__jira_search with JQL: "project = PROJ AND issuetype = Bug AND status != Closed"

# Get recent issues assigned to current user
mcp__mcp-atlassian__jira_search with JQL: "assignee = currentUser() AND updated >= -7d"

# Find issues in current sprint
mcp__mcp-atlassian__jira_search with JQL: "sprint in openSprints() AND project = PROJ"
```

### 2. Issue Creation with Proper Formatting

Always enforce Jira wiki markup syntax:

```
# Create issue with properly formatted description
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

h3. Related Information
- [PROJ-123] - Original feature implementation
- [Performance Analysis|https://wiki.example.com/performance]

*Priority:* High
*Affects Version:* 2.1.0
"
```

### 34. Jira Wiki Markup Syntax Reference

**Text Formatting:**
- `*bold*` → **bold**
- `_italic_` → *italic*
- `{{monospace}}` → `monospace`
- `-strikethrough-` → ~~strikethrough~~
- `+underline+` → underline
- `^superscript^` → superscript
- `~subscript~` → subscript

**Headings:**
```
h1. Largest Heading
h2. Section Heading
h3. Subsection Heading
h4. Minor Heading
h5. Smaller Heading
h6. Smallest Heading
```

**Lists:**
```
* Bulleted item
** Nested bullet
* Another item

# Numbered item
## Nested number
# Another numbered item
```

**Links:**
```
[PROJ-123] - Issue link
[~username] - User mention
[http://example.com] - External link
[Link Label|http://example.com] - Labeled link
[^attachment.pdf] - Attachment reference
```

**Code Blocks:**
```
{code:language}
code content here
{code}

Supported languages: java, javascript, python, sql, xml, json, bash, etc.
```

**Tables:**
```
||Header 1||Header 2||Header 3||
|Cell A1|Cell A2|Cell A3|
|Cell B1|Cell B2|Cell B3|
```

**Panels and Quotes:**
```
{panel:title=Important Note|bgColor=#FFFFCE}
Panel content here
{panel}

{quote}
Quoted text here
{quote}

bq. Single line quote
```

**Colors:**
```
{color:red}Red text{color}
{color:#FF0000}Hex color{color}
```

### 4. Issue Updates

```
# Update issue fields
mcp__mcp-atlassian__jira_update_issue
  issue_key: "PROJ-123"
  fields: {
    "summary": "Updated title",
    "description": "h2. Updated Description\n\nNew content with proper formatting",
    "priority": {"name": "High"},
    "labels": ["backend", "urgent"]
  }
```

### 5. Adding Comments

Always use Jira wiki markup in comments:

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

### 6. Work Logging

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

### 7. Issue Transitions

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

### 8. Issue Linking

```
mcp__mcp-atlassian__jira_create_issue_link
  link_type: "Blocks"
  inward_issue_key: "PROJ-123"
  outward_issue_key: "PROJ-456"
  comment: "This issue must be completed before PROJ-456 can proceed."
```

### 9. Batch Operations

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

## Common Use Cases

### 1. Bug Report Creation
```
Create detailed bug report with:
- h2. Description section
- h3. Steps to Reproduce (numbered list)
- h3. Expected vs Actual Behavior
- {code} blocks for error messages
- Screenshots as attachments
- Links to related issues [PROJ-XXX]
```

### 2. Feature Request Documentation
```
Document feature request with:
- h2. Feature Overview
- h3. User Stories (bulleted list)
- h3. Acceptance Criteria (numbered list)
- {panel} for important notes
- Links to design docs
- User mentions for stakeholders [~username]
```

### 3. Sprint Planning
```
Search sprint items:
JQL: "sprint = 'Sprint 42' AND project = PROJ ORDER BY priority DESC"

Bulk update priorities, estimates, assignees
Add sprint planning comments with tables showing capacity
```

### 4. Status Reports
```
Generate report from JQL results:
- Count issues by status
- List blockers with {color:red} highlighting
- Create summary table with progress
- Add worklog summaries
```

## Jira Syntax Validation

### Always Check:
- [ ] Headings use `h1.` through `h6.` format
- [ ] Bold uses `*text*` not `**text**`
- [ ] Code blocks use `{code:language}` not ``` markdown ```
- [ ] Lists use `*` or `#` at start of line
- [ ] Tables use `||` for headers, `|` for cells
- [ ] Links use `[label|url]` or `[PROJ-123]` format
- [ ] User mentions use `[~username]` format
- [ ] Colors use `{color:name}text{color}` format
- [ ] Panels use `{panel:title=X}content{panel}` format

### Common Mistakes to Avoid:
- ❌ Using Markdown syntax (`**bold**`, `## heading`)
- ❌ Forgetting space after heading marker (`h2.Title` → `h2. Title`)
- ❌ Using wrong list nesting (`**` for bullets, `##` for numbers)
- ❌ Missing language in code blocks (`{code}` → `{code:java}`)
- ❌ Incorrect link format (`[text](url)` → `[text|url]`)

## MCP Tool Reference

### Available Jira Tools:
- `jira_get_user_profile` - Retrieve user information
- `jira_get_issue` - Get issue details with fields
- `jira_search` - JQL-based issue search
- `jira_search_fields` - Find custom fields
- `jira_get_project_issues` - All issues in project
- `jira_get_transitions` - Available status transitions
- `jira_get_worklog` - Worklog entries for issue
- `jira_download_attachments` - Download issue attachments
- `jira_get_link_types` - Available link types
- `jira_create_issue` - Create new issue
- `jira_batch_create_issues` - Create multiple issues
- `jira_update_issue` - Update issue fields
- `jira_add_comment` - Add comment to issue
- `jira_add_worklog` - Log work time
- `jira_link_to_epic` - Link issue to epic
- `jira_create_issue_link` - Link two issues
- `jira_remove_issue_link` - Remove issue link
- `jira_transition_issue` - Change issue status
- `jira_get_project_versions` - Get fix versions

### Authentication Flow:
1. Verify MCP server configured with credentials
2. Use appropriate tools based on Jira Cloud vs Server/DC
3. Handle read-only mode gracefully
4. Check project filters (JIRA_PROJECTS_FILTER)

## Best Practices

### Writing Descriptions:
1. Start with h2. heading for main sections
2. Use h3. for subsections
3. Structure: Problem → Solution → Details → Next Steps
4. Include code blocks for technical content
5. Add links to related resources
6. Mention relevant users with [~username]
7. Use panels for important warnings/notes
8. Add tables for structured data

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

## Troubleshooting

### Common Issues:

**Authentication Failures:**
- Verify JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN set
- Check API token validity in Atlassian settings
- Ensure MCP server is running and accessible

**Syntax Errors:**
- Validate Jira wiki markup before submitting
- Test complex formatting in Jira UI first
- Check for proper heading format (h1. not #)
- Verify code block language is supported

**Search Issues:**
- Validate JQL syntax in Jira's search interface
- Check project filter configuration
- Verify field names are correct (use jira_search_fields)
- Ensure user has permission to view results

**Update Failures:**
- Verify issue exists and is accessible
- Check required fields for issue type
- Ensure user has edit permissions
- Validate field values match Jira schema

## References

- [Jira Wiki Markup Syntax](https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all)
- [mcp-atlassian GitHub](https://github.com/sooperset/mcp-atlassian)
- [JQL Reference](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
