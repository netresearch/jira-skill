#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira issue operations - get, update, and delete issue details."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click
from lib.changelog import (
    classify_transition,
    compute_time_in_status,
    extract_status_transitions,
    extract_status_transitions_with_authors,
    find_transition_window,
    format_timedelta,
    parse_jira_datetime,
)
from lib.client import LazyJiraClient, _sanitize_error, fetch_comments_paginated, resolve_assignee, resolve_status
from lib.config import load_status_sets
from lib.input import read_stdin_utf8
from lib.output import comment_to_text, compact_json, error, extract_adf_text, format_output, success, warning


def _expand_label_args(raw: tuple[str, ...]) -> list[str]:
    """Split repeatable CLI args on commas and strip whitespace."""
    out: list[str] = []
    for entry in raw:
        if not entry:
            continue
        for part in entry.split(","):
            cleaned = part.strip()
            if cleaned:
                out.append(cleaned)
    return out


def _labels_after_add_remove(existing: list[str], add: list[str], remove: list[str]) -> list[str]:
    """Merge labels case-insensitively while preserving first-seen casing from Jira."""
    by_lower: dict[str, str] = {}
    for lab in existing:
        if not lab:
            continue
        low = lab.casefold()
        if low not in by_lower:
            by_lower[low] = lab

    for lab in add:
        low = lab.casefold()
        if low not in by_lower:
            by_lower[low] = lab

    remove_lower = {lab.casefold() for lab in remove}
    for low in remove_lower:
        by_lower.pop(low, None)

    return sorted(by_lower.values(), key=str.casefold)


def _reference_label(ref) -> str:
    """Human-readable label for an issuetype/project reference dict."""
    if not isinstance(ref, dict):
        return str(ref)
    return str(ref.get("name") or ref.get("key") or ref.get("id") or ref)


def _reference_mismatch(requested, actual) -> tuple[str, str] | None:
    """Compare a requested issuetype/project reference against the re-fetched value.

    ``requested`` is whatever the caller put in the update payload — e.g.
    ``{"id": "7"}``, ``{"name": "Sub: Bug"}`` or ``{"key": "ABC"}``.
    ``actual`` is the field as returned by a fresh ``client.issue(...)`` read.

    Returns ``None`` when the change is verified (or cannot be meaningfully
    checked), or an ``(requested_label, actual_label)`` tuple on mismatch.

    Why: Jira's ``PUT /issue/{key}`` silently ignores some issuetype/project
    changes on Server/DC, returning success while leaving the field untouched
    (#115). We compare on whichever identifier the caller supplied (id / key /
    name) so the check works regardless of how the reference was expressed.
    """
    if not isinstance(requested, dict) or not isinstance(actual, dict):
        return None  # unrecognized shape — don't raise a false alarm
    for attr in ("id", "key", "name"):
        if attr not in requested:
            continue
        got = actual.get(attr)
        if got is None:
            continue  # this identifier isn't exposed in the refreshed value
        want = str(requested[attr])
        got = str(got)
        # Jira canonicalizes project keys to uppercase and resolves issue-type
        # names case-insensitively, so a caller-supplied lowercase value can be
        # applied correctly yet come back in different casing. Compare key/name
        # case-insensitively; only the opaque numeric id is matched exactly.
        applied = got == want if attr == "id" else got.casefold() == want.casefold()
        if not applied:
            return (_reference_label(requested), _reference_label(actual))
        return None  # matched on the supplied identifier — change applied
    return None  # nothing comparable


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira issue operations.

    Get, update, and delete Jira issue details.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command()
