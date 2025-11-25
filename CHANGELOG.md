# Changelog

All notable changes to the Jira Integration Skill will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2025-11-25

### BREAKING CHANGES

- **Removed MCP server dependency**: The `mcp-atlassian` Docker-based MCP server is no longer used
- **New invocation pattern**: All operations now use `uv run scripts/...` instead of MCP tool calls
- **Skill renamed**: `jira-mcp` → `jira-communication`

### Added

- **Script-based architecture**: Lightweight Python scripts with PEP 723 inline dependencies
- **Shared library** (`lib/`): Common utilities for client initialization, config, and output formatting
- **Core scripts** (`scripts/core/`):
  - `jira-validate.py` - Environment validation with actionable error messages
  - `jira-worklog.py` - Time tracking (add, list)
  - `jira-issue.py` - Issue operations (get, update)
  - `jira-search.py` - JQL search queries
- **Workflow scripts** (`scripts/workflow/`):
  - `jira-create.py` - Issue creation with all common fields
  - `jira-transition.py` - Status transitions with comments
  - `jira-comment.py` - Comment operations
  - `jira-sprint.py` - Sprint operations (list, issues, current)
  - `jira-board.py` - Board operations (list, issues)
- **Utility scripts** (`scripts/utility/`):
  - `jira-fields.py` - Field search and listing
  - `jira-user.py` - User information
  - `jira-link.py` - Issue linking
- **New features**:
  - `--dry-run` flag for all write operations
  - `--json`, `--quiet` output format options
  - Actionable error messages with suggestions
  - Auto-detection of Jira Cloud vs Server/DC

### Changed

- **Dependencies**: Now uses `uv`/`uvx` instead of Docker
- **Context usage**: Reduced from ~8,000-12,000 tokens to ~500 tokens
- **Startup time**: Reduced from 3-5s (Docker) to <1s

### Removed

- `mcp-atlassian` MCP server configuration
- Docker dependency
- Confluence operations (separate skill if needed)
- Old `jira-mcp` skill (use git history for reference)

### Migration

See `skills/jira-communication/references/migration-guide.md` for detailed migration instructions from v2.x.

## [2.0.1] - 2025-11-25

### Fixed
- **SKILL.md Frontmatter**: Removed invalid fields (`version`, `mcp_servers`) that are not recognized by Claude Code skill loading
- **Skill Triggering**: Moved "when to use" information from SKILL.md body to `description` field for proper skill activation
- **plugin.json Structure**: Added missing `skills` array declaration with proper paths to both skills

### Improved
- **Token Efficiency**: Reduced jira-mcp/SKILL.md from ~415 to ~129 lines (69% reduction)
- **Token Efficiency**: Reduced jira-syntax/SKILL.md from ~243 to ~83 lines (66% reduction)
- **Progressive Disclosure**: SKILL.md files now serve as lean entry points, directing to comprehensive reference files
- **Navigation**: Added Table of Contents to `jql-reference.md` and `jira-syntax-quick-reference.md` for easier navigation

### Changed
- **Description Field**: Now includes comprehensive trigger patterns (10 triggers for jira-mcp, 8 for jira-syntax)
- **SKILL.md Structure**: Follows skill-creator best practices with concise body pointing to references
- **Reference Files**: Long reference files (>100 lines) now have TOCs for better discoverability

### Documentation
- Updated CLAUDE.md to reflect leaner skill architecture
- Skills validated against skill-creator framework best practices

## [2.0.0] - 2024-11-07

### ⚠️ BREAKING CHANGES

**Major architectural redesign**: The unified `jira` skill has been split into two specialized skills within a single plugin:

- **jira-mcp**: MCP server communication and Jira API operations
- **jira-syntax**: Jira wiki markup syntax validation and templates

**Migration Required**: See MIGRATION.md for upgrade instructions.

### Changed
- **Plugin name**: `jira` → `jira-integration`
- **Skill structure**: Single unified skill → Two specialized skills
- **File organization**: Templates, references, and scripts reorganized by skill
- **Activation patterns**: Skills now activate independently based on context

### Added
- **jira-mcp skill**: Dedicated MCP communication and API operations
  - `references/jql-reference.md`: Comprehensive JQL syntax guide with examples
  - `references/mcp-tools-guide.md`: Complete MCP tool documentation
  - `references/workflow-patterns.md`: Common multi-step operation sequences
