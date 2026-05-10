#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira issue link operations - create links and list link types."""

import csv
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
from lib.client import LazyJiraClient, _sanitize_error
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
    """Jira issue link operations.

    Create links between issues and list available link types.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


def _resolve_link_type_verbs(client, link_type: str) -> dict:
    """Look up the canonical name + outward/inward verbs for a link type.

    Match is case-insensitive against the link type's ``name`` so users can
    pass e.g. ``blocks`` or ``Blocks``. Raises ValueError if the type is
    unknown, with a helpful list of available names.
    """
    types = client.get_issue_link_types() or []
    target = link_type.casefold()
    for entry in types:
        if not isinstance(entry, dict):
            continue
        if (entry.get("name") or "").casefold() == target:
            return {
                "name": entry.get("name") or link_type,
                "outward": entry.get("outward") or "links to",
                "inward": entry.get("inward") or "is linked from",
            }
    available = ", ".join(sorted({(e.get("name") or "").strip() for e in types if isinstance(e, dict)} - {""}))
    raise ValueError(f"Unknown link type {link_type!r}. Available: {available or '(none returned by Jira)'}")


@cli.command()
@click.argument("from_key", required=False)
@click.argument("to_key", required=False)
@click.option("--source", "source_key", help="Source/active actor (outward verb applies). Alias for TO_KEY.")
@click.option("--target", "target_key", help="Target/passive recipient (inward verb applies). Alias for FROM_KEY.")
@click.option("--type", "-t", "link_type", required=True, help='Link type name (e.g., "Blocks", "Relates")')
@click.option("--dry-run", is_flag=True, help="Show what would be created")
@click.pass_context
def create(
    ctx,
    from_key: str | None,
    to_key: str | None,
    source_key: str | None,
    target_key: str | None,
    link_type: str,
    dry_run: bool,
):
    """Create a link between two issues.

    Direction (matches Atlassian REST convention): the link is stored such
    that TO_KEY is the source/active actor (outward verb applies) and
    FROM_KEY is the destination/passive recipient (inward verb applies).
    Read 'create FROM TO --type X' as: "on FROM, record that TO does X to it".

    FROM_KEY: Destination/passive recipient (positional)

    TO_KEY: Source/active actor (positional)

    Use --source / --target for an explicit named alternative:

      --source S --target T --type X
        is equivalent to
      create T S --type X

    Examples:

      jira-link create FRONTEND-12 INFRA-99 --type Blockade
      # → "INFRA-99 blocks FRONTEND-12"

      jira-link create --source INFRA-99 --target FRONTEND-12 --type Blockade
      # same as above, more explicit

      jira-link create EFFECT-1 ROOT-2 --type Cause --dry-run
    """
    from_key, to_key = _resolve_create_args(from_key, to_key, source_key, target_key)

    ctx.obj["client"].with_context(issue_key=from_key)
    client = ctx.obj["client"]
    verbs = _fetch_verbs_or_exit(client, link_type, ctx.obj["debug"])

    canonical_name = verbs["name"]
    outward_verb = verbs["outward"]
    sentence = f"{to_key} {outward_verb} {from_key}"

    if dry_run:
        warning("DRY RUN - No link will be created")
        print(f"Would create: {sentence} (link-type: {canonical_name})")
        return

    # Atlassian REST convention: inwardIssue is the source of the outward
    # arrow (active actor), outwardIssue is the destination (passive
    # recipient). Empirically verified: a stored link with
    # inwardIssue=A, outwardIssue=B and link type "Cause" is rendered as
    # "A causes B" / "B is caused by A" by the Jira UI.
    # In our CLI, TO_KEY is the active actor → inwardIssue=TO_KEY.
    try:
        client.create_issue_link(
            {"type": {"name": canonical_name}, "inwardIssue": {"key": to_key}, "outwardIssue": {"key": from_key}}
        )
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to create link: {_sanitize_error(str(e))}")
        sys.exit(1)

    _emit_create_output(
        ctx, from_key=from_key, to_key=to_key, canonical_name=canonical_name, verbs=verbs, sentence=sentence
    )


def _resolve_create_args(
    from_key: str | None, to_key: str | None, source_key: str | None, target_key: str | None
) -> tuple[str, str]:
    """Resolve positional FROM/TO vs --source/--target. Mixing the two forms is rejected."""
    using_named = source_key is not None or target_key is not None
    using_positional = from_key is not None or to_key is not None

    if using_named and using_positional:
        error("Use either positional FROM_KEY TO_KEY or --source/--target, not both")
        sys.exit(1)
    if using_named:
        if source_key is None or target_key is None:
            error("Both --source and --target are required when using the named form")
            sys.exit(1)
        return target_key, source_key
    if from_key is None or to_key is None:
        error("Provide FROM_KEY and TO_KEY (or --source and --target)")
        sys.exit(1)
    return from_key, to_key


def _fetch_verbs_or_exit(client, link_type: str, debug: bool) -> dict:
    """Resolve the link type's verbs. On unknown/transport errors, print and exit."""
    try:
        return _resolve_link_type_verbs(client, link_type)
    except ValueError as e:
        if debug:
            raise
        error(_sanitize_error(str(e)))
        sys.exit(1)
    except Exception as e:
        if debug:
            raise
        error(f"Failed to resolve link type: {_sanitize_error(str(e))}")
        sys.exit(1)


