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
from datetime import date as _date
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


def _validate_iso_date(s: str) -> str:
    """Validate an ISO date string (YYYY-MM-DD) and return it unchanged.

    Jira rejects full timestamps like `2026-05-31T00:00:00Z` with a 400 on
    version start/release dates. This helper enforces the date-only shape
    client-side with a clear error. ``date.fromisoformat`` (Python 3.10) accepts
    only the strict ``YYYY-MM-DD`` shape, which is exactly what Jira requires.
    """
    if not isinstance(s, str):
        raise click.BadParameter(f'Expected YYYY-MM-DD, got "{s}". Timestamps are not allowed.')
    try:
        _date.fromisoformat(s)
    except ValueError as e:
        raise click.BadParameter(f'Expected YYYY-MM-DD, got "{s}" ({e}).') from e
    return s


def _validate_numeric_id(value: str, label: str = "version ID") -> str:
    """Reject non-numeric IDs so they cannot be interpolated into REST paths.

    The Jira REST surface treats version IDs as positional path segments
    (``/version/{id}``, ``/version/{src}/mergeto/{dst}``). A non-numeric value
    such as ``../../issue/KEY`` would otherwise traverse to a different
    resource. All callers feeding user input into a path must validate first.
    """
    if not isinstance(value, str) or not value.isdigit():
        raise click.BadParameter(f'{label} must be numeric, got "{value}".')
    return value


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


@cli.command("list")
@click.argument("project_key")
@click.option(
    "--status",
    type=click.Choice(["released", "unreleased", "archived", "all"]),
    default="unreleased",
    help="Filter by status",
)
@click.option("--query", help="Filter by name substring (paginated endpoint)")
@click.option(
    "--order-by",
    type=click.Choice(["sequence", "name", "startDate", "releaseDate"]),
    help="Sort order (paginated endpoint)",
)
@click.pass_context
def list_versions(ctx, project_key: str, status: str, query: str | None, order_by: str | None):
    """List versions in a project.

    Uses the flat `/project/{key}/versions` endpoint unless --query or --order-by
    is provided, in which case it switches to the paginated endpoint.
    """
    client = ctx.obj["client"]
    try:
        if query or order_by:
            try:
                versions = _fetch_versions_paginated(client, project_key, status=status, query=query, order_by=order_by)
            except Exception as paginated_err:
                # Older Jira DC (<9.x) returns 404 for /project/{key}/version.
                # Fall back to the flat endpoint and apply --query / --order-by
                # client-side so the user still gets a useful result.
                resp_status = getattr(getattr(paginated_err, "response", None), "status_code", None)
                if resp_status != 404:
                    raise
                warning(
                    "Paginated /project/{key}/version endpoint returned 404; "
                    "falling back to flat endpoint with client-side filter/sort."
                )
                versions = client.get(f"rest/api/2/project/{project_key}/versions") or []
                if query:
                    q = query.lower()
                    versions = [v for v in versions if q in (v.get("name", "") or "").lower()]
                if order_by:
                    versions = sorted(versions, key=lambda v: (v.get(order_by) is None, v.get(order_by) or ""))
            # Server-side `status` param is DC ≥9.x only; apply a client-side
            # safety filter so older servers don't silently return all statuses.
            if status != "all":
                versions = [v for v in versions if _status_of(v) == status]
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
    404; ``list_versions`` catches that and falls back to the flat
    `/project/{key}/versions` endpoint with client-side filter and sort so the
    user still gets a useful result.
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


def _fetch_counts(client, vid: str) -> dict:
    related = client.get(f"rest/api/2/version/{vid}/relatedIssueCounts") or {}
    unresolved = client.get(f"rest/api/2/version/{vid}/unresolvedIssueCount") or {}
    return {**related, **unresolved}


# Sentinel distinguishes "caller did not provide this key" from "caller passed None to clear".
_UNSET = object()


def _safe_update_version(client, vid: str, **patch) -> dict:
    """Safely update a version by GET + dict-merge + PUT.

    Why: Jira's `PUT /version/{id}` is treated as *replace* on some Server/DC
    deployments (and a few Cloud tenants), meaning any field omitted from the
    body is cleared. To avoid accidentally wiping `description`, `startDate`,
    etc. when the user only wants to update one field, we always fetch the
    current version first and merge the caller's patch onto it before PUTting.

    Any kwarg whose value is not the _UNSET sentinel is applied verbatim. Pass
    an explicit ``None`` to clear a field (e.g. `releaseDate=None` on unrelease);
    the null is preserved in the PUT body.
    """
    current = client.get(f"rest/api/2/version/{vid}") or {}
    merged = dict(current)
    for key, value in patch.items():
        if value is _UNSET:
            continue
        merged[key] = value
    # Strip server-managed fields we shouldn't echo back
    for ro in ("self", "operations", "projectId"):
        merged.pop(ro, None)
    return client.put(f"rest/api/2/version/{vid}", data=merged)


