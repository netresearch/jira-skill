# Jira MCP Workflow Patterns

Common multi-step operation sequences for Jira automation.

## Pattern 1: Create Validated Bug Report

**Steps:**
1. Get bug report template from jira-syntax
2. Fill template with issue details
3. Validate syntax with jira-syntax
4. Create issue via jira-mcp
5. Verify creation and return issue key

**Example:**
```
# Step 1: Use jira-syntax template
templates/bug-report-template.md

# Step 2: Fill with details (Jira wiki markup)
Description:
h2. Problem Description
Login functionality times out after 30 seconds when authenticating users.

h3. Steps to Reproduce
# Navigate to login page
# Enter valid credentials
# Click "Sign In"
# Wait 30+ seconds
# Observe timeout error

h3. Expected Behavior
- Login completes within 2 seconds
- User redirected to dashboard
- Session established correctly

h3. Actual Behavior
- Timeout occurs after 30 seconds
- Error message: "Connection timeout"
- User remains on login page

h3. Technical Details
{code:javascript}
// Auth service call
authService.login(username, password)
  .timeout(30000)
  .catch(err => console.error(err));
{code}

h3. Environment
- Browser: Chrome 120
- OS: Windows 11
- Version: 2.1.0

# Step 3: Validate syntax
scripts/validate-jira-syntax.sh <content>
✅ All checks passed

# Step 4: Create issue
mcp__mcp-atlassian__jira_create_issue
  project_key: "PROJ"
  summary: "Login timeout after 30 seconds"
  issue_type: "Bug"
  description: <validated_content>
  priority: "High"
  labels: ["backend", "authentication"]

# Step 5: Result
✅ Created: PROJ-789
```

---

## Pattern 2: Sprint Planning Workflow

**Steps:**
1. Search for unplanned issues
2. Filter by priority and estimate
3. Batch update sprint assignment
4. Add planning comments
5. Generate sprint summary

**Example:**
```
# Step 1: Find unplanned issues
mcp__mcp-atlassian__jira_search
  jql: "project = PROJ AND sprint IS EMPTY AND status != Closed ORDER BY priority DESC"
  max_results: 100

# Step 2: Review and select issues
# (Manual review or automated selection based on story points)

# Step 3: Update sprint field
For each selected issue:
  mcp__mcp-atlassian__jira_update_issue
    issue_key: <issue_key>
    fields: {
      "customfield_10020": "Sprint 42"  # Sprint field
    }

# Step 4: Add planning comment
mcp__mcp-atlassian__jira_add_comment
  issue_key: <issue_key>
  comment: "
h3. Sprint Planning

Added to Sprint 42 based on:
* Priority: High
* Story Points: 5
* Team Capacity: Available

h4. Dependencies
* Requires [PROJ-100] completion
* No blockers identified
"

# Step 5: Generate summary
mcp__mcp-atlassian__jira_search
  jql: "sprint = 'Sprint 42' AND project = PROJ"

Calculate:
- Total story points
- Issue breakdown by type
- Team assignments
```

---

## Pattern 3: Status Report Generation

**Steps:**
1. Query issues by status
2. Group and count results
3. Identify blockers
4. Generate formatted report
5. Post as comment or create issue

**Example:**
```
# Step 1: Get all active sprint issues
mcp__mcp-atlassian__jira_search
  jql: "sprint in openSprints() AND project = PROJ"
  fields: ["status", "summary", "assignee", "priority"]

# Step 2: Group by status
Count issues:
- To Do: 15
- In Progress: 8
- In Review: 5
- Done: 22

# Step 3: Find blockers
mcp__mcp-atlassian__jira_search
  jql: "project = PROJ AND status = Blocked AND sprint in openSprints()"

# Step 4: Generate report
Report Content:
h2. Sprint Status Report - <date>

h3. Progress Summary
||Status||Count||Percentage||
|Done|22|44%|
|In Review|5|10%|
|In Progress|8|16%|
|To Do|15|30%|

h3. Key Metrics
* Total Issues: 50
* Completed: 22 (44%)
* Remaining: 28 (56%)
* Story Points Completed: 45/100

h3. Blockers ({color:red}3 items{color})
* [PROJ-123] - Database migration pending
* [PROJ-456] - Waiting for API access
* [PROJ-789] - Design approval needed

h3. At Risk
Issues not updated in 3+ days:
* [PROJ-234] - Assigned to [~john.doe]
* [PROJ-567] - Unassigned

# Step 5: Create status report issue
mcp__mcp-atlassian__jira_create_issue
  project_key: "PROJ"
  summary: "Sprint 42 - Status Report - Week 3"
  issue_type: "Task"
  description: <report_content>
  labels: ["status-report", "sprint-42"]
```

---

## Pattern 4: Bulk Issue Creation with Links

**Steps:**
1. Define issue hierarchy (epic → stories → tasks)
2. Create epic
3. Batch create stories
4. Link stories to epic
5. Create subtasks and link

