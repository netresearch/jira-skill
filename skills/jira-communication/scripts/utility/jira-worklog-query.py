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

from datetime import date, datetime, timedelta, timezone

import click
from lib.client import LazyJiraClient
from lib.output import error, format_json, warning

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
    result = worklogs
    if user:

        def _match_user(wl: dict) -> bool:
            author = wl.get("author", {})
            return user in (
                author.get("name", ""),
                author.get("accountId", ""),
                author.get("displayName", ""),
            )

        result = [wl for wl in result if _match_user(wl)]
    if from_date:
        result = [wl for wl in result if wl.get("started", "")[:10] >= from_date]
    if to_date:
        result = [wl for wl in result if wl.get("started", "")[:10] <= to_date]
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting
# ═══════════════════════════════════════════════════════════════════════════════


def seconds_to_human(seconds: int) -> str:
    """Convert seconds to human-readable time (e.g., '2h 30m').

    Uses 8h workday for day calculation (Jira default).
    """
    if seconds <= 0:
        return "0m"
    days, remainder = divmod(seconds, 28800)  # 8h workday
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


def format_summary(worklogs: list[dict], issues: dict[str, str]) -> str:
    """Format worklogs as summary table grouped by issue."""
    if not worklogs:
        return "No worklogs found."

    # Group by issue
    by_issue: dict[str, int] = {}
    for wl in worklogs:
        key = wl.get("_issue_key", "Unknown")
        by_issue[key] = by_issue.get(key, 0) + wl.get("timeSpentSeconds", 0)

    lines = []
    lines.append(f"{'Issue':<14} {'Summary':<40} {'Time Spent':>10}")
    lines.append(f"{'-' * 14} {'-' * 40} {'-' * 10}")

    total_seconds = 0
    for key in sorted(by_issue):
        summary = issues.get(key, "")
        if len(summary) > 40:
            summary = summary[:37] + "..."
        seconds = by_issue[key]
        total_seconds += seconds
        lines.append(f"{key:<14} {summary:<40} {seconds_to_human(seconds):>10}")

    lines.append(f"{'':>14} {'':>40} {'─' * 10}")
    lines.append(f"{'':>14} {'Total:':>40} {seconds_to_human(total_seconds):>10}")
    return "\n".join(lines)


def format_detail(worklogs: list[dict]) -> str:
    """Format worklogs as detailed table with individual entries."""
    if not worklogs:
        return "No worklogs found."

    lines = []
    lines.append(f"{'Issue':<14} {'Date':<12} {'Author':<20} {'Time':>8} {'Comment'}")
    lines.append(f"{'-' * 14} {'-' * 12} {'-' * 20} {'-' * 8} {'-' * 30}")

    for wl in sorted(worklogs, key=lambda w: w.get("started", "")):
        key = wl.get("_issue_key", "Unknown")
        date_str = wl.get("started", "")[:10]
        author = wl.get("author", {}).get("displayName", "Unknown")
        if len(author) > 20:
            author = author[:17] + "..."
        time_str = seconds_to_human(wl.get("timeSpentSeconds", 0))
        comment = wl.get("comment", "")
        if isinstance(comment, dict):
            # ADF format — extract text
            from lib.output import extract_adf_text

            comment = extract_adf_text(comment)
        if len(comment) > 50:
            comment = comment[:47] + "..."
        lines.append(f"{key:<14} {date_str:<12} {author:<20} {time_str:>8} {comment}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetching
# ═══════════════════════════════════════════════════════════════════════════════


def search_issues(client, jql: str) -> list[dict]:
    """Search issues matching JQL, paginated. Returns list of {key, summary}."""
    issues = []
    start_at = 0
    page_size = 50
    while True:
        result = client.jql(jql, start=start_at, limit=page_size, fields="key,summary")
        for issue in result.get("issues", []):
            issues.append(
                {
                    "key": issue["key"],
                    "summary": issue.get("fields", {}).get("summary", ""),
                }
            )
        total = result.get("total", 0)
        start_at += page_size
        if start_at >= total:
            break
    return issues


def fetch_worklogs(client, issue_key: str, started_after: int, started_before: int) -> list[dict]:
    """Fetch worklogs for a single issue within time bounds. Returns raw worklog dicts."""
    result = client.issue_get_worklog(issue_key)
    worklogs = result.get("worklogs", [])
    # Tag each worklog with its issue key for later grouping
    for wl in worklogs:
        wl["_issue_key"] = issue_key
    return worklogs


def fetch_all_worklogs(client, issues: list[dict], from_date: str, to_date: str) -> list[dict]:
    """Fetch worklogs for all issues, with progress indicator."""
    # Convert dates to epoch ms for the API (used for potential future optimization)
    started_after = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    started_before = int(
        datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).timestamp()
        * 1000
    )

    total = len(issues)
    if total > 100:
        warning(f"Fetching worklogs for {total} issues — this may take a while...")

    all_worklogs = []
    for i, issue in enumerate(issues):
        if total > 10 and (i + 1) % 10 == 0:
            click.echo(f"  Fetching worklogs... {i + 1}/{total}", err=True)
        worklogs = fetch_worklogs(client, issue["key"], started_after, started_before)
        all_worklogs.extend(worklogs)

    return all_worklogs


