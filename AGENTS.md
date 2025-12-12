<!-- Managed by agent: keep sections & order; edit content, not structure. Last updated: 2025-12-12 -->

# AGENTS.md (root)

**Precedence:** The **closest AGENTS.md** to changed files wins. Root holds global defaults only.

## Project

Claude Code plugin with two skills. See SKILL.md in each skill directory for usage docs.

## Global rules

- Keep PRs small (~300 net LOC)
- Conventional Commits: `type(scope): subject`
- Version managed ONLY in `.claude-plugin/plugin.json`
- Update SKILL.md when changing user-facing behavior

## Pre-commit checks

```bash
# Verify scripts still work
uv run skills/jira-communication/scripts/core/jira-validate.py --help
```

## Index of scoped AGENTS.md

- `./skills/jira-communication/AGENTS.md` — Script development guide
- `./skills/jira-syntax/AGENTS.md` — Template/reference maintenance

## When instructions conflict

Nearest AGENTS.md wins. User prompts override files.

---

## SKILL.md conventions

Skills are user-facing docs that tell AI agents how to USE the skill. Based on the `skill-creator` skill patterns.

### Structure

```
skill-name/
├── SKILL.md              # Required: frontmatter + instructions
├── scripts/              # Optional: executable code
├── references/           # Optional: docs loaded on-demand
└── assets/               # Optional: templates, images for output
```

### SKILL.md format

```yaml
---
name: skill-name
description: >
  What this skill does AND when to use it.
  Include trigger keywords. This is the ONLY part
  Claude sees before activation - make it count.
---

# Skill Title

Instructions for using the skill...
```

### Key principles

1. **Description is the trigger**: Include all "when to use" info in YAML description, not body
2. **Concise over verbose**: Claude is smart - only add what it doesn't know
3. **Progressive disclosure**: Keep SKILL.md lean, put details in `references/`
4. **No duplication**: Info lives in SKILL.md OR references/, not both
5. **Examples over explanations**: Show, don't tell

### What NOT to include

- README.md, CHANGELOG.md, INSTALLATION.md (skill should be self-contained)
- Setup instructions for the user (that's documentation, not skill content)
- Verbose explanations of things Claude already knows

### References organization

For large skills, split by domain:
```
references/
├── api-cloud.md      # Cloud-specific docs
├── api-server.md     # Server-specific docs
└── troubleshooting.md
```

Claude loads only what's needed based on context.

---

## Maintaining this file (convention reference)

### Root file rules

- Keep thin (~30 lines excluding this section)
- Only global defaults - move details to scoped files
- Update timestamp in header when modified

### When to create scoped AGENTS.md

Create when a directory has ≥5 source files with distinct patterns or a different tech stack.

### Scoped file schema (9 sections)

```
## Overview             - Purpose of this subsystem
## Setup & environment  - Dev prerequisites
## Build & tests        - How to test changes
## Code style & conventions - Patterns for this code
## Security & safety    - Security practices
## PR/commit checklist  - Pre-PR requirements
## Good vs. bad examples - Dev patterns
## When stuck           - Where to find help
## House rules          - Local overrides
```

### Header format

```html
<!-- Managed by agent: keep sections & order; edit content, not structure. Last updated: YYYY-MM-DD -->
```