def _emit_create_output(ctx, *, from_key: str, to_key: str, canonical_name: str, verbs: dict, sentence: str) -> None:
    """Render the create result in json / quiet / human form."""
    if ctx.obj["json"]:
        format_output(
            {
                "from": from_key,
                "to": to_key,
                "source": to_key,
                "target": from_key,
                "type": canonical_name,
                "outward": verbs["outward"],
                "inward": verbs["inward"],
                "sentence": sentence,
                "created": True,
            },
            as_json=True,
        )
    elif ctx.obj["quiet"]:
        print("ok")
    else:
        success(f"Created: {sentence} (link-type: {canonical_name})")


@cli.command("list-types")
@click.pass_context
def list_types(ctx):
    """List available link types.

    Shows all issue link types configured in your Jira instance.

    Example:

      jira-link list-types
    """
    client = ctx.obj["client"]

    try:
        link_types = client.get_issue_link_types()

        if ctx.obj["json"]:
            format_output(link_types, as_json=True)
        elif ctx.obj["quiet"]:
            for lt in link_types:
                print(lt.get("name", ""))
        else:
            print("Available link types:\n")
            rows = []
            for lt in link_types:
                rows.append(
                    {"Name": lt.get("name", ""), "Inward": lt.get("inward", ""), "Outward": lt.get("outward", "")}
                )
            print(format_table(rows, ["Name", "Inward", "Outward"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get link types: {e}")
        sys.exit(1)


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_cmd(ctx, issue_key: str):
    """List all issue links on an issue.

    ISSUE_KEY: The Jira issue key (e.g. PROJ-123)

    Shows link ID, direction, link type, and the other issue's key and summary.

    Example:

      jira-link list PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        issue = client.issue(issue_key, fields="issuelinks")
        raw_links = (issue.get("fields") or {}).get("issuelinks") or []

        links = []
        for link in raw_links:
            link_id = link.get("id", "")
            type_obj = link.get("type") or {}
            type_name = type_obj.get("name", "")
            if "outwardIssue" in link:
                other = link["outwardIssue"]
                direction = "outward"
                relation = type_obj.get("outward", "")
            elif "inwardIssue" in link:
                other = link["inwardIssue"]
                direction = "inward"
                relation = type_obj.get("inward", "")
            else:
                other = {}
                direction = ""
                relation = ""
            other_key = other.get("key", "")
            other_summary = ((other.get("fields") or {}).get("summary")) or ""
            other_status = (((other.get("fields") or {}).get("status")) or {}).get("name", "")
            links.append(
                {
                    "id": link_id,
                    "type": type_name,
                    "direction": direction,
                    "relation": relation,
                    "other_key": other_key,
                    "other_summary": other_summary,
                    "other_status": other_status,
                }
            )

        if ctx.obj["json"]:
            format_output(links, as_json=True)
        elif ctx.obj["quiet"]:
            for link_entry in links:
                print(f"{link_entry['id']} {link_entry['type']} {link_entry['direction']} {link_entry['other_key']}")
        else:
            if not links:
                print(f"No issue links on {issue_key}")
                return
            rows = [
                {
                    "ID": link_entry["id"],
                    "Type": link_entry["type"],
                    "Direction": link_entry["direction"],
                    "Other": link_entry["other_key"],
                    "Summary": link_entry["other_summary"][:60],
                    "Status": link_entry["other_status"],
                }
                for link_entry in links
            ]
            print(format_table(rows, ["ID", "Type", "Direction", "Other", "Summary", "Status"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to list issue links for {issue_key}: {_sanitize_error(str(e))}")
        sys.exit(1)


def _link_matches(link: dict, to_key: str, link_type: str) -> bool:
    """Return True if an issue link targets to_key with link_type (case-insensitive)."""
    type_name = (link.get("type") or {}).get("name", "")
    if type_name.lower() != link_type.lower():
        return False
    other = link.get("outwardIssue") or link.get("inwardIssue") or {}
    other_key = other.get("key", "")
    return other_key.casefold() == to_key.casefold()


def _format_link_display(link: dict, context_key: str | None = None) -> str:
    """Format an issue link for human-readable output (e.g. 'blocks TEST-2').

    When context_key is provided, describe the link from that issue's
    perspective — matters when both inward and outward are populated
    (e.g. results from client.get_issue_link(id)).
    """
    type_obj = link.get("type") or {}
    type_name = type_obj.get("name", "")
    outward = link.get("outwardIssue") or {}
    inward = link.get("inwardIssue") or {}
    ctx_cf = context_key.casefold() if context_key else None
    if ctx_cf and outward.get("key", "").casefold() == ctx_cf and inward:
        return f"{type_obj.get('outward', type_name)} {inward.get('key', '?')}"
    if ctx_cf and inward.get("key", "").casefold() == ctx_cf and outward:
        return f"{type_obj.get('inward', type_name)} {outward.get('key', '?')}"
    if outward:
        return f"{type_obj.get('outward', type_name)} {outward.get('key', '?')}"
    if inward:
        return f"{type_obj.get('inward', type_name)} {inward.get('key', '?')}"
    return type_name


@cli.command()
@click.argument("issue_key")
@click.option("--id", "link_id", type=str, help="Issue link ID (from `jira-link list`)")
@click.option("--to", "to_key", help="Other issue key to identify the link by")
@click.option("--type", "-t", "link_type", help="Link type name (used with --to)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.pass_context
def delete(
    ctx,
    issue_key: str,
    link_id: str | None,
    to_key: str | None,
    link_type: str | None,
    dry_run: bool,
):
    """Delete an issue link.

    ISSUE_KEY: The Jira issue key that owns the link (e.g. PROJ-123)

    Identify the link by either --id or the combination of --to and --type.

    Examples:

      jira-link delete PROJ-123 --id 10042

      jira-link delete PROJ-123 --to PROJ-456 --type "Blocks" --dry-run
    """
    if link_id is None and not (to_key and link_type):
        error("Provide --id, or both --to and --type, to identify the link")
        sys.exit(1)
    if link_id is not None and (to_key or link_type):
        error("Use --id OR (--to and --type), not both")
        sys.exit(1)

    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Resolve to a single link_id + display string
        if link_id is not None:
            link = client.get_issue_link(link_id)
            inward_key = (link.get("inwardIssue") or {}).get("key") or ""
            outward_key = (link.get("outwardIssue") or {}).get("key") or ""
            if issue_key.casefold() not in {inward_key.casefold(), outward_key.casefold()}:
                error(f"Link id {link_id} is not associated with issue {issue_key}")
                sys.exit(1)
            display = _format_link_display(link, context_key=issue_key)
        else:
            issue = client.issue(issue_key, fields="issuelinks")
            raw_links = (issue.get("fields") or {}).get("issuelinks") or []
            matches = [lnk for lnk in raw_links if _link_matches(lnk, to_key, link_type)]
            if not matches:
                error(f"No {link_type!r} link between {issue_key} and {to_key}")
                sys.exit(1)
            if len(matches) > 1:
                ids = ", ".join(m.get("id", "?") for m in matches)
                error(f"Multiple matching links (ids: {ids}); use --id to disambiguate")
                sys.exit(1)
            link = matches[0]
            link_id = link.get("id")
            if not link_id:
                error("Matched link has no id; cannot delete")
                sys.exit(1)
            display = _format_link_display(link, context_key=issue_key)

        if dry_run:
            warning("DRY RUN - No link will be deleted")
            print(f"Would delete [{link_id}] {display}")
            return

        client.remove_issue_link(link_id)

        if ctx.obj["json"]:
            format_output({"key": issue_key, "id": link_id, "deleted": True}, as_json=True)
        elif ctx.obj["quiet"]:
            print("ok")
        else:
            success(f"Deleted link [{link_id}] {display}")

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to delete issue link: {_sanitize_error(str(e))}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# bulk-create / bulk-delete / invert: shared helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _normalize_csv_rows(reader: csv.DictReader) -> tuple[list[str], list[dict]]:
    """Strip + casefold field names so 'From' / ' to ' / 'TYPE' all work.

    The header validator is already case/whitespace-insensitive; without
    matching normalization on row extraction, headers that pass validation
    can still produce rows whose `.get('from')` returns None.
    """
    raw_fields = list(reader.fieldnames or [])
    if not raw_fields:
        return [], []
    fieldnames = [(f or "").strip().casefold() for f in raw_fields]
    rows: list[dict] = []
    for raw_row in reader:
        rows.append({fieldnames[i]: (raw_row.get(raw_fields[i]) or "") for i in range(len(raw_fields))})
    return fieldnames, rows


def _open_csv_rows(path: str) -> tuple[list[str], list[dict]]:
    """Read a CSV (or '-' for stdin) into (fieldnames, rows). Buffers fully.

    Field names and per-row keys are normalized to lower-case stripped form
    so headers like `From, To, Type` work the same as `from,to,type`.
    Returns ([], []) for an empty input (no header, no rows).
    """
    if path == "-":
        return _normalize_csv_rows(csv.DictReader(sys.stdin))
    with open(path, newline="", encoding="utf-8") as f:
        return _normalize_csv_rows(csv.DictReader(f))


def _validate_bulk_create_header(fieldnames: list[str]) -> None:
    """Exit 2 with a usage error if any of from/to/type is missing.

    Field names are already normalized (lower-cased + stripped) by
    `_open_csv_rows`, so this is a plain set check.
    """
    required = {"from", "to", "type"}
    missing = required - set(fieldnames)
    if missing:
        error(f"CSV header missing required column(s): {', '.join(sorted(missing))}")
        sys.exit(2)


def _build_link_type_cache(client) -> dict:
    """Single API call → casefolded-name → verbs dict.

    Used so bulk operations resolve every type name from one HTTP round-trip
    rather than one per row.
    """
    types = client.get_issue_link_types() or []
    cache: dict = {}
    for entry in types:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        cache[name.casefold()] = {
            "name": name,
            "outward": entry.get("outward") or "links to",
            "inward": entry.get("inward") or "is linked from",
        }
    return cache


def _resolve_type_from_cache(cache: dict, link_type: str) -> dict:
    """Look up a verbs dict from the cache. Raise ValueError if unknown."""
    verbs = cache.get(link_type.casefold())
    if verbs is None:
        available = ", ".join(sorted(v["name"] for v in cache.values()))
        raise ValueError(f"Unknown link type {link_type!r}. Available: {available or '(none returned by Jira)'}")
    return verbs


def _existing_link_between(
    client, from_key: str, to_key: str, type_name: str, links_cache: dict | None = None
) -> dict | None:
    """Return the first link of *type_name* between FROM and TO, ignoring direction.

    Reuses the existing `_link_matches` helper (case-insensitive match on
    type name AND on the other-issue key, in either inward or outward).
    Pass `links_cache` (a dict keyed by from_key) to memoize the per-issue
    fetch across rows — avoids the N+1 hit when many rows share the same
    `from_key`.
    """
    if links_cache is not None and from_key in links_cache:
        raw = links_cache[from_key]
    else:
        issue = client.issue(from_key, fields="issuelinks")
        raw = (issue.get("fields") or {}).get("issuelinks") or []
        if links_cache is not None:
            links_cache[from_key] = raw
    for lnk in raw:
        if _link_matches(lnk, to_key, type_name):
            return lnk
    return None


def _emit_jsonl(obj: dict) -> None:
    """One JSON object per line — JSONL, not a pretty-printed array."""
    print(json.dumps(obj, default=str))


# ═══════════════════════════════════════════════════════════════════════════════
# bulk-create
# ═══════════════════════════════════════════════════════════════════════════════


@cli.command("bulk-create")
@click.option(
    "--from-csv",
    "csv_path",
    required=True,
    help="CSV file path with header 'from,to,type'. Use '-' to read from stdin.",
)
@click.option("--dry-run", is_flag=True, help="Resolve verbs and print sentences; do not POST anything.")
@click.option(
    "--continue-on-error/--abort-on-error",
    "continue_on_error",
    default=False,
    help="On a failed row, keep going (default: abort with non-zero exit).",
)
@click.option(
    "--skip-existing",
    is_flag=True,
    help="Skip rows where a link of the same type already connects FROM and TO (either direction).",
)
@click.pass_context
def bulk_create(ctx, csv_path: str, dry_run: bool, continue_on_error: bool, skip_existing: bool):
    """Create many links from a CSV file.

    The CSV must have a header row with columns 'from', 'to', and 'type'.
    Each subsequent row creates one link via the same direction convention as
    `create FROM TO --type X` ("TO does X to FROM").

    \b
    Example CSV:
        from,to,type
        IOS-18,NRS-878,Cause
        IOS-18,NRT-4388,Deploy
        IOS-18,NRS-3106,Side effect

    Examples:

      jira-link bulk-create --from-csv links.csv --dry-run

      jira-link bulk-create --from-csv links.csv --skip-existing --continue-on-error

      cat links.csv | jira-link bulk-create --from-csv -
    """
    try:
        fieldnames, rows = _open_csv_rows(csv_path)
    except OSError as e:
        error(f"Cannot read CSV: {_sanitize_error(str(e))}")
        sys.exit(1)

    if not fieldnames and not rows:
        _emit_bulk_summary(ctx, created=0, skipped=0, failed=0)
        return

    _validate_bulk_create_header(fieldnames)

    client = ctx.obj["client"]
    try:
        type_cache = _build_link_type_cache(client)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to fetch link types: {_sanitize_error(str(e))}")
        sys.exit(1)

    counts = {"created": 0, "skipped": 0, "failed": 0}
    # Per-issue links cache: avoid re-fetching the same FROM ticket's
    # issuelinks for every row that shares it (N+1 → 1 per unique FROM).
    links_cache: dict = {}
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        ok = _bulk_create_row(
            ctx,
            client,
            type_cache,
            row,
            idx,
            total,
            dry_run=dry_run,
            skip_existing=skip_existing,
            counts=counts,
            links_cache=links_cache,
        )
        if not ok and not continue_on_error:
            _emit_bulk_summary(ctx, **counts)
            sys.exit(1)

    _emit_bulk_summary(ctx, **counts)
    if counts["failed"] and not continue_on_error:
        sys.exit(1)


def _bulk_create_row(
    ctx,
    client,
    type_cache: dict,
    row: dict,
    idx: int,
    total: int,
    *,
    dry_run: bool,
    skip_existing: bool,
    counts: dict,
    links_cache: dict | None = None,
) -> bool:
    """Process a single bulk-create row. Returns True on success or skip, False on failure."""
    from_key = (row.get("from") or "").strip()
    to_key = (row.get("to") or "").strip()
    raw_type = (row.get("type") or "").strip()
    if not (from_key and to_key and raw_type):
        _emit_bulk_row(ctx, idx, total, status="failed", reason="missing from/to/type column value")
        counts["failed"] += 1
        return False

    try:
        verbs = _resolve_type_from_cache(type_cache, raw_type)
    except ValueError as e:
        _emit_bulk_row(ctx, idx, total, status="failed", reason=_sanitize_error(str(e)))
        counts["failed"] += 1
        return False

    canonical_name = verbs["name"]
    sentence = f"{to_key} {verbs['outward']} {from_key}"

    if skip_existing:
        try:
            existing = _existing_link_between(client, from_key, to_key, canonical_name, links_cache=links_cache)
        except Exception as e:
            _emit_bulk_row(ctx, idx, total, status="failed", reason=_sanitize_error(str(e)))
            counts["failed"] += 1
            return False
        if existing is not None:
            _emit_bulk_row(
                ctx,
                idx,
                total,
                status="skipped",
                from_key=from_key,
                to_key=to_key,
                type_name=canonical_name,
                sentence=sentence,
            )
            counts["skipped"] += 1
            return True

    if dry_run:
        _emit_bulk_row(
            ctx,
            idx,
            total,
            status="created",
            sentence=sentence,
            type_name=canonical_name,
            from_key=from_key,
            to_key=to_key,
            dry_run=True,
        )
        counts["created"] += 1
        return True

    try:
        client.create_issue_link(
            {
                "type": {"name": canonical_name},
                "inwardIssue": {"key": to_key},
                "outwardIssue": {"key": from_key},
            }
        )
    except Exception as e:
        _emit_bulk_row(ctx, idx, total, status="failed", reason=_sanitize_error(str(e)))
        counts["failed"] += 1
        return False

    _emit_bulk_row(
        ctx,
        idx,
        total,
        status="created",
        sentence=sentence,
        type_name=canonical_name,
        from_key=from_key,
        to_key=to_key,
    )
    counts["created"] += 1
    return True


def _emit_bulk_row(ctx, idx: int, total: int, *, status: str, **fields) -> None:
    """Emit a per-row line (text/JSON/quiet)."""
    if ctx.obj["quiet"]:
        return
    if ctx.obj["json"]:
        payload = {"index": idx, "total": total, "status": status, **fields}
        _emit_jsonl(payload)
        return

    prefix = f"[{idx}/{total}]"
    if status == "created":
        sentence = fields.get("sentence", "")
        type_name = fields.get("type_name", "")
        if fields.get("dry_run"):
            print(f"{prefix} Would create: {sentence} (link-type: {type_name})")
        else:
            print(f"{prefix} {sentence} (link-type: {type_name})")
    elif status == "skipped":
        from_key = fields.get("from_key", "")
        to_key = fields.get("to_key", "")
        type_name = fields.get("type_name", "")
        print(f"{prefix} SKIP existing: {from_key} ↔ {to_key} ({type_name})")
    elif status == "failed":
        print(f"{prefix} FAIL: {fields.get('reason', '')}")


def _emit_bulk_summary(ctx, *, created: int, skipped: int, failed: int) -> None:
    """Emit the end-of-run summary."""
    if ctx.obj["json"]:
        _emit_jsonl({"summary": True, "created": created, "skipped": skipped, "failed": failed})
        return
    print(f"created: {created}, skipped: {skipped}, failed: {failed}")


# ═══════════════════════════════════════════════════════════════════════════════
# bulk-delete
# ═══════════════════════════════════════════════════════════════════════════════


def _read_ids_from_file(path: str) -> list[str]:
    """Read one ID per line from a file (or stdin if path == '-'). Blank lines ignored."""
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _resolve_bulk_delete_ids(ids: str | None, ids_file: str | None) -> list[str]:
    """Resolve --ids / --ids-file (mutually exclusive, exactly one required) to a list."""
    if (ids is None) == (ids_file is None):
        error("Provide exactly one of --ids or --ids-file")
        sys.exit(1)
    if ids is not None:
        return [s.strip() for s in ids.split(",") if s.strip()]
    try:
        return _read_ids_from_file(ids_file or "-")
    except OSError as e:
        error(f"Cannot read --ids-file: {_sanitize_error(str(e))}")
        sys.exit(1)


@cli.command("bulk-delete")
@click.option("--ids", help="Comma-separated link IDs (e.g. '101,102,103').")
@click.option(
    "--ids-file",
    help="Path with one link ID per line. Use '-' to read from stdin. Mutually exclusive with --ids.",
)
@click.option("--dry-run", is_flag=True, help="Show what would be deleted; do not call the API.")
@click.option(
    "--continue-on-error/--abort-on-error",
    "continue_on_error",
    default=False,
    help="On a failed row, keep going (default: abort with non-zero exit).",
)
@click.pass_context
def bulk_delete(ctx, ids: str | None, ids_file: str | None, dry_run: bool, continue_on_error: bool):
    """Delete many issue links by ID.

    Pass IDs as a comma-separated list (--ids) OR as a file with one per line
    (--ids-file). Each ID is looked up first so the per-row log shows the
    affected issues, then deleted.

    Examples:

      jira-link bulk-delete --ids 101,102,103 --dry-run

      jira-link bulk-delete --ids-file stale-links.txt --continue-on-error

      jira-link list PROJ-1 --quiet | awk '{print $1}' | jira-link bulk-delete --ids-file -
    """
    id_list = _resolve_bulk_delete_ids(ids, ids_file)
    if not id_list:
        _emit_bulk_delete_summary(ctx, {"created": 0, "failed": 0})
        return

    client = ctx.obj["client"]
    counts = {"created": 0, "skipped": 0, "failed": 0}  # 'created' = deleted in this command's reporting
    total = len(id_list)
    for idx, link_id in enumerate(id_list, start=1):
        ok = _bulk_delete_row(ctx, client, link_id, idx, total, dry_run=dry_run, counts=counts)
        if not ok and not continue_on_error:
            _emit_bulk_delete_summary(ctx, counts)
            sys.exit(1)

    _emit_bulk_delete_summary(ctx, counts)
    if counts["failed"] and not continue_on_error:
        sys.exit(1)


def _bulk_delete_row(ctx, client, link_id: str, idx: int, total: int, *, dry_run: bool, counts: dict) -> bool:
    """Delete one link by ID, with optional pre-fetch to log which issues are affected."""
    display = f"link {link_id}"
    try:
        link = client.get_issue_link(link_id)
        inward = (link.get("inwardIssue") or {}).get("key") or "?"
        outward = (link.get("outwardIssue") or {}).get("key") or "?"
        type_name = (link.get("type") or {}).get("name") or "?"
        display = f"[{link_id}] {outward} ↔ {inward} ({type_name})"
    except Exception as e:
        if not dry_run:
            _emit_bulk_delete_line(ctx, idx, total, status="failed", link_id=link_id, reason=_sanitize_error(str(e)))
            counts["failed"] += 1
            return False
        # In dry-run, lookup failure is not fatal — just keep the bare ID display.

    if dry_run:
        _emit_bulk_delete_line(ctx, idx, total, status="dry_run", link_id=link_id, display=display)
        counts["created"] += 1
        return True

    try:
        client.remove_issue_link(link_id)
    except Exception as e:
        _emit_bulk_delete_line(ctx, idx, total, status="failed", link_id=link_id, reason=_sanitize_error(str(e)))
        counts["failed"] += 1
        return False

    _emit_bulk_delete_line(ctx, idx, total, status="deleted", link_id=link_id, display=display)
    counts["created"] += 1
    return True


def _emit_bulk_delete_line(ctx, idx: int, total: int, *, status: str, link_id: str, **fields) -> None:
    """Emit a per-row line for bulk-delete."""
    if ctx.obj["quiet"]:
        return
    if ctx.obj["json"]:
        _emit_jsonl({"index": idx, "total": total, "status": status, "id": link_id, **fields})
        return

    prefix = f"[{idx}/{total}]"
    if status == "deleted":
        print(f"{prefix} Deleted {fields.get('display', link_id)}")
    elif status == "dry_run":
        print(f"{prefix} Would delete {fields.get('display', link_id)}")
    elif status == "failed":
        print(f"{prefix} FAIL: link {link_id}: {fields.get('reason', '')}")


def _emit_bulk_delete_summary(ctx, counts: dict) -> None:
    """Summary for bulk-delete (renames 'created' → 'deleted' in the public output)."""
    deleted = counts["created"]
    failed = counts["failed"]
    if ctx.obj["json"]:
        _emit_jsonl({"summary": True, "deleted": deleted, "failed": failed})
        return
    print(f"deleted: {deleted}, failed: {failed}")


# ═══════════════════════════════════════════════════════════════════════════════
# invert
# ═══════════════════════════════════════════════════════════════════════════════


def _invert_compute_plan(client, link_id: str) -> dict:
    """Fetch the link and compute the inversion plan.

    Returns a dict with: id, type_name, original_outward, original_inward,
    outward_verb, inward_verb, current_sentence, new_sentence.

    'Current' direction interpretation (matches the script's create convention):
      sentence = "<inwardIssue> <outward verb> <outwardIssue>"
    Inverting swaps the two issue keys.
    """
    link = client.get_issue_link(link_id)
    type_obj = link.get("type") or {}
    type_name = type_obj.get("name") or ""
    if not type_name:
        raise ValueError(f"Link {link_id} has no type name")
    outward_verb = type_obj.get("outward") or "links to"
    inward_verb = type_obj.get("inward") or "is linked from"
    outward_key = (link.get("outwardIssue") or {}).get("key") or ""
    inward_key = (link.get("inwardIssue") or {}).get("key") or ""
    if not (outward_key and inward_key):
        raise ValueError(f"Link {link_id} is missing outwardIssue/inwardIssue keys")
    current_sentence = f"{inward_key} {outward_verb} {outward_key}"
    new_sentence = f"{outward_key} {outward_verb} {inward_key}"
    return {
        "id": link_id,
        "type_name": type_name,
        "original_outward": outward_key,
        "original_inward": inward_key,
        "outward_verb": outward_verb,
        "inward_verb": inward_verb,
        "current_sentence": current_sentence,
        "new_sentence": new_sentence,
    }


def _invert_execute_with_rollback(client, plan: dict) -> None:
    """Delete the original link and create the inverted one. Rolls back on failure.

    Raises RuntimeError("INCONSISTENT STATE...") if both the inverted-create
    AND the rollback re-create fail — that's the case where a human needs to
    fix Jira manually.
    """
    link_id = plan["id"]
    type_name = plan["type_name"]
    original_outward = plan["original_outward"]
    original_inward = plan["original_inward"]

    # Capture the original payload BEFORE deletion (so rollback doesn't depend
    # on the link still existing).
    original_payload = {
        "type": {"name": type_name},
        "inwardIssue": {"key": original_inward},
        "outwardIssue": {"key": original_outward},
    }
    inverted_payload = {
        "type": {"name": type_name},
        "inwardIssue": {"key": original_outward},
        "outwardIssue": {"key": original_inward},
    }

    client.remove_issue_link(link_id)
    try:
        client.create_issue_link(inverted_payload)
    except Exception as inverted_exc:
        try:
            client.create_issue_link(original_payload)
        except Exception as rollback_exc:
            raise RuntimeError(
                f"INCONSISTENT STATE — original link {link_id} deleted but neither the inverted "
                f"link ({plan['new_sentence']}) nor the rollback ({plan['current_sentence']}) could "
                f"be created. Inverted error: {_sanitize_error(str(inverted_exc))}. "
                f"Rollback error: {_sanitize_error(str(rollback_exc))}."
            ) from rollback_exc
        # Rollback succeeded — surface the original failure to the caller.
        raise RuntimeError(
            f"Failed to create inverted link ({plan['new_sentence']}); original link restored. "
            f"Reason: {_sanitize_error(str(inverted_exc))}"
        ) from inverted_exc


@cli.command()
@click.option("--id", "link_id", required=True, help="Issue link ID to invert (from `jira-link list`).")
@click.option("--dry-run", is_flag=True, help="Show the current and inverted sentences; do not modify Jira.")
@click.pass_context
def invert(ctx, link_id: str, dry_run: bool):
    """Invert a link by deleting it and re-creating it with FROM/TO swapped.

    This is destructive: the original link is DELETED before the new one is
    created. If the create POST fails, the script attempts to recreate the
    original (best-effort). If that rollback also fails, you'll get an
    "INCONSISTENT STATE" error pointing at the link ID — fix it manually in
    the Jira UI.

    Always prefer --dry-run first.

    Examples:

      jira-link invert --id 10042 --dry-run
      # → "Would invert: ROOT-2 causes EFFECT-1 → EFFECT-1 causes ROOT-2"

      jira-link invert --id 10042
    """
    client = ctx.obj["client"]
    try:
        plan = _invert_compute_plan(client, link_id)
    except ValueError as e:
        if ctx.obj["debug"]:
            raise
        error(_sanitize_error(str(e)))
        sys.exit(1)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to fetch link {link_id}: {_sanitize_error(str(e))}")
        sys.exit(1)

    if dry_run:
        warning("DRY RUN - No link will be modified")
        print(f"Would invert: {plan['current_sentence']} → {plan['new_sentence']}")
        return

    try:
        _invert_execute_with_rollback(client, plan)
    except RuntimeError as e:
        if ctx.obj["debug"]:
            raise
        error(str(e))
        sys.exit(1)
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to invert link {link_id}: {_sanitize_error(str(e))}")
        sys.exit(1)

    _emit_invert_output(ctx, plan)


def _emit_invert_output(ctx, plan: dict) -> None:
    """Emit the success result for invert (json / quiet / human)."""
    if ctx.obj["json"]:
        format_output(
            {
                "id": plan["id"],
                "type": plan["type_name"],
                "old_sentence": plan["current_sentence"],
                "new_sentence": plan["new_sentence"],
                "inverted": True,
            },
            as_json=True,
        )
    elif ctx.obj["quiet"]:
        print("ok")
    else:
        success(f"Inverted: {plan['current_sentence']} → {plan['new_sentence']}")


if __name__ == "__main__":
    cli()
