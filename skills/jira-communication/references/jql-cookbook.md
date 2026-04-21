# JQL Cookbook — Translating Natural-Language Queries

How to turn questions like *"all my open bugs with no activity in 2 weeks"*
into safe, portable JQL — and which built-in scripts help with the fuzzy
parts (status names, usernames, board names).

This doc complements `jql-quick-reference.md`, which covers JQL *syntax*.
This one covers *reasoning*: which JQL expression is safe for which
natural-language term, and what to do when the user's phrasing is
ambiguous.

---

## Fuzzy term → safe JQL

| User says… | Safe JQL | Notes |
|---|---|---|
| "open" / "not done" | `statusCategory != Done` | **Prefer `statusCategory` over enumerating statuses** — workflow-agnostic. |
| "done" / "closed" | `statusCategory = Done` | Same reason. |
| "in progress" (generic) | `statusCategory = "In Progress"` | The *category* name, not a status name. |
| "not started" | `statusCategory = "To Do"` | Covers "Open", "To Do", "Reopened" across workflows. |
| "unresolved" | `resolution is EMPTY` | Orthogonal to status; some workflows close issues without setting resolution. |
| "my" / "mine" | `assignee = currentUser()` | Use `reporter = currentUser()` for *"I reported"*, `watcher = currentUser()` for *"I'm watching"*. |
| "no activity in N days" | `updated < -Nd` | `updated` covers any field change. |
| "stale in status" | See **"stale" section** below | `updated` is *not* sufficient — transitions can be older than last edit. |
| "recently updated" | `updated >= -7d` | Ask which "recent" means if unsure. |
| "recently created" | `created >= -7d` | Different from "updated"! |
| "urgent" | `priority in (Highest, High)` | Priority names are instance-configurable; verify with `jira-fields.py`. |
| "bug" | `issuetype = Bug` | ⚠️ Localized instances may use "Fehler" / "Defect". Enumerate issuetypes to verify. |
| "blocked" | **ambiguous** — see "blocked" section | Could be status, "Flagged" field, or `is blocked by` link. |
| "current sprint" | `sprint in openSprints()` | Requires Jira Software (Agile). |
| "backlog" | `sprint is EMPTY` | In Agile projects. |
| "due this week" | `duedate >= startOfWeek() AND duedate <= endOfWeek()` | `startOfWeek()` / `endOfWeek()` are JQL functions. |

---

## Status ambiguity — the #1 gotcha

Jira distinguishes **status** (workflow-specific) from **statusCategory**
(instance-wide). The three categories are always:

- `"To Do"` — issues not started
- `"In Progress"` — issues actively being worked
- `Done` — finished issues

**Rule of thumb: prefer `statusCategory` over `status` whenever the user's
wording is a category-level concept** ("open", "done", "active").

| Natural phrasing | Wrong (brittle) | Right (portable) |
|---|---|---|
| "open issues" | `status in (Open, "To Do", Reopened)` | `statusCategory != Done` |
| "finished issues" | `status = Closed` | `statusCategory = Done` |
| "anything actively being worked on" | `status = "In Progress"` | `statusCategory = "In Progress"` |

Reach for a specific `status = "X"` only when the user names a concrete
workflow step ("Code Review", "Staging Tested", "Awaiting QA").

---

## "Blocked" — three distinct meanings

| Meaning | JQL |
|---|---|
| Status called "Blocked" | `status = Blocked` (workflow-dependent) |
| Jira Agile "Flagged" field | `"Flagged" is not EMPTY` |
| Has an incoming `is blocked by` link | `issueFunction in hasLinks("is blocked by")` (ScriptRunner) |

When the user says *"what's blocked?"* without more context, start with
the **Flagged** interpretation on Agile projects, and confirm the intent.

---

## "Stale" — update vs. transition

If the user says *"issues stale in Review for >14 days"*, plain
`updated < -14d` is **not right** — a comment or description edit also
updates `updated`. Two options:

