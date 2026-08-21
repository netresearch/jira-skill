#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira watcher operations — list, add, and remove issue watchers."""

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
from lib.client import LazyJiraClient, resolve_assignee
from lib.output import error, format_json, success, warning

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
    """Jira watcher operations.

    List, add, and remove watchers on Jira issues.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_watcher_identifier(client, identifier: str) -> tuple[str, bool]:
    """Return (value, is_account_id) suitable for issue_add_watcher / issue_delete_watcher.

    Reuses resolve_assignee() for 'me' / accountId / user-search handling and
    unwraps the {"name": ...} / {"accountId": ...} dict into a flat string,
    because the watchers REST API takes a bare identifier as its JSON body
    (not an object). atlassian-python-api passes the string through verbatim.
    """
    resolved = resolve_assignee(client, identifier)
    if "accountId" in resolved:
        return resolved["accountId"], True
    return resolved["name"], False


def _watcher_api_arg(identifier: str, is_account_id_value: bool) -> dict:
    """Return the keyword arg dict for issue_delete_watcher.

    DC takes ?username=...; Cloud takes ?accountId=.... atlassian-python-api
    exposes both as keyword args; pick based on the resolved identifier
    shape (an account-id-shaped string means Cloud/accountId).
    """
    if is_account_id_value:
        return {"account_id": identifier}
    return {"username": identifier}


# ═══════════════════════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════════════════════


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_watchers(ctx, issue_key: str):
    """List watchers on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Example:

      jira-watchers list PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        data = client.issue_get_watchers(issue_key)

        if ctx.obj["json"]:
            print(format_json(data))
            return

        watchers = data.get("watchers", []) or []
        count = data.get("watchCount", len(watchers))
        is_watching = bool(data.get("isWatching"))

        if ctx.obj["quiet"]:
            for w in watchers:
                print(w.get("accountId") or w.get("name", ""))
            return

        if not watchers:
            print(f"No watchers for {issue_key}")
            return

        # Jira returns isWatching at the top level describing the caller —
        # surface it in the header so users know their own subscription state
        # without a second client.myself() round-trip.
        status = "you are watching" if is_watching else "you are not watching"
        print(f"Watchers for {issue_key} ({count}) — {status}:\n")
        for w in watchers:
            name = w.get("name") or w.get("accountId", "")
            display = w.get("displayName", "")
            print(f"  {name:<20} {display}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list watchers: {e}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.pass_context
def add(ctx, issue_key: str, user: str):
    """Add a watcher to an issue (default: yourself).

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Adding yourself requires only Browse Projects; adding someone else
    requires the Manage Watchers permission. Self-adds are idempotent —
    Jira silently accepts repeated adds.

    Examples:

      jira-watchers add PROJ-123

      jira-watchers add PROJ-123 --user asmith
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        identifier, _is_acct = _resolve_watcher_identifier(client, user)

        # POST body is a raw JSON-encoded string (e.g. '"jdoe"'), NOT
        # {"name": "jdoe"}. atlassian-python-api's issue_add_watcher handles
        # that correctly — do not wrap in a dict.
        client.issue_add_watcher(issue_key, identifier)

        suffix = " (you)" if user.lower() == "me" else ""

        if ctx.obj["json"]:
            print(format_json({"key": issue_key, "user": identifier, "added": True}))
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Added watcher to {issue_key}: {identifier}{suffix}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to add watcher: {e}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.pass_context
def remove(ctx, issue_key: str, user: str, dry_run: bool):
    """Remove a watcher from an issue (default: yourself).

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Removing yourself requires only Browse Projects; removing someone else
    requires Manage Watchers. Removing a non-watcher returns 404 — surfaced
    as a clean error, not a silent success.

    Examples:

      jira-watchers remove PROJ-123

      jira-watchers remove PROJ-123 --user asmith --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        identifier, is_acct = _resolve_watcher_identifier(client, user)
        suffix = " (you)" if user.lower() == "me" else ""

        if dry_run:
            warning("DRY RUN - No watcher will be removed")
            print(f"Would remove {identifier}{suffix} from {issue_key}")
            return

        kwargs = _watcher_api_arg(identifier, is_acct)
        client.issue_delete_watcher(issue_key, **kwargs)

        if ctx.obj["json"]:
            print(format_json({"key": issue_key, "user": identifier, "removed": True}))
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Removed watcher from {issue_key}: {identifier}{suffix}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to remove watcher: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