**Example:**
```
# Step 1: Create epic
mcp__mcp-atlassian__jira_create_issue
  project_key: "PROJ"
  summary: "User Authentication System"
  issue_type: "Epic"
  description: "
h2. Epic Overview
Implement complete user authentication system with OAuth and 2FA.

h3. Goals
* Secure user login
* Social provider integration
* Two-factor authentication
* Session management
"
# Returns: PROJ-1000 (epic)

# Step 2: Create stories
mcp__mcp-atlassian__jira_batch_create_issues
  issues: [
    {
      "project_key": "PROJ",
      "summary": "Implement OAuth login",
      "issue_type": "Story",
      "description": "h2. Story\nAs a user, I want to log in with Google/GitHub..."
    },
    {
      "project_key": "PROJ",
      "summary": "Add 2FA support",
      "issue_type": "Story",
      "description": "h2. Story\nAs a user, I want to enable 2FA..."
    },
    {
      "project_key": "PROJ",
      "summary": "Session management",
      "issue_type": "Story",
      "description": "h2. Story\nAs a user, I want secure session handling..."
    }
  ]
# Returns: PROJ-1001, PROJ-1002, PROJ-1003

# Step 3: Link stories to epic
For each story (PROJ-1001, PROJ-1002, PROJ-1003):
  mcp__mcp-atlassian__jira_link_to_epic
    issue_key: <story_key>
    epic_key: "PROJ-1000"

# Step 4: Create tasks for first story
mcp__mcp-atlassian__jira_batch_create_issues
  issues: [
    {
      "project_key": "PROJ",
      "summary": "Database schema for OAuth",
      "issue_type": "Task",
      "description": "h2. Technical Task\nCreate tables for OAuth providers..."
    },
    {
      "project_key": "PROJ",
      "summary": "OAuth API endpoints",
      "issue_type": "Task",
      "description": "h2. Technical Task\nImplement REST endpoints..."
    }
  ]
# Returns: PROJ-1004, PROJ-1005

# Step 5: Link tasks to story
mcp__mcp-atlassian__jira_create_issue_link
  link_type: "Relates"
  inward_issue_key: "PROJ-1004"
  outward_issue_key: "PROJ-1001"

mcp__mcp-atlassian__jira_create_issue_link
  link_type: "Relates"
  inward_issue_key: "PROJ-1005"
  outward_issue_key: "PROJ-1001"
```

---

## Pattern 5: Automated Workflow Transition

**Steps:**
1. Find issues ready for transition
2. Get available transitions
3. Validate transition criteria
4. Transition with comment
5. Update related fields

**Example:**
```
# Step 1: Find issues in "In Review" for 3+ days
mcp__mcp-atlassian__jira_search
  jql: "status = 'In Review' AND updated <= -3d AND project = PROJ"

# Step 2: For each issue, get transitions
mcp__mcp-atlassian__jira_get_transitions
  issue_key: "PROJ-123"
# Returns: [{"id": "31", "name": "Done"}, {"id": "41", "name": "Reject"}]

# Step 3: Validate criteria
Check:
- All required reviews completed
- No open comments
- Tests passed (check via CI integration or worklog)

# Step 4: Transition to Done
mcp__mcp-atlassian__jira_transition_issue
  issue_key: "PROJ-123"
  transition_id: "31"
  comment: "
h3. Automated Transition

This issue has been automatically moved to Done based on:

* {color:green}✓{color} In Review for 3+ days
* {color:green}✓{color} All reviews approved
* {color:green}✓{color} No blocking comments
* {color:green}✓{color} CI checks passed

h4. Review Summary
* Code review by [~jane.smith] - Approved
* QA testing complete - No issues found
* Performance tests passed

_Automated by workflow bot_
"
  fields: {
    "resolution": {"name": "Done"}
  }

# Step 5: Add worklog if needed
mcp__mcp-atlassian__jira_add_worklog
  issue_key: "PROJ-123"
  time_spent: "30m"
  comment: "Final review and deployment"
```

---

## Pattern 6: Cross-Project Issue Sync

**Steps:**
1. Search for issues in source project
2. Check if corresponding issue exists in target
3. Create or update target issue
4. Link issues across projects
5. Keep issues in sync

**Example:**
```
# Step 1: Get bug from customer project
mcp__mcp-atlassian__jira_get_issue
  issue_key: "CUST-456"

# Step 2: Search for existing engineering issue
mcp__mcp-atlassian__jira_search
  jql: "project = ENG AND summary ~ 'CUST-456'"

# Step 3: Create engineering issue if not exists
If not found:
  mcp__mcp-atlassian__jira_create_issue
    project_key: "ENG"
    summary: "[CUST-456] Login timeout issue"
    issue_type: "Bug"
    description: "
h2. Customer Report
Original Issue: [CUST-456]

h3. Customer Impact
<copy from CUST-456 description>

h3. Technical Investigation
<engineering details>
"
# Returns: ENG-789

# Step 4: Link issues
mcp__mcp-atlassian__jira_create_issue_link
  link_type: "Relates"
  inward_issue_key: "ENG-789"
  outward_issue_key: "CUST-456"
  comment: "Engineering issue created for investigation"

# Step 5: Sync status updates
When ENG-789 transitions:
  mcp__mcp-atlassian__jira_add_comment
    issue_key: "CUST-456"
    comment: "
h3. Engineering Update

Status: {color:blue}In Progress{color}

Our engineering team has started investigation in [ENG-789].
We'll keep you updated on progress.
"
```

---

## Best Practices

### Error Handling
```
For each MCP operation:
  Try:
    Execute operation
    Validate response
    Log success
  Catch:
    Log error details
    Check auth/permissions
    Retry if transient
    Notify on persistent failure
```

### Performance
- Batch operations when possible
- Use pagination for large result sets
- Cache project/field metadata
- Request only needed fields

### Content Quality
- Always validate syntax before submission
- Use templates for consistency
- Include proper formatting (h2/h3 headings)
- Add relevant links and mentions

### Workflow Automation
- Validate criteria before transitions
- Add informative comments
- Update all related fields
- Maintain audit trail

## References

- JQL Reference: `jql-reference.md`
- MCP Tools Guide: `mcp-tools-guide.md`
- Jira Syntax Validation: See jira-syntax skill
