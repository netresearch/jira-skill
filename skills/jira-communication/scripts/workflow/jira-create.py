#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira issue creation - create new issues with various types and fields."""

import json
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
from lib.client import LazyJiraClient, resolve_assignee, resolve_subtask_type
from lib.input import read_stdin_utf8
from lib.output import error, format_output, success, warning

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (just issue key)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira issue creation.

    Create new Jira issues with various types and configurations.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command()
@click.argument("project_key")
@click.argument("summary")
@click.option("--type", "-t", "issue_type", required=True, help="Issue type (Task, Bug, Story, Epic, etc.)")
@click.option("--description", "-d", help="Issue description (Jira wiki markup; '-' reads from stdin)")
@click.option("--priority", "-p", help="Priority name (High, Medium, Low, etc.)")
@click.option("--labels", "-l", help="Comma-separated labels")
@click.option("--assignee", "-a", help="Assignee username or email")
@click.option("--reporter", "-r", help="Reporter username or email")
@click.option("--parent", help="Parent issue key (creates a subtask)")
@click.option("--components", help="Comma-separated component names")
@click.option("--fields-json", help="JSON string of additional fields")
@click.option("--dry-run", is_flag=True, help="Show what would be created without making changes")
@click.pass_context
def issue(
    ctx,
    project_key: str,
    summary: str,
    issue_type: str,
    description: str | None,
    priority: str | None,
    labels: str | None,
    assignee: str | None,
    reporter: str | None,
    parent: str | None,
    components: str | None,
    fields_json: str | None,
    dry_run: bool,
):
    """Create a new Jira issue.

    PROJECT_KEY: The Jira project key (e.g., PROJ)

    SUMMARY: Issue summary/title

    Examples:

      jira-create issue PROJ "Fix login timeout" --type Bug --priority High

      jira-create issue PROJ "New feature" --type Story --parent PROJ-100

      jira-create issue PROJ "API documentation" --type Task -d "Update API docs" -l docs,api

      jira-create issue PROJ "Bug from QA" --type Bug --reporter jane.doe

      jira-create issue PROJ "Sprint goal" --type Epic

      jira-create issue PROJ "Test" --type Task --dry-run
    """
    client = ctx.obj["client"]

    # Build issue fields
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }

    if description == "-":
        # Same convention as `jira-issue update`. Without this, "-" was stored
        # verbatim and the issue was created with a one-character description —
        # the create call still reported success, so the loss surfaced only when
        # someone opened the ticket.
        if sys.stdin.isatty():
            error(
                "'-' requires piped input but stdin is a terminal",
                suggestion="Usage: cat body.txt | jira-create issue PROJ 'Summary' --description -",
            )
            sys.exit(1)
        max_size = 256 * 1024  # 256KB, above Jira's description limit
        try:
            description = read_stdin_utf8(max_size + 1)
        except UnicodeDecodeError:
            error(
                "stdin contains invalid text encoding (expected UTF-8)",
                suggestion="Ensure the piped file is valid UTF-8 text, not binary data.",
            )
            sys.exit(1)
        if len(description) > max_size:
            error(
                f"description from stdin exceeds {max_size} bytes",
                suggestion="Truncate the input or split it across a create plus an update.",
            )
            sys.exit(1)
        description = description.rstrip("\n")

    if description:
        fields["description"] = description

    if priority:
        fields["priority"] = {"name": priority}

    if labels:
        fields["labels"] = [lbl.strip() for lbl in labels.split(",")]

    if assignee:
        fields["assignee"] = resolve_assignee(client, assignee)

    if reporter:
        fields["reporter"] = resolve_assignee(client, reporter)

    if parent:
        # Resolve issue type to a valid subtask type for the target project
        resolved_type = resolve_subtask_type(client, project_key, issue_type)
        if resolved_type is None:
            error(
                f"Project {project_key} has no subtask issue types matching '{issue_type}'",
                suggestion=f"Run: uv run scripts/utility/jira-fields.py types {project_key} to list available types",
            )
            sys.exit(1)
        if resolved_type != issue_type:
            warning(f"Resolved issue type '{issue_type}' → '{resolved_type}' (subtask type for {project_key})")
            fields["issuetype"] = {"name": resolved_type}
            issue_type = resolved_type
        fields["parent"] = {"key": parent}

    if components:
        fields["components"] = [{"name": c.strip()} for c in components.split(",")]

    if fields_json:
        try:
            extra_fields = json.loads(fields_json)
            fields.update(extra_fields)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in --fields-json: {e}")
            sys.exit(1)

    # Dry run
    if dry_run:
        warning("DRY RUN - No issue will be created")
        print(f"\nWould create issue in {project_key}:")
        print(f"  Type: {issue_type}")
        print(f"  Summary: {summary}")
        if description:
            print(f"  Description: {description[:50]}...")
        if priority:
            print(f"  Priority: {priority}")
        if labels:
            print(f"  Labels: {labels}")
        if assignee:
            print(f"  Assignee: {assignee}")
        if reporter:
            print(f"  Reporter: {reporter}")
        if parent:
            print(f"  Parent: {parent}")
        if components:
            print(f"  Components: {components}")
        return

    try:
        result = client.create_issue(fields=fields)

        if ctx.obj["quiet"]:
            print(result["key"])
        elif ctx.obj["json"]:
            format_output(result, as_json=True)
        else:
            success(f"Created issue: {result['key']}")
            print(f"  Summary: {summary}")
            print(f"  Type: {issue_type}")
            print(f"  URL: {client.url}/browse/{result['key']}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to create issue: {e}")
        sys.exit(1)


