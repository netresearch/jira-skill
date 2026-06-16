#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "atlassian-python-api>=3.41.0,<4",
#     "click>=8.1.0,<9",
# ]
# ///
"""Jira issue transitions - list available transitions and change issue status."""

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
from lib.output import error, format_output, format_table, success, warning

# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _get_to_status(transition: dict) -> str:
    """Get target status name from transition, handling both Cloud and Server formats.

    Cloud returns: {'to': {'name': 'In Progress', ...}}
    Server/DC returns: {'to': 'In Progress'}
    """
    to_value = transition.get("to", "")
    if isinstance(to_value, dict):
        return to_value.get("name", "")
    return str(to_value)


def _normalize_transition_name(name: str) -> str:
    r"""Normalize a transition/status name for tolerant matching.

    Strips leading non-word noise (emoji, symbols, whitespace) and case-folds,
    so a user-supplied "Resolve" matches a Jira transition labelled "✅ Resolve".
    Uses ``\W`` (Unicode-aware) rather than an ASCII class so localized names
    (Cyrillic, Han, accented, …) are preserved instead of stripped to empty, and
    ``casefold()`` for correct Unicode case-insensitive comparison.
    """
    return re.sub(r"^\W+", "", name or "", flags=re.UNICODE).strip().casefold()


def find_matching_transition(transitions: list[dict], status_name: str) -> tuple[dict | None, list[dict]]:
    """Resolve a user-supplied name to a transition, tolerating emoji prefixes.

    Tiers, first hit wins: (1) exact case-insensitive on transition name or
    target status; (2) normalized equality (emoji/symbol prefix stripped);
    (3) unique normalized-substring match. Returns (match, candidates): match is
    the resolved transition or None; candidates lists the >1 transitions that an
    ambiguous substring matched (empty otherwise), so the caller can report them.
    """
    target = status_name.casefold()
    for t in transitions:
        if t.get("name", "").casefold() == target or _get_to_status(t).casefold() == target:
            return t, []

    norm_target = _normalize_transition_name(status_name)
    if norm_target:
        for t in transitions:
            if norm_target in (
                _normalize_transition_name(t.get("name", "")),
                _normalize_transition_name(_get_to_status(t)),
            ):
                return t, []

        substring = [
            t
            for t in transitions
            if norm_target in _normalize_transition_name(t.get("name", ""))
            or norm_target in _normalize_transition_name(_get_to_status(t))
        ]
        if len(substring) == 1:
            return substring[0], []
        if len(substring) > 1:
            return None, substring

    return None, []


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
    """Jira issue transitions.

    List available transitions and change issue status.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json
    ctx.obj["quiet"] = quiet
    ctx.obj["debug"] = debug
    ctx.obj["client"] = LazyJiraClient(env_file=env_file, profile=profile)


@cli.command("list")
@click.argument("issue_key")
@click.pass_context
def list_transitions(ctx, issue_key: str):
    """List available transitions for an issue.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    Shows all valid status transitions from the issue's current state.

    Example:

      jira-transition list PROJ-123
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        transitions = client.get_issue_transitions(issue_key)

        if ctx.obj["json"]:
            format_output(transitions, as_json=True)
        elif ctx.obj["quiet"]:
            for t in transitions:
                print(t.get("name", ""))
        else:
            # Get current status
            issue = client.issue(issue_key, fields="status")
            current_status = issue["fields"]["status"]["name"]

            print(f"Available transitions for {issue_key}")
            print(f"Current status: {current_status}\n")

            if not transitions:
                print("No transitions available from this status")
            else:
                rows = []
                for t in transitions:
                    rows.append({"ID": t.get("id", ""), "Name": t.get("name", ""), "To Status": _get_to_status(t)})
                print(format_table(rows, ["ID", "Name", "To Status"]))

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to get transitions for {issue_key}: {e}")
        sys.exit(1)


