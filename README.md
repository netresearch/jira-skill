# Jira Integration Plugin for Claude Code

[![CI](https://github.com/netresearch/jira-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/netresearch/jira-skill/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/netresearch/jira-skill)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%7C3.11%7C3.12%7C3.13-blue)](https://www.python.org/)

A Claude Code plugin providing comprehensive Jira integration through two specialized skills.

## Plugin Structure

| Skill | Purpose |
|-------|---------|
| `jira-communication` | API operations via Python CLI scripts |
| `jira-syntax` | Wiki markup syntax, templates, validation |

Each skill has its own `SKILL.md` with trigger conditions and usage instructions. Claude Code auto-discovers and activates skills based on context.

## 🔌 Skill Compatibility

The skills contained in this plugin follow the [Agent Skills open standard](https://agentskills.io) originally developed by Anthropic and released for cross-platform use.

**Supported Platforms:**
- ✅ Claude Code (Anthropic)
- ✅ Cursor
- ✅ GitHub Copilot
- ✅ Other skills-compatible AI agents

> Skills are portable packages of procedural knowledge that work across any AI agent supporting the Agent Skills specification.


## Features

- **Zero MCP overhead** - Scripts invoked via Bash, no tool descriptions loaded
- **Fast execution** - No Docker container spin-up
- **Full API coverage** - All common Jira operations supported
- **Jira Server/DC + Cloud** - Works with both deployment types

## Installation

### Download Options

Each release provides multiple packages to match your AI agent platform:

| Package | Use Case |
|---------|----------|
| `jira-integration-plugin-vX.X.X.zip` | **Full plugin** - Platforms supporting multi-skill plugins |
| `jira-communication-skill-vX.X.X.zip` | **Standalone skill** - Platforms requiring single SKILL.md per package |
| `jira-syntax-skill-vX.X.X.zip` | **Standalone skill** - Wiki markup only (no API scripts) |

Download from [Releases](https://github.com/netresearch/jira-skill/releases).

### Installation

Skills follow the [Agent Skills specification](https://agentskills.io/specification). Installation varies by platform:

**Multi-skill platforms** (e.g., Claude Code CLI):
```bash
# Install the full plugin containing both skills
claude plugins install path/to/jira-integration-plugin-vX.X.X.zip
```

**Single-skill platforms** (e.g., Claude Desktop, Cursor, GitHub Copilot):
1. Download the standalone skill ZIP (`jira-communication-skill-*.zip` or `jira-syntax-skill-*.zip`)
2. Import via your platform's skill/extension management

Refer to your AI agent's documentation for specific installation instructions.

### Prerequisites

1. **Install uv** (Python package runner):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Configure credentials** in `~/.env.jira`:
   ```
   JIRA_URL=https://your-instance.atlassian.net
   JIRA_USERNAME=your-email@example.com
   JIRA_API_TOKEN=your-api-token
   ```

   For Jira Server/DC with Personal Access Token:
   ```
   JIRA_URL=https://jira.yourcompany.com
   JIRA_PERSONAL_TOKEN=your-personal-access-token
   ```

3. **Validate setup**:
   ```bash
   uv run scripts/core/jira-validate.py --verbose
   ```

## Quick Start

> **Note:** Run commands from `skills/jira-communication/`, or prefix paths with `skills/jira-communication/` from the repo root.

```bash
# Search issues
uv run scripts/core/jira-search.py query "project = PROJ AND status = 'In Progress'"

# Get issue details
uv run scripts/core/jira-issue.py get PROJ-123

# Add worklog
uv run scripts/core/jira-worklog.py add PROJ-123 "2h 30m" -c "Code review"

# Create issue
uv run scripts/workflow/jira-create.py issue PROJ "Fix bug" --type Bug --priority High
```

## Available Scripts

### Core Operations (scripts/core/)

| Script | Commands | Usage |
|--------|----------|-------|
| `jira-setup.py` | (default) | Interactive credential setup |
| `jira-validate.py` | (default) | Validate environment setup |
| `jira-issue.py` | get, update | Get and update issues |
| `jira-search.py` | query | JQL search |
| `jira-worklog.py` | add, list | Time tracking |
| `jira-attachment.py` | download | Download issue attachments |

### Workflow Operations (scripts/workflow/)

| Script | Commands | Usage |
|--------|----------|-------|
| `jira-create.py` | issue | Create new issues |
| `jira-transition.py` | list, do | Change issue status |
| `jira-comment.py` | add, list | Issue comments |
| `jira-sprint.py` | list, issues, current | Sprint operations |
| `jira-board.py` | list, issues | Board operations |

### Utility Operations (scripts/utility/)

| Script | Commands | Usage |
|--------|----------|-------|
| `jira-fields.py` | search, list | Find field IDs |
| `jira-user.py` | me, get | User information |
| `jira-link.py` | create, list-types | Issue linking |

## Common Options

All scripts support:

- `--json` - Output as JSON
- `--quiet` / `-q` - Minimal output
- `--env-file PATH` - Custom environment file
- `--debug` - Show detailed errors
- `--help` - Show command help

Write operations also support:

- `--dry-run` - Preview changes without executing

## Script Usage Examples

### Search and Filter

```bash
# Find open bugs in project
uv run scripts/core/jira-search.py query "project = PROJ AND type = Bug AND status != Done"

# Find my assigned issues
uv run scripts/core/jira-search.py query "assignee = currentUser()"

# Output as JSON for processing
uv run scripts/core/jira-search.py query "project = PROJ" --json --max-results 100
```

### Issue Management

```bash
# Get issue details
uv run scripts/core/jira-issue.py get PROJ-123

# Update issue fields (dry-run first)
uv run scripts/core/jira-issue.py update PROJ-123 --labels "urgent,backend" --dry-run

# Create new issue
uv run scripts/workflow/jira-create.py issue PROJ "Implement feature X" --type Story --priority Medium
```

### Time Tracking

```bash
# Log time worked
uv run scripts/core/jira-worklog.py add PROJ-123 "2h 30m" -c "Implemented core logic"

# View worklogs
uv run scripts/core/jira-worklog.py list PROJ-123
```

### Workflow Transitions

```bash
# List available transitions
uv run scripts/workflow/jira-transition.py list PROJ-123

# Transition issue (dry-run first)
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress" --dry-run

# Execute transition
uv run scripts/workflow/jira-transition.py do PROJ-123 "In Progress"
```

### Comments

```bash
# Add comment
uv run scripts/workflow/jira-comment.py add PROJ-123 "Investigation complete - root cause identified"

# List recent comments
uv run scripts/workflow/jira-comment.py list PROJ-123 --limit 5
```

### Sprint & Board Operations

```bash
# List boards for project
uv run scripts/workflow/jira-board.py list --project PROJ

# Get board issues
uv run scripts/workflow/jira-board.py issues 42

# List sprints
uv run scripts/workflow/jira-sprint.py list 42 --state active

# Get sprint issues
uv run scripts/workflow/jira-sprint.py issues 123

# Get current sprint
uv run scripts/workflow/jira-sprint.py current 42
```

### Utility Operations

```bash
# Search for custom fields
uv run scripts/utility/jira-fields.py search "story points"

# List all custom fields
uv run scripts/utility/jira-fields.py list --type custom

# Get current user info
uv run scripts/utility/jira-user.py me

# List available link types
uv run scripts/utility/jira-link.py list-types

# Create issue link
uv run scripts/utility/jira-link.py create PROJ-123 PROJ-456 --type "Blocks" --dry-run
```

## Related Skills

- **jira-syntax** - Jira wiki markup validation and templates (unchanged)

## Troubleshooting

### "uv not found"

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### "Environment file not found"

Create `~/.env.jira` with your credentials.

### "Authentication failed"

1. Verify JIRA_URL is correct
2. For Cloud: JIRA_USERNAME is your email
3. For Server/DC: Use JIRA_PERSONAL_TOKEN instead
4. Regenerate your API token if expired

### Import errors when running scripts

Run scripts from the skill directory:
```bash
cd skills/jira-communication
uv run scripts/core/jira-issue.py get PROJ-123
```

## License

MIT

## Credits

Developed and maintained by [Netresearch DTT GmbH](https://www.netresearch.de/).

---

**Made with ❤️ for Open Source by [Netresearch](https://www.netresearch.de/)**
