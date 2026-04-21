# Watchers CRUD Design

**Date:** 2026-04-20
**Status:** Draft

## Goal

Add a `jira-watchers.py` script to list, add, and remove watchers on Jira issues. Watchers are currently not exposed anywhere in the skill, so users cannot self-subscribe to issues transitioned to review, attach a stakeholder to tickets with new UAT instructions, or un-watch noisy epics in bulk without leaving the CLI.

## Jira API

Watchers are a per-issue collection with a single REST path and three verbs. Reference: <https://docs.atlassian.com/software/jira/docs/api/REST/9.12.0/#api/2/issue-getIssueWatchers>.

- `GET /rest/api/2/issue/{key}/watchers` — list watchers
  - Returns `{"self": ..., "isWatching": bool, "watchCount": int, "watchers": [{...}]}`
  - Requires **View Voters and Watchers** on the project (plus **Browse Projects**).

- `POST /rest/api/2/issue/{key}/watchers` — add a watcher
  - Body is a **raw JSON string**, not a JSON object: `"jdoe"` on DC, `"557058:..."` on Cloud (quotes included, `Content-Type: application/json`).
  - Adding yourself requires only **Browse Projects**; adding someone else requires **Manage Watchers**.
  - Returns `204 No Content` on success.

- `DELETE /rest/api/2/issue/{key}/watchers?username=jdoe` (DC) or `?accountId=557058:...` (Cloud)
  - Removing yourself requires only **Browse Projects**; removing someone else requires **Manage Watchers**.
  - Returns `204 No Content` on success.

The `atlassian-python-api` library exposes all three (verified in 3.41.x):

- `issue_get_watchers(issue_key)` — `GET`
- `issue_add_watcher(issue_key, user)` — `POST`, passes `user` through as the raw body
- `issue_delete_watcher(issue_key, user=None, account_id=None)` — `DELETE`, picks query-param based on `client.cloud`

No fallback to `client.post/get/delete` is needed.

## New Script: `jira-watchers.py`

Location: `skills/jira-communication/scripts/utility/jira-watchers.py`

Follows existing conventions: PEP 723 header, Click group, `LazyJiraClient`, `lib.output` helpers, `--json` / `--quiet` / `--env-file` / `--profile` / `--debug` group options.

User identity is resolved through a small `_resolve_watcher_identifier(client, identifier)` helper that reuses `resolve_assignee()` from `lib/client.py`:

- `me` → `client.myself()` → `{"accountId": ...}` or `{"name": ...}`
- account-id-shaped string → `{"accountId": ...}` (via `is_account_id()`)
- anything else → `user_find_by_user_string(query=...)`, pick first hit

The add/delete calls need a flat string, not the dict that `resolve_assignee()` returns, so the helper unwraps it:

```python
def _resolve_watcher_identifier(client, identifier: str) -> tuple[str, bool]:
    """Return (value, is_account_id) suitable for issue_add_watcher / issue_delete_watcher."""
    resolved = resolve_assignee(client, identifier)
    if "accountId" in resolved:
        return resolved["accountId"], True
    return resolved["name"], False
```

## Subcommands

### `list ISSUE_KEY`

List watchers on an issue.

```
$ jira-watchers list PROJ-123
Watchers for PROJ-123 (3):

  jdoe           John Doe              (isWatching)
  asmith         Alice Smith
  bwilson        Bob Wilson            (isWatching = you)
```

JSON output: the raw API response (`{"watchCount": 3, "isWatching": true, "watchers": [...]}`).
Quiet output: one `username` (DC) or `accountId` (Cloud) per line.

### `add ISSUE_KEY [--user me|USER]`

Subscribe a user (default: yourself) to an issue. Idempotent — Jira silently accepts duplicate self-adds.

```
$ jira-watchers add PROJ-123
✓ Added watcher to PROJ-123: bwilson (you)

$ jira-watchers add PROJ-123 --user asmith
✓ Added watcher to PROJ-123: asmith
```

JSON output: `{"key": "PROJ-123", "user": "asmith", "added": true}`.

### `remove ISSUE_KEY [--user me|USER] [--dry-run]`

Unsubscribe a user (default: yourself). Supports `--dry-run` (writes are destructive per house rules).

```
$ jira-watchers remove PROJ-123
✓ Removed watcher from PROJ-123: bwilson (you)

$ jira-watchers remove PROJ-123 --user asmith --dry-run
⚠ DRY RUN - No watcher will be removed
Would remove asmith from PROJ-123
```

JSON output: `{"key": "PROJ-123", "user": "asmith", "removed": true}`.

## Use Cases

```bash
# Subscribe yourself when taking over a ticket
jira-watchers add PROJ-123
```
Stay in the loop on comments after picking up work.

```bash
# Subscribe a stakeholder when moving an issue to review
jira-watchers add PROJ-123 --user product.owner
```
The stakeholder gets notified about the review without a separate `@mention`.

