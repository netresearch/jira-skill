#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira field operations - search and list fields."""

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
from lib.client import LazyJiraClient, get_project_issue_types
from lib.output import error, format_output, format_table, warning

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (field IDs only)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira field operations.

    Search and list Jira fields (including custom fields).
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command()
@click.argument("keyword")
@click.option("--limit", "-n", default=20, help="Max results to show")
@click.pass_context
def search(ctx, keyword: str, limit: int):
    """Search fields by keyword.

    KEYWORD: Search term (matches name or ID)

    Useful for finding custom field IDs for --fields-json options.

    Examples:

      jira-fields search sprint

      jira-fields search "story points"

      jira-fields search customfield
    """
    client = ctx.obj["client"]

    try:
        # Get all fields
        fields = client.get_all_fields()

        # Filter by keyword (case-insensitive)
        keyword_lower = keyword.lower()
        matching = [
            f for f in fields if keyword_lower in f.get("name", "").lower() or keyword_lower in f.get("id", "").lower()
        ][:limit]

        if ctx.obj["json"]:
            format_output(matching, as_json=True)
        elif ctx.obj["quiet"]:
            for f in matching:
                print(f.get("id", ""))
        else:
            if not matching:
                print(f"No fields matching '{keyword}'")
            else:
                print(f"Fields matching '{keyword}' ({len(matching)} shown):\n")
                rows = []
                for f in matching:
                    rows.append(
                        {
                            "ID": f.get("id", ""),
                            "Name": f.get("name", ""),
                            "Type": f.get("schema", {}).get("type", "-"),
                            "Custom": "Yes" if f.get("custom", False) else "No",
                        }
                    )
                print(format_table(rows, ["ID", "Name", "Type", "Custom"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to search fields: {e}")
        sys.exit(1)


@cli.command("list")
@click.option(
    "--type",
    "-t",
    "field_type",
    type=click.Choice(["custom", "system", "all"]),
    default="all",
    help="Filter by field type",
)
@click.option("--limit", "-n", default=50, help="Max results to show")
@click.pass_context
def list_fields(ctx, field_type: str, limit: int):
    """List available fields.

    Examples:

      jira-fields list

      jira-fields list --type custom

      jira-fields list --type system --limit 100
    """
    client = ctx.obj["client"]

    try:
        fields = client.get_all_fields()

        # Filter by type
        if field_type == "custom":
            fields = [f for f in fields if f.get("custom", False)]
        elif field_type == "system":
            fields = [f for f in fields if not f.get("custom", False)]

        fields = fields[:limit]

        if ctx.obj["json"]:
            format_output(fields, as_json=True)
        elif ctx.obj["quiet"]:
            for f in fields:
                print(f.get("id", ""))
        else:
            type_label = field_type if field_type != "all" else "all"
            print(f"Jira fields ({type_label}, {len(fields)} shown):\n")
            rows = []
            for f in fields:
                rows.append(
                    {
                        "ID": f.get("id", ""),
                        "Name": f.get("name", ""),
                        "Custom": "Yes" if f.get("custom", False) else "No",
                    }
                )
            print(format_table(rows, ["ID", "Name", "Custom"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list fields: {e}")
        sys.exit(1)


@cli.command("types")
@click.argument("project", required=False)
@click.pass_context
def list_types(ctx, project: str | None):
    """List available issue types.

    If PROJECT is given, show types for that project (including subtask flag).
    Otherwise, show all global issue types.

    Examples:

      jira-fields.py types PROJ

      jira-fields.py types
    """
    client = ctx.obj["client"]

    try:
        if project:
            # Use project key for profile resolution
            client.with_context(issue_key=f"{project}-1")
            types = get_project_issue_types(client, project)
        else:
            types = client.get_all_issuetypes()

        if ctx.obj["json"]:
            format_output(types, as_json=True)
            return

        if not types:
            warning("No issue types found")
            return

        rows = []
        for t in types:
            rows.append(
                {
                    "Name": t.get("name", ""),
                    "ID": t.get("id", ""),
                    "Subtask": "Yes" if t.get("subtask") else "",
                }
            )
        rows.sort(key=lambda r: (r["Subtask"] != "Yes", r["Name"]))
        print(format_table(rows, ["Name", "ID", "Subtask"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list issue types: {e}")
        sys.exit(1)


def _resolve_issue_type_id(types: list[dict], issue_type: str) -> str | None:
    """Return the id of the issue type matching an id or a name (case-insensitive)."""
    for t in types:
        if str(t.get("id", "")) == issue_type:
            return str(t["id"])
    for t in types:
        if t.get("name", "").lower() == issue_type.lower():
            return str(t["id"])
    return None


def _fetch_create_meta(client, project: str, type_id: str) -> list[dict]:
    """Fetch every field of the create screen, following pagination.

    Server/DC lists the fields under ``values``, Cloud under ``fields``.
    """
    fields: list[dict] = []
    start = 0
    while True:
        page = client.get(
            f"rest/api/2/issue/createmeta/{project}/issuetypes/{type_id}",
            params={"startAt": start, "maxResults": 100},
        )
        batch = page.get("values", page.get("fields", []))
        fields.extend(batch)
        start += len(batch)
        if not batch or page.get("isLast", True) or start >= page.get("total", start):
            return fields


def _meta_rows(fields: list[dict]) -> list[dict]:
    rows = []
    for f in fields:
        allowed = [
            str(v.get("value") or v.get("name") or v.get("key") or v.get("id")) for v in f.get("allowedValues", [])
        ]
        shown = ", ".join(allowed[:5]) + (f" (+{len(allowed) - 5})" if len(allowed) > 5 else "")
        rows.append(
            {
                "ID": f.get("fieldId", f.get("key", "")),
                "Name": f.get("name", ""),
                "Required": "Yes" if f.get("required") else "",
                "Type": f.get("schema", {}).get("type", "-"),
                "Allowed": shown,
            }
        )
    rows.sort(key=lambda r: (r["Required"] != "Yes", r["Name"].lower()))
    return rows


@cli.command("meta")
@click.argument("project", required=False)
@click.argument("issue_type", required=False)
@click.option("--edit", "edit_key", help="Show the edit screen of this issue instead of a create screen")
@click.pass_context
def meta(ctx, project: str | None, issue_type: str | None, edit_key: str | None):
    """Show the fields a screen accepts: id, name, required, allowed values.

    PROJECT and ISSUE_TYPE (name or id) select a create screen. With --edit KEY
    the edit screen of that issue is shown instead. A field missing here is not
    on the screen, so Jira refuses to set it ("not on the appropriate screen").

    Examples:

      jira-fields.py meta PROJ Task

      jira-fields.py meta PROJ 10002 --json

      jira-fields.py meta --edit PROJ-123
    """
    client = ctx.obj["client"]

    try:
        if edit_key:
            client.with_context(issue_key=edit_key)
            data = client.get(f"rest/api/2/issue/{edit_key}/editmeta")
            fields = [{"fieldId": k, **v} for k, v in data.get("fields", {}).items()]
        else:
            if not project or not issue_type:
                error("PROJECT and ISSUE_TYPE are required unless --edit KEY is given")
                sys.exit(2)
            client.with_context(issue_key=f"{project}-1")
            types = get_project_issue_types(client, project)
            type_id = _resolve_issue_type_id(types, issue_type)
            if type_id is None:
                names = ", ".join(sorted(t.get("name", "") for t in types))
                error(f"Issue type '{issue_type}' not found in {project}. Available: {names}")
                sys.exit(1)
            fields = _fetch_create_meta(client, project, type_id)

        if ctx.obj["json"]:
            format_output(fields, as_json=True)
        elif ctx.obj["quiet"]:
            for f in fields:
                print(f.get("fieldId", ""))
        else:
            if not fields:
                warning("The screen has no fields")
                return
            print(format_table(_meta_rows(fields), ["ID", "Name", "Required", "Type", "Allowed"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to read screen metadata: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
