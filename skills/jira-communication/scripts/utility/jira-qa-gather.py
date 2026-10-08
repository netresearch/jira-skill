#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Single-call QA discovery: fetch everything a reviewer needs in one shot.

Aggregates issue + description + comments + worklog + structured issue links +
web/remote links + URLs extracted from prose (MR/PR/pipeline/commit/tag/release)
+ sibling tickets + a self-review check (does the changelog or worklog name the
reviewer as implementer?), so a QA reviewer (or QA-assistant skill) can read
context without making 5+ separate API calls. The description and every comment body
are printed in full (same rendering as ``jira-issue.py work``); ``--no-body``
keeps the metadata-only shape.

Designed for the peer-qa-review skill but useful for any review workflow.
"""

import re
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click
from lib.changelog import classify_transition, extract_status_transitions_with_authors, last_into_qa_index
from lib.client import LazyJiraClient, _sanitize_error, fetch_comments_paginated
from lib.config import load_status_sets
from lib.jql import jql_escape
from lib.output import error, extract_adf_text, format_output, warning
from lib.render import print_comment, print_description

# ═══════════════════════════════════════════════════════════════════════════════
# URL patterns reviewers care about (extracted from description + comments)
# ═══════════════════════════════════════════════════════════════════════════════

URL_PATTERNS: dict[str, re.Pattern[str]] = {
    "merge_request": re.compile(r"https?://[^\s\"'|\]]+/-/merge_requests/\d+"),
    "pull_request": re.compile(r"https?://github\.com/[^\s\"'|\]]+/pull/\d+"),
    "pipeline": re.compile(r"https?://[^\s\"'|\]]+/-/pipelines/\d+"),
    "commit": re.compile(r"https?://[^\s\"'|\]]+/-/commit/[a-f0-9]{7,}"),
    "tag": re.compile(r"https?://[^\s\"'|\]]+/-/tags/[^\s\"'|\]]+"),
    "release": re.compile(r"https?://github\.com/[^\s\"'|\]]+/releases/[^\s\"'|\]]+"),
    "issue_link": re.compile(r"https?://[^/\s]+/browse/[A-Z][A-Z0-9_]+-\d+"),
}


def _extract_urls(text: str) -> dict[str, list[str]]:
    """Pull review-relevant URLs out of a free-text blob.

    Returns a dict of category -> deduplicated, order-preserved URL list.
    """
    out: dict[str, list[str]] = {}
    if not text:
        return out
    for category, pattern in URL_PATTERNS.items():
        seen: list[str] = []
        for match in pattern.findall(text):
            if match not in seen:
                seen.append(match)
        if seen:
            out[category] = seen
    return out


def _merge_url_dicts(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    """Merge URL extraction results, preserving order and de-duping."""
    for category, urls in source.items():
        bucket = target.setdefault(category, [])
        for url in urls:
            if url not in bucket:
                bucket.append(url)


def _summary_keywords(summary: str) -> list[str]:
    """Pick token-like substrings from an issue summary for sibling search.

    Heuristic: keep tokens longer than 3 chars and not in a small stop-list.
    Used to find sibling tickets mentioning the same component/version.
    Deduplication is case-insensitive (so 'Jira' and 'jira' don't both pass).
    """
    stop = {
        "from",
        "with",
        "into",
        "this",
        "that",
        "fixes",
        "fix",
        "update",
        "upgrade",
        "remove",
        "create",
        "build",
        "implement",
        "support",
        "issue",
        "ticket",
        "task",
        "and",
        "the",
        "for",
    }
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9._-]{3,}", summary):
        token = raw.lower()
        if token in stop or token in seen:
            continue
        seen.add(token)
        tokens.append(raw)
    return tokens[:5]


def _comment_text(comment: dict) -> str:
    """Get plain text from a comment, handling both ADF and Server/DC formats."""
    body = comment.get("body", "")
    if isinstance(body, dict):
        return extract_adf_text(body) or ""
    return str(body or "")


def _person_key(person) -> str:
    """Stable user identifier: Server/DC ``name`` or Cloud ``accountId``."""
    if not isinstance(person, dict):
        return ""
    for field in ("name", "accountId"):
        value = person.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def _person_label(person) -> str | None:
    key = _person_key(person)
    if not key:
        return None
    display = person.get("displayName")
    return f"{display} ({key})" if isinstance(display, str) and display else key


def _author_key(transition: dict | None) -> str | None:
    return (transition or {}).get("author_key") or None


def _in_progress_transitions(
    transitions: list[dict], qa: set, status_categories: dict[str, str] | None
) -> tuple[list[dict], bool]:
    """Every move into an "indeterminate" (in progress) status, and whether the list is complete.

    Moves into or out of a QA status are skipped: a QA reject back to In Progress
    is the reviewer's verdict, not implementation work. The second value is
    ``False`` when the list may miss moves: the categories could not be read,
    or a move went to a status id they do not list (a deleted status), whose
    category is unknown. The moves into listed statuses are still returned, so
    a match among them still counts.
    """
    if status_categories is None:
        return [], False
    moves = [t for t in transitions if t["from"] not in qa and t["to"] not in qa]
    complete = all(t["to_id"] in status_categories for t in moves)
    return [t for t in moves if status_categories.get(t["to_id"]) == "indeterminate"], complete


def _authors(transitions: list[dict]) -> list[str]:
    """Distinct non-empty author keys, in changelog order."""
    return list(dict.fromkeys(t["author_key"] for t in transitions if t["author_key"]))


def _worklog_authors(worklogs: list[dict] | None) -> list[str] | None:
    if worklogs is None:
        return None
    return sorted({_person_key(w.get("author")) for w in worklogs} - {""})


def _changelog_hits(reviewer: str, events: list[dict], latest: str, earlier: str) -> list[tuple[str, dict]]:
    """The reviewer's own events, named ``latest`` for the newest one and ``earlier`` otherwise."""
    return [(latest if t is events[-1] else earlier, t) for t in events if t["author_key"] == reviewer]


def _reviewer_matches(
    reviewer: str | None,
    handovers: list[dict],
    worklog_authors: list[str] | None,
    in_progress: list[dict],
) -> tuple[list[str], list[dict]]:
    """Names of the signals that point at the reviewer, and the changelog events behind them.

    Every round counts, not only the latest: a reviewer who implemented an
    earlier round that QA rejected is still reviewing their own work.
    """
    if not reviewer:
        return [], []
    hits = _changelog_hits(reviewer, handovers, "implementer", "earlier_handover")
    in_progress_hits = _changelog_hits(reviewer, in_progress, "in_progress_by", "earlier_in_progress")
    worklog = ["worklog_author"] if worklog_authors and reviewer in worklog_authors else []
    names = list(dict.fromkeys([n for n, _ in hits] + worklog + [n for n, _ in in_progress_hits]))
    events = [
        {"signal": n, "created": t["created"].isoformat(), "from": t["from"], "to": t["to"]}
        for n, t in hits + in_progress_hits
    ]
    return names, events


def _unread_signals(readable: dict[str, bool]) -> list[str]:
    """Names of the inputs that could not be read, in the order given."""
    return [name for name, ok in readable.items() if not ok]


def _changelog_truncated(issue: dict) -> bool:
    """True when the embedded changelog holds fewer entries than its ``total``."""
    changelog = issue.get("changelog") or {}
    total = changelog.get("total")
    return isinstance(total, int) and total > len(changelog.get("histories") or [])


def _self_review_verdict(matched: list[str], handover: dict | None, unread: list[str]) -> tuple[str, str]:
    if matched:
        return "self", "reviewer matches " + ", ".join(matched)
    if handover is None:
        return "unknown", "no transition into a QA status in the changelog"
    if unread:
        return "unknown", "could not read: " + ", ".join(unread)
    return "other", "reviewer matches no implementation signal"


def compute_self_review(
    issue: dict,
    worklogs: list[dict] | None,
    reviewer: str | None,
    status_sets: dict,
    status_categories: dict[str, str] | None,
    worklog_complete: bool = True,
) -> dict:
    """Decide whether the reviewer would be reviewing their own work.

    The current assignee cannot answer this: workflows that unassign on the
    move into QA leave every QA ticket "Unassigned". The changelog and the
    worklog still name who did the work.

    ``worklogs`` / ``reviewer`` / ``status_categories`` are ``None`` when the
    corresponding fetch failed; ``worklog_complete`` is ``False`` when the
    worklog response holds fewer entries than its ``total``. A signal that
    could not be read never counts as "not you": a non-match is ``unknown``,
    not ``other``, when any input is missing, the changelog or the worklog is
    incomplete, the latest handover has no author, or a move went to a status
    the categories do not list.
    """
    fields = issue.get("fields") or {}
    transitions = extract_status_transitions_with_authors(issue)
    handovers = [t for t in transitions if classify_transition(t, status_sets) == "into_qa"]
    # The latest handover, shown as the implementer: the same one the `qa` verb names.
    idx = last_into_qa_index(transitions, status_sets)
    handover = transitions[idx] if idx is not None else None
    in_progress, categories_known = _in_progress_transitions(transitions, status_sets["qa"], status_categories)
    worklog_authors = _worklog_authors(worklogs)

    implementer = _author_key(handover)
    in_progress_by = _author_key(in_progress[-1] if in_progress else None)
    matched, matched_events = _reviewer_matches(reviewer, handovers, worklog_authors, in_progress)
    unread = _unread_signals(
        {
            "reviewer": bool(reviewer),
            "worklog": worklogs is not None,
            "worklog (incomplete)": worklog_complete,
            "status categories": categories_known,
            "changelog (truncated)": not _changelog_truncated(issue),
            "implementer (handover has no author)": handover is None or bool(implementer),
        }
    )
    verdict, reason = _self_review_verdict(matched, handover, unread)

    resolution = fields.get("resolution")
    return {
        "verdict": verdict,
        "reason": reason,
        "matched": matched,
        "matched_events": matched_events,
        "reviewer": reviewer or None,
        "implementer": implementer,
        "implementer_display": (handover or {}).get("author_name") or None,
        "handover": None
        if handover is None
        else {"created": handover["created"].isoformat(), "from": handover["from"], "to": handover["to"]},
        "handover_authors": _authors(handovers),
        "in_progress_by": in_progress_by,
        "in_progress_authors": _authors(in_progress),
        "in_progress_complete": categories_known,
        "worklog_authors": worklog_authors,
        "worklog_empty": None if worklogs is None else not worklogs,
        "resolution": resolution.get("name") if isinstance(resolution, dict) else None,
        # Information only: opening a ticket is not implementing it.
        "creator": _person_label(fields.get("creator")),
        "reporter": _person_label(fields.get("reporter")),
    }


def _worklog_empty_label(empty: bool | None) -> str:
    if empty is None:
        return "unknown"
    return "yes" if empty else "no"


def _print_self_review(sr: dict) -> None:
    print(f"\nSelf-review check: {sr['verdict']} ({sr['reason']})")
    if sr["verdict"] == "self":
        print(
            f"  WARNING: you ({sr['reviewer']}) would be reviewing your own work - matched: {', '.join(sr['matched'])}"
        )
        for e in sr["matched_events"]:
            print(f"    {e['signal']}: {e['created']} ({e['from']} → {e['to']})")
    handover = sr["handover"]
    if handover:
        print(
            f"  Implementer (moved into QA): {sr['implementer_display'] or '?'} ({sr['implementer'] or '?'}) "
            f"at {handover['created']} ({handover['from']} → {handover['to']})"
        )
    else:
        print("  Implementer (moved into QA): not found")
    print(f"  Reviewer (you): {sr['reviewer'] or 'unknown'}")
    print(f"  Handover authors (all rounds): {', '.join(sr['handover_authors']) or 'none'}")
    partial = "" if sr["in_progress_complete"] else " (incomplete: status categories not readable)"
    print(f"  In progress by: {sr['in_progress_by'] or 'none found'}{partial}")
    print(f"  In progress authors (all rounds): {', '.join(sr['in_progress_authors']) or 'none'}{partial}")
    authors = sr["worklog_authors"]
    print(f"  Worklog authors: {'not readable' if authors is None else ', '.join(authors) or 'none'}")
    print(f"  Creator / reporter (information only): {sr['creator'] or '-'} / {sr['reporter'] or '-'}")
    print(f"  Resolution: {sr['resolution'] or 'none'} | Worklog empty: {_worklog_empty_label(sr['worklog_empty'])}")


def _safe_message(exc: Exception) -> str:
    """Render an exception message with credentials/tokens redacted.

    Mirrors the sanitization done by client.py for connection errors.
    """
    return _sanitize_error(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.argument("issue_key")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Issue key only (after successful fetch)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.option("--no-siblings", is_flag=True, help="Skip sibling-ticket search")
@click.option(
    "--no-body",
    is_flag=True,
    help="Metadata only: omit the description and comment bodies from the text output",
)
@click.option(
    "--sibling-window",
    type=click.IntRange(min=1),
    default=60,
    show_default=True,
    metavar="DAYS",
    help="Sibling search window",
)
@click.option(
    "--max-siblings",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    metavar="N",
    help="Max sibling tickets to return",
)
def cli(
    issue_key: str,
    output_json: bool,
    quiet: bool,
    env_file: str | None,
    profile: str | None,
    debug: bool,
    no_siblings: bool,
    no_body: bool,
    sibling_window: int,
    max_siblings: int,
):
    """Gather everything a QA reviewer needs about an issue in one call.

    Returns issue + description + all comments (chronological, with author and
    date, rendered like `jira-issue.py work`) + worklog + structured issue links
    + web/remote links + URLs extracted from prose (MR/PR/pipeline/commit/tag/
    release) + sibling tickets in the same project + a self-review check that
    compares you with everyone who moved the ticket into QA or to In Progress,
    in any round, or logged work on it. No second call is needed to
    read the ticket text; --no-body restores the metadata-only output.

    ISSUE_KEY: Jira issue key (e.g., NRS-4365)

    Examples:

      jira-qa-gather.py NRS-4365

      jira-qa-gather.py NRS-4365 --no-body

      jira-qa-gather.py NRS-4365 --json
    """
    client = LazyJiraClient(env_file=env_file, profile=profile)
    client.with_context(issue_key=issue_key)

    bundle: dict = {"issue_key": issue_key}

    try:
        issue = client.issue(issue_key, expand="renderedFields,changelog")
        bundle["issue"] = issue
    except Exception as exc:
        if debug:
            raise
        error(f"Failed to fetch issue: {_safe_message(exc)}")
        sys.exit(1)

    # --quiet: minimal output AFTER a successful fetch (matches jira-issue.py
    # behaviour). Validates connectivity/permissions/existence before printing.
    if quiet:
        print(issue_key)
        return

    fields = issue.get("fields", {}) or {}
    summary = fields.get("summary", "") or ""
    project_key = (fields.get("project") or {}).get("key", "") or issue_key.split("-")[0]
    status = (fields.get("status") or {}).get("name", "")
    # The assignee says whether a QA ticket is claimed (`None` = unclaimed team
    # queue). It does NOT say who implemented it — workflows that unassign on
    # the move into QA blank it — so the self-review check below reads the
    # changelog and the worklog instead.
    assignee_field = fields.get("assignee") or {}
    assignee_name = assignee_field.get("name") or assignee_field.get("accountId") or ""
    assignee_display = assignee_field.get("displayName") or ""
    description = fields.get("description", "") or ""
    if isinstance(description, dict):
        description_text = extract_adf_text(description) or ""
    else:
        description_text = str(description)

    bundle["description"] = fields.get("description")

    # Comments — the embedded block on the issue payload is capped by Jira
    # (50 on Server/DC), so paginate like `jira-issue.py work` does and fall
    # back to the embedded block only if that call fails.
    comment_block = fields.get("comment") or {}
    comments: list[dict] = comment_block.get("comments", []) or []
    try:
        comments, _ = fetch_comments_paginated(client, issue_key)
    except Exception as exc:
        if debug:
            raise
        warning(f"Failed to page through comments, using the embedded block: {_safe_message(exc)}")
    bundle["comments"] = comments

    # Worklog
    worklogs: list[dict] = []
    worklog_read = False
    worklog_complete = True
    try:
        worklog_block = client.issue_get_worklog(issue_key) or {}
        worklogs = worklog_block.get("worklogs", []) or []
        # Only a response that carries a worklog list says who logged work; an
        # empty body or an error object must not read as "nobody did".
        worklog_read = isinstance(worklog_block.get("worklogs"), list)
        worklog_total = worklog_block.get("total")
        worklog_complete = not (isinstance(worklog_total, int) and worklog_total > len(worklogs))
    except Exception as exc:
        if debug:
            raise
        warning(f"Failed to fetch worklog: {_safe_message(exc)}")
    bundle["worklogs"] = worklogs
    bundle["worklog_total_seconds"] = sum(int(w.get("timeSpentSeconds") or 0) for w in worklogs)

    # Self-review inputs: who is asking, and which statuses are "In Progress".
    reviewer: str | None = None
    try:
        reviewer = _person_key(client.myself()) or None
    except Exception as exc:
        if debug:
            raise
        warning(f"Failed to read the authenticated user: {_safe_message(exc)}")
    status_categories: dict[str, str] | None = None
    try:
        statuses = client.get_all_statuses()
        if isinstance(statuses, list):
            # A status without a category key stays out of the map, so a move
            # into it reads as "category unknown", not as "not In Progress".
            status_categories = {
                str(s.get("id")): (s.get("statusCategory") or {}).get("key")
                for s in statuses
                if isinstance(s, dict) and (s.get("statusCategory") or {}).get("key")
            }
    except Exception as exc:
        if debug:
            raise
        warning(f"Failed to fetch status categories: {_safe_message(exc)}")
    bundle["self_review"] = compute_self_review(
        issue,
        worklogs if worklog_read else None,
        reviewer,
        load_status_sets(profile=profile, issue_key=issue_key),
        status_categories,
        worklog_complete,
    )

    bundle["assignee"] = assignee_name or None
    bundle["assignee_display"] = assignee_display or None

    # Structured issue links + web/remote links
    bundle["issue_links"] = fields.get("issuelinks", []) or []
    web_links: list[dict] = []
    try:
        web_links = client.get_issue_remote_links(issue_key) or []
    except Exception as exc:
        if debug:
            raise
        warning(f"Failed to fetch web links: {_safe_message(exc)}")
    bundle["web_links"] = web_links

    # Extracted URLs from description + every comment
    extracted: dict[str, list[str]] = {}
    _merge_url_dicts(extracted, _extract_urls(description_text))
    for comment in comments:
        _merge_url_dicts(extracted, _extract_urls(_comment_text(comment)))
    bundle["extracted_urls"] = extracted

    # Sibling tickets — same project, recently active (resolved OR still open),
    # with summary keyword overlap. "updated" rather than "resolved" so open
    # sibling work is included (often the most relevant for QA).
    siblings: list[dict] = []
    if not no_siblings and summary:
        keywords = _summary_keywords(summary)
        if keywords:
            kw_clause = " OR ".join(f'summary ~ "{jql_escape(k)}"' for k in keywords)
            jql = (
                f'project = "{jql_escape(project_key)}" AND key != "{jql_escape(issue_key)}" '
                f"AND ({kw_clause}) AND updated >= -{sibling_window}d "
                f"ORDER BY updated DESC"
            )
            try:
                results = client.jql(jql, limit=max_siblings, fields="summary,status,resolutiondate,updated")
                siblings = results.get("issues", []) if isinstance(results, dict) else []
            except Exception as exc:
                if debug:
                    raise
                warning(f"Sibling search failed: {_safe_message(exc)}")
    bundle["siblings"] = siblings

    if output_json:
        format_output(bundle, as_json=True)
        return

    # Human-readable summary
    print(f"{issue_key}: {summary}")
    assignee_label = f"{assignee_display} ({assignee_name})" if assignee_name else "Unassigned"
    print(
        f"Status: {status} | Assignee: {assignee_label} | Comments: {len(comments)} | "
        f"Worklog entries: {len(worklogs)} "
        f"({bundle['worklog_total_seconds'] // 60} min total)"
    )
    _print_self_review(bundle["self_review"])

    if not no_body:
        print_description(issue)

    # Printed unconditionally: "none" is a finding (an unlinked related ticket
    # is a QA check in its own right), whereas an omitted section reads as
    # "not checked" and invites the reader to assume links exist.
    if bundle["issue_links"]:
        print(f"\nIssue links ({len(bundle['issue_links'])}):")
        for link in bundle["issue_links"]:
            link_type = (link.get("type") or {}).get("name", "?")
            other = link.get("outwardIssue") or link.get("inwardIssue") or {}
            other_key = other.get("key", "?")
            other_summary = ((other.get("fields") or {}).get("summary") or "").strip()
            direction = "→" if "outwardIssue" in link else "←"
            print(f"  {link_type} {direction} {other_key}: {other_summary}")
    else:
        print("\nIssue links: none")

    if web_links:
        print(f"\nWeb/remote links ({len(web_links)}):")
        for wl in web_links:
            obj = wl.get("object") or {}
            print(f"  - {obj.get('title', '?')}: {obj.get('url', '?')}")
    else:
        print("\nWeb/remote links: none")

    if extracted:
        print("\nURLs extracted from description + comments:")
        for category, urls in extracted.items():
            print(f"  [{category}] ({len(urls)})")
            for url in urls:
                print(f"    {url}")

    if siblings:
        print(f"\nSibling tickets in {project_key} (last {sibling_window}d):")
        for sib in siblings:
            sf = sib.get("fields") or {}
            print(f"  {sib.get('key', '?')}: [{(sf.get('status') or {}).get('name', '?')}] {sf.get('summary', '')}")

    if not extracted and not siblings and not web_links:
        print("\n(no review-relevant URLs, web links, or sibling tickets found)")

    if comments and not no_body:
        print("\n" + "=" * 60)
        print(f"COMMENTS ({len(comments)} total — chronological)")
        print("=" * 60)
        for c in comments:
            print_comment(c)
        print()


if __name__ == "__main__":
    cli()