@cli.command("do")
@click.argument("issue_key")
@click.argument("status_name")
@click.option("--comment", "-c", help="Comment to add during transition")
@click.option("--resolution", "-r", help="Resolution name (for closing transitions)")
@click.option("--dry-run", is_flag=True, help="Show what would happen without making changes")
@click.pass_context
def do_transition(ctx, issue_key: str, status_name: str, comment: str | None, resolution: str | None, dry_run: bool):
    """Transition an issue to a new status.

    ISSUE_KEY: The Jira issue key (e.g., PROJ-123)

    STATUS_NAME: Target status name (e.g., "In Progress", "Done")

    Examples:

      jira-transition do PROJ-123 "In Progress"

      jira-transition do PROJ-123 "Done" --resolution Fixed

      jira-transition do PROJ-123 "Done" -c "Deployed to production" -r Fixed

      jira-transition do PROJ-123 "In Review" --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]

    try:
        # Get available transitions
        transitions = client.get_issue_transitions(issue_key)

        # Find matching transition (exact → emoji-tolerant → unique substring)
        matching, ambiguous = find_matching_transition(transitions, status_name)

        if not matching:
            if ambiguous:
                names = [t.get("name", "") for t in ambiguous]
                error(f"Transition '{status_name}' is ambiguous for {issue_key}")
                print(f"\nMatches: {', '.join(names)} — use the exact name")
            else:
                available = [t.get("name", "") for t in transitions]
                error(f"Transition '{status_name}' not available for {issue_key}")
                print(f"\nAvailable transitions: {', '.join(available)}")
            sys.exit(1)

        # Dry run
        if dry_run:
            warning("DRY RUN - No transition will be performed")
            print(f"\nWould transition {issue_key}:")
            print(f"  Transition: {matching['name']}")
            print(f"  To status: {_get_to_status(matching)}")
            if comment:
                print(f"  Comment: {comment}")
            if resolution:
                print(f"  Resolution: {resolution}")
            return

        # Build transition payload
        fields = {}
        if resolution:
            fields["resolution"] = {"name": resolution}

        # Perform transition - API uses target status name (not transition name/ID)
        # set_issue_status handles the transition ID lookup internally
        target_status = _get_to_status(matching)

        # Build update dict for comment if provided
        update = None
        if comment:
            update = {"comment": [{"add": {"body": comment}}]}

        client.set_issue_status(issue_key, target_status, fields=fields if fields else None, update=update)

        if ctx.obj["quiet"]:
            print(issue_key)
        elif ctx.obj["json"]:
            format_output(
                {"key": issue_key, "transition": matching["name"], "to_status": _get_to_status(matching)}, as_json=True
            )
        else:
            success(f"Transitioned {issue_key}")
            print(f"  Status: {_get_to_status(matching)}")
            if comment:
                if len(comment) > 50:
                    print(f"  Comment added: {comment[:50]}...")
                else:
                    print(f"  Comment added: {comment}")

    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to transition {issue_key}: {e}")
        sys.exit(1)


# Transition names/targets that move an issue *backwards* (or out of the
# forward flow). Skipped when the walker auto-picks the next step so a linear
# workflow doesn't bounce back toward where it came from.
# Matched as substrings so inflected forms are caught ("reopen" -> "Reopened",
# "cancel" -> "Cancelled", "reject" -> "Rejected").
_BACKWARD_SUBSTRINGS = ("reopen", "cancel", "reject", "decline", "abort")
# "back" is matched as a whole word only: "Move back" counts, but "Backlog",
# "Rollback" and "Feedback" must not be mistaken for backward transitions.
_BACKWARD_WORD_RE = re.compile(r"\bback\b")


def _is_backward(transition: dict, visited: set[str]) -> bool:
    """True if a transition leads backward: its name matches a backward verb,
    or its target status was already visited (would loop)."""
    name = (transition.get("name") or "").lower()
    if any(word in name for word in _BACKWARD_SUBSTRINGS) or _BACKWARD_WORD_RE.search(name):
        return True
    return _get_to_status(transition).lower() in visited


@cli.command("path")
@click.argument("issue_key")
@click.argument("target_status")
@click.option("--resolution", "-r", help="Resolution applied on the final transition")
@click.option("--comment", "-c", help="Comment added on the final transition")
@click.option(
    "--max-steps", type=click.IntRange(min=1), default=10, show_default=True, help="Safety cap on transitions walked"
)
@click.option("--dry-run", is_flag=True, help="Show the first planned step without transitioning")
@click.pass_context
def path_transition(
    ctx,
    issue_key: str,
    target_status: str,
    resolution: str | None,
    comment: str | None,
    max_steps: int,
    dry_run: bool,
):
    """Walk the workflow from the current status to TARGET_STATUS.

    Runs the list -> pick -> do loop internally, collapsing a multi-stage
    transition chain (e.g. QA -> UAT -> Resolved -> Closed) into one command.

    The Jira API only exposes the transitions available from the issue's
    *current* status, so the walk is greedy, not a full graph search: at each
    step it takes TARGET_STATUS if directly reachable, otherwise the single
    non-backward transition. If a step is ambiguous (several forward options)
    it stops and lists them so you can pick with `do`. --resolution/--comment
    apply only to the final transition.

    Examples:

      jira-transition path PROJ-123 Closed --resolution Done

      jira-transition path PROJ-123 "Ready for deployment" --dry-run
    """
    ctx.obj["client"].with_context(issue_key=issue_key)
    client = ctx.obj["client"]
    quiet, as_json = ctx.obj["quiet"], ctx.obj["json"]

    try:
        issue = client.issue(issue_key, fields="status")
        current = issue["fields"]["status"]["name"]
        target_l = target_status.lower()
        visited = {current.lower()}
        chain: list[str] = []

        if current.lower() == target_l:
            if as_json:
                format_output({"key": issue_key, "status": current, "steps": []}, as_json=True)
            elif quiet:
                print(issue_key)
            else:
                success(f"{issue_key} is already in status '{current}' - nothing to do")
            return

        for _ in range(max_steps):
            transitions = client.get_issue_transitions(issue_key)

            # Prefer a transition landing directly on the target.
            chosen = next((t for t in transitions if _get_to_status(t).lower() == target_l), None)
            is_final = chosen is not None

            if chosen is None:
                forward = [t for t in transitions if not _is_backward(t, visited)]
                if len(forward) != 1:
                    options = ", ".join(f"{t.get('name') or ''} -> {_get_to_status(t)}" for t in transitions) or "none"
                    reason = "no forward transition available" if not forward else "ambiguous next step"
                    error(
                        f"Cannot auto-advance {issue_key} from '{current}' toward '{target_status}': {reason}",
                        suggestion=f"Available transitions: {options}. "
                        f"Pick one explicitly with: jira-transition do {issue_key} <STATUS>",
                    )
                    sys.exit(1)
                chosen = forward[0]

            to_status = _get_to_status(chosen)

            if dry_run:
                warning("DRY RUN - No transition will be performed")
                print(f"\nNext step for {issue_key}: {chosen.get('name', '')} -> {to_status}")
                print(f"Current: {current} | Target: {target_status}")
                if not is_final:
                    print("(walk continues greedily from there; re-run without --dry-run to execute)")
                return

            fields = {"resolution": {"name": resolution}} if (resolution and is_final) else {}
            update = {"comment": [{"add": {"body": comment}}]} if (comment and is_final) else None
            client.set_issue_status(issue_key, to_status, fields=fields or None, update=update)

            chain.append(to_status)
            visited.add(to_status.lower())
            current = to_status
            if is_final:
                break
        else:
            error(f"Reached --max-steps ({max_steps}) before arriving at '{target_status}' (now at '{current}')")
            sys.exit(1)

        if as_json:
            format_output({"key": issue_key, "status": current, "steps": chain}, as_json=True)
        elif quiet:
            print(issue_key)
        else:
            success(f"Transitioned {issue_key} to '{current}'")
            print(f"  Path: {' -> '.join(chain)}")
            if resolution:
                print(f"  Resolution: {resolution}")

    except SystemExit:
        raise
    except Exception as e:
        if ctx.obj["debug"]:
            raise
        error(f"Failed to walk {issue_key} to '{target_status}': {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
