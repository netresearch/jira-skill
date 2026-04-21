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
@click.pass_context
def list_versions(ctx, project_key: str):
    """List versions in a project."""
    raise NotImplementedError


@cli.command()
@click.argument("version")
@click.pass_context
def get(ctx, version: str):
    """Get a single version by ID or name."""
    raise NotImplementedError


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
