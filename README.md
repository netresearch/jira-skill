<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
<!-- SPDX-FileCopyrightText: Netresearch DTT GmbH -->

# Jira Integration Plugin for Claude Code

[![CI](https://github.com/netresearch/jira-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/netresearch/jira-skill/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT%20%2B%20CC--BY--SA--4.0-blue.svg)](#license)
[![Python](https://img.shields.io/badge/python-3.10%7C3.11%7C3.12%7C3.13%7C3.14-blue)](https://www.python.org/)

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

### Marketplace (Recommended)

Add the [Netresearch marketplace](https://github.com/netresearch/claude-code-marketplace) once, then browse and install skills:

```bash
# Claude Code
/plugin marketplace add netresearch/claude-code-marketplace
/plugin install jira-integration@netresearch-claude-code-marketplace
```

### Without a marketplace

Since Claude Code 2.1.157 a plugin directory under your personal skills directory loads on its own, including the hooks this repo ships:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/netresearch/jira-skill.git \
  ~/.claude/skills/jira-integration
```

It loads as `jira-integration@skills-dir` on the next session. Update with `git -C ~/.claude/skills/jira-integration pull` and start a new session; remove it by deleting the directory. This route has no `claude plugin update`.

### npx ([skills.sh](https://skills.sh))

Install with any [Agent Skills](https://agentskills.io)-compatible agent:

```bash
npx skills add https://github.com/netresearch/jira-skill --skill jira-communication
npx skills add https://github.com/netresearch/jira-skill --skill jira-syntax
```

> **Limitation:** `npx skills` installs `SKILL.md`-based skills only. This repo also ships `hooks`, which it does not install — use the marketplace or the skills directory for those.

### Download Release

Download the [latest release](https://github.com/netresearch/jira-skill/releases/latest) and extract to your agent's skills directory.

### Git Clone

```bash
git clone https://github.com/netresearch/jira-skill.git
```

### Composer (PHP Projects)

```bash
composer require netresearch/jira-skill
```

Requires [netresearch/composer-agent-skill-plugin](https://github.com/netresearch/composer-agent-skill-plugin).
### npm (Node Projects)

```bash
npm install --save-dev \
  @netresearch/agent-skill-coordinator \
  github:netresearch/jira-skill
```

Requires [@netresearch/agent-skill-coordinator](https://github.com/netresearch/node-agent-skill-coordinator), which discovers the skill in `node_modules` and registers it in `AGENTS.md` via a `postinstall` hook. For pnpm, also allowlist the coordinator's postinstall:

```json
{
  "pnpm": {
    "onlyBuiltDependencies": ["@netresearch/agent-skill-coordinator"]
  }
}
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
pip install uv
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

## Governance and policies

This repository follows the Netresearch organisation policies:

- [Governance](https://github.com/netresearch/.github/blob/main/GOVERNANCE.md): ownership, roles, how decisions are made and disputes resolved, and continuity.
- [Roadmap](https://github.com/netresearch/.github/blob/main/ROADMAP.md): planned and explicitly excluded work for the coming year.
- [Handling of dependency and code analysis findings](https://github.com/netresearch/.github/blob/main/SECURITY.md#handling-of-dependency-and-code-analysis-findings): thresholds, deadlines and the exception process for dependency (SCA) and static analysis (SAST) findings.
- [Secret management](https://github.com/netresearch/.github/blob/main/SECURITY.md#secret-management): how CI and release credentials are stored, accessed and rotated.
- [Access roster](https://github.com/netresearch/.github/blob/main/docs/access-roster.md): who holds administrative access to this repository and the organisation.

The security assurance case for this plugin (how Jira credentials are read and where they are sent, trust boundaries, countermeasures and limits) is in [docs/SECURITY-ASSURANCE.md](docs/SECURITY-ASSURANCE.md).

Checks that run in this repository:

- Every pull request: Skill Validation (`lint.yml` and `validate.yml`: skill structure, plugin manifest sync, markdownlint, yamllint, actionlint, JSON syntax, version parity, ShellCheck, ruff; `validate.yml` runs ShellCheck at style severity) and Eval Validation (`eval-validate.yml`).
- Pull requests to `main`: CI (`ci.yml`: the pytest suite on Python 3.10 to 3.14 and bandit at severity medium over the scripts), CodeQL for `actions` and `python` (`codeql.yml`), `security.yml` with Betterleaks (secret scanning), zizmor (workflow static analysis), dependency review, Composer Audit and Opengrep SAST, Harness Verification (`harness-verify.yml`) and Template Drift (`check-template-drift.yml`). The organisation's security policy sets when dependency review and Opengrep fail: see [dependencies](https://github.com/netresearch/.github/blob/main/SECURITY.md#dependencies-software-composition-analysis) and [static analysis (SAST)](https://github.com/netresearch/.github/blob/main/SECURITY.md#static-analysis-sast).
- Also on every pull request: Labeler (`labeler.yml`) and, for dependency-update pull requests, auto-merge (`auto-merge-deps.yml`).
- Weekly: Dependency Audit (`dependency-audit.yml`) runs pip-audit over the PEP 723 dependencies of `skills/jira-communication/scripts`. Dependency review does not read PEP 723 blocks, so vulnerabilities in the Python dependencies are found by this weekly run, not per pull request.

## License

MIT

## Credits

Developed and maintained by [Netresearch DTT GmbH](https://www.netresearch.de/).

---

**Made with ❤️ for Open Source by [Netresearch](https://www.netresearch.de/)**
