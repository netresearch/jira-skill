#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira web link (remote link) operations - add, list, update, delete."""

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
from lib.client import LazyJiraClient
from lib.output import error, format_output, success, warning

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
    """Jira web link (remote link) operations.

    Add, list, update, and delete external URL links on Jira issues.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_link_by_url(client, issue_key: str, url: str) -> dict:
    """Find a single remote link by URL, or exit with an error.

    Returns:
        The matching remote link dict (with 'id', 'object', etc.).

    Raises:
        SystemExit on zero or multiple matches.
    """
    links = client.get_issue_remote_links(issue_key)
    matches = [link for link in links if link.get("object", {}).get("url") == url]

    if len(matches) == 0:
        error(f"No web link found with URL: {url}")
        sys.exit(1)
    if len(matches) > 1:
        error(f"Multiple web links found with URL: {url}. Use --id to specify")
        sys.exit(1)

    return matches[0]


# ═══════════════════════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════════════════════


@cli.command()
@click.argument("issue_key")
@click.option("--url", required=True, help="URL of the web link")
@click.option("--title", required=True, help="Title/label for the web link")
@click.option("--dry-run", is_flag=True, help="Show what would be created")
@click.pass_context
def add(ctx, issue_key: str, url: str, title: str, dry_run: bool):
    """Add a web link to an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Examples:

      jira-weblink add PROJ-123 --url https://example.com/doc --title "Design Doc"

      jira-weblink add PROJ-123 --url https://ci.example.com --title "CI" --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    if dry_run:
        warning("DRY RUN - No link will be created")
        print(f"\nWould add web link to {issue_key}: {title} \u2014 {url}")
        return

    try:
        result = client.create_or_update_issue_remote_links(issue_key, url, title)

        link_id = result.get("id") if isinstance(result, dict) else None

        if ctx.obj["json"]:
            data = {"key": issue_key, "url": url, "title": title, "created": True}
            if link_id is not None:
                data["id"] = link_id
            format_output(data, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Added web link to {issue_key}: {title} \u2014 {url}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to add web link: {e}")
        sys.exit(1)


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_links(ctx, issue_key: str):
    """List all web links on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Example:

      jira-weblink list PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        links = client.get_issue_remote_links(issue_key)

        if ctx.obj["json"]:
            format_output(links, as_json=True)
            return

        if not links:
            print(f"No web links found for {issue_key}")
            return

        if ctx.obj["quiet"]:
            for link in links:
                obj = link.get("object", {})
                print(f"{link.get('id', '')} {obj.get('url', '')}")
            return

        print(f"Web links for {issue_key}:\n")
        for link in links:
            link_id = link.get("id", "?")
            obj = link.get("object", {})
            title = obj.get("title", "(untitled)")
            link_url = obj.get("url", "")
            print(f"  [{link_id}] {title} \u2014 {link_url}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list web links: {e}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.option("--id", "link_id", type=int, help="Remote link ID")
@click.option("--url", help="URL to find the link by (if --id not given)")
@click.option("--title", help="New title for the web link")
@click.option("--new-url", help="New URL for the web link")
@click.pass_context
def update(ctx, issue_key: str, link_id: int | None, url: str | None, title: str | None, new_url: str | None):
    """Update an existing web link.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Identify the link by --id or --url. At least one of --title or --new-url is required.

    Examples:

      jira-weblink update PROJ-123 --id 42 --title "Updated Title"

      jira-weblink update PROJ-123 --url https://example.com --new-url https://example.com/v2
    """
    if link_id is None and url is None:
        error("Provide --id or --url to identify the web link")
        sys.exit(1)

    if title is None and new_url is None:
        error("Provide at least one of --title or --new-url")
        sys.exit(1)

    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Resolve link ID
        if link_id is None:
            resolved = _resolve_link_by_url(client, issue_key, url)
            link_id = resolved["id"]

        # Fetch current link to preserve fields not being updated
        current = client.get_issue_remote_link_by_id(issue_key, link_id)
        current_obj = current.get("object", {})

        final_url = new_url if new_url is not None else current_obj.get("url")
        final_title = title if title is not None else current_obj.get("title")

        if not final_url or not final_title:
            error("Cannot update: current link is missing url or title. Provide both --new-url and --title.")
            sys.exit(1)

        client.update_issue_remote_link_by_id(issue_key, link_id, final_url, final_title)

        if ctx.obj["json"]:
            format_output({"key": issue_key, "id": link_id, "updated": True}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Updated web link [{link_id}] on {issue_key}")

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to update web link: {e}")
        sys.exit(1)


@cli.command()
@click.argument("issue_key")
@click.option("--id", "link_id", type=int, help="Remote link ID")
@click.option("--url", help="URL to find the link by (if --id not given)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.pass_context
def delete(ctx, issue_key: str, link_id: int | None, url: str | None, dry_run: bool):
    """Delete a web link from an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Identify the link by --id or --url.

    Examples:

      jira-weblink delete PROJ-123 --id 42

      jira-weblink delete PROJ-123 --url https://example.com --dry-run
    """
    if link_id is None and url is None:
        error("Provide --id or --url to identify the web link")
        sys.exit(1)

    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Resolve link for display/ID
        if link_id is not None:
            link = client.get_issue_remote_link_by_id(issue_key, link_id)
        else:
            link = _resolve_link_by_url(client, issue_key, url)
            link_id = link["id"]

        link_obj = link.get("object", {})
        link_title = link_obj.get("title", "(untitled)")
        link_url = link_obj.get("url", "")

        if dry_run:
            warning("DRY RUN - No link will be deleted")
            print(f"Would delete [{link_id}] {link_title} \u2014 {link_url}")
            return

        client.delete_issue_remote_link_by_id(issue_key, link_id)

        if ctx.obj["json"]:
            format_output({"key": issue_key, "id": link_id, "deleted": True}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Deleted web link [{link_id}] from {issue_key}")

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete web link: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
