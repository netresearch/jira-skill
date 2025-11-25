# Migration Guide

## v3.0.0 → v3.0.1

### Breaking Change: jira-search.py CLI Options

The `--output` choice option in `jira-search.py` has been replaced with standard `--json` and `--quiet` flags for consistency with other scripts.

#### Migration

| Old Command | New Command |
|-------------|-------------|
| `jira-search query "..." --output table` | `jira-search query "..."` |
| `jira-search query "..." --output json` | `jira-search --json query "..."` |
| `jira-search query "..." --output keys` | `jira-search --quiet query "..."` |

**Note**: The `--json` and `--quiet` flags are now group-level options (before the subcommand), not command-level options.

### New CLI Options

The following scripts now support `--json` and `--quiet` options:

- `jira-validate.py` - `--json` outputs full validation result, `--quiet` outputs just "ok" or "error"
- `jira-fields.py` - `--quiet` outputs field IDs only (one per line)
- `jira-link.py` - `--quiet` outputs link type names only (one per line)

---

# Migration Guide: v1.x → v2.0.0

## Overview

Version 2.0.0 introduces a major architectural change by splitting the unified `jira` skill into two specialized skills within a single plugin:

- **jira-mcp**: MCP server communication and Jira API operations
- **jira-syntax**: Jira wiki markup syntax validation and templates

## Breaking Changes

### Plugin Name Change
- **Old**: `jira` (v1.x)
- **New**: `jira-integration` (v2.0.0+)

### Skill Structure
- **Old**: Single skill at `skills/jira/`
- **New**: Two skills at `skills/jira-mcp/` and `skills/jira-syntax/`

### File Paths
- **Templates**: `skills/jira/templates/` → `skills/jira-syntax/templates/`
- **References**: `skills/jira/references/jira-syntax-quick-reference.md` → `skills/jira-syntax/references/jira-syntax-quick-reference.md`
- **Scripts**: `skills/jira/scripts/` → `skills/jira-syntax/scripts/`

## Migration Steps

### Step 1: Uninstall Old Version

```bash
# Uninstall the old jira skill (v1.x)
/plugin uninstall jira
```

### Step 2: Install New Version

```bash
# Install the new jira-integration plugin (v2.0.0+)
/plugin install jira-integration
```

Both skills are automatically installed and configured.

### Step 3: Update MCP Configuration (if manually configured)

If you manually configured the MCP server in `~/.claude/mcp.json` instead of using the bundled configuration:

**Old configuration:**
```json
{
  "mcp-atlassian": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "--pull=always", "--env-file", "${HOME}/.env.jira",
             "ghcr.io/sooperset/mcp-atlassian:latest"]
  }
}
```

**New**: No changes needed - configuration remains the same and is bundled with the plugin.

### Step 4: Verify Installation

Test both skills:

```bash
# Test jira-syntax skill
"Show me the bug report template"
→ Should provide template from skills/jira-syntax/templates/

# Test jira-mcp skill
"Search for issues in project PROJ"
→ Should execute JQL query via mcp-atlassian
```

## Functionality Comparison

### What Stayed the Same ✅

- **MCP Server**: Still uses mcp-atlassian with same configuration
- **Credentials**: Same `~/.env.jira` file location and format
- **Templates**: Same bug report and feature request templates
- **Syntax Rules**: Same Jira wiki markup standards
- **MCP Tools**: All mcp-atlassian tools available (jira_create_issue, jira_search, etc.)

### What Changed 🔄

#### Automatic Skill Activation

**v1.x**: Single skill activated for all Jira operations

**v2.0.0**: Skills activate automatically based on context:
- `jira-syntax` activates when: formatting, templates, validation needed
- `jira-mcp` activates when: API operations, JQL queries, MCP tool calls needed

#### New References

