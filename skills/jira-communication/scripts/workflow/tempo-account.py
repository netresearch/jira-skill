#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Tempo Accounts (Server/DC) - create customers/accounts and link them to projects.

Tempo Accounts is a Jira plugin (rest/tempo-accounts/1/*), reachable with the
same Jira Personal Access Token this skill already uses elsewhere - no
separate credential. Requires the Tempo "Manage Accounts" permission, which
is independent of plain Jira project permissions.
"""

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
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (just the created key/id)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Tempo Accounts management.

    Create Tempo customers/accounts and link an account to a Jira project.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.group()
def customer():
    """Tempo customer (billing entity) management."""


@customer.command("create")
@click.argument("key")
@click.argument("name")
@click.option("--dry-run", is_flag=True, help="Show what would be created without making changes")
@click.pass_context
def customer_create(ctx, key: str, name: str, dry_run: bool):
    """Create a new Tempo customer.

    KEY: Short, stable customer key (e.g., NEWP)

    NAME: Full customer display name (e.g., "Example Customer GmbH")

    Example:

      tempo-account customer create NEWP "Example Customer GmbH"
    """
    client = ctx.obj["client"]

    if dry_run:
        warning("DRY RUN - No customer will be created")
        print("\nWould create Tempo customer:")
        print(f"  Key: {key}")
        print(f"  Name: {name}")
        return

    try:
        result = client.tempo_account_add_new_customer(key, name)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to create Tempo customer: {e}")
        sys.exit(1)

    if ctx.obj["quiet"]:
        print(key)
    elif ctx.obj["json"]:
        format_output(result, as_json=True)
    else:
        success(f"Created Tempo customer: {name}")
        print(f"  Key: {key}")


@cli.group()
def account():
    """Tempo account (cost-tracking entity) management."""


@account.command("create")
@click.argument("key")
@click.argument("name")
@click.option("--lead", required=True, help="Username of the account lead")
@click.option("--customer-key", required=True, help="Key of an existing Tempo customer this account belongs to")
@click.option("--dry-run", is_flag=True, help="Show what would be created without making changes")
@click.pass_context
def account_create(ctx, key: str, name: str, lead: str, customer_key: str, dry_run: bool):
    """Create a new Tempo account.

    KEY: Short, stable account key (e.g., NEWP)

    NAME: Full account display name (e.g., "Example Customer GmbH")

    Requires an existing Tempo customer (see: tempo-account customer create).

    Example:

      tempo-account account create NEWP "Example Customer GmbH" --lead jane.doe --customer-key NEWP
    """
    client = ctx.obj["client"]

    data = {
        "key": key,
        "name": name,
        "lead": {"name": lead},
        "customer": {"key": customer_key},
    }

    if dry_run:
        warning("DRY RUN - No account will be created")
        print("\nWould create Tempo account:")
        print(f"  Key: {key}")
        print(f"  Name: {name}")
        print(f"  Lead: {lead}")
        print(f"  Customer: {customer_key}")
        return

    try:
        result = client.tempo_account_add_account(data)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to create Tempo account: {e}")
        sys.exit(1)

    if ctx.obj["quiet"]:
        account_id = result.get("id") if isinstance(result, dict) else None
        print(account_id if account_id is not None else key)
    elif ctx.obj["json"]:
        format_output(result, as_json=True)
    else:
        success(f"Created Tempo account: {name}")
        print(f"  Key: {key}")
        print(f"  Lead: {lead}")
        print(f"  Customer: {customer_key}")
        if isinstance(result, dict) and result.get("id") is not None:
            print(f"  Account ID: {result['id']}")
            print("  Note: use this Account ID with 'tempo-account account link' to attach it to a project.")


@account.command("link")
@click.argument("account_id", type=int)
@click.argument("project_key")
@click.option("--default", "default_account", is_flag=True, help="Mark this as the project's default account")
@click.option("--dry-run", is_flag=True, help="Show what would be linked without making changes")
@click.pass_context
def account_link(ctx, account_id: int, project_key: str, default_account: bool, dry_run: bool):
    """Link an existing Tempo account to a Jira project.

    ACCOUNT_ID: Numeric Tempo account id (printed by 'account create')

    PROJECT_KEY: Key of the Jira project to link the account to (e.g., NEWP)

    Example:

      tempo-account account link 42 NEWP --default
    """
    client = ctx.obj["client"]

    try:
        project = client.project(project_key)
    except Exception as e:
        error(f"Could not resolve project '{project_key}': {e}")
        sys.exit(1)

    project_id = project.get("id") if isinstance(project, dict) else None
    if not project_id:
        error(f"Project '{project_key}' has no numeric id in the API response")
        sys.exit(1)

    if dry_run:
        warning("DRY RUN - No link will be created")
        print("\nWould link Tempo account to project:")
        print(f"  Account ID: {account_id}")
        print(f"  Project: {project_key} (id={project_id})")
        print(f"  Default account: {default_account}")
        return

    try:
        result = client.tempo_account_associate_with_jira_project(
            account_id, project_id, default_account=default_account
        )
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to link Tempo account to project: {e}")
        sys.exit(1)

    if ctx.obj["quiet"]:
        print(project_key)
    elif ctx.obj["json"]:
        format_output(result, as_json=True)
    else:
        success(f"Linked Tempo account {account_id} to project {project_key}")
        if default_account:
            print("  Marked as default account")


if __name__ == "__main__":
    cli()
