# Project Versions CRUD Design

**Date:** 2026-04-20
**Status:** Draft

## Goal

Add full CRUD for Jira project versions (a.k.a. "fix versions", "affects versions", "releases") to the Jira CLI skill, enabling release managers and developers to drive the release lifecycle from the command line. Typical flows covered: listing versions for a project, creating the next version before a sprint starts, marking a version released (`released=true` + `releaseDate`) after deploy, archiving old versions that no longer belong in pickers, and merging or deleting a version while reassigning `fixVersions` references on existing issues. The script should compose cleanly with `jira-search`, `jira-create`, and `jira-issue update` so that a release can be planned, executed, and closed end-to-end from the shell.

## Jira API

All endpoints below are documented under [Project Versions (Server/DC)](https://developer.atlassian.com/server/jira/platform/rest/v10002/api-group-project-version/) and [Project Versions (Cloud)](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-project-versions/).

| Method | Path | Purpose | Min. Permission |
|--------|------|---------|------------------|
| `GET` | `/rest/api/2/project/{projectIdOrKey}/versions` | List all versions for a project (flat array) | Browse Projects |
| `GET` | `/rest/api/2/project/{projectIdOrKey}/version?orderBy=&query=&status=released,unreleased` | Paginated search (DC ≥9.x, Cloud) | Browse Projects |
| `POST` | `/rest/api/2/version` | Create a version | Administer Projects |
| `GET` | `/rest/api/2/version/{id}` | Read one version | Browse Projects |
| `PUT` | `/rest/api/2/version/{id}` | Update any field (supports `expand=operations`) | Administer Projects |
| `DELETE` | `/rest/api/2/version/{id}?moveFixIssuesTo=&moveAffectedIssuesTo=` | Delete, optionally reassign `fixVersions` / `versions` refs | Administer Projects |
| `POST` | `/rest/api/2/version/{id}/move` | Reorder: `{"after": ".../version/{otherId}"}` **or** `{"position": "First\|Last\|Earlier\|Later"}` | Administer Projects |
| `POST` | `/rest/api/2/version/{id}/mergeto/{moveIssuesTo}` | Merge source into target (reassigns + deletes source) | Administer Projects |
| `GET` | `/rest/api/2/version/{id}/relatedIssueCounts` | Fixed + affected issue counts | Browse Projects |
| `GET` | `/rest/api/2/version/{id}/unresolvedIssueCount` | Unresolved count only | Browse Projects |

### Minimal payloads

Create (`POST /version`):

```json
{
  "name": "1.4.0",
  "project": "PROJ",
  "description": "Q2 2026 release",
  "startDate": "2026-05-01",
  "releaseDate": "2026-05-31",
  "released": false,
  "archived": false
}
```

Update (`PUT /version/{id}`) takes the same shape; see the safe-merge note in Gotchas.

Move (`POST /version/{id}/move`):

```json
{"after": "https://jira.example.com/rest/api/2/version/10042"}
```

…or:

```json
{"position": "Earlier"}
```

### atlassian-python-api coverage

The library exposes these helpers (verify against installed version with
`python -c "import atlassian; help(atlassian.Jira.add_version)"`):

- `get_project_versions(key)` — flat list
- `get_project_versions_paginated(key, start, limit, order_by=None, expand=None)` — DC ≥9.x / Cloud
- `add_version(name, project_key, is_released=False, is_archived=False)` — limited keyword set
- `update_version(version, name=None, description=None, is_released=None, is_archived=None, start_date=None, release_date=None)`
- `get_version(version)`
- `delete_version(version, moved_fixed=None, move_affected=None)`

The library does **not** wrap `move`, `mergeto`, `relatedIssueCounts`, or `unresolvedIssueCount`. For those, call the underlying HTTP client directly:

```python
client.post(f"rest/api/2/version/{vid}/move", data={"position": "Last"})
client.get(f"rest/api/2/version/{vid}/relatedIssueCounts")
```

Prefer raw HTTP for `add_version` / `update_version` as well, because the wrapper's argument surface drops several fields (e.g. `startDate`). A thin internal helper (`_put_version`, `_post_version`) keeps payload construction explicit and testable.

## Field name gotcha

Two issue fields reference versions, with confusingly similar names:

| Issue field | Jira UI label | Meaning |
|-------------|---------------|---------|
| `fixVersions` | "Fix Version/s" | Version(s) the issue is (or will be) fixed/released in |
| `versions` | "Affects Version/s" | Version(s) in which the issue was observed |

Both take an array of reference objects — either `[{"id": "10042"}]` or `[{"name": "1.4.0"}]`. It is a common bug to post `"version"` (singular) or `"fixVersion"` (singular, no `s`); Jira silently ignores unknown fields on create and returns a confusing "field does not exist on screen" on update. Wherever the script emits or consumes these, use the exact plural field names.

## New Script: `jira-version.py`

Location: `skills/jira-communication/scripts/workflow/jira-version.py` (workflow/, because version lifecycle is release-management-adjacent and composes with `jira-create` / `jira-transition`).

Follows existing conventions: PEP 723 header with `atlassian-python-api` and `click`, Click group with the standard global flags (`--json`, `--quiet`, `--env-file`, `--profile`, `--debug`), `LazyJiraClient`, and `lib.output` (`success`, `warning`, `error`, `format_output`).

### Subcommands

#### `list PROJECT_KEY [--status released|unreleased|archived|all] [--query TEXT] [--order-by sequence|name|startDate|releaseDate]`

Lists versions in a project. Default `--status unreleased`. Uses the paginated endpoint when `--query` or `--order-by` is set, otherwise falls back to the flat endpoint for older DC servers.

```
$ jira-version list PROJ --status unreleased --order-by releaseDate
Unreleased versions in PROJ (3):

  ID       NAME     STATUS       START        RELEASE      ISSUES
  10042    1.4.0    unreleased   2026-05-01   2026-05-31   12
  10045    1.5.0    unreleased   2026-06-01   2026-06-30   0
  10048    1.6.0    unreleased   -            -            0
```

JSON output: array of version objects as returned by the API, with `issueCount` merged in from `relatedIssueCounts` when present.

#### `get VERSION_ID_OR_NAME [--project PROJECT] [--counts]`

Reads one version. Accepts either a numeric ID or a name; when a name is given, `--project` must be set and the script resolves it via `list`. `--counts` additionally fetches `relatedIssueCounts` and `unresolvedIssueCount`.

```
$ jira-version get 10042 --counts
Version 10042 — 1.4.0
  Project:      PROJ
  Status:       unreleased
  Start:        2026-05-01
  Release:      2026-05-31
  Description:  Q2 2026 release
  Issues:       fixed=12 affected=3 unresolved=4
```

#### `create PROJECT_KEY NAME [--description TEXT] [--start-date YYYY-MM-DD] [--release-date YYYY-MM-DD] [--released] [--archived] [--dry-run]`

Creates a new version. `--released` + `--archived` default to `false`.

```
$ jira-version create PROJ "1.4.0" --release-date 2026-05-31 --description "Q2 2026 release"
Created version 10042 "1.4.0" in PROJ (release 2026-05-31)
```

Dry-run prints the composed payload without posting.

#### `update ID (--name|--description|--start-date|--release-date|--released/--unreleased|--archived/--unarchived)... [--dry-run]`

Updates any subset of fields. Internally performs **GET → merge → PUT** to protect against deployments that treat `PUT` as replace rather than patch (see Gotchas).

```
$ jira-version update 10042 --description "Q2 2026 release (postponed)" --release-date 2026-06-07
Updated version 10042
```

#### `release ID [--release-date YYYY-MM-DD] [--dry-run]`

Convenience wrapper: sets `released=true` and `releaseDate` (default: today). Equivalent to `update ID --released --release-date <d>`.

```
$ jira-version release 10042 --release-date 2026-05-31
Released version 10042 "1.4.0" on 2026-05-31
```

#### `unrelease ID [--dry-run]`

Sets `released=false` and clears `releaseDate`. **Important:** because Jira's `PUT` is treated as replace by some deployments, clearing `releaseDate` means **explicitly setting the key to `null`** in the merged payload — not omitting it. The safe-update helper handles this.

#### `archive ID [--dry-run]` / `unarchive ID [--dry-run]`

Toggle the `archived` flag. Archived versions disappear from most issue-level pickers but remain queryable.

#### `move ID (--after OTHER_ID | --position First|Last|Earlier|Later) [--dry-run]`

Reorder a version in the project's version list (affects sort order in pickers and reports).

```
$ jira-version move 10045 --after 10042
Moved version 10045 after 10042

$ jira-version move 10042 --position First
Moved version 10042 to First
```

#### `merge SRC_ID INTO DST_ID [--dry-run]`

Reassigns all `fixVersions` / `versions` references from SRC to DST, then deletes SRC. Dry-run fetches `relatedIssueCounts` on both sides and shows what would move.

```
$ jira-version merge 10050 INTO 10042 --dry-run
DRY RUN - No changes will be made
Would merge 10050 "1.4.0-dup" into 10042 "1.4.0":
  fixed issues to reassign:    7
  affected issues to reassign: 1
  source version would be deleted
```

#### `delete ID [--move-fix-to ID] [--move-affected-to ID] [--dry-run]`

Delete a version. Without `--move-fix-to` / `--move-affected-to`, references on existing issues become orphaned — the script prints a warning and requires `--dry-run` confirmation before the first non-dry-run invocation suggests a target.

```
$ jira-version delete 10050 --move-fix-to 10042
Deleted version 10050; 7 fixVersion refs reassigned to 10042
```

All destructive operations (`delete`, `merge`, `release`, `unrelease`, `archive`, `unarchive`) support `--dry-run`.

## Use Cases

Common release-management flows the script enables end-to-end from the shell:

1. **Create the next release at sprint start.**
   ```
   jira-version create PROJ "1.4.0" --release-date 2026-05-31 --description "Q2 2026 release"
   ```
   Release manager opens the sprint with the version already in the picker.

2. **Pick a fix-version when filing a new ticket.**
   ```
   jira-version list PROJ --status unreleased --order-by releaseDate
   ```
   Developers see upcoming versions in release-date order before setting `fixVersions`.

3. **Mark a version released after deploy.**
   ```
   jira-version release 10041 --release-date 2026-04-30
   ```
   Closes out the version and triggers release-report generation in Jira.

4. **Merge a duplicate version a PM accidentally created.**
   ```
   jira-version merge 10050 INTO 10042 --dry-run
   jira-version merge 10050 INTO 10042
   ```
   Reassigns references without touching issue history.

5. **Delete an abandoned version but preserve issue history.**
   ```
   jira-version delete 10048 --move-fix-to 10042
   ```
   Avoids orphaned `fixVersions` references.

6. **Decide whether a version is safe to archive.**
   ```
   jira-version get 10039 --counts
   ```
   Release manager checks `unresolved=0` before archiving.

7. **Bulk-retag issues to a renamed version.**
   ```
   jira-search query 'project = PROJ AND fixVersion = "1.4.0-candidate"' --fields key
   while read key; do
     jira-issue update "$key" --fields-json '{"fixVersions": [{"name": "1.4.0"}]}'
   done
   ```
   Composes with existing scripts; no new flags needed.

8. **Auto-assign fixVersion on new tickets for an active sprint.**
   ```
   VER=$(jira-version list PROJ --status unreleased --json | jq -r '.[0].name')
   jira-create issue PROJ "New task" -t "Technical task" \
     --fields-json "{\"fixVersions\": [{\"name\": \"$VER\"}]}"
   ```
   Chains `jira-version list` with `jira-create` without plumbing a dedicated flag.

## DC vs Cloud differences

| Concern | DC v2 | Cloud v3 |
|---------|-------|----------|
| Base path | `/rest/api/2/version` | `/rest/api/3/version` |
| Paginated search | `/project/{key}/version` (DC ≥9.x) | `/project/{key}/version` |
| Project field in create | `project` (key) or `projectId` | same |
| Description format | wiki markup | ADF (Atlassian Document Format) |
| Archive field | `archived` boolean | same |
| Move endpoint | `/version/{id}/move` | same |
| `expand=operations` | supported | supported |

The script targets `/rest/api/2/...` (DC is the primary deployment); Cloud works if wiki-markup descriptions are acceptable. A follow-up can add an `--api-version` switch if ADF support becomes necessary.

## Gotchas

- **`fixVersions` vs `versions`.** On issues, `fixVersions` = Fix Version/s, `versions` = Affects Version/s. Both are plural. Using the singular form (`fixVersion`, `version`) silently no-ops on create.
- **PUT is replace on some deployments.** `PUT /version/{id}` has been observed to clear omitted fields on older DC versions and some Cloud tenants. The `update` subcommand **always GETs first, merges user-provided fields, then PUTs** the full object. Clearing a field (e.g. `unrelease`) sets it to `null` explicitly in the merged payload — it does not omit it.
- **Date format.** `startDate` / `releaseDate` must be ISO `YYYY-MM-DD`. Timestamps (`...T00:00:00Z`) are rejected with a 400. The script validates the format client-side before posting.
- **Duplicate names.** Jira returns HTTP 409 when a version with the same name already exists in the project. Surface this as a clear `error()` message: `Version "1.4.0" already exists in PROJ (id=10042)` rather than a raw stack trace.
- **`move` uses self URLs.** The `--after` form requires a fully qualified `self` URL (`https://{JIRA_URL}/rest/api/2/version/{id}`), not a bare ID. Build it from `LazyJiraClient.base_url` — never hand-construct from user input.
- **Orphaned references on delete.** `DELETE /version/{id}` without `moveFixIssuesTo` / `moveAffectedIssuesTo` leaves dangling `fixVersions` / `versions` arrays on issues. The script warns with the fixed/affected counts from `relatedIssueCounts` and refuses to proceed without either `--move-*-to` or an explicit `--force` style confirmation (re-running with `--dry-run=false` after a prior dry-run).
- **Archived versions still filterable.** Archive does not hide a version from JQL (`fixVersion = "1.3.0"` still works); it only suppresses it in pickers. Document this in SKILL.md to avoid surprises.
- **`mergeto` deletes the source.** There is no "undo merge." Dry-run is mandatory for review; the script prints the issue counts on both sides before executing.

## Testing

Tests live at `tests/test_version.py` and follow the patterns in `tests/test_weblink.py` / `tests/test_link.py` (mock `LazyJiraClient`, assert on the request payload and on stdout).

Cases to cover:

- `list` with each `--status` value (`released`, `unreleased`, `archived`, `all`)
- `list` falls back to flat endpoint when `--order-by` / `--query` are absent
- `get` by numeric ID (direct GET)
- `get` by name with `--project` (calls list, filters, exits 1 on ambiguous/missing)
- `get --counts` merges `relatedIssueCounts` + `unresolvedIssueCount`
- `create` success (201) and duplicate-name 409 surfaces a clean error
- `create --dry-run` posts nothing and prints the composed payload
- `update` performs GET → merge → PUT; omitted fields retain their GET values
- `update` with `--unreleased` explicitly sets `releaseDate: null` in the payload
- `release` / `unrelease` set `released` + `releaseDate` correctly
- `archive` / `unarchive` toggle `archived` only; other fields untouched
- `move --after` builds the correct self URL from `LazyJiraClient.base_url`
- `move --position` posts `{"position": "First"}` etc.
- `merge --dry-run` fetches `relatedIssueCounts` on both sides and prints counts
- `merge` (non-dry) calls `/mergeto/{dst}` and does **not** issue a separate DELETE
- `delete` with `--move-fix-to` appends the query params correctly
- `delete` without any `--move-*-to` prints the orphan warning
- `delete --dry-run` makes no DELETE call

Fixtures: a `make_version(id, name, released=False, archived=False, **dates)` helper and a `mock_client` fixture that stubs `get`/`post`/`put`/`delete` on the underlying HTTP client.

## Files Changed

| Change | File | Description |
|--------|------|-------------|
| New | `scripts/workflow/jira-version.py` | Version CRUD script |
| New | `tests/test_version.py` | Tests for version subcommands |
| Modify | `SKILL.md` | Document new script; note `fixVersions` vs `versions` |

No changes required to `lib/client.py` or `lib/output.py`; existing helpers are sufficient. No new dependencies, so `plugin.json` is untouched.

## Out of Scope

- **Component CRUD** (`/rest/api/2/component`). Structurally similar but a separate feature; tracked for a follow-up design doc.
- **Issue-level `--fix-version` flag** on `jira-create` and `jira-issue update`. Users currently pass `--fields-json '{"fixVersions": [{"name": "..."}]}'`. A first-class flag would be nicer and is a likely follow-up, but is deliberately excluded here to keep this PR ~300 LOC.
- **Release notes generation** from version issue lists. Out of scope for this script; compose with `jira-search` over `fixVersion = "<name>"` if needed.
- **Cloud ADF description support.** `--description` accepts plain text / wiki markup only; ADF conversion is out of scope.
- **Sprint-to-version auto-linking.** No hook to set `fixVersions` on all issues in a sprint; can be composed with `jira-search` + `jira-issue update` in a one-liner.