def _emit_mutation_result(ctx, payload: dict, *, fallback_id: str, success_msg: str) -> None:
    """Render the result of a mutating subcommand honouring --json / --quiet.

    Why: without this, `release` / `archive` / `move` / `merge` / `delete` always
    print the ``✓ …`` success line, breaking `--quiet` pipelines and emitting
    non-JSON on `--json`. ``payload`` is the API response (may be empty); when
    empty we fall back to an id-only JSON object so consumers always get a
    structured result.
    """
    if ctx.obj.get("json"):
        data = dict(payload) if payload else {"id": fallback_id}
        format_output(data, as_json=True)
        return
    if ctx.obj.get("quiet"):
        vid = (payload or {}).get("id") or fallback_id
        print(vid)
        return
    success(success_msg)


def _version_self_url(client, vid: str) -> str:
    """Build a fully-qualified self URL for a version from the client's base URL.

    Used by `move --after OTHER_ID` where the Jira API expects a `self` URL
    rather than a bare ID. Constructed from the configured Jira base URL
    (never from user input) to avoid SSRF or cross-instance spoofing.
    """
    base = getattr(client, "url", "") or ""
    if not base:
        raise RuntimeError("Jira client has no configured URL; cannot build self URL")
    base = base.rstrip("/")
    return f"{base}/rest/api/2/version/{vid}"


@cli.command()
@click.argument("project_key")
@click.argument("name")
@click.option("--description", help="Version description (plain text or wiki markup)")
@click.option("--start-date", help="Start date YYYY-MM-DD")
@click.option("--release-date", help="Release date YYYY-MM-DD")
@click.option("--released", is_flag=True, help="Mark as released on creation")
@click.option("--archived", is_flag=True, help="Mark as archived on creation")
@click.option("--dry-run", is_flag=True, help="Show what would be created")
@click.pass_context
def create(ctx, project_key, name, description, start_date, release_date, released, archived, dry_run):
    """Create a new version in a project."""
    client = ctx.obj["client"]
    payload = {"name": name, "project": project_key, "released": released, "archived": archived}
    if description:
        payload["description"] = description
    if start_date:
        payload["startDate"] = _validate_iso_date(start_date)
    if release_date:
        payload["releaseDate"] = _validate_iso_date(release_date)

    if dry_run:
        warning("DRY RUN - No version will be created")
        print(f"Would POST rest/api/2/version with:\n  {payload}")
        return

    try:
        created = client.post("rest/api/2/version", data=payload)
        vid = (created or {}).get("id", "?")

        if ctx.obj["json"]:
            format_output(created, as_json=True)
        elif ctx.obj["quiet"]:
            print(vid)
        else:
            extra = f" (release {release_date})" if release_date else ""
            success(f'Created version {vid} "{name}" in {project_key}{extra}')

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 409:
            error(f'Version "{name}" already exists in {project_key}')
        else:
            error(f"Failed to create version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--name", help="New name")