# ═══════════════════════════════════════════════════════════════════════════════
# Tempo backend
# ═══════════════════════════════════════════════════════════════════════════════


def detect_tempo(client) -> bool:
    """Check if Tempo Timesheets plugin is available.

    Tries a minimal request to the Tempo REST API. Returns True if Tempo
    responds (200), False if the endpoint doesn't exist (404) or auth fails.
    """
    try:
        base_url = client.url.rstrip("/")
        url = f"{base_url}/rest/tempo-timesheets/4/worklogs"
        today = date.today().isoformat()
        params = {"dateFrom": today, "dateTo": today, "limit": 1}

        response = client._session.get(url, params=params, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def fetch_worklogs_tempo(
    client,
    from_date: str,
    to_date: str,
    user: str | None = None,
    project: str | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """Fetch worklogs from Tempo REST API with native date/user/project filtering.

    Returns (worklogs, issue_map) where worklogs are normalized to Jira format
    and issue_map maps issue keys to summaries.
    """
    base_url = client.url.rstrip("/")
    url = f"{base_url}/rest/tempo-timesheets/4/worklogs"
    params: dict = {
        "dateFrom": from_date,
        "dateTo": to_date,
        "limit": 1000,
        "offset": 0,
    }
    if user:
        params["worker"] = user
    if project:
        params["projectKey"] = project

    all_worklogs = []
    while True:
        response = client._session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Handle both array response and paginated object response
        if isinstance(data, list):
            entries = data
            all_worklogs.extend(normalize_tempo_worklog(wl) for wl in entries)
            break  # Array response = no pagination
        else:
            entries = data.get("results", data.get("worklogs", []))
            all_worklogs.extend(normalize_tempo_worklog(wl) for wl in entries)
            metadata = data.get("metadata", {})
            if not metadata.get("next"):
                break
            params["offset"] = metadata.get("offset", 0) + metadata.get("limit", 1000)

    # Build issue_map via batch JQL instead of N+1 individual fetches
    issue_keys = {wl["_issue_key"] for wl in all_worklogs if wl["_issue_key"] != "Unknown"}
    issue_map: dict[str, str] = {}
    if issue_keys:
        jql = f"issueKey in ({', '.join(sorted(issue_keys))})"
        try:
            found = search_issues(client, jql)
            issue_map = {i["key"]: i["summary"] for i in found}
        except Exception:
            # Fallback: empty summaries if batch fetch fails
            issue_map = {k: "" for k in issue_keys}

    return all_worklogs, issue_map


def normalize_tempo_worklog(tempo_wl: dict) -> dict:
    """Convert a Tempo worklog to Jira-compatible format.

    Normalizes field names and adds _issue_key so existing filter/format
    functions work unchanged.
    """
    started = tempo_wl.get("started", "")
    # Tempo returns date-only "2026-04-01"; pad to ISO timestamp for consistency
    if len(started) == 10:
        started = f"{started}T00:00:00.000+0000"

    return {
        "id": str(tempo_wl.get("tempoWorklogId", "")),
        "started": started,
        "timeSpentSeconds": tempo_wl.get("timeSpentSeconds", 0),
        "timeSpent": "",
        "comment": tempo_wl.get("comment", ""),
        "author": tempo_wl.get("author", {}),
        "_issue_key": tempo_wl.get("issue", {}).get("key", "Unknown"),
    }


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
@click.option(
    "--backend",
    type=click.Choice(["auto", "jira", "tempo"]),
    default="auto",
    help="Backend: auto (detect Tempo), jira (force JQL), tempo (force Tempo)",
)
def cli(
    from_date,
    to_date,
    user,
    project,
    issue,
    epic,
    sprint,
    detail,
    output_json,
    quiet,
    env_file,
    profile,
    debug,
    backend,
):
    """Query worklogs across issues with flexible filters.

    Default: current user's worklogs for the current week, grouped by issue.

    Examples:

      jira-worklog-query.py                          # my week
      jira-worklog-query.py --project HMKG            # my week on HMKG
      jira-worklog-query.py --from 2026-03-01 --to 2026-03-31 --detail
    """
    client = LazyJiraClient(env_file=env_file, profile=profile)

    try:
        # Resolve defaults
        today = date.today()
        if not from_date:
            monday = today - timedelta(days=today.weekday())
            from_date = monday.isoformat()
        if not to_date:
            to_date = today.isoformat()

        # Resolve user default
        effective_user = user
        if not effective_user:
            me = client.myself()
            effective_user = me.get("name") or me.get("accountId", "")

        # Parse issue list
        issue_list = [k.strip() for k in issue.split(",")] if issue else None

        # Determine backend
        use_tempo = False
        if backend == "tempo":
            use_tempo = True
        elif backend == "auto":
            use_tempo = detect_tempo(client)
            if use_tempo and debug:
                click.echo("Tempo detected — using Tempo API", err=True)

        if use_tempo:
            # Tempo path: native filtering, no JQL needed
            # Note: Tempo doesn't support issue/epic/sprint filters natively,
            # so we warn if those are specified
            if issue_list or epic or sprint:
                warning("Tempo backend does not support --issue, --epic, or --sprint filters. Ignoring them.")

            if debug:
                click.echo(f"Tempo query: {from_date} to {to_date}, user={effective_user}, project={project}", err=True)

            all_worklogs, issue_map = fetch_worklogs_tempo(
                client, from_date, to_date, user=effective_user, project=project
            )

            # Client-side filter (Tempo already filters by user/date/project,
            # but we still filter for consistency and to handle edge cases)
            filtered = filter_worklogs(all_worklogs, user=effective_user, from_date=from_date, to_date=to_date)
        else:
            # Jira REST path: JQL search + per-issue fetch
            jql = build_jql(
                from_date, to_date, user=effective_user, project=project, issues=issue_list, epic=epic, sprint=sprint
            )

            if debug:
                click.echo(f"JQL: {jql}", err=True)

            issues = search_issues(client, jql)

            if not issues:
                if output_json:
                    click.echo("[]")
                elif not quiet:
                    click.echo(f"No issues found with worklogs for {from_date} to {to_date}")
                return

            all_worklogs = fetch_all_worklogs(client, issues, from_date, to_date)
            filtered = filter_worklogs(all_worklogs, user=effective_user, from_date=from_date, to_date=to_date)
            issue_map = {i["key"]: i["summary"] for i in issues}

        # Handle empty results (common path for both backends)
        if not filtered:
            if output_json:
                click.echo("[]")
            elif not quiet:
                click.echo(f"No worklogs found for {from_date} to {to_date}")
            return

        # Output
        if output_json:
            click.echo(format_json(filtered))
        elif quiet:
            total_seconds = sum(wl.get("timeSpentSeconds", 0) for wl in filtered)
            click.echo(seconds_to_human(total_seconds))
        elif detail:
            backend_label = " (via Tempo)" if use_tempo else ""
            header = f"Worklogs for {effective_user} | {from_date} -> {to_date}{backend_label}"
            click.echo(header)
            click.echo()
            click.echo(format_detail(filtered))
        else:
            backend_label = " (via Tempo)" if use_tempo else ""
            header = f"Worklogs for {effective_user} | {from_date} -> {to_date}{backend_label}"
            click.echo(header)
            click.echo()
            click.echo(format_summary(filtered, issue_map))

    except Exception as e:
        if debug:
            raise
        error(f"Failed to query worklogs: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
