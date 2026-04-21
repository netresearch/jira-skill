# Issue Changelog / History Design

**Date:** 2026-04-20
**Status:** Draft

## Goal

Expose an issue's change history ("who changed what, when") to agents and humans. The feature feeds audit trails, sprint retrospectives, and activity reports — answering questions like *who moved PROJ-123 to Done?*, *when did a given custom field last change?*, or *who un-assigned me yesterday?* External activity/reporting tools are likely consumers: feeding changelog rows lets them reconstruct "what did I touch this week" even when no worklog was booked.

## Jira API

Two endpoints exist, and they behave very differently:

### Jira DC (v2) — embedded, capped at 100

```
GET /rest/api/2/issue/{key}?expand=changelog
```

The response contains a `changelog` object with `histories[]`. **The DC endpoint is hard-capped at 100 history entries**; there is no native pagination and no `startAt`/`maxResults` parameters on the issue resource. Long-lived tickets (e.g. long-running epics) will silently truncate. See [Jira DC 9.x — Get issue](https://docs.atlassian.com/software/jira/docs/api/REST/9.12.0/#api/2/issue-getIssue) and the `expand` notes on that page.

### Jira Cloud (v3) — dedicated, paginated

```
GET /rest/api/3/issue/{issueIdOrKey}/changelog?startAt=0&maxResults=100
```

Paginated, default `maxResults=100`, max `1000`. Designed for long histories. See [Cloud v3 — Get changelogs](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-changelog-get).

### Payload shape (both)

```json
{
  "histories": [
    {
      "id": "10001",
      "author": { "accountId": "...", "name": "...", "displayName": "..." },
      "created": "2026-04-18T09:12:33.000+0000",
      "items": [
        {
          "field": "status",
          "fieldtype": "jira",
          "fieldId": "status",
          "from": "10000", "fromString": "In Progress",
          "to": "10001",   "toString": "Done"
        }
      ]
    }
  ]
}
```

### Pitfall — JQL search does not reliably return histories

`POST /rest/api/2/search` with `expand=changelog` returns histories on Cloud but is inconsistent on DC (truncated or omitted depending on the instance configuration). **Always hit the per-issue endpoint.** Bulk history across a JQL result set is out of scope for this feature.

### `atlassian-python-api` support

- DC form already works: `client.issue(key, expand="changelog")` returns `{"changelog": {"histories": [...]}}`.
- No first-class Cloud helper was found by grepping the installed package (`rg -n "changelog" $(python -c 'import atlassian, os; print(os.path.dirname(atlassian.__file__))')`). If that remains true at implementation time, fall back to the raw call:
  ```python
  client.get(f"rest/api/3/issue/{key}/changelog", params={"startAt": 0, "maxResults": 100})
  ```
  — this re-uses the session/auth already configured on `LazyJiraClient`.

### Permissions

*Browse Projects* on the issue's project. No extra permissions; if the user can `get` the issue, they can read its changelog.

## New Subcommand: `jira-issue.py changelog`

Extend the existing `skills/jira-communication/scripts/core/jira-issue.py` — the changelog is tightly coupled to the issue resource, exactly like `get`, `update`, and `delete`. Adding a sibling command keeps the CLI surface discoverable (`jira-issue --help` lists it) and matches the pattern established by the weblink design (weblinks got their own script because they're a separate REST resource with full CRUD; changelog is read-only and attached to the issue).

No new script, no new library module. The date-parsing helper is reused from `jira-worklog-query.py` (see below).

## CLI surface

```
jira-issue.py changelog ISSUE_KEY
    [--field FIELD]...          # repeatable; match by field id OR display name (case-insensitive)
    [--since DATE]              # ISO (2026-03-01) or relative (7d, 2w, 1m) — same parser as jira-worklog-query
    [--until DATE]              # same
    [--author USER]             # username, accountId, display name, or "me"
    [--limit N]                 # cap total entries printed
```

### Examples

```
jira-issue.py changelog PROJ-123
jira-issue.py changelog PROJ-123 --field status
jira-issue.py changelog PROJ-123 --field customfield_10100 --since 30d   # example custom field id — yours will differ
jira-issue.py changelog PROJ-123 --author me --since 7d --json
```

### Filter semantics

- `--field` is repeatable and case-insensitive. `--field status --field sprint` matches items whose `fieldId`, `field` (display), or `fieldSchema.customId` resolves to one of those. Resolution order: `fieldId` → `field` (display name, lowercased) → `"customfield_" + str(fieldSchema.customId)`.
- `--since` / `--until` filter by the parent history entry's `created` timestamp. Date parsing is reused from `jira-worklog-query.py` (relative forms like `7d`, `2w`, `1m`, plus ISO `YYYY-MM-DD`). Extract the parser into `lib/dates.py` if it hasn't been extracted already — otherwise import from the utility script.
- `--author` resolves via `resolve_assignee` in `lib/client.py` (already handles `me` and account-id vs username ambiguity); filtering compares against `author.accountId`, `author.name`, and `author.displayName`.
- `--limit` is applied **after** filtering. On DC, when the raw payload returns exactly 100 histories, emit a warning regardless of limit:
  ```
  ⚠ DC returned 100 history entries (cap). Results may be truncated.
  ```

### Output

**Default (human table):**

```
PROJ-123 changelog (3 entries)

WHEN              WHO            FIELD       FROM           TO
2026-04-18 09:12  Alice Example  status      In Progress    Done
2026-04-17 14:55  Bob Example    assignee    Alice Example  Bob Example
2026-04-17 14:55  Bob Example    Sprint      Sprint 42      Sprint 43
```

**`--json` (flattened rows, not raw API):**

```json
[
  {
    "created": "2026-04-18T09:12:33.000+0000",
    "author": {"accountId": "...", "name": "aexample", "displayName": "Alice Example"},
    "field": "status",
    "fieldId": "status",
    "from": "10000",
    "to":   "10001",
    "fromString": "In Progress",
    "toString":   "Done"
  }
]
```

Rationale: agents want one row per item, not nested `histories[].items[]`. The fan-out happens once, here.

**`--quiet` (tab-separated, one row per line):**

```
2026-04-18T09:12:33+0000	aexample	status	In Progress	Done
```

## Use cases

```
# 1. Who moved PROJ-123 to Done and when (audit trail)
jira-issue.py changelog PROJ-123 --field status
```
→ One-shot answer to the most common retrospective question.

```
# 2. When did this custom field last change? (debugging sprint loss, etc.)
jira-issue.py changelog PROJ-123 --field customfield_10100   # example custom field id — yours will differ
```
→ Custom fields (sprint, story points, team, …) sometimes drop silently when scope changes; this surfaces the culprit.

```
# 3. Epic link churn — reparenting audit
jira-issue.py changelog PROJ-123 --field "Epic Link" --json
```
→ Feed into a script to detect tickets that hopped epics mid-sprint.

```
# 4. Review a field's change history before handing off to another team
jira-issue.py changelog PROJ-123 --field customfield_10100 --limit 3   # example custom field id — yours will differ
```
→ Verify what the latest value was and who wrote it before transitioning the ticket onward.

```
# 5. All status transitions for a ticket (sprint retro)
jira-issue.py changelog PROJ-123 --field status --since 30d
```
→ Reconstruct the ticket's flow through the board.

```
# 6. Reproduce "who un-assigned me from PROJ-456?"
jira-issue.py changelog PROJ-456 --field assignee --since 14d
```
→ Debug workflow/automation misfires.

```
# 7. Feed external activity/reporting tools
jira-issue.py changelog PROJ-123 --author me --since 7d --json
```
→ JSON rows slot straight into an activity timeline built by an external tool.

## DC vs Cloud differences

| Concern | DC v2 | Cloud v3 |
|---|---|---|
| Endpoint | `GET /rest/api/2/issue/{key}?expand=changelog` — embedded | `GET /rest/api/3/issue/{key}/changelog` — dedicated |
| Pagination | none (hard cap 100) | `startAt` / `maxResults`, default 100, max 1000 |
| Helper in `atlassian-python-api` | `client.issue(key, expand="changelog")` | likely none — fall back to `client.get(...)` |
| Long histories | problematic, silent truncation | designed for it |
| Truncation detection | `len(histories) == 100` heuristic | check `isLast` flag in response |

### Detection

Use `is_cloud` from `lib.config.load_config` (already exposed — check `lib/config.py` to confirm the exact attribute name). Dispatch:

```python
if client.is_cloud:
    histories = _fetch_cloud_changelog(client, key, limit)
else:
    histories = _fetch_dc_changelog(client, key)  # warns if len == 100
```

Both helpers return the same `histories[]` shape so the flatten/filter/format pipeline stays single-path.

## Gotchas

- **Silent 100-entry cap on DC.** Surface a warning on stderr whenever `len(histories) == 100`. Don't raise — the user may genuinely have exactly 100 entries, but the warning prompts them to check the ticket in the browser for the full record.
- **Field name vs id.** The `items[].field` value is sometimes a display name ("Sprint"), sometimes an id ("status"). For `--field` matching, check in order: `fieldId` → lowercased `field` → `"customfield_" + str(fieldSchema.customId)`. Write a `_item_matches_field(item, requested)` helper and unit-test it against both forms.
- **`fromString` / `toString` may be null** when a field was cleared (e.g. assignee removed). Render as `∅` in the human table and leave as JSON `null` in `--json` output. Do not coalesce to empty string — that loses information.
- **Author identity differs between DC and Cloud.** DC has `author.name`, Cloud has `author.accountId`. Reuse the account-id detection already in `lib/client.py` (`resolve_assignee` handles this for writes; factor out the read side if needed). The JSON `author` object keeps whichever keys the API returned.
- **Timezone.** Jira returns `created` in the instance's configured zone with an offset suffix. Display in local time for the table, keep the raw ISO string in JSON.

## Testing

Follow patterns from `tests/test_weblink.py` and `tests/test_link.py`: mock `LazyJiraClient`, feed synthetic payloads, assert on formatter output and flattened JSON rows.

**Fixtures needed:**
- `fixture_changelog_dc_embedded.json` — DC shape: full issue with `changelog.histories` inline, exactly 100 entries (to exercise the truncation warning), plus a small 3-entry variant.
- `fixture_changelog_cloud_paginated.json` — Cloud shape: `{values: [...], isLast: true, maxResults: 100, startAt: 0, total: 42}`, plus a paginated variant (`isLast: false`) to test fetch-all.

**Test cases:**

- `test_changelog_dc_parses_embedded` — basic happy path, DC
- `test_changelog_cloud_paginated_fetches_all_pages` — follows `isLast: false` through two pages
- `test_changelog_dc_warns_on_100_cap` — asserts stderr contains the cap warning
- `test_filter_by_field_matches_fieldId` — `--field status`
- `test_filter_by_field_matches_display_name_case_insensitive` — `--field Sprint` matches `field: "Sprint"`
- `test_filter_by_field_matches_customfield_via_schema` — `--field customfield_10100` matches via `fieldSchema.customId: 10100`
- `test_filter_by_since_until` — date window, including relative form `7d`
- `test_filter_by_author_me` — resolves `me` via `myself()` and matches `accountId`
- `test_filter_by_author_username_dc` — matches `author.name`
- `test_null_from_to_strings_render_as_empty_sentinel` — `fromString: null` → `∅` in text, `null` in JSON
- `test_json_output_is_flattened_rows` — one row per item, not nested histories
- `test_quiet_output_tab_separated` — shape check
- `test_limit_applied_after_filter` — `--field status --limit 2` returns 2 rows even if 50 status items exist

## Out of scope

- **Worklog history** — separate API (`/issue/{key}/worklog`), already covered by `jira-worklog-query.py`.
- **Comment history** — comment edits have their own endpoint; not a priority.
- **Attachment history** — tracked as `Attachment` items in the changelog already; no separate endpoint needed, but no dedicated filter either.
- **Project- or board-level changelog** — no Jira endpoint exposes this; would require crawling many issues.
- **Writing to the changelog** — read-only feature. Jira does not expose write access to history.
- **Bulk changelog across a JQL result set** — DC's `expand=changelog` on search is unreliable; a proper bulk implementation would need per-issue fetches and belongs in an external activity/reporting tool, not this script.