1. **Approximation (pure JQL):** `status = Review AND updated < -14d` —
   catches most cases, but misses issues that had recent edits while
   still stuck in Review.
2. **Exact (needs changelog):** use
   `jira-issue time-in-status <KEY> --status Review` on each
   candidate to get the true per-status duration.

Document the limitation when presenting the result.

---

## Resolution helpers — point the user here

Most fuzzy terms can be resolved *before* building JQL:

| What to resolve | Helper |
|---|---|
| Status name ("review" → "In Review") | `lib.client.resolve_status(client, "review")` — case-insensitive, substring, errors on ambiguity. |
| Username / display name ("John" → accountId / username) | `lib.client.resolve_assignee(client, "John")` or `jira-user.py search "John"`. |
| Custom field name ("Epic Link" → `customfield_10014`) | `jira-fields.py search "Epic Link"`. |
| Board by name | `jira-board.py list --name "Lithium"` (server-side partial match). |
| Issue type canonical name | `jira-fields.py types PROJ` (per-project types incl. localized names). |
| Priority / resolution list | `GET /rest/api/2/priority`, `GET /rest/api/2/resolution` (use `atlassian-python-api`'s generic `.get()`). |

When a resolver returns an ambiguous result, **surface the candidates**
and ask the user — don't silently pick the first match.

---

## Worked example 1: *"all bug issues open for more than 2 weeks"*

**Step 1 — parse the terms:**
- "bug" → `issuetype = Bug` (⚠️ verify per instance)
- "open" → `statusCategory != Done`
- "for more than 2 weeks" → **ambiguous**; three interpretations:
  - **A**: no activity for 14+ days → `updated < -14d`
  - **B**: existed 14+ days → `created < -14d`
  - **C**: stuck in current status 14+ days → needs `time-in-status`,
    not pure JQL

**Step 2 — pick the most common interpretation:** A.

**Step 3 — assemble:**

```text
issuetype = Bug AND statusCategory != Done AND updated < -14d
```

**Step 4 — surface the assumption:**

> "I interpreted '2 weeks open' as *'no activity for 14+ days'*.
> If you meant *created 14+ days ago* or *stuck in one status for 14+
> days*, say so and I'll rerun."

---

## Worked example 2: *"all my issues with no activity past 2 weeks"*

- "my" → `assignee = currentUser()`
- "no activity" → `updated`
- "past 2 weeks" → `< -14d`

```text
assignee = currentUser() AND updated < -14d
```

No resolvers needed. No ambiguity worth surfacing.

---

## Worked example 3: *"how long has PROJ-123 been in Review?"*

Not a JQL question — use the changelog:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/core/jira-issue.py \
    time-in-status PROJ-123 --status review
```

`--status review` resolves via `resolve_status()`; matches "In Review"
or "Code Review" unambiguously on most instances.

---

## Ambiguity protocol

When translating, Claude should:

1. **Translate unambiguous mappings directly** — "my" → `currentUser()`,
   "open" → `statusCategory != Done`.
2. **Resolve instance-specific terms before building JQL** — run
   `resolve_status` / `jira-user search` when the term names a status or
   person.
3. **Pick a sensible default for vague time terms** — "recently" → 7d,
   "stale" → 14d, "long-standing" → 30d — and **state the assumption in
   the response**.
4. **On resolver ambiguity, ask** — never silently pick the first match.
   Surface the candidates.
5. **When no pure-JQL expression is accurate, say so** — e.g., *"stale
   in Review"* strictly needs `time-in-status`; JQL alone is an
   approximation.

---

## What's deliberately not here

- **Hardcoded per-workflow shortcuts** like `status = "Code Review"`.
  Status names vary per instance. Resolve first.
- **Saved-query templates.** Users who want named saved JQLs can use
  Jira's built-in Filters (web UI) — they're reusable across this skill
  and Jira itself.
- **Priority / resolution name lists.** These are instance-configurable;
  fetch them at runtime via the REST API.
