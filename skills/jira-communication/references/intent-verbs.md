# Intent verbs

`jira-issue.py work / qa / qa-fail / act` — single-call context bundles for the four common intents.

## When to load

Whenever you have a Jira issue key and need more than just meta. Each verb composes the right bundle for one intent. Empirically replaces 3–6 separate calls.

## The four verbs

```bash
jira-issue.py work    KEY   # description + all comments + attachments + links
jira-issue.py qa      KEY   # description + handover bundle (comments around INTO_QA transition)
jira-issue.py qa-fail KEY   # description + reviewer rejection + implementer scope context
jira-issue.py act     KEY   # meta + available transitions
```

`jira-issue.py get KEY` stays minimal (meta only) — backwards compatible.

## QA-handover heuristic (`qa` verb)

The handover comment is *not* always written after the transition. Empirical sample (10 tickets, 41 transitions): 80% of handover comments come **before** the transition click.

The verb finds the most recent INTO_QA transition (by classification, see below) and includes:

1. All comments by the **transition author** in `[T_prev, min(T_next, T_transition + 1h)]` — captures the handover whether written before or after the click. `T_prev` and `T_next` bracket the transition between adjacent status changes.
2. All comments by **any author** in `[T_transition, T_next)` — the QA discussion that follows.

Deduplicated, chronologically sorted. Fallback if no INTO_QA in changelog: last 5 comments + warning.

## QA-fail heuristic (`qa-fail` verb)

Symmetric to `qa`:

1. Find the most recent **REJECT** transition.
2. Include all comments by the **reviewer** (transition author) in `[T_prev_into_qa, T_transition + 1h]`.
3. Include all comments by **any author** in `[T_transition, T_next)`.
4. Include all comments by the **implementer** (= author of the most recent INTO_QA before the reject) in `[T_prev_into_qa - 1h, T_transition]` — this captures the implementer's scope/clarification context that the rejection is reacting to. The 1h backward extension catches handover comments written just before the INTO_QA click.

Fallback if no REJECT in changelog: last 5 comments + warning.

## Status-set classification

Transitions are classified using three configurable status sets:

| Set | Default | Meaning |
|---|---|---|
| `qa_status_names` | `QA, Review, In Review, Code Review, Ready for QA, QA2, UAT, Acceptance, Testing` | Where the work goes for review |
| `working_status_names` | `In Progress, Open, Reopened, To Do, In Development, Backlog, QA failed` | Where rejected work lands. **Note:** `QA failed` is in this set, not `qa`, because it's functionally a reject-target (review verdict: send back to dev), not a review stage. |
| `resolved_status_names` | `Closed, Resolved, Done, Won't Fix, Cancelled` | Terminal states |

A transition is classified as:

- `into_qa` — `from ∉ qa AND to ∈ qa` (handover)
- `reject` — `from ∈ qa AND to ∈ working` (fail)
- `forward` — `from ∈ qa AND to ∈ qa AND from ≠ to` (multi-stage progression: `QA→QA2`, `Review→UAT`, `QA→Acceptance` — **NOT** a fail)
- `resolved` — `to ∈ resolved`
- `out` — `from ∈ qa AND to ∉ qa` (uncategorised QA exit)
- `other` — neither side touches QA

Forward-progression detection is what lets a multi-stage QA workflow (Review → UAT → Acceptance → Closed) work identically to a single-stage one without code changes.

## Configuring status sets per Jira instance

Per profile in `~/.jira/profiles.json`:

```json
{
  "profiles": {
    "myinstance": {
      "url": "https://jira.example.com",
      "token": "...",
      "qa_status_names": ["Review", "UAT", "Acceptance"],
      "working_status_names": ["In Progress", "Backlog", "Reject"],
      "resolved_status_names": ["Done", "Cancelled"]
    }
  }
}
```

Or via env vars (comma-separated):

```bash
JIRA_QA_STATUS_NAMES="Review,UAT,Acceptance"
JIRA_WORKING_STATUS_NAMES="In Progress,Backlog,Reject"
JIRA_RESOLVED_STATUS_NAMES="Done,Cancelled"
```

## Output formats

All verbs support the standard global flags:

- (default) Human-readable text bundle
- `--json` Structured payload (`comments` is always a list of comment dicts; verb-specific keys like `reject_transition`, `handover_transition`, `implementer` for context)
- `--quiet` Issue key only (after successful fetch — validates connectivity)

Each verb also has `--truncate N` to cap description and per-comment body length.

## Example: NRS-4412-style QA-fail follow-up

The motivating case: "what did Björn reject, and what was Sebastian's scope context?"

Before (6 calls): `jira-issue get`, `jira-comment list`, `jira-comment list | tail`, `jira-comment list | head`, etc.

After (1 call):

```bash
jira-issue.py qa-fail NRS-4412
```

Returns: description + Sebastian's scope-setting handover comment + Björn's full AC review with rejection + Sebastian's response + subsequent resolution. Chronologically sorted, ready to read.
