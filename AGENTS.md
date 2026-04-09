<!-- Managed by agent: keep sections & order; edit content, not structure. Last updated: 2026-04-09 -->

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

## Release workflow

Releases are automated via GitHub Actions (`.github/workflows/release.yml`). On tag push, it creates 3 packages:

| Package | Description |
|---------|-------------|
| `jira-integration-plugin-vX.X.X.zip` | Full plugin (multi-skill compatible tools) |
| `jira-communication-skill-vX.X.X.zip` | Standalone skill (Claude Desktop compatible) |
| `jira-syntax-skill-vX.X.X.zip` | Standalone skill (Claude Desktop compatible) |

**Steps:**
1. Check commits since last release: `git log --oneline v<last>..HEAD`
2. Backfill any missing CHANGELOG entries
3. Update CHANGELOG.md with new version entry
4. Bump version in `.claude-plugin/plugin.json`
5. Commit: `git commit -m "chore: release v<version>"`
6. Tag: `git tag v<version>`
7. Push: `git push origin main --tags`

The GitHub Action automatically creates the release with all 3 download packages.

## Index of scoped AGENTS.md

- `./skills/jira-communication/AGENTS.md` — Script development guide
- `./skills/jira-syntax/AGENTS.md` — Template/reference maintenance

## Commands

```bash
# Validate Jira environment setup
uv run skills/jira-communication/scripts/core/jira-validate.py --help

# Search Jira issues
uv run skills/jira-communication/scripts/core/jira-search.py query "<JQL>"

# Get issue details
uv run skills/jira-communication/scripts/core/jira-issue.py get <ISSUE-KEY>

# Verify agent harness compliance
bash scripts/verify-harness.sh --format=text --status
```

## When instructions conflict

Nearest AGENTS.md wins. User prompts override files.

