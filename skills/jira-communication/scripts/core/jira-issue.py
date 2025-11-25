#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0",
#     "click>=8.1.0",
# ]
# ///
"""Jira issue operations - get and update issue details."""

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
from lib.client import get_jira_client
from lib.output import format_output, success, error, warning

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════

@click.group()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--quiet', '-q', is_flag=True, help='Minimal output')
@click.option('--env-file', type=click.Path(), help='Environment file path')
@click.option('--debug', is_flag=True, help='Show debug information on errors')
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, debug: bool):
    """Jira issue operations.

    Get and update Jira issue details.
    """
    ctx.ensure_object(dict)
    ctx.obj['json'] = output_json
    ctx.obj['quiet'] = quiet
    ctx.obj['debug'] = debug
    try:
        ctx.obj['client'] = get_jira_client(env_file)
    except Exception as e:
        if debug:
            raise
        error(str(e))
        sys.exit(1)


@cli.command()
@click.argument('issue_key')
@click.option('--fields', '-f', help='Comma-separated fields to return')
@click.option('--expand', '-e', help='Fields to expand (changelog,transitions,renderedFields)')
@click.pass_context
def get(ctx, issue_key: str, fields: str | None, expand: str | None):
    """Get issue details.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue get PROJ-123

      jira-issue get PROJ-123 --fields summary,status,assignee

      jira-issue get PROJ-123 --expand changelog,transitions
    """
    client = ctx.obj['client']

    try:
        # Build parameters
        params = {}
        if fields:
            params['fields'] = fields.split(',')
        if expand:
            params['expand'] = expand

        issue = client.issue(issue_key, **params)

        if ctx.obj['json']:
            format_output(issue, as_json=True)
        elif ctx.obj['quiet']:
            print(issue['key'])
        else:
            _print_issue(issue)

    except Exception as e:
        if ctx.obj['debug']:
            raise
        error(f"Failed to get issue {issue_key}: {e}")
        sys.exit(1)


def _print_issue(issue: dict) -> None:
    """Pretty print issue details."""
    fields = issue.get('fields', {})

    print(f"\n{issue['key']}: {fields.get('summary', 'No summary')}")
    print("=" * 60)

    # Status and type
    status = fields.get('status', {}).get('name', 'Unknown')
    issue_type = fields.get('issuetype', {}).get('name', 'Unknown')
    priority = fields.get('priority', {}).get('name', 'None')
    print(f"Type: {issue_type} | Status: {status} | Priority: {priority}")

    # Assignee and reporter
    assignee = fields.get('assignee', {})
    reporter = fields.get('reporter', {})
    assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
    reporter_name = reporter.get('displayName', 'Unknown') if reporter else 'Unknown'
    print(f"Assignee: {assignee_name} | Reporter: {reporter_name}")

    # Labels
    labels = fields.get('labels', [])
    if labels:
        print(f"Labels: {', '.join(labels)}")

    # Description
    description = fields.get('description')
    if description:
        print(f"\nDescription:")
        # Handle both string and ADF format
        if isinstance(description, str):
            desc_text = description
        elif isinstance(description, dict):
            # ADF format - extract text content
            desc_text = _extract_adf_text(description)
        else:
            desc_text = str(description)

        # Truncate if too long
        if len(desc_text) > 500:
            desc_text = desc_text[:497] + "..."
        print(f"  {desc_text}")

    # Dates
    created = fields.get('created', '')[:10] if fields.get('created') else 'N/A'
    updated = fields.get('updated', '')[:10] if fields.get('updated') else 'N/A'
    print(f"\nCreated: {created} | Updated: {updated}")
    print()


def _extract_adf_text(adf: dict) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not isinstance(adf, dict):
        return str(adf)

    text_parts = []
    content = adf.get('content', [])

    for block in content:
        if block.get('type') == 'paragraph':
            for item in block.get('content', []):
                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
        elif block.get('type') == 'text':
            text_parts.append(block.get('text', ''))

    return ' '.join(text_parts)


@cli.command()
@click.argument('issue_key')
@click.option('--summary', '-s', help='New summary')
@click.option('--priority', '-p', help='Priority name')
@click.option('--labels', '-l', help='Comma-separated labels (replaces existing)')
@click.option('--assignee', '-a', help='Assignee username or email')
@click.option('--fields-json', help='JSON string of additional fields to update')
@click.option('--dry-run', is_flag=True, help='Show what would be updated without making changes')
@click.pass_context
def update(ctx, issue_key: str, summary: str | None, priority: str | None,
           labels: str | None, assignee: str | None, fields_json: str | None,
           dry_run: bool):
    """Update issue fields.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Examples:

      jira-issue update PROJ-123 --summary "New title"

      jira-issue update PROJ-123 --priority High --labels backend,urgent

      jira-issue update PROJ-123 --fields-json '{"customfield_10001": "value"}'

      jira-issue update PROJ-123 --summary "Test" --dry-run
    """
    client = ctx.obj['client']

    # Build update payload
    update_fields = {}

    if summary:
        update_fields['summary'] = summary

    if priority:
        update_fields['priority'] = {'name': priority}

    if labels:
        update_fields['labels'] = [l.strip() for l in labels.split(',')]

    if assignee:
        # Handle different assignee formats
        if '@' in assignee:
            update_fields['assignee'] = {'emailAddress': assignee}
        else:
            update_fields['assignee'] = {'name': assignee}

    if fields_json:
        try:
            extra_fields = json.loads(fields_json)
            update_fields.update(extra_fields)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in --fields-json: {e}")
            sys.exit(1)

    if not update_fields:
        error("No fields specified for update")
        click.echo("\nUse one or more of: --summary, --priority, --labels, --assignee, --fields-json")
        sys.exit(1)

    if dry_run:
        warning("DRY RUN - No changes will be made")
        print(f"\nWould update {issue_key} with:")
        for key, value in update_fields.items():
            print(f"  {key}: {value}")
        return

    try:
        client.update_issue_field(issue_key, update_fields)

        if ctx.obj['quiet']:
            print(issue_key)
        elif ctx.obj['json']:
            format_output({'key': issue_key, 'updated': list(update_fields.keys())}, as_json=True)
        else:
            success(f"Updated {issue_key}")
            for key in update_fields:
                print(f"  ✓ {key}")

    except Exception as e:
        if ctx.obj['debug']:
            raise
        error(f"Failed to update {issue_key}: {e}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
