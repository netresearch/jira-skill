# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code skill for Jira integration using the mcp-atlassian MCP server. The skill enforces Jira wiki markup syntax standards and provides templates, validation scripts, and comprehensive reference documentation for working with Jira issues.

**Key Principle**: All Jira content (descriptions, comments) MUST use Jira wiki markup syntax, NOT Markdown. This is the core purpose of this skill.

## Architecture

### Project Structure

```
jira-skill/
├── skills/jira/              # Main skill directory
│   ├── SKILL.md              # Skill metadata and activation patterns
│   ├── templates/            # Jira ticket templates (bug reports, features)
│   ├── references/           # Jira syntax documentation
│   └── scripts/              # Validation utilities
├── .claude-plugin/           # Marketplace plugin metadata
├── .mcp.json                 # MCP server configuration
└── README.md                 # User-facing documentation
```

### Core Components

**SKILL.md**: The skill activation file that defines:
* When the skill should be invoked (file patterns, keywords, tasks)
* Workflow patterns for Jira operations
* MCP tool reference for mcp-atlassian integration
* Jira wiki markup syntax examples

**Templates**: Pre-formatted templates that enforce Jira syntax:
* `bug-report-template.md` - Comprehensive bug documentation structure
* `feature-request-template.md` - Detailed feature proposal format

**References**: Complete Jira wiki markup documentation:
* `jira-syntax-quick-reference.md` - Full syntax reference with examples

**Scripts**: Validation utilities:
* `validate-jira-syntax.sh` - Syntax validation for Jira wiki markup

## Development Workflow

### When Modifying Templates

1. **Validate Syntax**: Ensure all Jira wiki markup follows official standards
2. **Test in Jira**: Complex formatting should be verified in actual Jira instance
3. **Update Checklist**: Templates include validation checklists - keep them current
4. **Preserve Structure**: Templates follow established section patterns (h2. for main, h3. for sub)

### When Updating Documentation

1. **README.md**: User-facing documentation with installation and usage examples
2. **SKILL.md**: Technical reference for Claude Code skill activation
3. **Syntax Reference**: Keep `jira-syntax-quick-reference.md` comprehensive and accurate

### When Adding Features

1. **MCP Tool Usage**: New features should leverage mcp-atlassian tools
2. **Syntax Enforcement**: All new templates/examples must use correct Jira wiki markup
3. **Template Structure**: Follow existing template patterns (sections, formatting, checklists)

## MCP Server Integration

This skill **bundles its own MCP configuration** via `.mcp.json` - users do not need to manually configure the mcp-atlassian server.

### Automatic MCP Configuration

The skill includes `.mcp.json` which automatically configures the mcp-atlassian server using Docker:

```json
{
  "mcp-atlassian": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "--pull=always", "--env-file", "${JIRA_ENV_FILE}",
             "ghcr.io/sooperset/mcp-atlassian:latest"],
    "env": {
      "JIRA_ENV_FILE": "${HOME}/.env.jira"
    }
  }
}
```

**Key Point**: No manual MCP server configuration required - the skill handles this automatically.

### User Setup Requirements

Users only need to create `~/.env.jira` with their credentials:
* `JIRA_URL` - Jira instance URL (e.g., `https://company.atlassian.net`)
* `JIRA_USERNAME` - User email (Cloud) or username (Server/DC)
* `JIRA_API_TOKEN` - API token or Personal Access Token

### Available MCP Tools

All tools use the prefix `mcp__mcp-atlassian__jira_*` :
* **Read**: `get_issue`,  `search`,  `get_project_issues`,  `get_transitions`,  `get_worklog`
* **Write**: `create_issue`,  `batch_create_issues`,  `update_issue`,  `add_comment`,  `add_worklog`,  `transition_issue`
* **Link**: `create_issue_link`,  `link_to_epic`,  `remove_issue_link`
* **Attachments**: `download_attachments`

## Testing and Validation

### Syntax Validation

```bash
# Validate Jira syntax in a file or string
./skills/jira/scripts/validate-jira-syntax.sh <file_or_text>
```

### Manual Testing Workflow

1. Ensure `~/.env.jira` is configured with valid credentials
2. Use the skill - MCP server starts automatically via `.mcp.json`
3. Test MCP tool calls through Claude Code
4. Verify formatting renders correctly in Jira web interface
5. Validate syntax using validation script

## Marketplace Integration

This skill is part of the Netresearch Claude Code Marketplace.

### Plugin Metadata

`.claude-plugin/plugin.json` defines marketplace properties:
* name, version, description
* category, keywords
* author information

File needs to follow plugin schema: <https://code.claude.com/docs/en/plugins-reference#plugin-manifest-schema>

### Version Management

Version follows SemVer format in SKILL.md frontmatter:

```yaml
version: "1.0.0"
```

## Key Constraints

1. **Syntax Enforcement**: Never compromise on Jira wiki markup standards
2. **MCP Dependency**: Skill requires mcp-atlassian to be configured
3. **Template Fidelity**: Templates must match Jira's expected structure
4. **Documentation Accuracy**: Syntax references must align with official Jira docs

## References

* Official Jira Wiki Markup: <https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all>
* mcp-atlassian GitHub: <https://github.com/sooperset/mcp-atlassian>
* JQL Documentation: <https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/>
* Claude Code Plugins: <https://code.claude.com/docs/en/plugins-reference>