@click.option("--description", help="New description")
@click.option("--start-date", help="New start date YYYY-MM-DD")
@click.option("--release-date", help="New release date YYYY-MM-DD")
@click.option("--released/--unreleased", default=None, help="Mark released or unreleased")
@click.option("--archived/--unarchived", default=None, help="Mark archived or unarchived")
@click.option("--dry-run", is_flag=True, help="Show what would be updated")
@click.pass_context
def update(ctx, version_id, name, description, start_date, release_date, released, archived, dry_run):
    """Update fields on an existing version (safe-merge: GET + merge + PUT)."""
    _validate_numeric_id(version_id)
    client = ctx.obj["client"]

    patch: dict = {}
    if name is not None:
        patch["name"] = name
    if description is not None:
        patch["description"] = description
    if start_date is not None:
        patch["startDate"] = _validate_iso_date(start_date)
    if release_date is not None:
        patch["releaseDate"] = _validate_iso_date(release_date)
    if released is True:
        patch["released"] = True
    elif released is False:
        # --unreleased: clear releaseDate unless caller also set --release-date
        patch["released"] = False
        patch.setdefault("releaseDate", None)
    if archived is True:
        patch["archived"] = True
    elif archived is False:
        patch["archived"] = False

    if not patch:
        error(
            "No fields to update. Provide at least one of --name / --description / --start-date / --release-date / --released/--unreleased / --archived/--unarchived"
        )
        sys.exit(2)

    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would PUT rest/api/2/version/{version_id} with patch:\n  {patch}")
        return

    try:
        _safe_update_version(client, version_id, **patch)
        if ctx.obj["json"]:
            format_output({"id": version_id, "updated": True, "patch": patch}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Updated version {version_id}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to update version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--release-date", help="Release date YYYY-MM-DD (default: today)")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def release(ctx, version_id, release_date, dry_run):
    """Mark a version released (sets released=true + releaseDate)."""
    _validate_numeric_id(version_id)
    rdate = _validate_iso_date(release_date) if release_date else _date.today().isoformat()
    patch = {"released": True, "releaseDate": rdate}

    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would release {version_id} on {rdate}")
        return

    client = ctx.obj["client"]
    try:
        updated = _safe_update_version(client, version_id, **patch) or {}
        _emit_mutation_result(
            ctx,
            updated,
            fallback_id=version_id,
            success_msg=f"Released version {version_id} on {rdate}",
        )
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to release version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def unrelease(ctx, version_id, dry_run):
    """Mark a version unreleased (clears releaseDate)."""
    _validate_numeric_id(version_id)
    patch = {"released": False, "releaseDate": None}

    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would unrelease {version_id} (releaseDate cleared)")
        return

    client = ctx.obj["client"]
    try:
        updated = _safe_update_version(client, version_id, **patch) or {}
        _emit_mutation_result(
            ctx,
            updated,
            fallback_id=version_id,
            success_msg=f"Unreleased version {version_id}",
        )
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to unrelease version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def archive(ctx, version_id, dry_run):
    """Archive a version (hides it from pickers)."""
    _validate_numeric_id(version_id)
    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would archive {version_id}")
        return
    client = ctx.obj["client"]
    try:
        updated = _safe_update_version(client, version_id, archived=True) or {}
        _emit_mutation_result(
            ctx,
            updated,
            fallback_id=version_id,
            success_msg=f"Archived version {version_id}",
        )
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to archive version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def unarchive(ctx, version_id, dry_run):
    """Unarchive a version."""
    _validate_numeric_id(version_id)
    if dry_run:
        warning("DRY RUN - No version will be updated")
        print(f"Would unarchive {version_id}")
        return
    client = ctx.obj["client"]
    try:
        updated = _safe_update_version(client, version_id, archived=False) or {}
        _emit_mutation_result(
            ctx,
            updated,
            fallback_id=version_id,
            success_msg=f"Unarchived version {version_id}",
        )
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to unarchive version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--after", help="Move this version to directly after the given version ID")
@click.option(
    "--position", type=click.Choice(["First", "Last", "Earlier", "Later"]), help="Move relative to current position"
)
@click.option("--dry-run", is_flag=True, help="Show what would change")
@click.pass_context
def move(ctx, version_id, after, position, dry_run):
    """Reorder a version within its project."""
    _validate_numeric_id(version_id)
    if bool(after) == bool(position):
        error("Provide exactly one of --after or --position")
        sys.exit(2)

    client = ctx.obj["client"]
    if after:
        if not _is_numeric_id(after):
            error(f'--after expects a numeric version ID, got "{after}"')
            sys.exit(2)
        body = {"after": _version_self_url(client, after)}
    else:
        body = {"position": position}

    if dry_run:
        warning("DRY RUN - No version will be moved")
        print(f"Would POST rest/api/2/version/{version_id}/move with:\n  {body}")
        return

    try:
        resp = client.post(f"rest/api/2/version/{version_id}/move", data=body) or {}
        msg = f"Moved version {version_id} after {after}" if after else f"Moved version {version_id} to {position}"
        _emit_mutation_result(ctx, resp, fallback_id=version_id, success_msg=msg)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to move version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("src_id")
@click.argument("into", type=click.Choice(["INTO"]))
@click.argument("dst_id")
@click.option("--dry-run", is_flag=True, help="Show what would change without calling mergeto")
@click.pass_context
def merge(ctx, src_id, into, dst_id, dry_run):
    """Merge SRC_ID INTO DST_ID.

    Reassigns fixVersions / versions references from SRC to DST, then deletes
    SRC server-side. There is no undo.
    """
    _validate_numeric_id(src_id, label="SRC_ID")
    _validate_numeric_id(dst_id, label="DST_ID")
    client = ctx.obj["client"]

    if dry_run:
        warning("DRY RUN - No changes will be made")
        try:
            counts = client.get(f"rest/api/2/version/{src_id}/relatedIssueCounts") or {}
            src = client.get(f"rest/api/2/version/{src_id}") or {}
            dst = client.get(f"rest/api/2/version/{dst_id}") or {}
        except Exception as e:
            if ctx.obj["debug"]:
                raise
            error(f"Failed to preview merge: {e}")
            sys.exit(1)
        fixed = counts.get("issuesFixedCount", "?")
        affected = counts.get("issuesAffectedCount", "?")
        print(f'Would merge {src_id} "{src.get("name", "?")}" INTO {dst_id} "{dst.get("name", "?")}":')
        print(f"  fixed issues to reassign:    {fixed}")
        print(f"  affected issues to reassign: {affected}")
        print("  source version would be deleted")
        return

    try:
        client.post(f"rest/api/2/version/{src_id}/mergeto/{dst_id}")
        if ctx.obj.get("json"):
            format_output({"src": src_id, "dst": dst_id, "merged": True}, as_json=True)
        elif ctx.obj.get("quiet"):
            print(dst_id)
        else:
            success(f"Merged {src_id} into {dst_id}; source deleted")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to merge version: {e}")
        sys.exit(1)


@cli.command()
@click.argument("version_id")
@click.option("--move-fix-to", help="Reassign fixVersions refs to this version ID")
@click.option("--move-affected-to", help="Reassign affectsVersions refs to this version ID")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.pass_context
def delete(ctx, version_id, move_fix_to, move_affected_to, dry_run):
    """Delete a version, optionally reassigning fixVersions/versions refs."""
    _validate_numeric_id(version_id)
    client = ctx.obj["client"]
    if dry_run:
        try:
            v = client.get(f"rest/api/2/version/{version_id}") or {}
            counts = client.get(f"rest/api/2/version/{version_id}/relatedIssueCounts") or {}
        except Exception as e:
            if ctx.obj["debug"]:
                raise
            error(f"Failed to preview delete: {e}")
            sys.exit(1)
        warning("DRY RUN - No version will be deleted")
        fixed = counts.get("issuesFixedCount", "?")
        affected = counts.get("issuesAffectedCount", "?")
        print(f'Would delete {version_id} "{v.get("name", "?")}":')
        print(f"  fixVersion refs:        {fixed}" + (f" → {move_fix_to}" if move_fix_to else " (would be orphaned)"))
        print(
            f"  affectsVersion refs:    {affected}"
            + (f" → {move_affected_to}" if move_affected_to else " (would be orphaned)")
        )
        return

    # non-dry-run
    for flag, val in (("--move-fix-to", move_fix_to), ("--move-affected-to", move_affected_to)):
        if val and not _is_numeric_id(val):
            error(f'{flag} expects a numeric version ID, got "{val}"')
            sys.exit(2)

    params: dict = {}
    if move_fix_to:
        params["moveFixIssuesTo"] = move_fix_to
    if move_affected_to:
        params["moveAffectedIssuesTo"] = move_affected_to

    if not move_fix_to and not move_affected_to:
        warning(
            "No --move-fix-to / --move-affected-to provided. "
            "fixVersions/versions references on existing issues will be orphaned."
        )

    try:
        client.delete(f"rest/api/2/version/{version_id}", params=params or None)
        if ctx.obj.get("json"):
            payload = {"id": version_id, "deleted": True}
            if move_fix_to:
                payload["moveFixIssuesTo"] = move_fix_to
            if move_affected_to:
                payload["moveAffectedIssuesTo"] = move_affected_to
            format_output(payload, as_json=True)
        elif ctx.obj.get("quiet"):
            print(version_id)
        else:
            parts = []
            if move_fix_to:
                parts.append(f"fixVersion refs reassigned to {move_fix_to}")
            if move_affected_to:
                parts.append(f"affectsVersion refs reassigned to {move_affected_to}")
            detail = "; " + "; ".join(parts) if parts else ""
            success(f"Deleted version {version_id}{detail}")
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete version: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
