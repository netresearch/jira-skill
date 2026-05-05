#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
#     "requests>=2.31.0,<3",
# ]
# ///
"""Jira issue move - move issues between projects or change issue type."""

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
import requests
from lib.client import LazyJiraClient, _sanitize_error
from lib.output import error, format_output, success, warning

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (just new issue key)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira issue move.

    Change issue type within the same project.

    Cross-project moves are intentionally refused by this command because
    they are not safely supported via the standard issue edit endpoint
    (some Jira versions ignore project changes without error).
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command("issue")
@click.argument("issue_key")
@click.argument("target_project")
@click.option("--issue-type", "-t", help="Issue type in target project (default: keep current)")
@click.option("--dry-run", is_flag=True, help="Show what would happen without making changes")
@click.pass_context
def move_issue(ctx, issue_key: str, target_project: str, issue_type: str | None, dry_run: bool):
    """Change an issue's type within the same project.

    ISSUE_KEY: The Jira issue key to move (e.g., NRS-4301)

    TARGET_PROJECT: Target project key (e.g., SRVUC). Use the same project key
    to change issue type. Cross-project moves are refused.

    Examples:

      jira-move issue NRS-4301 PROJ --issue-type Task  (change type, same project)

      jira-move issue NRS-4301 NRS --issue-type Task --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Fetch current issue details
        issue = client.issue(issue_key, fields="summary,issuetype,status,project")
        fields = issue["fields"]
        current_project = fields["project"]["key"]
        current_type = fields["issuetype"]["name"]
        summary = fields["summary"]
        status = fields["status"]["name"]

        same_project = current_project.upper() == target_project.upper()

        if same_project and not issue_type:
            error(f"{issue_key} is already in project {target_project} (use --issue-type to change type)")
            sys.exit(1)

        target_type = issue_type or current_type

        if same_project and target_type == current_type:
            error(f"{issue_key} is already type {current_type} in project {target_project}")
            sys.exit(1)

        # IMPORTANT: Cross-project moves are NOT safely supported via the standard
        # issue edit endpoint. Refuse even for --dry-run so we never preview an
        # operation this command will not execute.
        if not same_project:
            error(
                "Cross-project move is not supported safely by this command yet. "
                "Refusing to proceed to avoid partial moves. "
                "Use the Jira UI Move action (or implement bulk move API support)."
            )
            sys.exit(1)

        # Dry run (same project only — cross-project moves are refused above)
        if dry_run:
            warning("DRY RUN - No changes will be made")
            print(f"\nWould change type of {issue_key}:")
            print(f"  Summary:  {summary}")
            print(f"  From:     {current_type}")
            print(f"  To:       {target_type}")
            print(f"  Status:   {status}")
            return

        # Use the REST API directly — atlassian-python-api doesn't have a move method.
        #
        # IMPORTANT: Cross-project moves are NOT safely supported via the standard
        # issue edit endpoint. Some Jira Server/DC versions silently ignore
        # `project` updates, which looks like success but leaves the issue in the
        # old project with a changed issue type (data corruption).
        # PUT /rest/api/2/issue/{issueKey} with issuetype change (same project)
        update_fields = {"fields": {"issuetype": {"name": target_type}}}

        url = f"{client.url}/rest/api/2/issue/{issue_key}"
        # atlassian-python-api has no public method for issue move/edit.
        # Using _session directly is intentional; version range (>=3.41.0,<4) in
        # PEP 723 header guards against breaking changes across major versions.
        response = client._session.put(url, json=update_fields)

        if response.status_code == 204:
            # Verify the update actually applied (defense against silent failures)
            refreshed = client.issue(issue_key, fields="issuetype,project")
            refreshed_fields = refreshed.get("fields") or {}
            refreshed_type = (refreshed_fields.get("issuetype") or {}).get("name")
            refreshed_project = (refreshed_fields.get("project") or {}).get("key")
            if refreshed_project and refreshed_project.upper() != current_project.upper():
                error(
                    f"Move verification failed: issue ended up in unexpected project "
                    f"{refreshed_project} (expected {current_project})"
                )
                sys.exit(1)
            if refreshed_type and refreshed_type != target_type:
                error(f"Type verification failed: issue is type {refreshed_type} (expected {target_type})")
                sys.exit(1)
            # Type change within same project — key stays the same
            if ctx.obj["quiet"]:
                print(issue_key)
            elif ctx.obj["json"]:
                format_output(
                    {
                        "key": issue_key,
                        "old_type": current_type,
                        "new_type": target_type,
                        "project": current_project,
                        "summary": summary,
                    },
                    as_json=True,
                )
            else:
                success(f"Changed {issue_key} type: {current_type} → {target_type}")
                print(f"  Summary:    {summary}")
        elif response.status_code == 400:
            # Common: issue type not available in target project
            detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            errors = detail.get("errors", {})
            error_msgs = detail.get("errorMessages", [])
            msg = "; ".join(error_msgs) if error_msgs else "; ".join(f"{k}: {v}" for k, v in errors.items())
            error(f"Cannot move {issue_key} to {target_project}: {msg}")
            if "issuetype" in str(errors).lower() or "issue type" in msg.lower():
                print("\nHint: Use --issue-type to specify a valid type in the target project")
            sys.exit(1)
        else:
            response.raise_for_status()

    except requests.HTTPError as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to move {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to move {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
