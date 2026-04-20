#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira issue link operations - create links and list link types."""

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
from lib.client import LazyJiraClient, _sanitize_error
from lib.output import error, format_output, format_table, success, warning

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
    """Jira issue link operations.

    Create links between issues and list available link types.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command()
@click.argument("from_key")
@click.argument("to_key")
@click.option("--type", "-t", "link_type", required=True, help='Link type name (e.g., "Blocks", "Relates")')
@click.option("--dry-run", is_flag=True, help="Show what would be created")
@click.pass_context
def create(ctx, from_key: str, to_key: str, link_type: str, dry_run: bool):
    """Create a link between two issues.

    FROM_KEY: Source issue key

    TO_KEY: Target issue key

    Examples:

      jira-link create PROJ-123 PROJ-456 --type "Blocks"

      jira-link create PROJ-123 PROJ-456 --type "Relates" --dry-run
    """
    ctx.obj["client"].with_context(issue_key=from_key)
    client = ctx.obj["client"]

    if dry_run:
        warning("DRY RUN - No link will be created")
        print("\nWould create link:")
        print(f"  {from_key} --[{link_type}]--> {to_key}")
        return

    try:
        client.create_issue_link(
            {"type": {"name": link_type}, "inwardIssue": {"key": to_key}, "outwardIssue": {"key": from_key}}
        )

        if ctx.obj["json"]:
            format_output({"from": from_key, "to": to_key, "type": link_type, "created": True}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Created link: {from_key} --[{link_type}]--> {to_key}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to create link: {e}")
        sys.exit(1)


@cli.command("list-types")
@click.pass_context
def list_types(ctx):
    """List available link types.

    Shows all issue link types configured in your Jira instance.

    Example:

      jira-link list-types
    """
    client = ctx.obj["client"]

    try:
        link_types = client.get_issue_link_types()

        if ctx.obj["json"]:
            format_output(link_types, as_json=True)
        elif ctx.obj["quiet"]:
            for lt in link_types:
                print(lt.get("name", ""))
        else:
            print("Available link types:\n")
            rows = []
            for lt in link_types:
                rows.append(
                    {"Name": lt.get("name", ""), "Inward": lt.get("inward", ""), "Outward": lt.get("outward", "")}
                )
            print(format_table(rows, ["Name", "Inward", "Outward"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get link types: {e}")
        sys.exit(1)


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_cmd(ctx, issue_key: str):
    """List all issue links on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Shows link ID, direction, link type, and the other issue's key and summary.

    Example:

      jira-link list PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        issue = client.issue(issue_key, fields="issuelinks")
        raw_links = (issue.get("fields") or {}).get("issuelinks") or []

        links = []
        for link in raw_links:
            link_id = link.get("id", "")
            type_obj = link.get("type") or {}
            type_name = type_obj.get("name", "")
            if "outwardIssue" in link:
                other = link["outwardIssue"]
                direction = "outward"
                relation = type_obj.get("outward", "")
            elif "inwardIssue" in link:
                other = link["inwardIssue"]
                direction = "inward"
                relation = type_obj.get("inward", "")
            else:
                other = {}
                direction = ""
                relation = ""
            other_key = other.get("key", "")
            other_summary = ((other.get("fields") or {}).get("summary")) or ""
            other_status = (((other.get("fields") or {}).get("status")) or {}).get("name", "")
            links.append(
                {
                    "id": link_id,
                    "type": type_name,
                    "direction": direction,
                    "relation": relation,
                    "other_key": other_key,
                    "other_summary": other_summary,
                    "other_status": other_status,
                }
            )

        if ctx.obj["json"]:
            format_output(links, as_json=True)
        elif ctx.obj["quiet"]:
            for link_entry in links:
                print(
                    f"{link_entry['id']} {link_entry['type']} {link_entry['direction']} {link_entry['other_key']}"
                )
        else:
            if not links:
                print(f"No issue links on {issue_key}")
                return
            rows = [
                {
                    "ID": link_entry["id"],
                    "Type": link_entry["type"],
                    "Direction": link_entry["direction"],
                    "Other": link_entry["other_key"],
                    "Summary": link_entry["other_summary"][:60],
                    "Status": link_entry["other_status"],
                }
                for link_entry in links
            ]
            print(format_table(rows, ["ID", "Type", "Direction", "Other", "Summary", "Status"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list issue links for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


def _link_matches(link: dict, to_key: str, link_type: str) -> bool:
    """Return True if an issue link targets to_key with link_type (case-insensitive)."""
    type_name = (link.get("type") or {}).get("name", "")
    if type_name.lower() != link_type.lower():
        return False
    other = link.get("outwardIssue") or link.get("inwardIssue") or {}
    other_key = other.get("key", "")
    return other_key.casefold() == to_key.casefold()


def _format_link_display(link: dict, context_key: str | None = None) -> str:
    """Format an issue link for human-readable output (e.g. 'blocks TEST-2').

    When context_key is provided, describe the link from that issue's
    perspective — matters when both inward and outward are populated
    (e.g. results from client.get_issue_link(id)).
    """
    type_obj = link.get("type") or {}
    type_name = type_obj.get("name", "")
    outward = link.get("outwardIssue") or {}
    inward = link.get("inwardIssue") or {}
    if context_key and outward.get("key") == context_key and inward:
        return f"{type_obj.get('outward', type_name)} {inward.get('key', '?')}"
    if context_key and inward.get("key") == context_key and outward:
        return f"{type_obj.get('inward', type_name)} {outward.get('key', '?')}"
    if outward:
        return f"{type_obj.get('outward', type_name)} {outward.get('key', '?')}"
    if inward:
        return f"{type_obj.get('inward', type_name)} {inward.get('key', '?')}"
    return type_name


@cli.command()
@click.argument("issue_key")
@click.option("--id", "link_id", type=str, help="Issue link ID (from `jira-link list`)")
@click.option("--to", "to_key", help="Other issue key to identify the link by")
@click.option("--type", "-t", "link_type", help="Link type name (used with --to)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.pass_context
def delete(
    ctx,
    issue_key: str,
    link_id: str | None,
    to_key: str | None,
    link_type: str | None,
    dry_run: bool,
):
    """Delete an issue link.

    ISSUE_KEY: The Jira issue key that owns the link (e.g. PROJ-123)

    Identify the link by either --id or the combination of --to and --type.

    Examples:

      jira-link delete PROJ-123 --id 10042

      jira-link delete PROJ-123 --to PROJ-456 --type "Blocks" --dry-run
    """
    if link_id is None and not (to_key and link_type):
        error("Provide --id, or both --to and --type, to identify the link")
        sys.exit(1)
    if link_id is not None and (to_key or link_type):
        error("Use --id OR (--to and --type), not both")
        sys.exit(1)

    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Resolve to a single link_id + display string
        if link_id is not None:
            link = client.get_issue_link(link_id)
            inward_key = (link.get("inwardIssue") or {}).get("key") or ""
            outward_key = (link.get("outwardIssue") or {}).get("key") or ""
            if issue_key.casefold() not in {inward_key.casefold(), outward_key.casefold()}:
                error(f"Link id {link_id} is not associated with issue {issue_key}")
                sys.exit(1)
            display = _format_link_display(link, context_key=issue_key)
        else:
            issue = client.issue(issue_key, fields="issuelinks")
            raw_links = (issue.get("fields") or {}).get("issuelinks") or []
            matches = [lnk for lnk in raw_links if _link_matches(lnk, to_key, link_type)]
            if not matches:
                error(f"No {link_type!r} link from {issue_key} to {to_key}")
                sys.exit(1)
            if len(matches) > 1:
                ids = ", ".join(m.get("id", "?") for m in matches)
                error(f"Multiple matching links (ids: {ids}); use --id to disambiguate")
                sys.exit(1)
            link = matches[0]
            link_id = link.get("id")
            if not link_id:
                error("Matched link has no id; cannot delete")
                sys.exit(1)
            display = _format_link_display(link, context_key=issue_key)

        if dry_run:
            warning("DRY RUN - No link will be deleted")
            print(f"Would delete [{link_id}] {display}")
            return

        client.remove_issue_link(link_id)

        if ctx.obj["json"]:
            format_output({"key": issue_key, "id": link_id, "deleted": True}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Deleted link [{link_id}] {display}")

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete issue link: {_sanitize_error(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