@click.argument("issue_key")
@click.option("--fields", "-f", help="Comma-separated fields to return")
@click.option("--expand", "-e", help="Fields to expand (changelog,transitions,renderedFields)")
@click.option("--truncate", type=int, metavar="N", help="Truncate description to N characters")
@click.option("--full", is_flag=True, help="[DEPRECATED] Show full content (now default behavior)")
@click.option(
    "--raw",
    is_flag=True,
    help=(
        "With --json: preserve every key on the Jira response (including null "
        "customfields). Without --raw, null/empty fields are stripped. In either "
        "case an extra `webLinks` key is added by this script from a separate "
        "remote-links API call."
    ),
)
@click.pass_context
def get(
    ctx,
    issue_key: str,
    fields: str | None,
    expand: str | None,
    truncate: int | None,
    full: bool,
    raw: bool,
):
    """Get issue details.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue get PROJ-123

      jira-issue get PROJ-123 --fields summary,status,assignee

      jira-issue get PROJ-123 --expand changelog,transitions

      jira-issue --json get PROJ-123         # compact JSON (null/empty stripped)

      jira-issue --json get PROJ-123 --raw   # full Jira payload, incl. null customfields
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    # Warn about deprecated --full flag
    if full:
        warning("--full is deprecated (full content is now shown by default). Use --truncate N to limit output.")

    try:
        # Normalize requested fields once — used for both fetch gating and display
        parsed = [f.strip() for f in fields.split(",") if f.strip()] if fields else []
        requested = set(parsed) if parsed else None

        # Build parameters — strip our pseudo-field "weblinks" before sending to Jira
        params = {}
        if parsed:
            api_fields = ",".join(f for f in parsed if f != "weblinks")
            if api_fields:
                params["fields"] = api_fields
        if expand:
            params["expand"] = expand

        issue = client.issue(issue_key, **params)

        # Fetch web links (separate API call, not a field on the issue)
        # Skip if --quiet or if --fields was given without "weblinks"
        web_links = []
        if not ctx.obj["quiet"] and (requested is None or "weblinks" in requested):
            try:
                web_links = client.get_issue_remote_links(issue_key)
            except Exception:
                if ctx.obj["debug"]:
                    raise
                warning("Failed to fetch web links")
                web_links = []

        if ctx.obj["json"]:
            issue["webLinks"] = web_links
            payload = issue if raw else compact_json(issue)
            format_output(payload, as_json=True)
        elif ctx.obj["quiet"]:
            print(issue["key"])
        else:
            _print_issue(issue, truncate=truncate, requested_fields=requested, web_links=web_links)

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get issue {issue_key}: {e}")
        sys.exit(1)


def _print_issue(
    issue: dict,
    truncate: int | None = None,
    requested_fields: set | None = None,
    web_links: list | None = None,
) -> None:
    """Pretty print issue details.

    Args:
        issue: The issue dict from Jira API
        truncate: If set, truncate description to this many characters
        requested_fields: Pre-parsed set of field names to display (None = show all)
        web_links: List of remote link dicts from a separate API call
    """
    fields = issue.get("fields", {})
    # Accept both set and comma-separated string for backwards compatibility
    if isinstance(requested_fields, str):
        requested = set(f.strip() for f in requested_fields.split(","))
    else:
        requested = requested_fields

    def should_show(field_name: str) -> bool:
        """Check if a field should be shown based on requested fields."""
        if requested is None:
            return True
        return field_name in requested

    def field_available(field_name: str) -> bool:
        """Check if a field was returned by the API."""
        return field_name in fields

    # Header with summary
    if should_show("summary") or requested is None:
        summary = fields.get("summary", "No summary") if field_available("summary") else "[not requested]"
        print(f"\n{issue['key']}: {summary}")
        print("=" * 60)
    else:
        print(f"\n{issue['key']}")
        print("=" * 60)

    # Status, type, priority row - only show if any were requested or no filter
    show_status_row = requested is None or any(f in requested for f in ["status", "issuetype", "priority"])
    if show_status_row:
        parts = []
        if should_show("issuetype") and field_available("issuetype"):
            issue_type = fields.get("issuetype", {}).get("name", "Unknown")
            parts.append(f"Type: {issue_type}")
        if should_show("status") and field_available("status"):
            status = fields.get("status", {}).get("name", "Unknown")
            parts.append(f"Status: {status}")
        if should_show("priority") and field_available("priority"):
            priority = fields.get("priority", {}).get("name", "None") if fields.get("priority") else "None"
            parts.append(f"Priority: {priority}")
        if parts:
            print(" | ".join(parts))

    # Assignee and reporter row
    show_people_row = requested is None or any(f in requested for f in ["assignee", "reporter"])
    if show_people_row:
        parts = []
        if should_show("assignee") and field_available("assignee"):
            assignee = fields.get("assignee", {})
            assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
            parts.append(f"Assignee: {assignee_name}")
        if should_show("reporter") and field_available("reporter"):
            reporter = fields.get("reporter", {})
            reporter_name = reporter.get("displayName", "Unknown") if reporter else "Unknown"
            parts.append(f"Reporter: {reporter_name}")
        if parts:
            print(" | ".join(parts))

    # Labels
    if should_show("labels") and field_available("labels"):
        labels = fields.get("labels", [])
        if labels:
            print(f"Labels: {', '.join(labels)}")

    # Description
    if should_show("description") and field_available("description"):
        description = fields.get("description")
        if description:
            print("\nDescription:")
            # Handle both string and ADF format
            if isinstance(description, str):
                desc_text = description
            elif isinstance(description, dict):
                # ADF format - extract text content
                desc_text = extract_adf_text(description)
            else:
                desc_text = str(description)

            # Truncate if requested
            if truncate and len(desc_text) > truncate:
                # Find word boundary for clean truncation
                truncated = desc_text[:truncate].rsplit(" ", 1)[0]
                print(f"  {truncated}...")
                print(f"  [truncated at {truncate} chars]")
            else:
                # Print full description, preserving line breaks
                for line in desc_text.split("\n"):
                    print(f"  {line}")

    # Dates
    show_dates_row = requested is None or any(f in requested for f in ["created", "updated"])
    if show_dates_row:
        parts = []
        if should_show("created") and field_available("created"):
            created = fields.get("created", "")[:10] if fields.get("created") else "N/A"
            parts.append(f"Created: {created}")
        if should_show("updated") and field_available("updated"):
            updated = fields.get("updated", "")[:10] if fields.get("updated") else "N/A"
            parts.append(f"Updated: {updated}")
        if parts:
            print(f"\n{' | '.join(parts)}")

    # Attachments
    if should_show("attachment") and field_available("attachment"):
        attachments = fields.get("attachment", [])
        if attachments:
            print("\n" + "=" * 60)
            print("ATTACHMENTS")
            print("=" * 60)
            for att in attachments:
                filename = att.get("filename", "Unknown")
                url = att.get("content", "")
                print(f"  • {filename} - {url}")

    # Issue Links
    if should_show("issuelinks") and field_available("issuelinks"):
        issue_links = fields.get("issuelinks", [])
        if issue_links:
            print("\n" + "=" * 60)
            print("ISSUE LINKS")
            print("=" * 60)
            for link in issue_links:
                link_type = link.get("type", {})
                if "outwardIssue" in link:
                    outward = link["outwardIssue"]
                    label = link_type.get("outward", "links to")
                    key = outward.get("key", "?")
                    summary = outward.get("fields", {}).get("summary", "")
                    print(f"  {label} \u2192 {key}: {summary}")
                if "inwardIssue" in link:
                    inward = link["inwardIssue"]
                    label = link_type.get("inward", "is linked by")
                    key = inward.get("key", "?")
                    summary = inward.get("fields", {}).get("summary", "")
                    print(f"  {label} \u2190 {key}: {summary}")

    # Web Links (from separate API call, gated by --fields like issue links)
    if web_links and should_show("weblinks"):
        print("\n" + "=" * 60)
        print("WEB LINKS")
        print("=" * 60)
        for link in web_links:
            link_id = link.get("id", "?")
            obj = link.get("object", {})
            title = obj.get("title", "(untitled)")
            link_url = obj.get("url", "")
            print(f"  [{link_id}] {title} \u2014 {link_url}")

    # Comments \u2014 always surface the count when the comment field is present, so a
    # populated discussion is never invisible (the original silent `-f comment` trap).
    # Full bodies stay in the `work` command / `jira-comment.py list`.
    if field_available("comment"):
        comment_field = fields.get("comment") or {}
        # Jira may send total/comments as explicit null, so guard against None
        # rather than relying on dict.get defaults (a present-but-null key skips them).
        comment_total = comment_field.get("total")
        if comment_total is None:
            comment_total = len(comment_field.get("comments") or [])
        if comment_total:
            print(
                f"\nComments: {comment_total} "
                f"(run `jira-issue.py work {issue['key']}` or `jira-comment.py list {issue['key']}` to read them)"
            )
        else:
            print("\nComments: 0")

    # Parent \u2014 cheap, high-value metadata; same silent-omission gap as comments.
    if field_available("parent"):
        parent = fields.get("parent") or {}
        parent_key = parent.get("key")
        if parent_key:
            parent_summary = (parent.get("fields") or {}).get("summary", "")
            print(f"\nParent: {parent_key}" + (f": {parent_summary}" if parent_summary else ""))

    # Subtasks \u2014 list compactly (keys are short); closes the silent `-f subtasks` gap.
    if field_available("subtasks"):
        subtasks = fields.get("subtasks") or []
        if subtasks:
            print(f"\nSubtasks ({len(subtasks)}):")
            for subtask in subtasks:
                subtask_fields = subtask.get("fields") or {}
                subtask_status = (subtask_fields.get("status") or {}).get("name", "")
                suffix = f" [{subtask_status}]" if subtask_status else ""
                print(f"  \u2022 {subtask.get('key', '?')}: {subtask_fields.get('summary') or ''}{suffix}")

    # Safety net: never let an explicitly requested field render nothing silently.
    # Any -f field that reached the payload but has no renderer above gets a
    # one-line pointer instead of vanishing (the core correctness fix).
    if requested is not None:
        rendered_fields = {
            "summary",
            "issuetype",
            "status",
            "priority",
            "assignee",
            "reporter",
            "labels",
            "description",
            "created",
            "updated",
            "attachment",
            "issuelinks",
            "weblinks",
            "comment",
            "parent",
            "subtasks",
        }
        for field_name in sorted(requested):
            if field_name not in rendered_fields and field_available(field_name):
                print(f"\n{field_name}: present in the response but not rendered here, use `--json` to view it")

    print()


@cli.command("time-in-status")
@click.argument("issue_key")
@click.option(
    "--status",
    "-s",
    "status_filter",
    help="Show only time spent in this status (resolved via resolve_status)",
)
@click.pass_context
def time_in_status_cmd(ctx, issue_key: str, status_filter: str | None):
    """Show how long an issue has spent in each status.

    Fetches the changelog and computes cumulative duration per status.
    If the issue has re-entered a status, durations are summed.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue time-in-status PROJ-123

      jira-issue time-in-status PROJ-123 --status Review

      jira-issue --json time-in-status PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        issue = client.issue(issue_key, expand="changelog")
        fields = issue.get("fields", {})
        current_status = (fields.get("status") or {}).get("name", "")
        created_raw = fields.get("created", "")
        if not created_raw:
            error(f"Issue {issue_key} has no 'created' timestamp")
            sys.exit(1)

        transitions = extract_status_transitions(issue)
        issue_created = parse_jira_datetime(created_raw)
        now = datetime.now(timezone.utc)

        per_status = compute_time_in_status(issue_created, transitions, current_status, now)

        # Optionally filter to a single status (with resolution)
        resolved_status = None
        if status_filter:
            try:
                resolved_status = resolve_status(client, status_filter)
            except ValueError as e:
                error(str(e))
                sys.exit(1)

        if ctx.obj["json"]:
            # Prefer the canonical key from the fetched issue over the user-supplied
            # identifier (callers may pass an issue ID; Jira returns the key).
            payload = {
                "key": issue.get("key", issue_key),
                "current_status": current_status,
                "time_in_status": {name: int(delta.total_seconds()) for name, delta in per_status.items()},
            }
            if resolved_status is not None:
                payload["filter_status"] = resolved_status
                payload["filter_seconds"] = int(per_status.get(resolved_status, timedelta(0)).total_seconds())
            format_output(payload, as_json=True)
            return

        if ctx.obj["quiet"]:
            if resolved_status is not None:
                delta = per_status.get(resolved_status)
                print(format_timedelta(delta) if delta else "0m")
            else:
                print(current_status)
            return

        summary = fields.get("summary", "")
        print(f"\n{issue_key}: {summary}")
        print("=" * 60)
        if resolved_status is not None:
            delta = per_status.get(resolved_status)
            duration = format_timedelta(delta) if delta else "0m"
            marker = " (current)" if resolved_status == current_status else ""
            print(f'In "{resolved_status}"{marker}: {duration}')
            print()
            return

        # Show all statuses, ordered by first appearance in the timeline
        order = _status_order(current_status, transitions)
        width = max((len(s) for s in per_status), default=0)
        print("Time in status:")
        for name in order:
            if name not in per_status:
                continue
            marker = "  ← current" if name == current_status else ""
            print(f"  {name.ljust(width)}  {format_timedelta(per_status[name])}{marker}")
        print()

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to compute time-in-status for {issue_key}: {e}")
        sys.exit(1)


