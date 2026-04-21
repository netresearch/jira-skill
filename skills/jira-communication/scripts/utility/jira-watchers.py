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
from lib.client import LazyJiraClient, is_account_id, resolve_assignee
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

    Reuses resolve_assignee() for the hard part (me / accountId / user search) and
    unwraps the dict into a flat string — the watchers REST API takes a bare
    identifier, not {"name": ...} / {"accountId": ...}.
    """
    raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════════════════════


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_watchers(ctx, issue_key: str):
    """List watchers on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)
    """
    raise NotImplementedError


@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.pass_context
def add(ctx, issue_key: str, user: str):
    """Add a watcher to an issue (default: yourself)."""
    raise NotImplementedError


@cli.command()
@click.argument("issue_key")
@click.option("--user", default="me", help="Username, accountId, email, or 'me' (default: me)")
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.pass_context
def remove(ctx, issue_key: str, user: str, dry_run: bool):
    """Remove a watcher from an issue (default: yourself)."""
    raise NotImplementedError


if __name__ == "__main__":
    cli()