- **jira-syntax skill**: Dedicated syntax validation and templates
  - Same templates moved from unified skill
  - Same syntax reference and validation scripts
- **MIGRATION.md**: Complete migration guide from v1.x to v2.0.0
- **Plugin-level configuration**: Both skills declared in single `plugin.json`

### Improved
- **Separation of concerns**: API operations vs syntax enforcement
- **Offline capability**: jira-syntax works without MCP server for validation
- **Clearer activation**: Skills activate based on specific context
- **Better documentation**: Dedicated references for each domain
- **Easier maintenance**: Update skills independently

### Removed
- Old unified `skills/jira/` directory (archived in `archive/jira-unified/`)

## [1.0.3] - 2024-11-07

### Fixed
- Added Docker as explicit prerequisite in README.md to prevent installation errors
- Removed references to non-existent templates (Task Template, Comment Templates) from documentation
- Updated template section to accurately reflect available resources

### Added
- CHANGELOG.md following Keep a Changelog format for better version tracking

## [1.0.2] - 2024-11-07

### Fixed
- Moved MCP server configuration inline to avoid collisions when working on this project
- Fixed environment file path for Docker-based MCP server execution
- Corrected `JIRA_ENV_FILE` reference to use `${HOME}/.env.jira` instead of relative path

### Changed
- Updated plugin metadata for better marketplace integration
- Cleaned up CLAUDE.md documentation for clearer skill guidance

## [1.0.1] - 2024-11-06

### Changed
- Updated plugin metadata and documentation
- Improved CLAUDE.md with clearer project architecture guidance

## [1.0.0] - 2024-11-06

### Added
- Initial release of Jira Integration Skill
- Automatic MCP server configuration via bundled `.mcp.json`
- Docker-based mcp-atlassian server integration
- Comprehensive Jira wiki markup syntax enforcement
- Bug report template with proper Jira formatting
- Feature request template with acceptance criteria structure
- Complete Jira syntax quick reference documentation
- Syntax validation script for Jira wiki markup
- Support for all mcp-atlassian MCP tools:
  - Issue CRUD operations (create, read, update, search)
  - JQL query support for advanced searching
  - Project and sprint management
  - Worklog tracking and time logging
  - Comment management with proper formatting
  - Issue linking (blocks, relates to, duplicates, epic)
  - Attachment upload and download
  - Issue transitions and workflow management
  - Batch operations for bulk updates
- Comprehensive README with installation and usage examples
- Integration with Netresearch Claude Code Marketplace
- MIT License

### Documentation
- Complete README.md with installation, usage, and troubleshooting
- SKILL.md activation patterns and workflow guidance
- CLAUDE.md project architecture and development guidelines
- Jira syntax quick reference with examples
- Template documentation for bug reports and feature requests

## Release Notes

### Version 1.0.2
This release focuses on improving the reliability of MCP server configuration by moving it inline with the skill. This prevents configuration conflicts and ensures the correct environment file path is used for Docker-based execution.

### Version 1.0.0
First stable release providing comprehensive Jira integration through Claude Code. The skill enforces proper Jira wiki markup syntax across all operations, includes ready-to-use templates, and provides seamless Docker-based MCP server integration with zero manual configuration required.

## Links

- [Repository](https://github.com/netresearch/jira-skill)
- [mcp-atlassian](https://github.com/sooperset/mcp-atlassian)
- [Claude Code Marketplace](https://github.com/netresearch/claude-code-marketplace)
- [Jira Wiki Markup Reference](https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all)

[Unreleased]: https://github.com/netresearch/jira-skill/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/netresearch/jira-skill/compare/2.0.1...v3.0.0
[2.0.1]: https://github.com/netresearch/jira-skill/compare/2.0.0...2.0.1
[2.0.0]: https://github.com/netresearch/jira-skill/compare/1.0.3...2.0.0
[1.0.3]: https://github.com/netresearch/jira-skill/compare/1.0.2...1.0.3
[1.0.2]: https://github.com/netresearch/jira-skill/compare/1.0.1...1.0.2
[1.0.1]: https://github.com/netresearch/jira-skill/compare/1.0.0...1.0.1
[1.0.0]: https://github.com/netresearch/jira-skill/releases/tag/1.0.0