def _status_order(current_status: str, transitions: list) -> list[str]:
    """Return statuses in the order they first appear on the timeline."""
    seen: list[str] = []
    if transitions:
        first_from = transitions[0].get("from") or current_status
        if first_from and first_from not in seen:
            seen.append(first_from)
        for t in transitions:
            to = t.get("to")
            if to and to not in seen:
                seen.append(to)
    if current_status and current_status not in seen:
        seen.append(current_status)
    return seen


@cli.command()
@click.argument("issue_key")
@click.option("--summary", "-s", help="New summary")
@click.option("--description", "-d", help="New description (Jira wiki markup; '-' reads from stdin)")
@click.option("--priority", "-p", help="Priority name")
@click.option("--labels", "-l", help="Comma-separated labels (replaces existing)")
@click.option(
    "--add-label",
    multiple=True,
    help="Add label(s); repeatable and comma-separated (case-insensitive dedupe)",
)
@click.option(
    "--remove-label",
    multiple=True,
    help="Remove label(s); repeatable and comma-separated (matches case-insensitively)",
)
@click.option("--assignee", "-a", help="Assignee username or email")
@click.option("--fields-json", help="JSON string of additional fields to update")
@click.option("--dry-run", is_flag=True, help="Show what would be updated without making changes")
@click.pass_context
def update(
    ctx,
    issue_key: str,
    summary: str | None,
    description: str | None,
    priority: str | None,
    labels: str | None,
    add_label: tuple[str, ...],
    remove_label: tuple[str, ...],
    assignee: str | None,
    fields_json: str | None,
    dry_run: bool,
):
    """Update issue fields.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue update PROJ-123 --summary "New title"

      jira-issue update PROJ-123 --description "$(cat body.txt)"

      jira-issue update PROJ-123 --description -            # read from stdin

      jira-issue update PROJ-123 --priority High --labels backend,urgent

      jira-issue update PROJ-123 --fields-json '{"customfield_10001": "value"}'

      jira-issue update PROJ-123 --summary "Test" --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    # Build update payload
    update_fields = {}

    if summary:
        update_fields["summary"] = summary

    if description is not None:
        if description == "-":
            if sys.stdin.isatty():
                error(
                    "'-' requires piped input but stdin is a terminal",
                    suggestion="Usage: cat body.txt | jira-issue update PROJ-123 --description -",
                )
                sys.exit(1)
            max_size = 256 * 1024  # 256KB, above Jira's description limit
            try:
                description = read_stdin_utf8(max_size + 1)
            except UnicodeDecodeError:
                error(
                    "stdin contains invalid text encoding (expected UTF-8)",
                    suggestion="Ensure the piped file is valid UTF-8 text, not binary data.",
                )
                sys.exit(1)
            if len(description) > max_size:
                error(
                    f"description from stdin exceeds {max_size} bytes",
                    suggestion="Truncate the input or split the description across multiple updates.",
                )
                sys.exit(1)
            description = description.rstrip("\n")
        update_fields["description"] = description

    if priority:
        update_fields["priority"] = {"name": priority}

    if labels and (add_label or remove_label):
        error("Do not combine --labels with --add-label/--remove-label (choose replace or incremental update).")
        sys.exit(1)

    if labels:
        update_fields["labels"] = [l.strip() for l in labels.split(",")]

    if add_label or remove_label:
        issue = client.issue(issue_key, fields="labels")
        existing = (issue.get("fields") or {}).get("labels") or []
        add_clean = _expand_label_args(add_label)
        remove_clean = _expand_label_args(remove_label)
        update_fields["labels"] = _labels_after_add_remove(list(existing), add_clean, remove_clean)

    if assignee:
        update_fields["assignee"] = resolve_assignee(client, assignee)

    if fields_json:
        try:
            extra_fields = json.loads(fields_json)
            update_fields.update(extra_fields)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in --fields-json: {e}")
            sys.exit(1)

    if not update_fields:
        error("No fields specified for update")
        click.echo(
            "\nUse one or more of: --summary, --description, --priority, --labels, "
            "--add-label, --remove-label, --assignee, --fields-json"
        )
        sys.exit(1)

    if dry_run:
        warning("DRY RUN - No changes will be made")
        print(f"\nWould update {issue_key} with:")
        for key, value in update_fields.items():
            print(f"  {key}: {value}")
        return

    try:
        client.update_issue_field(issue_key, update_fields)

        # Read-after-write verification (#115). update_issue_field returns
        # without error even when Jira's PUT /issue/{key} endpoint silently
        # ignores the change — which it does for issuetype and project on
        # Server/DC. Re-fetch those fields and compare against what we asked
        # for, mirroring the defensive check in jira-move.py, so we never
        # report a false-positive success.
        verify_fields = [f for f in ("issuetype", "project") if f in update_fields]
        if verify_fields:
            refreshed = client.issue(issue_key, fields=",".join(verify_fields))
            refreshed_fields = refreshed.get("fields") or {}
            for field in verify_fields:
                mismatch = _reference_mismatch(update_fields[field], refreshed_fields.get(field))
                if not mismatch:
                    continue
                requested_label, actual_label = mismatch
                if field == "issuetype":
                    error(
                        f"issuetype change was not applied: issue is still '{actual_label}' "
                        f"(requested '{requested_label}')",
                        suggestion=(
                            "Jira's edit endpoint silently ignores some issue-type changes "
                            "(notably between Sub-Task types). Use 'jira-move issue' for type "
                            "changes, or change it via the Jira UI's Move action."
                        ),
                    )
                else:
                    error(
                        f"project change was not applied: issue is still in '{actual_label}' "
                        f"(requested '{requested_label}')",
                        suggestion=(
                            "Moving an issue between projects is not supported via the edit "
                            "endpoint. Use the Jira UI's Move action."
                        ),
                    )
                sys.exit(1)

        if ctx.obj["quiet"]:
            print(issue_key)
        elif ctx.obj["json"]:
            format_output({"key": issue_key, "updated": list(update_fields.keys())}, as_json=True)
        else:
            success(f"Updated {issue_key}")
            for key in update_fields:
                print(f"  ✓ {key}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to update {issue_key}: {e}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.option("--delete-subtasks", is_flag=True, help="Also delete subtasks of the issue")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without making changes")
@click.pass_context
def delete(ctx, issue_key: str, delete_subtasks: bool, dry_run: bool):
    """Delete an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Requires delete permission in the Jira project. Use --dry-run to preview.

    Examples:

      jira-issue delete PROJ-123

      jira-issue delete PROJ-123 --dry-run

      jira-issue delete PROJ-123 --delete-subtasks
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Fetch issue summary for confirmation output
        issue = client.issue(issue_key, fields="summary,subtasks")
        summary = issue.get("fields", {}).get("summary", "No summary")
        subtasks = issue.get("fields", {}).get("subtasks", [])

        if dry_run:
            warning("DRY RUN - No issue will be deleted")
            print(f"\nWould delete {issue_key}: {summary}")
            if subtasks:
                print(f"\n  Subtasks ({len(subtasks)}):")
                for st in subtasks:
                    st_summary = st.get("fields", {}).get("summary", "No summary")
                    print(f"    {st['key']}: {st_summary}")
                if not delete_subtasks:
                    warning("Subtasks exist. Use --delete-subtasks to delete them too, or deletion will fail.")
            return

        client.delete_issue(issue_key, delete_subtasks=delete_subtasks)

        if ctx.obj["quiet"]:
            print("ok")
        elif ctx.obj["json"]:
            format_output({"key": issue_key, "deleted": True, "subtasks_deleted": delete_subtasks}, as_json=True)
        else:
            success(f"Deleted {issue_key}: {summary}")
            if subtasks and delete_subtasks:
                print(f"  Also deleted {len(subtasks)} subtask(s)")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# Intent verbs: work / qa / qa-fail / act
