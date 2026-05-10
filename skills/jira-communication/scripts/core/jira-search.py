#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira search operations - query issues using JQL."""

import re
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
from lib.output import error, format_output, format_table, warning

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output (keys only)")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name from ~/.jira/profiles.json")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
@click.pass_context
def cli(ctx, output_json: bool, quiet: bool, env_file: str | None, profile: str | None, debug: bool):
    """Jira search operations.

    Query Jira issues using JQL (Jira Query Language).
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)
# Strip 'single-quoted' and "double-quoted" string literals so values
# like `summary ~ 'order by'` don't trip the ORDER BY detector.
_QUOTED_RE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")


def _has_top_level_order_by(jql: str) -> bool:
    """True if JQL contains a real ORDER BY clause (ignores quoted literals)."""
    return bool(_ORDER_BY_RE.search(_QUOTED_RE.sub("", jql)))


def _append_order_by(jql: str, order_by_clauses: tuple[str, ...]) -> str:
    """Append --order-by clauses to a JQL string.

    Errors if the JQL already contains an ORDER BY (case-insensitive,
    ignoring quoted string literals so `summary ~ 'order by'` does not
    trigger). The user has to choose one form because concatenation would
    produce invalid JQL.
    """
    if not order_by_clauses:
        return jql
    if _has_top_level_order_by(jql):
        raise click.UsageError(
            "JQL already contains 'ORDER BY'; pass either --order-by or embed "
            "ORDER BY in the JQL, not both. "
            "Tip: ORDER BY can also be embedded directly in the JQL string."
        )
    cleaned: list[str] = []
    for clause in order_by_clauses:
        clause = (clause or "").strip()
        if not clause:
            raise click.UsageError(
                '--order-by requires a non-empty value, e.g. --order-by "updated DESC". '
                "Tip: ORDER BY can also be embedded directly in the JQL string."
            )
        cleaned.append(clause)
    return f"{jql.rstrip()} ORDER BY {', '.join(cleaned)}"


@cli.command()
@click.argument("jql")
@click.option("--max-results", "-n", default=50, help="Maximum results to return")
@click.option("--fields", "-f", default="key,summary,status,assignee,priority", help="Comma-separated fields to return")
@click.option(
    "--start-at",
    default=0,
    type=click.IntRange(min=0),
    help="Starting index for pagination (0-based)",
)
@click.option("--truncate", type=int, metavar="N", help="Truncate field values to N characters")
@click.option(
    "--order-by",
    "order_by",
    multiple=True,
    metavar="FIELD [ASC|DESC]",
    help=(
        'Append an ORDER BY clause to the JQL (e.g. "updated DESC"). '
        "Repeatable for multi-key sorts. Errors if the JQL already contains ORDER BY. "
        "Tip: ORDER BY can also be embedded directly in the JQL string."
    ),
)
@click.pass_context
def query(
    ctx,
    jql: str,
    max_results: int,
    fields: str,
    start_at: int,
    truncate: int | None,
    order_by: tuple[str, ...],
):
    """Search issues using JQL.

    JQL: Jira Query Language query string (passed directly to Jira API — treat as trusted input)

    Examples:

      jira-search query "project = PROJ AND status = 'In Progress'"

      jira-search query "assignee = currentUser()" --max-results 20

      jira-search query "project = PROJ" --order-by "updated DESC"

      jira-search query "project = PROJ" --order-by "priority DESC" --order-by "created ASC"

      jira-search --json query "updated >= -7d"

      jira-search --quiet query "labels = urgent"

    Common JQL patterns:

      project = PROJ                    # Issues in project
      assignee = currentUser()          # My issues
      status = "In Progress"            # By status
      updated >= -7d                    # Updated last 7 days
      sprint in openSprints()           # Current sprint
      labels = backend                  # By label
      priority = High                   # By priority

    Sorting:

      ORDER BY can be embedded directly in the JQL string
      (e.g. "project = PROJ ORDER BY updated DESC") or supplied via the
      --order-by flag. Use one form or the other, not both.
    """
    client = ctx.obj["client"]

    try:
        jql = _append_order_by(jql, order_by)
    except click.UsageError as e:
        error(str(e))
        sys.exit(2)

    field_list = [f.strip() for f in fields.split(",")]

    try:
        results = client.jql(jql, limit=max_results, start=start_at, fields=field_list)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Search failed: {e}")
        sys.exit(1)

    issues = results.get("issues", [])
    total = results.get("total")
    _warn_if_capped(issues, total, max_results, start_at)
    _emit_query_output(ctx, issues, field_list, truncate, total, start_at)


def _warn_if_capped(issues: list, total, max_results: int, start_at: int) -> None:
    if isinstance(total, int) and max_results > len(issues) and (start_at + len(issues)) < total:
        warning(
            f"Server capped results: requested --max-results {max_results}, "
            f"received {len(issues)} (total matches: {total}). "
            "Use pagination with --start-at to fetch further pages."
        )


def _emit_query_output(ctx, issues: list, field_list: list, truncate: int | None, total, start_at: int) -> None:
    """Render search results in json / quiet / table form."""
    if ctx.obj["json"]:
        format_output(issues, as_json=True)
        return
    if ctx.obj["quiet"]:
        for issue in issues:
            print(issue["key"])
        return
    if total is None:
        total = len(issues)
    if not issues:
        if total > 0:
            print(f"No issues on this page (total: {total}). Try a smaller --start-at.")
        else:
            print("No issues found")
        return
    _print_results_table(issues, field_list, truncate=truncate)
    issue_label = "issue" if total == 1 else "issues"
    print(f"\n(showing {start_at + 1}-{start_at + len(issues)} of {total} {issue_label})")


def _print_results_table(issues: list, fields: list, truncate: int | None = None) -> None:
    """Print search results as a table.

    Args:
        issues: List of issue dicts from Jira API
        fields: List of field names to display
        truncate: If set, truncate field values to this many characters
    """
    # Build table data
    rows = []
    for issue in issues:
        row = {"key": issue["key"]}
        issue_fields = issue.get("fields", {})

        for field in fields:
            if field == "key":
                continue

            value = issue_fields.get(field)

            # Handle nested objects
            if isinstance(value, dict):
                if "name" in value:
                    value = value["name"]
                elif "displayName" in value:
                    value = value["displayName"]
                elif "value" in value:
                    value = value["value"]
                else:
                    value = str(value)
            elif isinstance(value, list):
                value = ", ".join(str(v) for v in value[:3])
                if len(issue_fields.get(field, [])) > 3:
                    value += "..."
            elif value is None:
                value = "-"
            else:
                value = str(value)

            # Truncate if requested
            if truncate and len(str(value)) > truncate:
                value = str(value)[: truncate - 3] + "..."

            row[field] = value

        rows.append(row)

    # Print table
    columns = ["key"] + [f for f in fields if f != "key"]
    print(format_table(rows, columns))


if __name__ == "__main__":
    cli()
