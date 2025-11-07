# Jira Integration Skill

Intelligent Jira integration for Claude Code using the mcp-atlassian MCP server with automatic Jira wiki markup syntax enforcement.

## Overview

This skill enables seamless interaction with Jira through Claude Code, ensuring all ticket content follows official Jira wiki markup standards. It provides comprehensive templates, syntax validation, and workflow guidance for common Jira operations.

## Features

### 🎯 Core Capabilities
- **Issue Management**: Create, read, update, and search Jira issues
- **Syntax Enforcement**: Automatic Jira wiki markup validation and formatting
- **JQL Queries**: Powerful searching with Jira Query Language
- **Bulk Operations**: Create or update multiple issues efficiently
- **Work Logging**: Track time spent with properly formatted entries
- **Issue Linking**: Connect related issues (blocks, relates to, duplicates)
- **Attachments**: Upload and download file attachments
- **Transitions**: Move issues through workflow states

### 📝 Templates Included
- **Bug Report Template**: Comprehensive bug documentation with proper formatting
- **Feature Request Template**: Detailed feature proposals with acceptance criteria
- **Task Template**: Standard task structure with checklists
- **Comment Templates**: Structured updates and status reports

### 🎨 Jira Syntax Support
- Headings (h1-h6)
- Text formatting (bold, italic, monospace, strikethrough)
- Lists (bulleted, numbered, mixed)
- Tables with headers
- Code blocks with syntax highlighting
- Panels and quotes
- Colors and highlighting
- Links (issues, users, external, attachments)
- Special blocks (expand, noformat, quote)

## Installation

### Prerequisites

1. **mcp-atlassian MCP Server**: This skill requires the mcp-atlassian MCP server
   - Repository: https://github.com/sooperset/mcp-atlassian
   - Install via Docker or follow repository installation instructions

2. **Jira Credentials**: You need one of:
   - **Cloud**: API token from https://id.atlassian.com/manage-profile/security/api-tokens
   - **Server/DC**: Personal Access Token from your Jira instance

### MCP Server Configuration

**Note**: The skill includes automatic MCP configuration via `.mcp.json` - you don't need to manually configure `~/.claude/mcp.json`.

#### Quick Setup with Docker (Recommended)

1. **Create Environment File** (`~/.env.jira`):
   ```bash
   # Create ~/.env.jira with your credentials:
   JIRA_URL=https://yourcompany.atlassian.net
   JIRA_USERNAME=your.email@company.com
   JIRA_API_TOKEN=your-api-token
   ```

2. **Install Skill** (MCP server starts automatically):
   ```bash
   # The skill's bundled .mcp.json will automatically start the Docker container
   # No manual MCP server setup needed!
   ```

#### Manual Configuration

For manual setup without Docker:

```bash
# For Jira Cloud
export JIRA_URL="https://yourcompany.atlassian.net"
export JIRA_USERNAME="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"

# For Jira Server/Data Center
export JIRA_URL="https://jira.yourcompany.com"
export JIRA_USERNAME="your-username"
export JIRA_API_TOKEN="your-personal-access-token"

# Optional: Filter to specific projects
export JIRA_PROJECTS_FILTER="PROJ1,PROJ2,PROJ3"
```

**Note**: The MCP server runs automatically via Docker when you use the skill. No manual setup required!

### Install Skill

```bash
# Add marketplace (if not already added)
/plugin marketplace add netresearch/claude-code-marketplace

# Install Jira skill
/plugin install jira
```

## Usage

### Quick Start

1. **Search for Issues**
   ```
   Search for all open bugs in project PROJ
   → Uses: mcp__mcp-atlassian__jira_search with JQL
   ```

2. **Create Bug Report**
   ```
   Create a bug report for login issue
   → Uses bug-report-template.md
   → Enforces Jira wiki markup syntax
   ```

3. **Add Comment**
   ```
   Add status update comment to PROJ-123
   → Automatically formats with h3 headings
   → Uses proper Jira syntax for all content
   ```

