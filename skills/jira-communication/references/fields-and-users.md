# Fields and Users — Reference Data Lookup

## When to load

Load this reference whenever the user needs to: look up a custom field ID, list issue types for a project, search for a Jira user, or resolve a username/accountId for use as a reporter, assignee, or watcher value.

## Users

```bash
# Resolve a specific identifier — prints the canonical record
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py get john.doe

# Free-text search (by display name or email fragment)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py search "doreen"

# The current authenticated user (what `--assignee me` resolves to)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-user.py me
```

Useful when `--assignee`, `--reporter`, or `--user` rejects a value: search returns the canonical username (Server/DC) or accountId (Cloud) the API expects.

**`[~mention]` in comments needs the canonical username, not a guess.** The mention token resolves on the account's `name`/`key` — which can differ from **both** the display name and the email local-part (renamed accounts are common: e.g. display "Jane Doe", email `jane.doe@…`, but `name=jane.smith` after a rename). Guessing from the display name or email silently produces a non-notifying mention. Every posting command (`jira-comment add/edit`, `jira-transition do --comment`, `jira-worklog add --comment`, the `--description` of `jira-create`/`jira-issue update`) therefore verifies each `[~username]` at post time and aborts with suggestions on a miss (`--no-verify-mentions` skips). For ticket participants no lookup is needed at all: `jira-issue get/work`, `jira-comment list` and `jira-worklog list` print the technical identifier in parentheses next to each display name (Server/DC username, or `accountid:<id>` on Cloud) — copy it into the mention. For anyone else, `jira-user.py search "<display name>"` resolves it. If someone says "your mention pinged the wrong/no user", this is why. (Jira **Cloud** uses `[~accountId:<accountId>]` instead of `[~username]`; resolve the `accountId` the same way and use that form.)

## Assignee — assign and unassign

```bash
# Assign to a user (or to self)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --assignee john.doe
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --assignee me

# Unassign — clear the assignee (no dedicated flag; use the field directly)
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py update PROJ-123 --fields-json '{"assignee": null}'
```

There is no `--unassign` flag: `--assignee` only *sets* a value. To clear the
assignee, pass `{"assignee": null}` via `--fields-json` (works on Server/DC). On
some instances a `null` assignment can revert to a project default rather than
"Unassigned" — verify with `uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py get PROJ-123`
afterwards (look for `Assignee: Unassigned`).

## Custom fields

```bash
# Search field metadata by name fragment
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py search "sprint"
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py search "epic"

# Dump all fields as JSON (for grep/jq pipelines)
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py --json search ""
```

The key you need for `--fields-json` is the `id` (e.g. `customfield_<N>`) — not the human name.

## Issue types per project

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py types PROJ
```

Prints every issue type the project accepts, including sub-task types. Issue type names are **case-sensitive** on create (`jira-create.py --type`).

## Common custom-field shapes (IDs vary per instance)

| Field | Type | Notes |
|---|---|---|
| Sprint | integer | Sprint ID, not name |
| Epic Link | string | Epic issue key, e.g. `"PROJ-1940"` |
| UAT / Test instructions | text | QA hand-off notes |

Always confirm the `id` with `jira-fields.py search` on the target instance — custom-field numbering is not portable.

## Confirm the TYPE before you read the value

The `id` tells you which field to ask for; it does not tell you what comes back. A
field whose name reads like a number often is not one, and the mismatch surfaces as a
`TypeError` in the caller rather than as a Jira error:

```bash
# schema.type for one field — the half that decides how to parse the value
uv run ${CLAUDE_SKILL_DIR}/scripts/utility/jira-fields.py --json search "budget" \
  | jq -r '.[] | "\(.id)\t\(.schema.type // "—")\t\(.schema.items // "-")\t\(.name)"'
```

What the common types actually deliver in `fields`:

| `schema.type` | Value shape | Reading it |
|---|---|---|
| `number` | `3958.51` | `float(v)` |
| `string` | `"Q3/2026"` | as is |
| `option` | `{"self":…,"value":"> 25.000 EUR","id":"10026"}` | `v["value"]` — **never** `float(v)` |
| `array` | list of whatever `schema.items` names | iterate, then read each element by its `items` type — `labels` is `items=string`, a multi-select is `items=option` |
| `user` | Server/DC: `{"name":…,"key":…,"displayName":…}` · Cloud: `{"accountId":…,"displayName":…}` | `v["name"]` on Server/DC, `v["accountId"]` on Cloud — this skill targets Server/DC |
| `account` (Tempo) | `{"id":…,"key":…,"name":…}` on read | asymmetric: writing takes the **account id** as a bare string (`"208"`), and the key or name is rejected with `Account id 'null' is invalid` |

The case that motivates this: a field called `Vertrieb: Budget` on jira.netresearch.de
turned out to be an `option` with three size brackets rather than an amount. Reading it
with `float()` raised `TypeError` and killed the collector that held it — and because
no issue in the queried set carried a value at first, it shipped and waited. A single
`schema.type` lookup before the first read costs one call.

Corollary: a field that is empty everywhere you looked is not evidence of its type.
Query one issue that actually has a value (`"<Field>" is not EMPTY`) and look at the
raw JSON.

## Jira Server config reads: three access tiers — "no REST to SET" does not mean "no way to READ"

For scheme assignments, mail handlers, components, categories on Jira Server, try in order:

1. **REST with PAT** — workflow/notification/permission/issue-type schemes + associations, components, versions, watchers, role actors, category, lead (`/rest/api/2/project/<KEY>/<resource>`, `/rest/api/2/<scheme>/<id>/associations`).
2. **Project-level admin HTML with PAT** — screen scheme, issue type screen scheme, anything on `/plugins/servlet/project-config/<KEY>/…`; scheme names are extractable from the returned HTML.
3. **Site-level admin HTML** (`/secure/admin/…`) — WebSudo-gated: PAT alone gets a 200 with `<title>Administrator Access…</title>` and a password form. Genuinely needs a human. **Detection rule:** a body containing "Administrator Access" means you hit WebSudo, not the data — never trust byte count alone.

Only declare "manual UI check needed" after tiers 1 AND 2 both failed.
