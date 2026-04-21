#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira project version operations - list, get, create, update, release lifecycle, move, merge, delete."""

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
from lib.output import error, format_output, format_table, success, warning


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _status_of(v: dict) -> str:
    if v.get("archived"):
        return "archived"
    return "released" if v.get("released") else "unreleased"


def _fmt_list_row(v: dict) -> dict:
    return {
        "ID": v.get("id", ""),
        "NAME": v.get("name", ""),
        "STATUS": _status_of(v),
        "START": v.get("startDate", "-") or "-",
        "RELEASE": v.get("releaseDate", "-") or "-",
        "ISSUES": v.get("issueCount", "-") if v.get("issueCount") is not None else "-",
    }


def _is_numeric_id(s: str) -> bool:
    return s.isdigit()


def _render_version(v: dict, counts: dict | None = None) -> str:
    lines = [
        f"Version {v.get('id', '?')} — {v.get('name', '')}",
        f"  Project:      {v.get('project', v.get('projectId', ''))}",
        f"  Status:       {_status_of(v)}",
        f"  Start:        {v.get('startDate', '-') or '-'}",
        f"  Release:      {v.get('releaseDate', '-') or '-'}",
    ]
    if v.get("description"):
        lines.append(f"  Description:  {v['description']}")
    if counts:
        fixed = counts.get("issuesFixedCount", counts.get("fixed", "?"))
        affected = counts.get("issuesAffectedCount", counts.get("affected", "?"))
        unresolved = counts.get("issuesUnresolvedCount", counts.get("unresolved", "?"))
        lines.append(f"  Issues:       fixed={fixed} affected={affected} unresolved={unresolved}")
    return "\n".join(lines)


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
    """Jira project version operations.

    Manage the release lifecycle: list, create, release, archive, merge, delete versions.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


# All subcommands are stubs. TDD will flesh them out task by task.


@cli.command("list")
@click.argument("project_key")
@click.option("--status", type=click.Choice(["released", "unreleased", "archived", "all"]),
              default="unreleased", help="Filter by status")
@click.option("--query", help="Filter by name substring (paginated endpoint)")
@click.option("--order-by", type=click.Choice(["sequence", "name", "startDate", "releaseDate"]),
              help="Sort order (paginated endpoint)")
@click.pass_context
def list_versions(ctx, project_key: str, status: str, query: str | None, order_by: str | None):
    """List versions in a project.

    Uses the flat `/project/{key}/versions` endpoint unless --query or --order-by
    is provided, in which case it switches to the paginated endpoint.
    """
    client = ctx.obj["client"]
    try:
        if query or order_by:
            versions = _fetch_versions_paginated(client, project_key, status=status,
                                                 query=query, order_by=order_by)
        else:
            versions = client.get(f"rest/api/2/project/{project_key}/versions") or []
            if status != "all":
                versions = [v for v in versions if _status_of(v) == status]

        if ctx.obj["json"]:
            format_output(versions, as_json=True)
            return
        if ctx.obj["quiet"]:
            for v in versions:
                print(v.get("id", ""))
            return

        print(f"{status.capitalize()} versions in {project_key} ({len(versions)}):\n")
        rows = [_fmt_list_row(v) for v in versions]
        print(format_table(rows, columns=["ID", "NAME", "STATUS", "START", "RELEASE", "ISSUES"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list versions: {e}")
        sys.exit(1)


def _fetch_versions_paginated(client, project_key, status=None, query=None, order_by=None):
    """Paginated search via `/project/{key}/version`.

    Availability: Jira Server/DC >=9.x and Jira Cloud. Older DC versions return
    404 — callers should rely on the flat `/project/{key}/versions` endpoint
    and filter client-side when `--query` / `--order-by` are not supplied.
    """
    all_values: list[dict] = []
    start_at = 0
    page_size = 50
    while True:
        params = {"startAt": start_at, "maxResults": page_size}
        if query:
            params["query"] = query
        if order_by:
            params["orderBy"] = order_by
        if status and status != "all":
            params["status"] = status
        page = client.get(f"rest/api/2/project/{project_key}/version", params=params) or {}
        values = page.get("values", [])
        all_values.extend(values)
        if page.get("isLast", True) or not values:
            break
        start_at += len(values) or page_size
    return all_values


@cli.command()
@click.argument("version")
@click.option("--project", help="Required when VERSION is a name (not an ID)")
@click.option("--counts", is_flag=True, help="Include fixed/affected/unresolved issue counts")
@click.pass_context
def get(ctx, version: str, project: str | None, counts: bool):
    """Get a single version by ID or name."""
    client = ctx.obj["client"]
    try:
        if _is_numeric_id(version):
            v = client.get(f"rest/api/2/version/{version}")
        else:
            v = _resolve_version_by_name(client, version, project)  # implemented in Task 6

        extra = None
        if counts:
            extra = _fetch_counts(client, v["id"])  # implemented in Task 7

        if ctx.obj["json"]:
            payload = dict(v)
            if extra:
                payload["_counts"] = extra
            format_output(payload, as_json=True)
            return
        if ctx.obj["quiet"]:
            print(v.get("id", ""))
            return
        print(_render_version(v, counts=extra))

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get version: {e}")
        sys.exit(1)


def _resolve_version_by_name(client, name: str, project_key: str | None) -> dict:
    if not project_key:
        error("--project is required when looking up a version by name")
        sys.exit(2)
    versions = client.get(f"rest/api/2/project/{project_key}/versions") or []
    matches = [v for v in versions if v.get("name") == name]
    if not matches:
        error(f'No version named "{name}" found in {project_key}')
        sys.exit(1)
    if len(matches) > 1:
        ids = ", ".join(v.get("id", "?") for v in matches)
        error(f'Multiple versions named "{name}" in {project_key} (ids: {ids})')
        sys.exit(1)
    return matches[0]


def _fetch_counts(client, vid):
    raise NotImplementedError  # Task 7


@cli.command()
@click.argument("project_key")
@click.argument("name")
@click.pass_context
def create(ctx, project_key: str, name: str):
    """Create a new version in a project."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def update(ctx, version_id: str):
    """Update fields on an existing version (GET + merge + PUT)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def release(ctx, version_id: str):
    """Mark a version released (sets released=true + releaseDate)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def unrelease(ctx, version_id: str):
    """Mark a version unreleased (clears releaseDate)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def archive(ctx, version_id: str):
    """Archive a version (hides it from pickers)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def unarchive(ctx, version_id: str):
    """Unarchive a version."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def move(ctx, version_id: str):
    """Reorder a version within its project."""
    raise NotImplementedError


@cli.command()
@click.argument("src_id")
@click.argument("into", type=click.Choice(["INTO"]))
@click.argument("dst_id")
@click.pass_context
def merge(ctx, src_id: str, into: str, dst_id: str):
    """Merge SRC_ID INTO DST_ID (reassign refs + delete source)."""
    raise NotImplementedError


@cli.command()
@click.argument("version_id")
@click.pass_context
def delete(ctx, version_id: str):
    """Delete a version, optionally reassigning fixVersions/versions refs."""
    raise NotImplementedError


if __name__ == "__main__":
    cli()
