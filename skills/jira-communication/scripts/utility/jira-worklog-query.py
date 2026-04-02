#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Cross-cutting worklog query — fetch worklogs by date range, user, project, and more."""

import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Shared library import
# ═══════════════════════════════════════════════════════════════════════════════
_script_dir = Path(__file__).parent
_lib_path = _script_dir.parent / "lib"
if _lib_path.exists():
    sys.path.insert(0, str(_lib_path.parent))

import click

# ═══════════════════════════════════════════════════════════════════════════════
# Query building
# ═══════════════════════════════════════════════════════════════════════════════


def build_jql(
    from_date: str,
    to_date: str,
    user: str | None = None,
    project: str | None = None,
    issues: list[str] | None = None,
    epic: str | None = None,
    sprint: str | None = None,
) -> str:
    """Build JQL query from worklog filters."""
    clauses = [
        f'worklogDate >= "{from_date}"',
        f'worklogDate <= "{to_date}"',
    ]
    if user:
        clauses.append(f'worklogAuthor = "{user}"')
    if project:
        clauses.append(f'project = "{project}"')
    if issues:
        quoted = ", ".join(f'"{k}"' for k in issues)
        clauses.append(f"issueKey in ({quoted})")
    if epic:
        clauses.append(f'"Epic Link" = "{epic}"')
    if sprint:
        if sprint.isdigit():
            clauses.append(f"sprint = {sprint}")
        else:
            clauses.append(f'sprint = "{sprint}"')
    return " AND ".join(clauses)


# ═══════════════════════════════════════════════════════════════════════════════
# Filtering
# ═══════════════════════════════════════════════════════════════════════════════


def filter_worklogs(
    worklogs: list[dict],
    user: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Client-side filter worklogs by author and date range."""
    raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════════════════


def seconds_to_human(seconds: int) -> str:
    """Convert seconds to human-readable time (e.g., '2h 30m')."""
    raise NotImplementedError


def format_summary(worklogs: list[dict], issues: dict[str, str]) -> str:
    """Format worklogs as summary table grouped by issue."""
    raise NotImplementedError


def format_detail(worklogs: list[dict]) -> str:
    """Format worklogs as detailed table with individual entries."""
    raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetching
# ═══════════════════════════════════════════════════════════════════════════════


def search_issues(client, jql: str) -> list[dict]:
    """Search issues matching JQL, paginated. Returns list of {key, summary}."""
    raise NotImplementedError


def fetch_worklogs(client, issue_key: str, started_after: int, started_before: int) -> list[dict]:
    """Fetch worklogs for a single issue within time bounds. Returns raw worklog dicts."""
    raise NotImplementedError


def fetch_all_worklogs(client, issues: list[dict], from_date: str, to_date: str) -> list[dict]:
    """Fetch worklogs for all issues, with progress indicator."""
    raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Definition
# ═══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option("--from", "from_date", help="Start date YYYY-MM-DD (default: Monday of current week)")
@click.option("--to", "to_date", help="End date YYYY-MM-DD (default: today)")
@click.option("--user", help="Username or accountId (default: current user)")
@click.option("--project", help="Project key (e.g., HMKG)")
@click.option("--issue", help="Issue key(s), comma-separated")
@click.option("--epic", help="Epic key (e.g., HMKG-1940)")
@click.option("--sprint", help="Sprint name or ID")
@click.option("--detail", is_flag=True, help="Show individual worklog entries")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.option("--env-file", type=click.Path(), help="Environment file path")
@click.option("--profile", "-P", help="Jira profile name")
@click.option("--debug", is_flag=True, help="Show debug information on errors")
def cli(from_date, to_date, user, project, issue, epic, sprint, detail, output_json, quiet, env_file, profile, debug):
    """Query worklogs across issues with flexible filters.

    Default: current user's worklogs for the current week, grouped by issue.

    Examples:

      jira-worklog-query.py                          # my week
      jira-worklog-query.py --project HMKG            # my week on HMKG
      jira-worklog-query.py --from 2026-03-01 --to 2026-03-31 --detail
    """
    pass


if __name__ == "__main__":
    cli()
