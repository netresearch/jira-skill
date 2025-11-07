# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code plugin providing comprehensive Jira integration through **two specialized skills**:

1. **jira-mcp**: MCP server communication for all Jira API operations
2. **jira-syntax**: Jira wiki markup syntax validation, templates, and formatting

**Key Principle**: All Jira content (descriptions, comments) MUST use Jira wiki markup syntax, NOT Markdown. This is enforced by the jira-syntax skill and consumed by the jira-mcp skill.

## Architecture

### Project Structure (v2.0.0+)

```
jira-skill/
├── skills/
│   ├── jira-mcp/               # MCP communication skill
│   │   ├── SKILL.md            # MCP operations and API workflows
│   │   └── references/
│   │       ├── jql-reference.md        # JQL syntax and examples
│   │       ├── mcp-tools-guide.md      # Complete MCP tool documentation
│   │       └── workflow-patterns.md    # Common operation sequences
│   └── jira-syntax/            # Syntax validation skill
│       ├── SKILL.md            # Syntax validation workflows
│       ├── templates/
│       │   ├── bug-report-template.md
│       │   └── feature-request-template.md
│       ├── references/
│       │   └── jira-syntax-quick-reference.md
│       └── scripts/
│           └── validate-jira-syntax.sh
├── .claude-plugin/
│   └── plugin.json             # Plugin metadata declaring both skills
├── archive/
│   └── jira-unified/           # Old v1.x unified skill (archived)
└── README.md                   # User-facing documentation
```

### Skill Separation Rationale

**Why Two Skills?**

1. **Separation of Concerns**: API operations (jira-mcp) vs syntax enforcement (jira-syntax)
2. **Independent Activation**: Skills activate based on context (MCP operations vs formatting)
3. **Offline Capability**: jira-syntax works offline for validation without MCP server
4. **Modularity**: Clear boundaries between API communication and content formatting

### Core Components

**jira-mcp Skill** (`skills/jira-mcp/SKILL.md`):
* MCP server configuration and tool workflows
* JQL query patterns and examples
* Issue CRUD operations
* Workflow automation patterns
* References: JQL syntax, MCP tools guide, workflow patterns

**jira-syntax Skill** (`skills/jira-syntax/SKILL.md`):
* Jira wiki markup syntax rules
* Template provision and application
* Syntax validation workflows
* Templates: Bug reports, feature requests
* References: Complete Jira syntax documentation
* Scripts: Automated syntax checking

**Plugin Configuration** (`.claude-plugin/plugin.json`):
* Declares both skills with paths
* MCP server configuration for mcp-atlassian
* Plugin metadata and versioning

## Development Workflow

### When Modifying jira-syntax Skill

1. **Validate Syntax**: Ensure all Jira wiki markup in templates follows official standards
2. **Test in Jira**: Complex formatting should be verified in actual Jira instance
3. **Update Checklist**: Templates include validation checklists - keep them current
4. **Preserve Structure**: Templates follow established section patterns (h2. for main, h3. for sub)
5. **Update References**: Keep `jira-syntax-quick-reference.md` comprehensive and accurate

### When Modifying jira-mcp Skill

1. **MCP Tool Usage**: New features should leverage mcp-atlassian tools correctly
2. **Update References**: Maintain `jql-reference.md`, `mcp-tools-guide.md`, `workflow-patterns.md`
3. **Test MCP Operations**: Verify tool calls work against real Jira instance
4. **Document Workflows**: Add new patterns to workflow-patterns.md

### When Updating Documentation

1. **README.md**: User-facing documentation with installation and usage examples
2. **SKILL.md files**: Technical reference for skill activation (update both as needed)
3. **MIGRATION.md**: Document breaking changes and upgrade paths
4. **plugin.json**: Update version numbers following SemVer

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