#
# Each verb is a single-call composition that returns the *minimal* bundle a
# user actually needs for one specific intent — instead of forcing them to
# stitch together `get` + `comment list` + `transition list` themselves.
# ═══════════════════════════════════════════════════════════════════════════════

# Note: ``comment`` is intentionally NOT in INTENT_FIELDS — Jira returns only
# the first 50 comments in the embedded payload. The intent verbs fetch
# comments separately via fetch_comments_paginated() to avoid silently
# truncating long-running tickets.
INTENT_FIELDS = (
    "summary,status,assignee,reporter,priority,issuetype,description,attachment,issuelinks,labels,created,updated"
)


def _author_matches(author: dict, key: str, name: str) -> bool:
    """True if a comment/transition author matches by Server name or Cloud accountId."""
    if not author:
        return False
    a_key = author.get("name") or author.get("accountId") or ""
    a_name = author.get("displayName", "")
    return bool((key and a_key == key) or (name and a_name == name))


def _comments_in_range(comments: list, start, end, author_filter: tuple[str, str] | None = None) -> list:
    """Filter comments by ``start <= created < end`` (half-open), optionally by author key+name.

    The end bound is exclusive so a comment created exactly at the next status
    transition is attributed to the next QA window, not the current one.
    """
    out = []
    for c in comments:
        try:
            created = parse_jira_datetime(c.get("created", ""))
        except (ValueError, TypeError):
            continue
        if start is not None and created < start:
            continue
        if end is not None and created >= end:
            continue
        if author_filter is not None:
            if not _author_matches(c.get("author") or {}, *author_filter):
                continue
        out.append(c)
    return out


