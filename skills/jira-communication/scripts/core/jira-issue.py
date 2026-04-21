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
    compute_time_in_status,
    extract_status_transitions,
    format_timedelta,
    parse_jira_datetime,
)
from lib.client import LazyJiraClient, _sanitize_error, resolve_assignee, resolve_status
from lib.output import compact_json, error, extract_adf_text, format_output, success, warning

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
    help="With --json: return the full Jira payload. Without --raw, null/empty fields are stripped.",
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
            payload = {
                "key": issue_key,
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
@click.option("--priority", "-p", help="Priority name")
@click.option("--labels", "-l", help="Comma-separated labels (replaces existing)")
@click.option("--assignee", "-a", help="Assignee username or email")
@click.option("--fields-json", help="JSON string of additional fields to update")
@click.option("--dry-run", is_flag=True, help="Show what would be updated without making changes")
@click.pass_context
def update(
    ctx,
    issue_key: str,
    summary: str | None,
    priority: str | None,
    labels: str | None,
    assignee: str | None,
    fields_json: str | None,
    dry_run: bool,
):
    """Update issue fields.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue update PROJ-123 --summary "New title"

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

    if priority:
        update_fields["priority"] = {"name": priority}

    if labels:
        update_fields["labels"] = [l.strip() for l in labels.split(",")]

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
        click.echo("\nUse one or more of: --summary, --priority, --labels, --assignee, --fields-json")
        sys.exit(1)

    if dry_run:
        warning("DRY RUN - No changes will be made")
        print(f"\nWould update {issue_key} with:")
        for key, value in update_fields.items():
            print(f"  {key}: {value}")
        return

    try:
        client.update_issue_field(issue_key, update_fields)

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


if __name__ == "__main__":
    cli()