@cli.command()
@click.argument("key")
@click.argument("name")
@click.option(
    "--from-project",
    "source_project",
    required=True,
    help="Key or ID of an existing project whose configuration (schemes) to copy",
)
@click.option("--lead", required=True, help="Username of the new project's lead")
@click.option(
    "--bootstrap-issues",
    is_flag=True,
    help="Create the XXX-1 config-hub issue ('Projektmanagement') after project creation",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip the historical-key-collision check (see below) and proceed anyway",
)
@click.option("--dry-run", is_flag=True, help="Show what would be created without making changes")
@click.pass_context
def project(
    ctx,
    key: str,
    name: str,
    source_project: str,
    lead: str,
    bootstrap_issues: bool,
    force: bool,
    dry_run: bool,
):
    """Create a new Jira project by copying configuration from an existing project.

    KEY: The new project's key (e.g., NEWP)

    NAME: The new project's display name (e.g., "Example Customer GmbH")

    Uses Jira's "shared configuration" mechanism (the same one behind the UI's
    "Share settings with an existing project" option) to copy the permission,
    notification and workflow schemes from --from-project, so the new project
    matches an existing convention without manually specifying scheme IDs.

    Before creating, checks whether KEY-1 already resolves to an issue. Jira
    keeps project-key renames as permanent redirects (rename a project's key
    and its old key still resolves to the same issues forever) — reusing an
    old, renamed-away key silently skips however many issue numbers that key
    already used, so the new project's first bootstrap issue would NOT be
    KEY-1. Use --force to proceed anyway if this is expected.

    Examples:

      jira-create project NEWP "Example Customer GmbH" --from-project TMPL --lead jane.doe

      jira-create project OPSNEWP "OPS Example Customer GmbH" --from-project OPS --lead jane.doe --bootstrap-issues
    """
    client = ctx.obj["client"]

    try:
        source = client.project(source_project)
    except Exception as e:
        error(f"Could not resolve --from-project '{source_project}': {e}")
        sys.exit(1)

    source_id = source.get("id") if isinstance(source, dict) else None
    if not source_id:
        error(f"Project '{source_project}' has no numeric id in the API response")
        sys.exit(1)

    collision = _check_key_collision(client, key)
    if collision and not force:
        error(
            f"'{key}-1' already resolves to an existing issue ({collision}). "
            f"This key was likely used by a project since renamed away from it — Jira will "
            f"silently skip numbering, so the new project's first issue would NOT be {key}-1. "
            f"Pick a different key, or pass --force to proceed anyway."
        )
        sys.exit(1)
    elif collision:
        warning(f"Proceeding despite '{key}-1' already resolving to {collision} (--force)")

    if dry_run:
        warning("DRY RUN - No project will be created")
        print("\nWould create project:")
        print(f"  Key: {key}")
        print(f"  Name: {name}")
        print(f"  Lead: {lead}")
        print(f"  Copying schemes from: {source_project} (id={source_id})")
        if bootstrap_issues:
            print(f"  Would create bootstrap issue: {key}-1 (Projektmanagement, Issue Number One)")
        return

    try:
        result = client.create_project_from_shared_template(source_id, key, name, lead)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to create project: {e}")
        sys.exit(1)

    if ctx.obj["quiet"]:
        print(key)
    elif ctx.obj["json"]:
        format_output(result, as_json=True)
    else:
        success(f"Created project: {key}")
        print(f"  Name: {name}")
        print(f"  Lead: {lead}")
        print(f"  Configuration copied from: {source_project}")
        print(f"  URL: {client.url}/browse/{key}")

    if bootstrap_issues:
        _create_bootstrap_issues(client, key, ctx.obj)


