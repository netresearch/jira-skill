# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Claude Code plugin providing comprehensive Jira integration through **two specialized skills**:

1. **jira-communication**: Script-based Jira API operations via Python scripts (v3.0.0+)
2. **jira-syntax**: Jira wiki markup syntax validation, templates, and formatting

**Key Principle**: All Jira content (descriptions, comments) MUST use Jira wiki markup syntax, NOT Markdown. This is enforced by the jira-syntax skill.

## Architecture

### Project Structure (v3.0.0+)

```
jira-skill/
├── skills/
│   ├── jira-communication/       # Script-based API operations
│   │   ├── SKILL.md              # Skill entry point
│   │   ├── scripts/
│   │   │   ├── lib/              # Shared utilities (client, config, output)
│   │   │   ├── core/             # Core operations (validate, issue, search, worklog)
│   │   │   ├── workflow/         # Workflow operations (create, transition, comment, sprint, board)
│   │   │   └── utility/          # Utility operations (fields, user, link)
│   │   └── references/
│   │       └── migration-guide.md
│   └── jira-syntax/              # Syntax validation skill
│       ├── SKILL.md
│       ├── templates/
│       ├── references/
│       └── scripts/
├── .claude-plugin/
│   └── plugin.json               # Plugin metadata (v3.0.0)
├── README.md
├── CHANGELOG.md
└── MIGRATION.md
```

### Script-Based Architecture (v3.0.0)

The v3.0.0 release replaces the MCP-based approach with lightweight Python scripts:

**Benefits**:
- Zero MCP context overhead (~500 tokens vs ~8,000-12,000)
- Fast startup (<1s vs 3-5s Docker spin-up)
- No Docker dependency (uses `uv` for Python execution)
- Full Jira Server/DC + Cloud support

**Script Categories**:
- **Core** (`scripts/core/`): validate, issue, search, worklog
- **Workflow** (`scripts/workflow/`): create, transition, comment, sprint, board
- **Utility** (`scripts/utility/`): fields, user, link

### Shared Library (`scripts/lib/`)

All scripts share common utilities:
- `client.py` - Jira client initialization with auth auto-detection
- `config.py` - Environment configuration loading
- `output.py` - Consistent output formatting (table, JSON, quiet)

## Development Workflow

### When Modifying Scripts

1. **Follow existing patterns**: All scripts use argparse with subcommands
2. **Use shared lib**: Import from `lib/` for client, config, output
3. **Support all output formats**: `--json`, `--quiet`, default table
4. **Add --dry-run for write ops**: Preview changes without executing
5. **Test against real Jira**: Verify both Cloud and Server/DC

### When Adding New Scripts

1. Place in appropriate directory (core/workflow/utility)
2. Use PEP 723 inline dependencies
3. Add PYTHONPATH manipulation for lib imports
4. Follow existing script structure and naming
5. Update SKILL.md and README.md

### When Modifying jira-syntax Skill

1. **Validate Syntax**: Ensure all Jira wiki markup follows official standards
2. **Test in Jira**: Complex formatting should be verified in actual Jira instance
3. **Update References**: Keep `jira-syntax-quick-reference.md` accurate

## User Setup Requirements

Users need to create `~/.env.jira` with credentials:

**For Jira Cloud**:
```
JIRA_URL=https://company.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-api-token
```

**For Jira Server/DC**:
```
JIRA_URL=https://jira.yourcompany.com
JIRA_PERSONAL_TOKEN=your-personal-access-token
```

## Testing

### Validate Environment
```bash
cd skills/jira-communication
uv run scripts/core/jira-validate.py --verbose
```

### Test Individual Scripts
```bash
uv run scripts/core/jira-search.py query "project = PROJ" --max-results 5
uv run scripts/core/jira-issue.py get PROJ-123
uv run scripts/utility/jira-user.py me
```

### Test with Dry-Run
```bash
uv run scripts/workflow/jira-create.py issue PROJ "Test" --type Task --dry-run
uv run scripts/workflow/jira-transition.py do PROJ-123 "Done" --dry-run
```

## Plugin Configuration

`.claude-plugin/plugin.json` defines:
- Plugin metadata (name, version, description)
- Skills array with paths to both skills
- No MCP server configuration (v3.0.0+)

Version is managed ONLY in `plugin.json`, NOT in SKILL.md frontmatter.

## Key Constraints

1. **Syntax Enforcement**: Never compromise on Jira wiki markup standards
2. **Script Execution**: Run scripts from `skills/jira-communication/` directory
3. **PYTHONPATH**: Scripts manipulate path for lib imports (don't change this pattern)
4. **Auth Auto-Detection**: Scripts detect Cloud vs Server/DC based on env vars

## References

* Official Jira Wiki Markup: <https://jira.atlassian.com/secure/WikiRendererHelpAction.jspa?section=all>
* JQL Documentation: <https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/>
* Claude Code Plugins: <https://code.claude.com/docs/en/plugins-reference>
* uv Documentation: <https://docs.astral.sh/uv/>