def _dedupe_comments(comments: list) -> list:
    """Deduplicate by comment ID, returning chronological order."""
    seen: set[str] = set()
    out: list = []
    for c in comments:
        cid = c.get("id", "")
        if cid in seen:
            continue
        seen.add(cid)
        out.append(c)
    return sorted(out, key=lambda c: c.get("created", ""))


def _collect_handover_bundle(issue: dict, comments: list, status_sets: dict) -> dict:
    """Compose the qa (handover) bundle. See PLAN-context-fetch-optimization.md."""
    transitions = extract_status_transitions_with_authors(issue)

    into_qa_indices = [i for i, t in enumerate(transitions) if classify_transition(t, status_sets) == "into_qa"]
    if not into_qa_indices:
        return {"fallback": True, "comments": comments[-5:], "transition": None}

    target_idx = into_qa_indices[-1]
    target = transitions[target_idx]
    t_transition = target["created"]
    t_prev, t_next = find_transition_window(transitions, target_idx)
    one_hour = timedelta(hours=1)
    end_for_author = (t_transition + one_hour) if t_next is None else min(t_next, t_transition + one_hour)

    handover = _comments_in_range(
        comments, t_prev, end_for_author, author_filter=(target["author_key"], target["author_name"])
    )
    after = _comments_in_range(comments, t_transition, t_next)
    return {
        "fallback": False,
        "comments": _dedupe_comments(handover + after),
        "transition": target,
    }