**v2.0.0 adds:**
- `skills/jira-mcp/references/jql-reference.md` - Comprehensive JQL guide
- `skills/jira-mcp/references/mcp-tools-guide.md` - Complete MCP tool documentation
- `skills/jira-mcp/references/workflow-patterns.md` - Common operation sequences

#### Improved Workflow

**Old workflow (v1.x):**
```
User request → Unified skill → Template/API operation
```

**New workflow (v2.0.0):**
```
User request → jira-syntax (template + validation) → jira-mcp (API submission)
→ Result: Validated content submitted to Jira
```

## Benefits of the New Architecture

### 1. Separation of Concerns
- **jira-syntax**: Pure syntax validation, no API dependencies
- **jira-mcp**: Pure API operations, relies on jira-syntax for formatting

### 2. Offline Capability
- **jira-syntax** works offline for validation and template access
- No MCP server needed for syntax checking

### 3. Clearer Activation
- Skills activate based on specific context
- No ambiguity about which operations each skill handles

### 4. Better Documentation
- Dedicated references for JQL, MCP tools, and workflows
- Easier to find relevant documentation

### 5. Easier Maintenance
- Update syntax rules independently from API operations
- Add new templates without touching MCP code

## Troubleshooting

### Issue: Skills Not Activating

**Solution:**
1. Verify installation: `/plugin list` should show `jira-integration`
2. Check both skills exist: `ls skills/jira-mcp/` and `ls skills/jira-syntax/`
3. Reinstall if needed: `/plugin uninstall jira-integration` then `/plugin install jira-integration`

### Issue: MCP Tools Not Found

**Solution:**
1. Verify `~/.env.jira` exists with valid credentials
2. Ensure Docker is running: `docker ps`
3. Check MCP server configuration in `.claude-plugin/plugin.json`
4. Test MCP connection: Try a simple JQL query

### Issue: Templates Not Found

**Solution:**
1. Check templates exist: `ls skills/jira-syntax/templates/`
2. Verify paths updated in any custom references
3. Use correct file paths:
   - Bug report: `skills/jira-syntax/templates/bug-report-template.md`
   - Feature request: `skills/jira-syntax/templates/feature-request-template.md`

### Issue: Syntax Validation Not Working

**Solution:**
1. Verify scripts exist: `ls skills/jira-syntax/scripts/`
2. Check script permissions: `chmod +x skills/jira-syntax/scripts/validate-jira-syntax.sh`
3. Test manually: `skills/jira-syntax/scripts/validate-jira-syntax.sh "h2. Test"`

## Rollback Procedure

If you need to rollback to v1.x:

```bash
# Uninstall v2.0.0
/plugin uninstall jira-integration

# Reinstall v1.x
/plugin install jira@1.0.3
```

**Note**: v1.x is archived and no longer actively maintained. Migration to v2.0.0 is recommended.

## FAQ

### Q: Do I need to reconfigure the MCP server?
**A**: No, MCP configuration remains unchanged. Same credentials and setup.

### Q: Will my existing Jira issues be affected?
**A**: No, this is purely a client-side change. Existing Jira data is untouched.

### Q: Can I use only one skill?
**A**: Both skills are installed together, but they activate independently based on context.

### Q: Are there new features in v2.0.0?
**A**: Yes! New comprehensive references for JQL, MCP tools, and workflow patterns.

### Q: Do templates work differently?
**A**: No, templates have the same content and structure, just moved to `jira-syntax` skill.

### Q: Is the syntax validation different?
**A**: No, same validation rules and script, just organized under `jira-syntax` skill.

## Support

For migration issues:
- Check this guide first
- Review README.md for current documentation
- Review CLAUDE.md for development guidance
- Create issue in repository if problem persists

## Version History

- **v1.0.0 - v1.0.3**: Unified skill architecture
- **v2.0.0**: Two-skill architecture (jira-mcp + jira-syntax)
- **v3.0.0**: Script-based architecture (jira-communication + jira-syntax)
- **v3.0.1**: CLI consistency - all scripts support `--json` and `--quiet`