def _check_key_collision(client, key: str) -> str | None:
    """Check whether KEY-1 already resolves to an issue from a different project.

    Jira preserves a permanent key->issue redirect when a project is renamed,
    so an old, renamed-away key can be reused for a brand-new project, but
    the issue-numbering counter for that key still silently skips whatever
    numbers the old project already used. This is only detectable by probing
    KEY-1 before creation — Jira gives no warning otherwise.

    Returns a human-readable "FOUND-KEY (project NAME)" description if a
    collision is detected, else None. Never raises — a failure of this
    diagnostic-only check must not block project creation.
    """
    try:
        result = client.jql(f'key = "{key}-1"', fields=["summary", "project"], limit=1)
        issues = result.get("issues", [])
        if not issues:
            return None
        found = issues[0]
        found_key = found.get("key", "?")
        found_project = found.get("fields", {}).get("project", {}).get("key", "?")
        return f"{found_key} (project {found_project})"
    except Exception:
        return None


def _create_bootstrap_issues(client, project_key: str, ctx_obj: dict) -> None:
    """Create the XXX-1 convention issue (Config Hub / "Projektmanagement").

    Matches the NR-wide "New project structure — first issue" convention.

    Uses this instance's dedicated "Issue Number One" issue type
    (purpose-built for exactly this "config hub" role) rather than a plain
    Task, with summary "Projektmanagement" per NR convention. Falls back to
    Task if a --from-project template's issue type scheme doesn't include
    it — issue type schemes vary per template and this issue existing at all
    matters more than its exact type.
    """
    config_hub_description = "Mail-Handler-Adressen, Matrix-Webhook-URL und weitere Projekt-Einstellungen."

    def _config_hub_fields(issue_type: str) -> dict:
        return {
            "project": {"key": project_key},
            "summary": "Projektmanagement",
            "issuetype": {"name": issue_type},
            "description": config_hub_description,
        }

    def _report_created(issue_key: str) -> None:
        """Announce the bootstrap issue without corrupting machine-readable output.

        `success()` writes to stdout, so emitting it under `--json` or `--quiet`
        would append a `✓` line to the payload the caller is parsing.
        """
        if ctx_obj.get("quiet") or ctx_obj.get("json"):
            return
        success(f"Created {issue_key}: Projektmanagement")

    try:
        result = client.create_issue(fields=_config_hub_fields("Issue Number One"))
        _report_created(result["key"])
    except Exception as e:
        warning(f"'Issue Number One' type unavailable, falling back to Task: {e}")
        try:
            result = client.create_issue(fields=_config_hub_fields("Task"))
            _report_created(result["key"])
        except Exception as e2:
            warning(f"Could not create bootstrap issue 'Projektmanagement': {e2}")


if __name__ == "__main__":
    cli()
