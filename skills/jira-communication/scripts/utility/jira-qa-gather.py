#!/usr/bin/env -S uv run --script
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
+ sibling tickets, so a QA reviewer (or QA-assistant skill) can read context
without making 5+ separate API calls. The description and every comment body
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
from lib.client import LazyJiraClient, _sanitize_error, fetch_comments_paginated
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
    release) + sibling tickets in the same project. No second call is needed to
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
        issue = client.issue(issue_key, expand="renderedFields")
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
    # Reviewers decide whether to claim a QA ticket by comparing the current
    # assignee against themselves, so the bundle has to carry it. `None` is a
    # meaningful value here (unclaimed team queue), not a missing one.
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
    try:
        worklog_block = client.issue_get_worklog(issue_key) or {}
        worklogs = worklog_block.get("worklogs", []) or []
    except Exception as exc:
        if debug:
            raise
        warning(f"Failed to fetch worklog: {_safe_message(exc)}")
    bundle["worklogs"] = worklogs
    bundle["worklog_total_seconds"] = sum(int(w.get("timeSpentSeconds") or 0) for w in worklogs)

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
