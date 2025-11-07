# JQL (Jira Query Language) Reference

## Overview

JQL is a powerful query language for searching issues in Jira. It uses a SQL-like syntax to filter and retrieve issues based on various criteria.

## Basic Syntax

```
field operator value
```

**Example:**
```
project = "PROJ"
assignee = currentUser()
status IN ("To Do", "In Progress")
```

## Common Fields

### Issue Fields
| Field | Description | Example |
|-------|-------------|---------|
| `project` | Project key or name | `project = PROJ` |
| `issuetype` | Issue type | `issuetype = Bug` |
| `status` | Current status | `status = "In Progress"` |
| `priority` | Issue priority | `priority = High` |
| `assignee` | Assigned user | `assignee = john.doe` |
| `reporter` | User who created issue | `reporter = currentUser()` |
| `summary` | Issue summary text | `summary ~ "login error"` |
| `description` | Issue description | `description ~ "timeout"` |
| `labels` | Issue labels | `labels = backend` |
| `component` | Component name | `component = "API Server"` |
| `fixVersion` | Fix version | `fixVersion = "1.2.0"` |
| `affectedVersion` | Affected version | `affectedVersion = "1.1.0"` |

### Date/Time Fields
| Field | Description | Example |
|-------|-------------|---------|
| `created` | Creation date | `created >= -7d` |
| `updated` | Last update date | `updated >= "2024-01-01"` |
| `resolved` | Resolution date | `resolved >= startOfWeek()` |
| `due` | Due date | `due < now()` |

### Agile Fields
| Field | Description | Example |
|-------|-------------|---------|
| `sprint` | Sprint name/ID | `sprint in openSprints()` |
| `epic link` | Linked epic | `"epic link" = PROJ-100` |
| `story points` | Story points | `"story points" > 5` |

## Operators

### Comparison Operators
| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Equals | `status = "To Do"` |
| `!=` | Not equals | `priority != Low` |
| `>` | Greater than | `created > -30d` |
| `>=` | Greater or equal | `priority >= Medium` |
| `<` | Less than | `due < now()` |
| `<=` | Less or equal | `"story points" <= 8` |

### Text Operators
| Operator | Description | Example |
|----------|-------------|---------|
| `~` | Contains text | `summary ~ "login"` |
| `!~` | Does not contain | `description !~ "deprecated"` |

### List Operators
| Operator | Description | Example |
|----------|-------------|---------|
| `IN` | Matches any value in list | `status IN ("To Do", "In Progress")` |
| `NOT IN` | Doesn't match any value | `priority NOT IN (Low, Lowest)` |

### Null Operators
| Operator | Description | Example |
|----------|-------------|---------|
| `IS EMPTY` | Field has no value | `assignee IS EMPTY` |
| `IS NOT EMPTY` | Field has a value | `fixVersion IS NOT EMPTY` |
| `IS NULL` | Field is null | `resolution IS NULL` |
| `IS NOT NULL` | Field is not null | `duedate IS NOT NULL` |

## Functions

### User Functions
| Function | Description | Example |
|----------|-------------|---------|
| `currentUser()` | Currently logged-in user | `assignee = currentUser()` |
| `membersOf()` | Members of a group | `assignee IN membersOf("developers")` |

### Date Functions
| Function | Description | Example |
|----------|-------------|---------|
| `now()` | Current date/time | `created > now()` |
| `startOfDay()` | Start of current day | `created >= startOfDay()` |
| `endOfDay()` | End of current day | `due <= endOfDay()` |
| `startOfWeek()` | Start of current week | `updated >= startOfWeek()` |
| `endOfWeek()` | End of current week | `due <= endOfWeek()` |
| `startOfMonth()` | Start of current month | `created >= startOfMonth()` |
| `endOfMonth()` | End of current month | `due <= endOfMonth()` |

### Sprint Functions
| Function | Description | Example |
|----------|-------------|---------|
| `openSprints()` | Currently active sprints | `sprint IN openSprints()` |
| `closedSprints()` | Completed sprints | `sprint IN closedSprints()` |
| `futureSprints()` | Upcoming sprints | `sprint IN futureSprints()` |

## Logical Operators

### AND
Combine multiple conditions (all must be true):
```
project = PROJ AND status = "In Progress" AND assignee = currentUser()
```

