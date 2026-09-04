#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira worklog operations - add and list time tracking entries."""

import sys
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import (TR1.1.1 - PYTHONPATH approach)
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import re

import click
from lib.client import LazyJiraClient
from lib.output import comment_to_text, error, format_output, success
from lib.users import check_mentions_cli, person_label

# Trailing UTC offset in any ISO-8601 spelling: "Z", "+01:00" or "+0100".
_TZ_SUFFIX_RE = re.compile(r"(?:(?P<utc>[Zz])|(?P<sign>[+-])(?P<hh>\d{2}):?(?P<mm>\d{2}))$")

# Date and time to the second, with an optional fractional part of any length.
_DATE_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?$")


def normalize_iso_timestamp(timestamp: str) -> str:
    """Normalize ISO timestamp to Jira's required format.

    Jira requires: YYYY-MM-DDTHH:MM:SS.sss+ZZZZ (e.g., 2025-01-15T09:00:00.000+0100)

    Accepts various formats:
      - 2025-01-15T09:00:00 (adds local timezone)
      - 2025-01-15T09:00 (adds seconds and local timezone)
      - 2025-01-15 (adds time 00:00:00 and local timezone)
      - 2025-01-15T09:00:00+01:00 (converts timezone format)
      - 2025-01-15T09:00:00.123456+01:00 (truncates to milliseconds, converts timezone)
      - 2025-01-15T09:00:00Z (Z is +0000, a spelling Jira itself rejects)
      - 2025-01-15T09:00:00.000+0100 (pass through)

    Anything else is returned exactly as the caller typed it, so an
    unrecognised shape reaches Jira intact rather than half-rewritten.
    """
    # Already in Jira format (has milliseconds and compact timezone)
    if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{4}$", timestamp):
        return timestamp

    # Get local timezone offset
    local_tz = datetime.now().astimezone().strftime("%z")  # e.g., +0100

    # Date only: 2025-01-15
    if re.match(r"^\d{4}-\d{2}-\d{2}$", timestamp):
        return f"{timestamp}T00:00:00.000{local_tz}"

    # Split the offset off the timestamp body; a bare body inherits local time.
    tz_match = _TZ_SUFFIX_RE.search(timestamp)
    if tz_match:
        body = timestamp[: tz_match.start()]
        if tz_match.group("utc"):
            tz_compact = "+0000"
        else:
            tz_compact = f"{tz_match.group('sign')}{tz_match.group('hh')}{tz_match.group('mm')}"
    else:
        body, tz_compact = timestamp, local_tz

    # No seconds: 2025-01-15T09:00
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", body):
        body = f"{body}:00"

    # Seconds, with or without a fractional part — Jira takes exactly 3 digits.
    dt_match = _DATE_TIME_RE.match(body)
    if dt_match:
        millis = (dt_match.group(2) or "").ljust(3, "0")[:3]
        return f"{dt_match.group(1)}.{millis}{tz_compact}"

    # Fallback: the original input, offset included (let Jira handle/reject it)
    return timestamp


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
    """Jira worklog operations.

    Add and list time tracking entries for Jira issues.

    TIME_SPENT format examples: '2h', '2h 30m', '1d', '30m'
    (passed directly to Jira API - see D10)
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command()
@click.argument("issue_key")
@click.argument("time_spent")
@click.option("--comment", "-c", help="Worklog comment")
@click.option(
    "--started", help="Start time (ISO format: YYYY-MM-DD, YYYY-MM-DDTHH:MM, or YYYY-MM-DDTHH:MM:SS; default: now)"
)
@click.option("--no-verify-mentions", is_flag=True, help="Skip [~username] mention verification in --comment")
@click.pass_context
def add(ctx, issue_key: str, time_spent: str, comment: str | None, started: str | None, no_verify_mentions: bool):
    """Add worklog entry to an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    TIME_SPENT: Time spent in Jira format (e.g., '2h 30m', '1d', '30m')

    Examples:

      jira-worklog add PROJ-123 "2h 30m" -c "Code review"

      jira-worklog add PROJ-123 "1d" --started "2025-01-15T09:00:00"
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    # A worklog comment renders wiki markup — same mention gate as jira-comment add
    check_mentions_cli(client, comment, skip=no_verify_mentions)

    try:
        # Build worklog data for JSON API
        worklog_data = {
            "timeSpent": time_spent,
        }

        if comment:
            worklog_data["comment"] = comment

        if started:
            worklog_data["started"] = normalize_iso_timestamp(started)
        else:
            # Default to current time in local timezone (Jira format)
            worklog_data["started"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S.000%z")

        # Add worklog via REST API (using issue_add_json_worklog which accepts timeSpent string)
        result = client.issue_add_json_worklog(issue_key, worklog_data)

        if ctx.obj["quiet"]:
            print(result.get("id", "ok"))
        elif ctx.obj["json"]:
            format_output(result, as_json=True)
        else:
            success(f"Added worklog to {issue_key}: {time_spent}")
            if comment:
                print(f"  Comment: {comment}")
            print(f"  Worklog ID: {result.get('id', 'N/A')}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to add worklog to {issue_key}: {e}")
        sys.exit(1)


@cli.command("list")
@click.argument("issue_key")
@click.option("--limit", "-n", default=10, help="Max entries to show")
@click.option("--truncate", type=int, metavar="N", help="Truncate comments to N characters")
@click.pass_context
def list_worklogs(ctx, issue_key: str, limit: int, truncate: int | None):
    """List worklog entries for an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-worklog list PROJ-123

      jira-worklog list PROJ-123 --limit 5 --json
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        result = client.issue_get_worklog(issue_key)
        worklogs = result.get("worklogs", [])

        # Newest first, then limit
        worklogs = list(reversed(worklogs))[:limit]

        if ctx.obj["json"]:
            format_output(worklogs, as_json=True)
        elif ctx.obj["quiet"]:
            for wl in worklogs:
                print(wl.get("id", ""))
        else:
            if not worklogs:
                print(f"No worklogs found for {issue_key}")
            else:
                print(f"Worklogs for {issue_key} ({len(worklogs)} shown):\n")
                for wl in worklogs:
                    author = person_label(wl.get("author"))
                    time_spent = wl.get("timeSpent", "N/A")
                    started = wl.get("started", "N/A")[:10] if wl.get("started") else "N/A"
                    worklog_id = wl.get("id", "N/A")
                    comment = comment_to_text(wl.get("comment"))

                    print(f"  [{started}] {author}: {time_spent}  (id {worklog_id})")
                    if comment:
                        # Truncate if requested
                        if truncate and len(comment) > truncate:
                            comment = comment[: truncate - 3] + "..."
                        print(f"           {comment}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get worklogs for {issue_key}: {e}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.argument("worklog_id")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
@click.pass_context
def delete(ctx, issue_key: str, worklog_id: str, dry_run: bool):
    """Delete a worklog entry from an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    WORKLOG_ID: The numeric worklog id, as printed by `add` and `list`

    Use this to undo a booking made against the wrong issue, the wrong
    duration, or the wrong system — e.g. when the team's system of record is a
    separate time tracker that syncs its own entries into Jira, and a direct
    Jira worklog would double-book.

    Deleting another user's worklog requires the "Delete All Worklogs"
    permission; your own needs "Delete Own Worklogs".

    Examples:

      jira-worklog delete PROJ-123 409062 --dry-run

      jira-worklog delete PROJ-123 409062
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Fetch the entry first so the operator sees which booking is going
        # away — a bare numeric id is easy to mistype and impossible to sanity
        # check after the fact.
        existing = client.get(f"rest/api/2/issue/{issue_key}/worklog/{worklog_id}") or {}
        author = person_label(existing.get("author"))
        time_spent = existing.get("timeSpent", "N/A")
        started = existing.get("started", "N/A")[:10] if existing.get("started") else "N/A"

        if dry_run:
            print(f"Would delete worklog {worklog_id} from {issue_key}:")
            print(f"  [{started}] {author}: {time_spent}")
            return

        client.delete(f"rest/api/2/issue/{issue_key}/worklog/{worklog_id}")

        if ctx.obj["quiet"]:
            print(worklog_id)
        elif ctx.obj["json"]:
            format_output({"deleted": worklog_id, "issue": issue_key}, as_json=True)
        else:
            success(f"Deleted worklog {worklog_id} from {issue_key}")
            print(f"  [{started}] {author}: {time_spent}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete worklog {worklog_id} from {issue_key}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
