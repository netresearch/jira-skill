# PRD: Jira Skill Migration to Script-Based Architecture

**Version:** 1.0
**Author:** Claude Code Assistant
**Date:** 2025-11-25
**Status:** Draft - Pending Review

---

## Executive Summary

Migrate the jira-mcp skill from the context-heavy mcp-atlassian Docker-based MCP server to a lightweight, script-based architecture using `uvx` (uv run) with `atlassian-python-api` and `click` for CLI definitions.

**Key Benefits:**
- **Zero MCP server overhead** - no tool descriptions loaded
- **Faster startup** - no Docker container spin-up
- **Full API coverage** - scripts provide complete Jira functionality
- **Better maintainability** - simple Python scripts vs. complex MCP server

---

## Problem Statement

### Current State

The jira-mcp skill currently ships the `mcp-atlassian` MCP server via Docker:

```json
"mcpServers": {
  "mcp-atlassian": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "--pull=always", "--env-file", "${HOME}/.env.jira",
             "ghcr.io/sooperset/mcp-atlassian:latest"]
  }
}
```

### Problems Identified

| Problem | Impact | Severity |
|---------|--------|----------|
| **Context overhead** | ~25 tools loaded = ~8,000-12,000 tokens per session | High |
| **Docker dependency** | Container spin-up latency, `--pull=always` network overhead | Medium |
| **Tool bloat** | Confluence tools loaded but unused; many Jira tools rarely used | Medium |
| **Credential handling** | Env file must be mounted into container | Low |

### Usage Analysis (from 126 debug sessions)

Real-world tool usage reveals that **5 tools account for 80% of all usage**:

| Rank | Tool | Usage Count | % of Total |
|------|------|-------------|------------|
| 1 | `jira_add_worklog` | 595 | 22.8% |
| 2 | `jira_get_issue` | 485 | 18.6% |
| 3 | `jira_search` | 280 | 10.7% |
| 4 | `jira_update_issue` | 210 | 8.1% |
| 5 | `jira_create_issue` | 190 | 7.3% |
| 6-25 | Other tools | 848 | 32.5% |