### Common Workflows

#### Creating Issues

The skill automatically enforces Jira wiki markup:

```
Create feature request for bulk export functionality

Result:
✅ h2. headings for main sections
✅ h3. headings for subsections
✅ Numbered lists for acceptance criteria
✅ Tables for metrics
✅ Code blocks with syntax highlighting
✅ Proper panel formatting for important notes
```

#### Searching Issues

Use natural language or JQL:

```
"Find high priority bugs assigned to me from last week"

Converts to:
JQL: "project = PROJ AND priority = High AND assignee = currentUser() AND created >= -7d"
```

#### Updating Issues

```
Update PROJ-123 description with technical details

Result:
✅ Preserves existing formatting
✅ Adds new sections with proper syntax
✅ Includes code blocks for technical content
✅ Links to related issues correctly
```

## Templates

### Bug Report (`skills/jira/templates/bug-report-template.md`)

Comprehensive bug documentation structure:
- Environment details
- Steps to reproduce
- Expected vs actual behavior
- Error messages in panels
- Screenshots and attachments
- Related issues
- Technical notes

### Feature Request (`skills/jira/templates/feature-request-template.md`)

Detailed feature proposal format:
- Business value and user impact
- User stories
- Acceptance criteria
- Functional requirements (must/should/could have)
- Non-functional requirements
- Technical considerations
- UI/UX mockups
- Dependencies and open questions
- Success metrics

## Jira Syntax Reference

Complete wiki markup syntax available in `skills/jira/references/jira-syntax-quick-reference.md`

### Quick Reference

```
*bold*                      → Bold text
_italic_                    → Italic text
{{monospace}}               → Code/paths
h2. Heading                 → Section heading
* Bullet item               → Bulleted list
# Numbered item             → Numbered list
[PROJ-123]                  → Issue link
[~username]                 → User mention
{code:java}...{code}        → Code block
||Header||                  → Table header
|Cell|                      → Table cell
{panel:title=X}...{panel}   → Highlighted panel
{color:red}text{color}      → Colored text
```

## MCP Tools Used

This skill leverages the following mcp-atlassian tools:

### Read Operations
- `jira_get_issue` - Retrieve issue details
- `jira_search` - Search with JQL
- `jira_get_project_issues` - List project issues
- `jira_get_transitions` - Available status changes
- `jira_get_worklog` - Time tracking entries
- `jira_get_user_profile` - User information
- `jira_search_fields` - Custom field discovery

### Write Operations
- `jira_create_issue` - Create new issue
- `jira_batch_create_issues` - Bulk creation
- `jira_update_issue` - Update fields
- `jira_add_comment` - Add comments
- `jira_add_worklog` - Log work time
- `jira_transition_issue` - Change status
- `jira_create_issue_link` - Link issues
- `jira_link_to_epic` - Epic linking

### File Operations
- `jira_download_attachments` - Download files

## Best Practices

