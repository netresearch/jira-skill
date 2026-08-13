<!-- Managed by agent: keep sections & order; edit content, not structure. Last updated: 2026-04-09 -->

# AGENTS.md (root)

**Precedence:** The **closest AGENTS.md** to changed files wins. Root holds global defaults only.

## Project

Claude Code plugin with two skills. See SKILL.md in each skill directory for usage docs.

## Global rules

- Keep PRs small (~300 net LOC)
- Conventional Commits: `type(scope): subject`
- Version source of truth: `.claude-plugin/plugin.json`; `plugin.json` and both `skills/*/SKILL.md` `metadata.version` must match (parity enforced by pre-commit and CI)
- Update SKILL.md when changing user-facing behavior

## Dependencies

- **`atlassian-python-api` is pinned `>=3.41,<4` on purpose — do NOT bump to v4 without a Jira Cloud test tenant.** Primary target is jira.netresearch.de (Jira Server/DC 9.12), where v3 works fine. v4 added Cloud's `search/jql` (Atlassian removed `/rest/api/3/search` on Cloud — CHANGE-2046) but had DC regressions through 4.0.5 (fixed in 4.0.6). Cloud-pathway bug reports against this skill are "known, blocked on test infra" — acknowledge, don't re-investigate, until a Cloud tenant is available.

## Pre-commit checks

```bash
# Verify scripts still work
uv run skills/jira-communication/scripts/core/jira-validate.py --help

# Tests (note: --no-project — pyproject.toml has no [project] table)
uv run --no-project --with pytest --with atlassian-python-api --with click --with requests \
    python -m pytest tests/ -q

# Both ruff gates, at repo scope, pinned to the version CI uses.
# `check` and `format --check` are SEPARATE gates: a rename that changes line
# length can pass the first and fail the second.
uvx --no-build ruff@0.16.0 check .
uvx --no-build ruff@0.16.0 format --check $(git ls-files '*.py')

# Markdown
npx --yes markdownlint-cli2 "**/*.md"
```

The authoritative gate list is the "Python lint" step of
`netresearch/skill-repo-skill/.github/workflows/validate.yml` — read it there rather
than trusting this block if CI disagrees. Note `Skill Validation` can report
`Errors: 0` from its own script and still fail on a later step; find the culprit with
`gh run view <id> --json jobs --jq '.jobs[].steps[] | select(.conclusion=="failure") | .name'`.

## Release workflow

Releases are automated via GitHub Actions (`.github/workflows/release.yml`). On tag push, it publishes three package families (zip + tar.gz each, plus `SHA256SUMS.txt` with a Sigstore signature and SLSA provenance):

| Package | Description |
|---------|-------------|
| `jira-integration-plugin-vX.X.X.zip` | Full plugin (multi-skill compatible tools) |
| `jira-communication-skill-vX.X.X.zip` | Standalone skill (Claude Desktop compatible) |
| `jira-syntax-skill-vX.X.X.zip` | Standalone skill (Claude Desktop compatible) |

**Steps (release PR — `main` requires pull requests; do not push it directly, that only works via owner bypass and rings the ruleset alarm):**
1. Check commits since last release: `git log --oneline v<last>..HEAD`
2. Backfill any missing CHANGELOG entries, rename `[Unreleased]` to `[<version>] - <today>`, add a fresh empty `[Unreleased]` above it
3. Bump the version in `.claude-plugin/plugin.json` **and** `plugin.json`
4. Bump `metadata.version` in **both** `skills/*/SKILL.md` to match (CI and the pre-commit parity hook validate consistency)
5. Branch `release/v<version>`, commit `chore: release v<version>` (signed, as always), push, open a PR with the same title
6. Merge the PR once CI is green — plain merge, no bypass
7. Tag the merge commit: `git fetch origin main`, assert local HEAD equals the remote `main` tip, then `git tag -s v<version> -m "v<version>"` (signed annotated — never lightweight)
8. Push the tag: `git push origin v<version>`

The GitHub Action on the tag push creates the release with all packages, checksums and SLSA provenance. Never `gh release create`. Write the narrative release notes before tagging and apply them with `gh release edit v<version> --notes-file …` once the Action has published.

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

# Run the eval suite (writes to evals/comprehensive-workspace/<timestamp>/)
bash evals/run-evals.sh

# Optional: emit a consolidated results JSON (pass/fail + tool-call count per eval)
bash evals/run-evals.sh my-iteration --results-json evals/results/my-iteration.json
```

## When instructions conflict

Nearest AGENTS.md wins. User prompts override files.
