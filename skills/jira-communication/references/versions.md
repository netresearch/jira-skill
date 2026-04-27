# Versions — Releases and Fix/Affects Versions

## When to load

Load this reference whenever the user asks about fix/affects versions, releases, or CRUD on project versions (list, get, create, update, release, unrelease, archive, unarchive, move, merge, delete).

## List

```bash
# Default: unreleased versions in the project's native sequence (server order)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py list PROJ

# Filter by status (released | unreleased | archived | all)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py list PROJ --status released

# Paginated search with free-text query and explicit ordering
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py list PROJ \
    --status unreleased --query "1.4" --order-by releaseDate

# Machine-readable outputs
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py --json list PROJ
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py --quiet list PROJ
```

## Get

```bash
# By numeric ID
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py get 10042

# By name (requires --project to disambiguate)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py get "1.4.0" --project PROJ

# With fixed / affected / unresolved counts merged in
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py get 10042 --counts
```

## Create

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py create PROJ "1.4.0" \
    --release-date 2026-05-31 --description "Q2 2026 release"

# Full form with a start date and explicit released/archived flags
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py create PROJ "1.5.0" \
    --start-date 2026-06-01 --release-date 2026-06-30 --released --archived

# Preview the composed payload without hitting the API
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py create PROJ "1.4.0" \
    --release-date 2026-05-31 --dry-run
```

## Update

```bash
# Any subset of fields; internally GET → merge → PUT to protect omitted fields
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py update 10042 \
    --description "Q2 2026 release (postponed)" --release-date 2026-06-07

# Renaming
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py update 10042 --name "1.4.0-rc2"

# Preview merged payload
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py update 10042 --name "1.4.0-rc2" --dry-run
```

## Release / unrelease

```bash
# Mark released with a specific date
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py release 10042 --release-date 2026-05-31

# Omit --release-date to default to today
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py release 10042

# Roll back: sets released=false and explicitly clears releaseDate (null in payload)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py unrelease 10042
```

## Archive / unarchive

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py archive 10039
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py unarchive 10039
```

## Move

```bash
# After another version (IDs must be numeric; the script builds the
# `self` URL client-side from the configured Jira base URL before POSTing)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py move 10045 --after 10042

# Relative position: First | Last | Earlier | Later
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py move 10042 --position First
```

## Merge

```bash
# Preview: fetches relatedIssueCounts on the source and prints what would move
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py merge 10050 INTO 10042 --dry-run

# Execute: reassigns fixVersions/versions references, then deletes the source
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py merge 10050 INTO 10042
```

## Delete

```bash
# Safe: reassign fix-version refs to another version before deleting
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py delete 10050 --move-fix-to 10042

# Reassign both fix and affects references
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py delete 10050 \
    --move-fix-to 10042 --move-affected-to 10042

# Preview (shows orphan counts when no --move-*-to is provided)
uv run ${CLAUDE_SKILL_DIR}/scripts/workflow/jira-version.py delete 10050 --dry-run
```

## Gotchas

- **Plural field names only.** On issues, use `fixVersions` (Fix Version/s) and `versions` (Affects Version/s). The singular forms `fixVersion` and `version` silently no-op on create and give a confusing "field does not exist on screen" error on update.
- **Safe-merge update.** `update` always performs GET → merge → PUT because some Jira deployments treat PUT as replace. Clearing a field (e.g. `unrelease`) emits an explicit `null` in the payload rather than omitting the key.
- **409 on duplicate names.** Creating a version whose name already exists in the project returns HTTP 409; the script surfaces it as `Version "X" already exists in PROJ`.
- **Orphaned references on delete.** `delete` without `--move-fix-to` / `--move-affected-to` leaves dangling `fixVersions` / `versions` arrays on issues. Prefer `--dry-run` first to read the reassign counts.
- **Numeric IDs only on mutating subcommands.** `update`, `release`, `unrelease`, `archive`, `unarchive`, `move`, `merge`, `delete` validate that every positional and target version ID is numeric before any HTTP call, so values like `../../issue/KEY` cannot reach the REST path. Look the version up by name (`get NAME --project PROJ`) first if you only have a name.
- **Paginated endpoint fallback.** `--query` / `--order-by` use the paginated `/project/{key}/version` endpoint (Jira Cloud + DC ≥9.x). On older DC the endpoint returns 404 and the script automatically retries the flat endpoint, applying `--query` substring filter and `--order-by` sort client-side.
- **Archived still filterable.** Archive only hides a version from pickers; JQL like `fixVersion = "1.3.0"` keeps matching archived versions.

## See also

`docs/plans/2026-04-20-versions-design.md` for the full design trail.