```bash
# Subscribe QA when transitioning to QA
jira-watchers add PROJ-456 --user qa.lead
```
Useful as a follow-up to a transition when handing over to QA.

```bash
# Un-watch a noisy epic
jira-watchers remove PROJ-789
```
Shortcut for "stop notifying me about this epic" without opening the web UI.

```bash
# Bulk-watch all children of an epic (no bulk endpoint — loop JQL)
jira-search.py query '"Epic Link" = PROJ-789' --json \
  | jq -r '.issues[].key' \
  | xargs -I{} jira-watchers add {}
```
There is no `POST /watchers/bulk`, so loop client-side.

```bash
# After leaving a sprint mid-flight, re-watch only the ones still open
jira-search.py query 'sprint = 42 AND assignee was currentUser() AND resolution = Unresolved' --json \
  | jq -r '.issues[].key' \
  | xargs -I{} jira-watchers add {}
```
Keeps you informed about the handover without claiming them again.

## DC vs Cloud Differences

| Concern | Server / DC | Cloud |
|---|---|---|
| User identity | `username` (e.g. `jdoe`) | `accountId` (e.g. `557058:d5765ebc-...`) |
| `POST` body | `"jdoe"` (JSON string) | `"557058:..."` (JSON string) |
| `DELETE` query param | `?username=jdoe` | `?accountId=557058:...` |
| `client.cloud` flag | `False` | `True` — drives `issue_delete_watcher`'s param choice |

Identity resolution leans on existing helpers in `skills/jira-communication/scripts/lib/client.py`:

- `is_account_id(s)` — distinguishes Cloud account IDs (new-style `557058:...` and legacy 24-char hex) from usernames.
- `resolve_assignee(client, identifier)` — the canonical flow used by `jira-create.py` / `jira-issue.py`; we reuse it so `me`, `asmith`, `alice.smith@example.com`, and raw account IDs all resolve the same way they do elsewhere.

Because `issue_add_watcher` uses the same raw-body format on both deployments, one code path handles both — the resolved string simply differs.

## Gotchas

- **POST body is a raw JSON-encoded string, not an object.** `{"name": "jdoe"}` returns `400`. `atlassian-python-api` handles this correctly (it passes `data=user` straight through), but any fallback to `client.post(...)` must do the same — pass the username/accountId as a bare string and let the library JSON-encode it.
- **Success is `204 No Content`**, so the add/remove responses have no body. Do not try to parse JSON from the return value of `issue_add_watcher` / `issue_delete_watcher`.
- **Self-watch is idempotent.** Adding yourself when you are already watching returns `204`, not an error. The script should treat repeated adds as success (no special handling needed).
- **No bulk watcher endpoint exists.** For multi-issue operations, loop over a JQL result set (see the epic-children example above). Do not build a bulk wrapper inside the script — keep the shell pipeline idiomatic.
- **Removing a watcher who is not watching** returns `404` on DC and `404` on Cloud. Surface this as a clear error; do not silently succeed.
- **Cloud email lookup is deprecated.** `user_find_by_user_string(query=email)` still works but may return `[]` for privacy-protected accounts — fall back to asking for an accountId.

## Testing

Follow the patterns in `tests/test_weblink.py` and `tests/test_link.py`: Click `CliRunner` with `obj={"client": MagicMock(...)}`, no real network.

Cases to add in `tests/test_watchers.py`:

- `list` — watchers present: renders header, count, display names, `isWatching` marker.
- `list` — empty watcher list: prints `No watchers for {key}`.
- `list --json` — returns the raw API payload unchanged.
- `add` default — resolves `me` via `client.myself()`, calls `issue_add_watcher` with the unwrapped identifier.
- `add --user asmith` — calls `user_find_by_user_string`, then `issue_add_watcher` with `"asmith"`.
- `add --user 557058:abc...` — account-id-shaped input skips search and is passed through.
- `remove` default + DC — calls `issue_delete_watcher(user="bwilson")`.
- `remove` default + Cloud — calls `issue_delete_watcher(account_id="557058:...")` (gate on `client.cloud`).
- `remove --dry-run` — prints the warning, does not call `issue_delete_watcher`.
- `remove` against a non-watcher — 404 surfaces as a clean error, exit code 1.
- Quiet mode on `add` / `remove` prints `ok`; JSON mode emits the documented payload.

## Out of Scope

- Bulk watcher endpoint wrappers (no such API — use shell loops).
- Adding a watcher section to `jira-issue.py get` (separate API call, noisy by default; reconsider later).
- Vote operations — same REST neighborhood but a distinct feature; track separately.
- Watcher subscriptions based on JQL saved filters (Jira-side feature, not API-exposed).
- Slack / email notification routing — orthogonal to Jira watchers.
- Changes to `lib/client.py` or `lib/output.py` (existing helpers sufficient).
- Changes to `plugin.json` (no new dependencies).