**Key Insight:** Worklog operations (#1) were barely documented but are the most-used feature.

---

## Goals & Non-Goals

### Goals

1. **G1:** Eliminate MCP server context overhead
2. **G2:** Maintain 100% feature parity for top 10 most-used operations
3. **G3:** Provide pre-flight validation for environment, dependencies, and credentials
4. **G4:** Support both Jira Cloud and Jira Server/Data Center (Server/DC priority)
5. **G5:** Enable easy extensibility for new operations

### Non-Goals

1. **NG1:** Support Confluence operations (separate skill if needed)
2. **NG2:** Implement rarely-used operations (<10 uses) in Phase 1
3. **NG3:** Build a custom MCP server wrapper
4. **NG4:** Support authentication methods beyond API tokens (OAuth, etc.)

---

## Solution Overview

### Architecture Decision

**Selected Approach:** uvx + atlassian-python-api + Click scripts

| Approach Considered | Context Impact | Complexity | Selected |
|---------------------|---------------|------------|----------|
| Keep mcp-atlassian | High (~10K tokens) | Low | ❌ |
| jira-cli-mcp wrapper | Medium (~3K tokens) | Low | ❌ |
| **uvx + Python scripts** | **Minimal (~500 tokens)** | **Medium** | **✅** |
| ankitpokhrel/jira-cli direct | Minimal | Medium | ❌ |

**Rationale:**
- Zero MCP overhead - scripts invoked via Bash, no tool descriptions loaded
- Full API access via atlassian-python-api (mature, well-maintained)
- Click provides professional CLI UX with minimal boilerplate
- PEP 723 inline dependencies = self-contained, reproducible scripts
- Easy to extend, test, and maintain

### Technology Stack

| Component | Technology | Version | Purpose |
|-----------|------------|---------|---------|
| Runtime | uv / uvx | ≥0.4.0 | Script execution with inline deps |
| Jira SDK | atlassian-python-api | ≥3.41.0 | Jira REST API wrapper |
| CLI Framework | click | ≥8.1.0 | Command-line interface |
| HTTP Client | requests | ≥2.28.0 | Connection testing |

---

## Technical Requirements

### TR1: Script Infrastructure

#### TR1.1: PEP 723 Inline Dependencies
All scripts MUST use PEP 723 inline script metadata:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0",
#     "click>=8.1.0",
# ]
# ///
```

#### TR1.1.1: Shared Library Architecture (Decision: 2025-11-25)

**Initial Approach (Phase 1-2):** PYTHONPATH manipulation with shared `lib/` directory

Scripts use path manipulation to import shared utilities:

```python
import sys
from pathlib import Path

# Add lib/ to import path (enables shared utilities)
_lib_path = Path(__file__).parent.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

from lib.client import get_jira_client
from lib.output import format_output
```

**Future Option (Phase 3+):** Code generation for fully self-contained scripts

To enable future migration to standalone scripts:
1. Keep `lib/` modules small and focused (<100 lines each)
2. No circular imports between lib modules
3. Mark inlinable code with boundary comments:

```python
# lib/client.py
# === INLINE_START: client ===
def get_jira_client(env_file=None):
    ...
# === INLINE_END: client ===
```

**Rationale:** This hybrid approach provides:
- DRY principle compliance during development
- Shared bug fixes across all scripts
- Clear migration path to fully portable scripts if needed
- Acceptable trade-off: scripts must be run from skill directory or with proper path

#### TR1.2: Click CLI Structure
All scripts MUST use Click for CLI definition:

```python
import click

@click.group()
@click.pass_context
def cli(ctx):
    """Jira operations."""
    ctx.ensure_object(dict)
    ctx.obj['client'] = get_jira_client()

@cli.command()
@click.argument('issue_key')
@click.pass_context
def get(ctx, issue_key):
    """Get issue details."""
    ...
```

#### TR1.3: Output Format
- Default: Human-readable formatted output
- `--json` flag: Machine-readable JSON output
- `--quiet` flag: Minimal output (for scripting)

#### TR1.4: Error Handling
- Clear error messages with actionable suggestions
- Appropriate exit codes (see validation script spec)
- No stack traces in production (use `--debug` for verbose errors)

### TR2: Environment & Authentication

#### TR2.1: Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_URL` | Yes | Jira instance URL (e.g., `https://company.atlassian.net`) |
| `JIRA_USERNAME` | Yes | Email (Cloud) or username (Server/DC) |
| `JIRA_API_TOKEN` | Yes | API token or Personal Access Token |
| `JIRA_CLOUD` | No | Force Cloud mode (`true`/`false`), auto-detected if omitted |

#### TR2.2: Environment File Support
- Default location: `~/.env.jira`
- Override via `--env-file` flag
- Format: Standard dotenv (KEY=value, one per line)

#### TR2.3: Validation Script
Pre-flight validation MUST check (in order):

1. **Runtime dependencies**
   - `uv` / `uvx` is installed and accessible
   - Python version meets requirements (≥3.10)

2. **Environment configuration**
   - Environment file exists (`~/.env.jira` or `--env-file`)
   - Required variables are present and non-empty (`JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`)
   - URL format is valid (protocol, domain)

3. **Connectivity & authentication**
   - Server is reachable (connection test with timeout)
   - Credentials are valid (authenticate and get current user)
   - Optional: Project access verification (if `--project` specified)

**Error Handling:**
- Provide clear, actionable error messages (not just exit codes)
- Include suggestions for resolution (e.g., "Run: curl -LsSf https://astral.sh/uv/install.sh | sh")
- Show which check failed and why
- `--verbose` flag for detailed diagnostic output

**Example error output:**
```
✗ Runtime check failed: 'uv' command not found

  To install uv, run:
    curl -LsSf https://astral.sh/uv/install.sh | sh

  Or visit: https://docs.astral.sh/uv/getting-started/installation/
```

### TR3: Script Specifications

#### TR3.1: Core Scripts (P0 - Phase 1)

Based on usage analysis, these scripts cover 67.5% of all operations:

**jira-worklog.py** (595 + 152 = 747 uses)
```
Commands:
  add <issue_key> <time_spent> [--comment TEXT] [--started DATETIME]
  list <issue_key> [--limit N]

Examples:
  jira-worklog add PROJ-123 "2h 30m" --comment "Code review"
  jira-worklog list PROJ-123

Note: TIME_SPENT is passed directly to Jira API (e.g., "2h 30m")
```

**jira-issue.py** (485 + 210 = 695 uses)
```
Commands:
  get <issue_key> [--fields FIELDS] [--expand changelog,transitions]
  update <issue_key> [--summary TEXT] [--priority NAME] [--labels L1,L2] [--json FIELDS]

Examples:
  jira-issue get PROJ-123
  jira-issue get PROJ-123 --fields summary,status,assignee
  jira-issue update PROJ-123 --priority High --labels backend,urgent
```

**jira-search.py** (280 uses)
```
Commands:
  query <jql> [--max-results N] [--fields FIELDS] [--output table|json|keys]

Examples:
  jira-search query "project = PROJ AND status = 'In Progress'"
  jira-search query "assignee = currentUser()" --max-results 20 --output json
```

**jira-validate.py** (new - required for setup)
```
Commands:
  (default) [--verbose] [--project KEY] [--env-file PATH]

Examples:
  jira-validate
  jira-validate --verbose --project HMKG
```

#### TR3.2: Workflow Scripts (P1 - Phase 2)

**jira-create.py** (190 uses)
```
Commands:
  issue <project_key> <summary> --type TYPE [--description TEXT] [--priority NAME]
        [--labels L1,L2] [--assignee USER] [--parent EPIC_KEY]

Examples:
  jira-create issue PROJ "Fix login timeout" --type Bug --priority High
  jira-create issue PROJ "New feature" --type Story --parent PROJ-100
```

**jira-transition.py** (151 + 24 = 175 uses)
```
Commands:
  list <issue_key>
  do <issue_key> <status_name> [--comment TEXT] [--resolution NAME]

Examples:
  jira-transition list PROJ-123
  jira-transition do PROJ-123 "In Progress"
  jira-transition do PROJ-123 "Done" --resolution Fixed --comment "Deployed to prod"
```

**jira-comment.py** (82 uses)
```
Commands:
  add <issue_key> <comment_text>
  list <issue_key> [--limit N]

Examples:
  jira-comment add PROJ-123 "Fixed in commit abc123"
  jira-comment list PROJ-123 --limit 5
```

**jira-sprint.py** (145 + 127 = 272 uses)
```
Commands:
  list <board_id> [--state active|future|closed]
  issues <sprint_id> [--fields FIELDS]
  current <board_id>

Examples:
  jira-sprint list 42 --state active
  jira-sprint issues 123
  jira-sprint current 42
```

**jira-board.py** (136 + 127 = 263 uses)
```
Commands:
  list [--project KEY] [--type scrum|kanban]
  issues <board_id> [--jql JQL]

Examples:
  jira-board list --project PROJ
  jira-board issues 42 --jql "status = 'In Progress'"
```

#### TR3.3: Utility Scripts (P2 - Phase 3)

**jira-fields.py** (167 uses)
```
Commands:
  search <keyword> [--limit N]
  list [--type custom|system]
```

**jira-user.py** (170 uses)
```
Commands:
  me
  get <user_identifier>
```

**jira-link.py** (6 uses - lowest priority)
```
Commands:
  create <from_key> <to_key> --type TYPE
  list-types
```

---

## Directory Structure

```
skills/
├── jira-communication/        # Renamed from jira-mcp
│   ├── SKILL.md               # Updated skill definition
│   ├── scripts/
│   │   ├── lib/               # Shared utilities (TR1.1.1)
│   │   │   ├── __init__.py
│   │   │   ├── client.py      # Jira client initialization
│   │   │   ├── output.py      # Formatting helpers
│   │   │   └── config.py      # Environment handling
│   │   │
│   │   ├── core/              # P0 - Must have
│   │   │   ├── jira-validate.py
│   │   │   ├── jira-worklog.py
│   │   │   ├── jira-issue.py
│   │   │   └── jira-search.py
│   │   │
│   │   ├── workflow/          # P1 - Important
│   │   │   ├── jira-create.py
│   │   │   ├── jira-transition.py
│   │   │   ├── jira-comment.py
│   │   │   ├── jira-sprint.py
│   │   │   └── jira-board.py
│   │   │
│   │   └── utility/           # P2 - Nice to have
│   │       ├── jira-fields.py
│   │       ├── jira-user.py
│   │       └── jira-link.py
│   │
│   ├── tools/                 # Build & development tools
│   │   └── build_scripts.py   # Future: generates standalone scripts (Option A)
│   │
│   ├── build/                 # Generated standalone scripts (Phase 3+)
│   │   └── .gitkeep
│   │
│   └── references/
│       ├── jql-reference.md   # Keep existing
│       ├── script-usage.md    # New: script documentation
│       └── migration-guide.md # New: from MCP to scripts
│
└── jira-syntax/               # UNCHANGED - remains as-is (offline syntax validation)
    ├── SKILL.md
    ├── templates/
    ├── references/
    └── scripts/
```

**Note:** The `jira-syntax` skill is **not affected** by this migration. It provides offline Jira wiki markup validation and templates, independent of API communication.

---

## Migration Plan

### Phase 1: Foundation (P0 Scripts)
**Scope:** Core scripts + validation
**Coverage:** ~68% of usage

| Task | Description | Est. Effort |
|------|-------------|-------------|
| 1.1 | Create `lib/` shared utilities (client, config, output) | 2h |
| 1.2 | Implement `jira-validate.py` | 2h |
| 1.3 | Implement `jira-worklog.py` | 2h |
| 1.4 | Implement `jira-issue.py` | 2h |
| 1.5 | Implement `jira-search.py` | 2h |
| 1.6 | Update SKILL.md with new invocation patterns | 1h |
| 1.7 | Test all P0 scripts against real Jira instance | 2h |

**Deliverable:** Working MVP with top 4 operations

### Phase 2: Workflow Expansion (P1 Scripts)
**Scope:** Workflow scripts
**Coverage:** ~90% of usage

| Task | Description | Est. Effort |
|------|-------------|-------------|
| 2.1 | Implement `jira-create.py` | 2h |
| 2.2 | Implement `jira-transition.py` | 1.5h |
| 2.3 | Implement `jira-comment.py` | 1h |
| 2.4 | Implement `jira-sprint.py` | 2h |
| 2.5 | Implement `jira-board.py` | 1.5h |
| 2.6 | Integration testing | 2h |

**Deliverable:** Full workflow support

### Phase 3: Completion (P2 Scripts + Polish)
**Scope:** Utility scripts + documentation
**Coverage:** ~100% of common usage

| Task | Description | Est. Effort |
|------|-------------|-------------|
| 3.1 | Implement P2 scripts (fields, user, link) | 3h |
| 3.2 | Write migration guide from MCP | 2h |
| 3.3 | Update README.md | 1h |
| 3.4 | Remove mcp-atlassian from plugin.json | 0.5h |
| 3.5 | Final testing + documentation review | 2h |

**Deliverable:** Production-ready v3.0.0

### Phase 4: Deprecation
**Scope:** Archive old approach

| Task | Description | Est. Effort |
|------|-------------|-------------|
| 4.1 | Move old jira-mcp to archive/ | 0.5h |
| 4.2 | Update CHANGELOG.md | 0.5h |
| 4.3 | Tag release v3.0.0 | 0.5h |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| MCP server dependency | Required | Eliminated | No MCP tools loaded |
| Startup latency | ~3-5s (Docker) | <1s (script) | Time to first operation |
| Operation coverage | 100% | ≥95% | Supported vs. used operations |
| Jira Server/DC support | Partial | Full | All scripts tested on Server/DC |
| User satisfaction | N/A | No regressions | User feedback |

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| atlassian-python-api breaking changes | Low | High | Pin version, monitor releases |
| uv/uvx not installed on user system | Medium | High | Document prerequisite, provide install instructions |
| Click learning curve for contributors | Low | Low | Well-documented examples, consistent patterns |
| Missing edge-case operations | Medium | Medium | Phase 2/3 covers long tail; easy to add scripts |
| Jira Server/DC API differences | Medium | Medium | Test on both, document differences |

---

## Dependencies

### External Dependencies

| Dependency | Version | License | Notes |
|------------|---------|---------|-------|
| [uv](https://github.com/astral-sh/uv) | ≥0.4.0 | MIT | Required for uvx/uv run |
| [atlassian-python-api](https://github.com/atlassian-api/atlassian-python-api) | ≥3.41.0 | Apache-2.0 | Jira REST API wrapper |
| [click](https://github.com/pallets/click) | ≥8.1.0 | BSD-3-Clause | CLI framework |
| [requests](https://github.com/psf/requests) | ≥2.28.0 | Apache-2.0 | HTTP client (for validation) |

### Internal Dependencies

- jira-syntax skill (unchanged, no dependencies on jira-mcp)

---

## Open Questions

1. ~~**Q1:** Should we support `--dry-run` for write operations?~~
   - **Decision (D3):** Yes, for create/update/transition operations ✅

2. **Q2:** Should we provide a shell wrapper script for easier invocation?
   - **Status:** Open - decide during Phase 1 implementation
   - **Recommendation:** Optional, document both direct `uv run` and wrapper approaches

3. **Q3:** Should we support config file (beyond env vars) for defaults?
   - **Status:** Deferred to Phase 3, env vars sufficient for MVP

4. ~~**Q4:** Should we rename skill from `jira-mcp` to something else?~~
   - **Decision (D2):** Rename to `jira-communication` ✅

---

## Decisions Made

| ID | Date | Decision | Rationale |
|----|------|----------|-----------|
| D1 | 2025-11-25 | Use PYTHONPATH manipulation for shared lib/ (Option C) with future migration path to code generation (Option A) | Balance DRY principle with PEP 723 goals; enables shared bug fixes while preserving future portability option |
| D2 | 2025-11-25 | Rename skill to `jira-communication` | Describes purpose (API communication) not implementation detail |
| D3 | 2025-11-25 | Support `--dry-run` for write operations (Q1) | Essential for safety in production workflows |
| D4 | 2025-11-25 | Keep `jira-syntax` skill unchanged | Separate concern (offline formatting) independent of API migration |
| D5 | 2025-11-25 | Remove MCP server entirely (no fallback) | Clean break; scripts provide full functionality |
| D6 | 2025-11-25 | No backward compatibility required | Fresh start; migration guide sufficient |
| D7 | 2025-11-25 | Validation script checks uvx/uv installation | Pre-flight validation must verify all runtime dependencies |
| D8 | 2025-11-25 | Prefer actionable error messages over exit codes | Better UX with suggestions for resolution |
| D9 | 2025-11-25 | Jira Server/DC is testing priority (Cloud also supported) | Server/DC is primary use case |
| D10 | 2025-11-25 | Time format passed directly to Jira API | Let Jira handle validation; document "2h 30m" as example |

### D1: Shared Library Architecture

**Context:** PEP 723 is designed for self-contained single-file scripts, but the PRD proposed a shared `lib/` directory for code reuse.

**Decision:** Implement hybrid approach:
- **Phase 1-2:** Use PYTHONPATH manipulation to enable imports from shared `lib/`
- **Phase 3+:** Option to generate fully standalone scripts via `build_scripts.py`

**Trade-offs Accepted:**
- Scripts must be run from skill directory or with full path (not truly portable)
- Path manipulation adds ~10 lines boilerplate per script
- Future migration requires maintaining inline boundary markers

**Benefits:**
- Single source of truth for client initialization, output formatting, config handling
- Bug fixes automatically apply to all scripts
- Clear migration path if portability becomes critical

See TR1.1.1 for implementation details.

---

## Appendix

### A1: Click vs argparse Comparison

| Feature | argparse | Click |
|---------|----------|-------|
| Boilerplate | High | Low |
| Subcommands | Manual | Decorators |
| Help generation | Basic | Rich |
| Testing | Manual | Built-in |
| Color output | Manual | Built-in |
| Progress bars | No | Yes |

**Decision:** Click provides better UX with less code.

### A2: Sample Click Script Structure

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["atlassian-python-api>=3.41.0", "click>=8.1.0"]
# ///
"""Jira worklog operations - add and list time tracking entries."""

import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# Future: This block will be replaced by inlined code via build_scripts.py
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib" if _script_dir.name != "scripts" else _script_dir / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click
from lib.client import get_jira_client
from lib.output import format_output

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════

@click.group()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--env-file', type=click.Path(), help='Environment file path')
@click.option('--debug', is_flag=True, help='Show debug information on errors')
@click.pass_context
def cli(ctx, output_json, env_file, debug):
    """Jira worklog operations."""
    ctx.ensure_object(dict)
    ctx.obj['json'] = output_json
    ctx.obj['debug'] = debug
    try:
        ctx.obj['client'] = get_jira_client(env_file)
    except Exception as e:
        if debug:
            raise
        raise click.ClickException(str(e))

@cli.command()
@click.argument('issue_key')
@click.argument('time_spent')
@click.option('--comment', '-c', help='Worklog comment')
@click.option('--started', help='Start time (ISO format, default: now)')
@click.pass_context
def add(ctx, issue_key, time_spent, comment, started):
    """Add worklog entry to an issue.

    TIME_SPENT format: '2h', '2h 30m', '1d', '30m'
    """
    client = ctx.obj['client']
    result = client.issue_worklog(issue_key, time_spent, comment=comment, started=started)
    format_output(result, ctx.obj['json'])

@cli.command('list')
@click.argument('issue_key')
@click.option('--limit', '-n', default=10, help='Max entries to show')
@click.pass_context
def list_worklogs(ctx, issue_key, limit):
    """List worklog entries for an issue."""
    client = ctx.obj['client']
    result = client.issue_get_worklog(issue_key)
    format_output(result[:limit], ctx.obj['json'])

if __name__ == '__main__':
    cli()
```

**Invocation Examples:**
```bash
# From skill directory (recommended)
cd skills/jira-communication
uv run scripts/core/jira-worklog.py add PROJ-123 "2h 30m" -c "Code review"

# With full path
uv run /path/to/skills/jira-communication/scripts/core/jira-worklog.py list PROJ-123
```

### A3: References

- [atlassian-python-api Documentation](https://atlassian-python-api.readthedocs.io/)
- [Click Documentation](https://click.palletsprojects.com/)
- [PEP 723 - Inline Script Metadata](https://peps.python.org/pep-0723/)
- [uv Documentation](https://docs.astral.sh/uv/)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-25 | Claude | Initial draft |
| 1.1 | 2025-11-25 | Claude | Added TR1.1.1 (shared lib architecture decision), updated directory structure, added Decisions Made section, enhanced sample script with PYTHONPATH pattern |
| 1.2 | 2025-11-25 | Claude | Clarified decisions D4-D10: jira-syntax unchanged, MCP removed, no backward compat, validation includes uvx check, actionable error messages, Server/DC priority, time format pass-through. Removed token count claims. Updated goals (G1-G5), TR2.3 validation requirements, success metrics. |