### Always Use Proper Syntax
- ✅ `h2. Heading` not `## Heading`
- ✅ `*bold*` not `**bold**`
- ✅ `{{code}}` not `` `code` ``
- ✅ `[Label|url]` not `[Label](url)`
- ✅ `{code:java}` not ``` ```java ```

### Structure Content
- Use h2. for main sections
- Use h3. for subsections
- Use numbered lists for steps/criteria
- Use tables for structured data
- Use panels for important notices

### Include Context
- Link to related issues with [PROJ-XXX]
- Mention stakeholders with [~username]
- Reference attachments with [^filename]
- Add code examples in {code} blocks

### Validate Before Submitting
- Check heading format (h1.-h6. with space)
- Verify list nesting (* vs ** vs ***)
- Confirm code blocks have language specified
- Ensure tables have proper header/cell syntax
- Test links are formatted correctly

## Troubleshooting

### Syntax Not Rendering

**Problem**: Jira shows raw markup instead of formatted content

**Solution**:
- Verify you're using Jira wiki markup, not Markdown
- Check for space after heading markers (`h2. ` not `h2.`)
- Ensure code blocks use `{code:lang}` not ``` lang ```
- Confirm tables use `||` for headers, `|` for cells

### Authentication Issues

**Problem**: MCP tools return authentication errors

**Solution**:
- Verify JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN are set
- Test credentials in Jira web interface
- Check API token hasn't expired
- Ensure MCP server is running

### Search Returns No Results

**Problem**: JQL query finds no issues

**Solution**:
- Test JQL in Jira's search interface first
- Check JIRA_PROJECTS_FILTER if set
- Verify user has view permissions
- Use simpler query to narrow down issue

### Field Updates Fail

**Problem**: Cannot update specific issue fields

**Solution**:
- Use `jira_search_fields` to find correct field names
- Check field is editable for current issue type
- Verify user has edit permissions
- Ensure field value matches Jira schema

## Examples

### Create Bug with Full Context

```javascript
mcp__mcp-atlassian__jira_create_issue({
  project_key: "PROJ",
  summary: "Login timeout on large file uploads",
  issue_type: "Bug",
  description: `
h2. Bug Description

Users experience session timeouts when uploading files larger than 50MB through the admin interface.

h3. Environment
* *Browser:* Chrome 120, Firefox 115
* *OS:* Windows 11, macOS 14
* *Version:* 3.2.1
* *Deployment:* Production

h3. Steps to Reproduce
# Login as administrator
# Navigate to {{/admin/uploads}}
# Select file > 50MB
# Click *Upload* button
# Wait 60 seconds
# Observe session timeout error

h3. Expected Behavior
Large file uploads should complete without session timeout, or show progress indicator.

h3. Actual Behavior
After 60 seconds, user receives {{SessionExpiredException}} and must re-authenticate.

{panel:title=Error Stack Trace|bgColor=#FFEBE9}
{code:java}
com.example.SessionExpiredException: Session expired after 60000ms
    at com.example.auth.SessionManager.validateSession(SessionManager.java:145)
    at com.example.upload.FileUploadServlet.doPost(FileUploadServlet.java:78)
{code}
{panel}

h3. Impact
* Affects 30% of admin users
* Blocks large dataset imports
* Workaround: Split files into smaller chunks

h3. Suggested Fix
Extend session timeout during active file uploads or implement resumable upload protocol.

[~backend.lead] [~devops.engineer]
`,
  additional_fields: {
    priority: { name: "High" },
    labels: ["upload", "session", "timeout"],
    components: [{ name: "File Upload" }]
  }
})
```

### Search and Batch Update

```javascript
// 1. Search for issues
const results = mcp__mcp-atlassian__jira_search({
  jql: "project = PROJ AND status = 'In Review' AND updated < -14d",
  fields: "summary,assignee,status"
})

// 2. Batch update stale review tickets
for (const issue of results.issues) {
  mcp__mcp-atlassian__jira_add_comment({
    issue_key: issue.key,
    comment: `
h3. Review Reminder

This ticket has been in review for over 2 weeks.

[~${issue.fields.assignee.name}] Please update the status or provide an ETA.

*Next Action:* Move to {{In Progress}} or {{Done}} by end of week.
`
  })
}
```

## Contributing

This skill is part of the Netresearch Claude Code Marketplace. To contribute:

1. Fork the repository
2. Make improvements to templates or documentation
3. Ensure Jira syntax compliance
4. Submit pull request

## License

MIT License - See LICENSE file for details

## Resources

- [mcp-atlassian GitHub](https://github.com/sooperset/mcp-atlassian)
- [Jira Wiki Markup Syntax](https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all)
- [JQL Reference](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Netresearch Claude Code Marketplace](https://github.com/netresearch/claude-code-marketplace)

## Support

For issues or questions:
- MCP Server: https://github.com/sooperset/mcp-atlassian/issues
- Skill Issues: Create issue in marketplace repository
- Jira Syntax: Refer to official Atlassian documentation