def _collect_reject_bundle(issue: dict, comments: list, status_sets: dict) -> dict:
    """Compose the qa-fail (reject) bundle. See PLAN-context-fetch-optimization.md."""
    transitions = extract_status_transitions_with_authors(issue)

    reject_indices = [i for i, t in enumerate(transitions) if classify_transition(t, status_sets) == "reject"]
    if not reject_indices:
        return {"fallback": True, "comments": comments[-5:], "transition": None}

    target_idx = reject_indices[-1]
    target = transitions[target_idx]
    t_transition = target["created"]
    _, t_next = find_transition_window(transitions, target_idx)

    # Most recent INTO_QA before the reject = QA window start + implementer identity.
    implementer = None
    t_prev_into_qa = None
    for i in range(target_idx - 1, -1, -1):
        if classify_transition(transitions[i], status_sets) == "into_qa":
            t_prev_into_qa = transitions[i]["created"]
            implementer = (transitions[i]["author_key"], transitions[i]["author_name"])
            break

    one_hour = timedelta(hours=1)
    reviewer_filter = (target["author_key"], target["author_name"])
    reviewer_comments = _comments_in_range(
        comments, t_prev_into_qa, t_transition + one_hour, author_filter=reviewer_filter
    )
    after = _comments_in_range(comments, t_transition, t_next)
    impl_comments = []
    if implementer is not None:
        # Extend back -1h to catch handover comments written just before the
        # INTO_QA click (empirically 80% of handover comments precede the click).
        impl_start = (t_prev_into_qa - one_hour) if t_prev_into_qa else None
        impl_comments = _comments_in_range(comments, impl_start, t_transition, author_filter=implementer)
    return {
        "fallback": False,
        "comments": _dedupe_comments(reviewer_comments + after + impl_comments),
        "transition": target,
        "implementer": implementer,
    }