### OR
Match any condition:
```
priority = High OR priority = Highest
```

### NOT
Negate a condition:
```
NOT status = Closed
```

## Common Query Patterns

### My Open Issues
```
assignee = currentUser() AND resolution = Unresolved
```

### Bugs Created This Week
```
issuetype = Bug AND created >= startOfWeek()
```

### Overdue Tasks
```
due < now() AND status != Done
```

### Current Sprint Issues
```
sprint IN openSprints() AND project = PROJ
```

### Recently Updated Issues
```
updated >= -7d ORDER BY updated DESC
```

### High Priority Unassigned
```
priority IN (High, Highest) AND assignee IS EMPTY
```

### Issues Without Fix Version
```
fixVersion IS EMPTY AND status IN ("In Progress", "To Do")
```

### Epic's Child Issues
```
"epic link" = PROJ-100
```

### Issues With Specific Label
```
labels = "backend" AND status != Closed
```

### Issues Created by Team Members
```
reporter IN membersOf("engineering-team") AND created >= -30d
```

## Sorting

Add `ORDER BY` to sort results:

```
# Sort by priority descending
project = PROJ ORDER BY priority DESC

# Sort by multiple fields
project = PROJ ORDER BY priority DESC, created ASC

# Common sort fields
ORDER BY created DESC          # Newest first
ORDER BY updated DESC          # Recently updated
ORDER BY priority DESC         # Highest priority
ORDER BY "story points" DESC   # Largest first
ORDER BY key ASC               # By issue key
```

## Advanced Patterns

### Complex Conditions with Parentheses
```
project = PROJ AND (
    (priority = High AND assignee = currentUser()) OR
    (status = Blocked AND assignee IS EMPTY)
)
```

### Text Search Across Fields
```
text ~ "authentication" AND project = PROJ
```

### Date Range Query
```
created >= "2024-01-01" AND created <= "2024-01-31"
```

### Unresolved Issues Updated Recently
```
resolution = Unresolved AND updated >= -14d ORDER BY updated DESC
```

### Sprint Burndown Query
```
sprint = "Sprint 42" AND status != Done
```

### Issues Linked to Specific Epic
```
"epic link" = PROJ-100 ORDER BY priority DESC, key ASC
```

## Performance Tips

1. **Be Specific**: Use project filters to narrow results
   ```
   project = PROJ AND ...  # Better than just searching all projects
   ```

2. **Use Indexed Fields**: Fields like `project`, `status`, `assignee` are indexed
   ```
   project = PROJ AND status = "In Progress"  # Fast
   ```

3. **Avoid Wildcards**: Don't overuse text search
   ```
   summary ~ "login"        # Better
   summary ~ "*login*"      # Slower
   ```

4. **Limit Results**: Use `maxResults` parameter in API calls
   ```
   mcp__mcp-atlassian__jira_search
     jql: "project = PROJ"
     max_results: 50  # Don't fetch thousands of results
   ```

5. **Use Functions Wisely**: Date functions are efficient
   ```
   updated >= startOfWeek()  # Efficient
   ```

## Common Errors

### Syntax Errors
- **Missing quotes**: `status = In Progress` → `status = "In Progress"`
- **Case sensitivity**: Field names are case-insensitive, but values are case-sensitive
- **Invalid operators**: `status EQUALS "Done"` → `status = "Done"`

### Field Errors
- **Custom fields**: Use quotes for custom fields: `"Story Points" > 5`
- **Non-existent fields**: Verify field name exists in your Jira instance

### Value Errors
- **Invalid status**: Verify status exists in project workflow
- **Invalid user**: Use actual username or email
- **Date format**: Use `YYYY-MM-DD` or relative dates like `-7d`

## Testing JQL Queries

1. **Test in Jira UI first**: Use Jira's search interface to validate syntax
2. **Start simple**: Build complex queries incrementally
3. **Check field names**: Use `jira_search_fields` to find custom field names
4. **Verify permissions**: Ensure you have access to view results

## References

- [Official JQL Documentation](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
- [JQL Functions Reference](https://support.atlassian.com/jira-cloud/docs/jql-functions/)
- [JQL Keywords Reference](https://support.atlassian.com/jira-cloud/docs/jql-keywords/)
