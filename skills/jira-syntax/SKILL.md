---
version: "2.0.0"
---

# Jira Syntax Validation Skill

## When to Use This Skill

Invoke this skill when working with Jira wiki markup syntax, formatting, and templates:

**File/Command Patterns:**
- Files ending in `.jira.txt`, `.wiki`
- Writing Jira descriptions or comments
- Template requests for bug reports, features, etc.

**Keywords/Commands:**
- "jira syntax", "jira format", "wiki markup"
- "validate jira", "check jira syntax"
- "bug report template", "feature template"
- "convert markdown to jira"

**Tasks:**
- Validate Jira wiki markup syntax
- Apply pre-formatted content templates
- Convert Markdown to Jira wiki markup
- Format descriptions and comments correctly
- Check syntax compliance before submission
- Provide syntax examples and references

## Workflow

### 1. Template Application

Use templates for common Jira content types:

```
Bug Report Template:
- Located in: templates/bug-report-template.md
- Sections: Problem, Steps to Reproduce, Expected vs Actual, Technical Details
- Pre-formatted with correct h2./h3. headings

Feature Request Template:
- Located in: templates/feature-request-template.md
- Sections: Feature Overview, User Stories, Acceptance Criteria, Technical Approach
- Includes {panel} and table examples
```

### 2. Syntax Validation

Before submitting content to Jira, validate syntax:

```bash
# Validate syntax in a file
scripts/validate-jira-syntax.sh path/to/content.txt

# Validate syntax in a string
scripts/validate-jira-syntax.sh "h2. My Heading\n\nSome content"
```

### 3. Jira Wiki Markup Syntax Reference

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

## Jira Syntax Validation Checklist

### Always Check:
- [ ] Headings use `h1.` through `h6.` format (not Markdown `#`)
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

## Integration with jira-mcp Skill

This skill works alongside the jira-mcp skill for complete Jira integration:

1. **jira-syntax** provides templates and validates formatting
2. **jira-mcp** submits validated content to Jira via API

**Example Workflow:**
```
User: "Create bug report for login issue"
→ jira-syntax: Provides bug-report-template.md
→ User: Fills template with guidance
→ jira-syntax: Validates syntax with scripts/validate-jira-syntax.sh
→ jira-mcp: Creates issue via mcp__mcp-atlassian__jira_create_issue
→ Result: ✅ Properly formatted issue created in Jira
```

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

### Template Usage:
1. Choose appropriate template for content type
2. Fill all required sections
3. Maintain heading hierarchy (h2 → h3 → h4)
4. Validate syntax before submission
5. Test complex formatting in Jira UI first

### Syntax Validation:
1. Run validation script before submitting
2. Fix reported syntax errors
3. Verify heading format and spacing
4. Check code block languages
5. Validate link formats

## Available Templates

### Bug Report Template
- **Path**: `templates/bug-report-template.md`
- **Sections**: Problem Description, Steps to Reproduce, Expected Behavior, Actual Behavior, Technical Details
- **Use Cases**: Bug reports, defect documentation, regression issues

### Feature Request Template
- **Path**: `templates/feature-request-template.md`
- **Sections**: Feature Overview, User Stories, Acceptance Criteria, Technical Approach
- **Use Cases**: Feature proposals, enhancement requests, new functionality

## References

- **Quick Reference**: `references/jira-syntax-quick-reference.md` - Comprehensive syntax examples
- [Official Jira Wiki Markup](https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all) - Atlassian documentation
- **Validation Script**: `scripts/validate-jira-syntax.sh` - Automated syntax checking

## Troubleshooting

### Syntax Errors:
- Validate Jira wiki markup before submitting
- Test complex formatting in Jira UI first
- Check for proper heading format (h1. not #)
- Verify code block language is supported
- Run validation script to catch common errors

### Template Issues:
- Ensure all required sections are filled
- Maintain heading hierarchy
- Don't mix Markdown and Jira syntax
- Preserve template structure and formatting

### Validation Script Problems:
- Ensure script has execute permissions: `chmod +x scripts/validate-jira-syntax.sh`
- Check file path is correct
- Verify content is properly escaped for shell