def _truncate_text(text: str, n: int) -> str:
    if not n or len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + " …[truncated]"


def _print_comment(c: dict, *, truncate: int | None = None) -> None:
    author = (c.get("author") or {}).get("displayName", "Unknown")
    created = c.get("created", "")[:16].replace("T", " ")
    body = comment_to_text(c.get("body"))
    if truncate:
        body = _truncate_text(body, truncate)
    print(f"\n--- [{created}] {author} ---")
    for line in body.split("\n"):
        print(line)


def _print_intent_header(issue: dict) -> None:
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    status = (fields.get("status") or {}).get("name", "")
    assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")
    print(f"\n{issue['key']}: {summary}")
    print("=" * 60)
    print(f"Status: {status} | Assignee: {assignee}")


def _print_intent_description(issue: dict, *, truncate: int | None = None) -> None:
    description = issue.get("fields", {}).get("description")
    if not description:
        return
    if isinstance(description, dict):
        description = extract_adf_text(description)
    text = str(description)
    if truncate:
        text = _truncate_text(text, truncate)
    print("\nDescription:")
    for line in text.split("\n"):
        print(f"  {line}")


def _intent_bundle_payload(issue: dict, comments: list, *, extras: dict | None = None) -> dict:
    """Build the JSON payload for an intent verb."""
    fields = issue.get("fields", {})
    payload = {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "description": fields.get("description"),
        "comments": comments,
    }
    if extras:
        payload.update(extras)
    return payload


def _resolve_status_sets_for_ctx(ctx, issue_key: str | None = None) -> dict:
    """Load status sets, mirroring load_config's auto-resolution.

    Honors --profile if explicit; otherwise auto-resolves by issue-key project
    prefix or default profile. Falls back to env / built-in defaults if no
    profiles.json is configured.
    """
    profile = None
    client_obj = ctx.obj.get("client")
    if client_obj is not None:
        profile = getattr(client_obj, "_profile", None)
    return load_status_sets(profile=profile, issue_key=issue_key)


@cli.command()
@click.argument("issue_key")
@click.option("--truncate", type=int, metavar="N", help="Truncate description and each comment to N chars")
@click.pass_context
def work(ctx, issue_key: str, truncate: int | None):
    """Fetch full working context: description + all comments + attachments + links.

    Use when starting work on a ticket or doing triage. Single call.

    Example:

      jira-issue work NRS-4412
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]
    try:
        issue = client.issue(issue_key, fields=INTENT_FIELDS)

        # --quiet only validates the fetch — skip optional side calls (mirrors `get --quiet`)
        if ctx.obj["quiet"]:
            print(issue["key"])
            return

        comments, _ = fetch_comments_paginated(client, issue_key)
        web_links = []
        try:
            web_links = client.get_issue_remote_links(issue_key)
        except Exception:
            if ctx.obj["debug"]:
                raise
            warning("Failed to fetch web links")

        if ctx.obj["json"]:
            fields = issue.get("fields", {})
            extras = {
                "attachments": fields.get("attachment") or [],
                "issueLinks": fields.get("issuelinks") or [],
                "webLinks": web_links,
            }
            format_output(_intent_bundle_payload(issue, comments, extras=extras), as_json=True)
            return

        issue["webLinks"] = web_links
        _print_issue(issue, truncate=truncate, web_links=web_links)
        if comments:
            print("=" * 60)
            print(f"COMMENTS ({len(comments)} total — chronological)")
            print("=" * 60)
            for c in comments:
                _print_comment(c, truncate=truncate)
            print()
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to fetch work context for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.option("--truncate", type=int, metavar="N", help="Truncate description and each comment to N chars")
@click.pass_context
def qa(ctx, issue_key: str, truncate: int | None):
    """Fetch QA review context: description + handover comments since transition into QA.

    Use when starting a QA review. Returns the implementer's handover comment
    (regardless of whether written before or after the transition click) plus
    any subsequent QA discussion.

    Example:

      jira-issue qa NRS-4412
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]
    try:
        issue = client.issue(issue_key, fields=INTENT_FIELDS, expand="changelog")
        if ctx.obj["quiet"]:
            print(issue["key"])
            return

        comments, _ = fetch_comments_paginated(client, issue_key)
        sets = _resolve_status_sets_for_ctx(ctx, issue_key)
        bundle = _collect_handover_bundle(issue, comments, sets)

        if ctx.obj["json"]:
            extras = {"handover_fallback": bundle["fallback"]}
            if bundle["transition"]:
                extras["handover_transition"] = {
                    "created": bundle["transition"]["created"].isoformat(),
                    "from": bundle["transition"]["from"],
                    "to": bundle["transition"]["to"],
                    "author": bundle["transition"]["author_name"],
                }
            format_output(_intent_bundle_payload(issue, bundle["comments"], extras=extras), as_json=True)
            return

        _print_intent_header(issue)
        _print_intent_description(issue, truncate=truncate)
        if bundle["fallback"]:
            print("\n[no INTO-QA transition found — falling back to last 5 comments]")
        else:
            t = bundle["transition"]
            print(f"\nHandover: {t['created'].isoformat()} by {t['author_name']} ({t['from']} → {t['to']})")
        print("\n" + "=" * 60)
        print(f"HANDOVER COMMENTS ({len(bundle['comments'])})")
        print("=" * 60)
        for c in bundle["comments"]:
            _print_comment(c, truncate=truncate)
        print()
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to fetch QA context for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command("qa-fail")
@click.argument("issue_key")
@click.option("--truncate", type=int, metavar="N", help="Truncate description and each comment to N chars")
@click.pass_context
def qa_fail(ctx, issue_key: str, truncate: int | None):
    """Fetch QA-fail follow-up context: description + reviewer rejection + implementer scope.

    Use when continuing work after a QA reject. Returns the reviewer's rejection
    comment (regardless of order vs. transition), the implementer's scope/clarification
    comments from the same QA window, and any subsequent discussion.

    Example:

      jira-issue qa-fail NRS-4412
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]
    try:
        issue = client.issue(issue_key, fields=INTENT_FIELDS, expand="changelog")
        if ctx.obj["quiet"]:
            print(issue["key"])
            return

        comments, _ = fetch_comments_paginated(client, issue_key)
        sets = _resolve_status_sets_for_ctx(ctx, issue_key)
        bundle = _collect_reject_bundle(issue, comments, sets)

        if ctx.obj["json"]:
            extras = {"reject_fallback": bundle["fallback"]}
            if bundle["transition"]:
                extras["reject_transition"] = {
                    "created": bundle["transition"]["created"].isoformat(),
                    "from": bundle["transition"]["from"],
                    "to": bundle["transition"]["to"],
                    "reviewer": bundle["transition"]["author_name"],
                }
            if bundle.get("implementer"):
                extras["implementer"] = bundle["implementer"][1]
            format_output(_intent_bundle_payload(issue, bundle["comments"], extras=extras), as_json=True)
            return

        _print_intent_header(issue)
        _print_intent_description(issue, truncate=truncate)
        if bundle["fallback"]:
            print("\n[no REJECT transition found — falling back to last 5 comments]")
        else:
            t = bundle["transition"]
            print(f"\nReject: {t['created'].isoformat()} by {t['author_name']} ({t['from']} → {t['to']})")
            if bundle.get("implementer"):
                print(f"Implementer (for scope context): {bundle['implementer'][1]}")
        print("\n" + "=" * 60)
        print(f"QA-FAIL COMMENTS ({len(bundle['comments'])})")
        print("=" * 60)
        for c in bundle["comments"]:
            _print_comment(c, truncate=truncate)
        print()
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to fetch QA-fail context for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.pass_context
def act(ctx, issue_key: str):
    """Fetch meta + available transitions in one call (use before changing status).

    Example:

      jira-issue act NRS-4412
      jira-issue --json act NRS-4412 | jq '.transitions[].name'
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]
    try:
        issue = client.issue(issue_key, fields="summary,status,assignee,priority,issuetype")
        # Fetching transitions IS the core purpose of `act` — surface failures
        # rather than silently returning an empty list (which a caller might
        # interpret as "no transitions are available").
        transitions = client.get_issue_transitions(issue_key) or []

        if ctx.obj["json"]:
            payload = {
                "key": issue.get("key"),
                "summary": issue.get("fields", {}).get("summary"),
                "status": (issue.get("fields", {}).get("status") or {}).get("name"),
                "assignee": (issue.get("fields", {}).get("assignee") or {}).get("displayName"),
                "transitions": [
                    {"id": t.get("id"), "name": t.get("name") or t.get("to", {}).get("name")} for t in transitions
                ],
            }
            format_output(payload, as_json=True)
            return
        if ctx.obj["quiet"]:
            print(issue["key"])
            return

        _print_intent_header(issue)
        print("\nAvailable transitions:")
        if not transitions:
            print("  (none)")
        for t in transitions:
            name = t.get("name") or (t.get("to") or {}).get("name", "?")
            print(f"  • {name} (id={t.get('id', '?')})")
        print()
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to fetch act context for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
