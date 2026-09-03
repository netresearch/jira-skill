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
from lib.users import check_mentions_cli

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


def fetch_transitions(client, issue_key: str) -> list[dict]:
    """Available transitions **with their screens**.

    The bare listing answers half the question: which transitions exist. The
    other half — what each one requires — lives in the screen, and only
    ``expand=transitions.fields`` returns it. Without the expansion a caller
    cannot tell "requires nothing" from "nobody asked", which is exactly the
    confusion that put twelve status changes into two tickets that needed two.

    Falls back to the unexpanded listing if the instance or library version does
    not support the expansion, so this degrades to the previous behaviour rather
    than failing.
    """
    try:
        raw = client.get_issue_transitions_full(issue_key, expand="transitions.fields")
        if isinstance(raw, dict):
            transitions = raw.get("transitions")
            # An empty list is a successful answer -- "this issue offers no
            # transitions" -- not a reason to ask again. Retrying there turns a
            # legitimate empty result into an error whenever the second call
            # fails.
            #
            if isinstance(transitions, list) and all(_usable_transition(t) for t in transitions):
                return transitions
    except Exception:  # noqa: BLE001 - any API/library shape problem falls back
        pass
    return client.get_issue_transitions(issue_key)


def _usable_transition(entry: object) -> bool:
    """Whether an expanded transition entry can be consumed as-is.

    Every caller does ``entry.get(...)`` and `required_fields` walks the field
    spec, so a malformed member raises *past* the fallback instead of using it
    — the failure this module's fetch exists to avoid.

    An absent ``fields`` key stays valid on purpose: that is what an unexpanded
    answer looks like, and callers already report it as `?`. Only a ``fields``
    that is present and not a mapping of mappings is rejected.

    The transition id is deliberately not checked here. Rejecting the response
    over a missing id would fall back to ``get_issue_transitions``, which reads
    the same endpoint and does ``int(transition["id"])`` — so the id would only
    move the crash one layer down. `do` guards it where it is actually used.
    """
    if not isinstance(entry, dict):
        return False
    if "fields" not in entry:
        return True
    spec = entry["fields"]
    return isinstance(spec, dict) and all(isinstance(v, dict) for v in spec.values())


def _contract_lines(matching: dict, required: list[str], spec_known: bool) -> list[str]:
    """What the selector resolved to, for whoever has to read the outcome.

    Both `do` paths render this from here because they drifted once: the caveat
    below was added to the dry run and not to the real one, so the run that
    actually changes a ticket was the run that said least about what it was
    doing.
    """
    lines = [
        f"  Transition: {matching.get('name')} (id {matching.get('id')})",
        f"  To status: {_get_to_status(matching)}",
        f"  Requires: {(', '.join(required) or '-') if spec_known else '?'}",
    ]
    if not spec_known:
        lines.append(
            "  The field spec was not returned, so required fields were NOT "
            "checked — `?` is not `-`. The transition may still be rejected "
            "for a field nothing here could see."
        )
    return lines


def _ambiguous_selectors(transitions: list[dict]) -> list[str]:
    """Human-readable notes for names or targets shared by >1 transition."""
    notes = []
    for key, label in (("name", "name"), ("to", "target")):
        seen: dict[str, list[dict]] = {}
        for t in transitions:
            # Normalize both sides the way find_matching_transition does.
            # Case-folding the target only would let `✅ Closed` and `✖ Closed`
            # be refused by `do` while `list` shows no ambiguity at all — the
            # reader would then have no way to learn why.
            raw_value = t.get("name", "") if key == "name" else _get_to_status(t)
            value = _normalize_transition_name(raw_value)
            if value:
                seen.setdefault(value, []).append(t)
        for value, group in seen.items():
            if len(group) > 1:
                ids = ", ".join(f"{t.get('id')} ({t.get('name')})" for t in group)
                notes.append(f"{label} {value!r} → {ids}")
    return notes


def _missing_hint(missing: list[str]) -> str:
    """What to do about the fields this transition declares and we did not send.

    Only `resolution` has a flag here. Naming --resolution for an unmet
    `assignee` or a custom field would send the reader after an option that
    cannot help them.
    """
    flagged = [f for f in missing if f == "resolution"]
    other = [f for f in missing if f != "resolution"]
    parts = ["This is the transition's own screen talking, not a convention."]
    if flagged:
        parts.append("Pass --resolution <name> for `resolution`.")
    if other:
        parts.append(
            "No flag exists here for "
            + ", ".join(f"`{f}`" for f in other)
            + " — POST the transition yourself with those fields, or choose a "
            "transition that does not ask for them."
        )
    parts.append("`list` shows the requirements per transition.")
    return " ".join(parts)


def required_fields(transition: dict) -> list[str]:
    """Field keys this transition's screen marks required.

    Present only when the transitions were fetched with
    ``expand=transitions.fields``; an unexpanded transition yields ``[]``, which
    is indistinguishable from "requires nothing" — so callers that care must ask
    for the expansion rather than infer from a bare listing.
    """
    return sorted(k for k, v in (transition.get("fields") or {}).items() if v.get("required"))


def settable_fields(transition: dict) -> list[str]:
    """Every field key this transition's screen accepts, required or not."""
    return sorted((transition.get("fields") or {}).keys())


def find_matching_transition(transitions: list[dict], status_name: str) -> tuple[dict | None, list[dict]]:
    """Resolve a user-supplied name or id to a transition, tolerating emoji prefixes.

    Tiers, first hit wins: (0) exact transition **id**; (1) exact
    case-insensitive on transition name or target status; (2) normalized
    equality (emoji/symbol prefix stripped); (3) unique normalized-substring
    match. Returns (match, candidates): match is the resolved transition or
    None; candidates lists the >1 transitions an ambiguous selector matched
    (empty otherwise), so the caller can report them.

    Tier 0 exists because a name is not always a usable selector: two
    transitions from one status can share a target (``✅ Done → Closed`` and
    ``✖ Close → Closed``, which differ in whether they require a resolution),
    and two can share a display name up to an emoji (``✅ QA → Resolved`` and
    ``❌ QA → Reopened``, which are opposite outcomes). The id from the
    transition listing is the only unambiguous handle, so accept it.

    Tier 1 collects *all* exact matches rather than returning the first. Silently
    picking one of two transitions that lead to different places is how a ticket
    ends up Reopened when the reviewer meant Resolved.
    """
    selector = (status_name or "").strip()

    by_id = [t for t in transitions if str(t.get("id", "")) == selector]
    if by_id:
        return by_id[0], []

    target = selector.casefold()
    exact = [t for t in transitions if t.get("name", "").casefold() == target or _get_to_status(t).casefold() == target]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, exact

    norm_target = _normalize_transition_name(status_name)
    if norm_target:
        # Same rule one tier down: `QA` normalizes to the same string for both
        # `✅ QA → Resolved` and `❌ QA → Reopened`, so collect and report rather
        # than take the first.
        norm_exact = [
            t
            for t in transitions
            if norm_target
            in (
                _normalize_transition_name(t.get("name", "")),
                _normalize_transition_name(_get_to_status(t)),
            )
        ]
        if len(norm_exact) == 1:
            return norm_exact[0], []
        if len(norm_exact) > 1:
            return None, norm_exact

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
        transitions = fetch_transitions(client, issue_key)

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
                    # "-" would read as "requires nothing". Without the screen
                    # we do not know, and that is a different statement -- the
                    # exact confusion required_fields() warns about.
                    if "fields" not in t:
                        requires = accepts = "?"
                    else:
                        req = required_fields(t)
                        optional = [f for f in settable_fields(t) if f not in req]
                        requires = ", ".join(req) or "-"
                        accepts = ", ".join(optional) or "-"
                    rows.append(
                        {
                            "ID": t.get("id", ""),
                            "Name": t.get("name", ""),
                            "To Status": _get_to_status(t),
                            "Requires": requires,
                            "Also accepts": accepts,
                        }
                    )
                print(format_table(rows, ["ID", "Name", "To Status", "Requires", "Also accepts"]))
                if any("fields" not in t for t in transitions):
                    print("\n`?` means the field spec was not returned, not that the transition requires nothing.")
                dupes = _ambiguous_selectors(transitions)
                if dupes:
                    print(
                        "\nAmbiguous by name or target: "
                        + "; ".join(dupes)
                        + ".\nSelect those by ID — the label and the target status do not "
                        "identify them."
                    )

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
@click.option("--no-verify-mentions", is_flag=True, help="Skip [~username] mention verification in --comment")
@click.option("--dry-run", is_flag=True, help="Show what would happen without making changes")
@click.pass_context
def do_transition(
    ctx,
    issue_key: str,
    status_name: str,
    comment: str | None,
    resolution: str | None,
    no_verify_mentions: bool,
    dry_run: bool,
):
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

    # A transition comment is a real issue comment — same mention gate as jira-comment add
    if not dry_run:
        check_mentions_cli(client, comment, skip=no_verify_mentions)

    try:
        # With their screens: what each transition requires is half the answer,
        # and a bare listing cannot express it.
        transitions = fetch_transitions(client, issue_key)

        # Find matching transition (id → exact → emoji-tolerant → unique substring)
        matching, ambiguous = find_matching_transition(transitions, status_name)

        if not matching:
            if ambiguous:
                rows = ", ".join(f"{t.get('id')} {t.get('name')} → {_get_to_status(t)}" for t in ambiguous)
                error(f"Transition '{status_name}' is ambiguous for {issue_key}")
                print(f"\nMatches: {rows}\nThese lead to different places. Pass the transition ID, not the name.")
            else:
                available = ", ".join(f"{t.get('id')} {t.get('name')}" for t in transitions)
                error(f"Transition '{status_name}' not available for {issue_key}")
                print(f"\nAvailable transitions: {available}")
            sys.exit(1)

        # Without the screen we do not know what this transition wants, and
        # saying "-" would claim it wants nothing — the same conflation `list`
        # avoids with `?`. Skip the pre-check and say so, rather than implying a
        # check happened.
        spec_known = "fields" in matching
        required = required_fields(matching)
        supplied = {"resolution"} if resolution else set()
        missing = [f for f in required if f not in supplied] if spec_known else []

        # Dry run
        if dry_run:
            warning("DRY RUN - No transition will be performed")
            print(f"\nWould transition {issue_key}:")
            for line in _contract_lines(matching, required, spec_known):
                print(line)
            if comment:
                print(f"  Comment: {comment}")
            if resolution:
                print(f"  Resolution: {resolution}")
            if missing:
                error("Missing required field(s) for this transition: " + ", ".join(missing))
                print("  " + _missing_hint(missing))
                sys.exit(1)
            return

        if missing:
            error(f"Transition '{matching['name']}' requires: {', '.join(missing)}")
            print("\n" + _missing_hint(missing))
            sys.exit(1)

        # The id is what gets posted, so an entry without one cannot be acted
        # on. Formatting it anyway sends {"id": "None"} and the API answers with
        # a rejection that says nothing about where the None came from.
        transition_id = matching.get("id")
        if not transition_id:
            error(f"Transition '{matching.get('name')}' for {issue_key} has no id")
            print(
                "\nThe id is the only handle a transition is posted with, and this entry "
                "carried none. Run `list` to see what the server offers for this issue."
            )
            sys.exit(1)

        # The contract this resolved to, on the path that actually changes the
        # ticket -- not only under --dry-run. When the POST is rejected for a
        # field, this is what tells the reader whether it was even checked.
        if not ctx.obj["quiet"] and not ctx.obj["json"]:
            print(f"Transitioning {issue_key}:")
            for line in _contract_lines(matching, required, spec_known):
                print(line)

        # Build transition payload
        fields = {}
        if resolution:
            fields["resolution"] = {"name": resolution}

        # Post the transition by ID. Going via the target status name would let
        # the API re-resolve it, and a target is not always unique: one ticket
        # can offer `✅ Done → Closed` and `✖ Close → Closed`, which differ in
        # what they require. The ID is the only handle that means one thing.
        payload: dict = {"transition": {"id": str(transition_id)}}
        if fields:
            payload["fields"] = fields
        if comment:
            payload["update"] = {"comment": [{"add": {"body": comment}}]}

        client.post(f"rest/api/2/issue/{issue_key}/transitions", data=payload)

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

            # By id, for the same reason `do` is. set_issue_status() re-resolves
            # the target through get_transition_id_to_status_name(), which
            # returns the FIRST transition whose target matches the name -- so
            # the walker's own choice is discarded wherever two transitions
            # share a target, which is exactly where the choice mattered. It
            # also returns None when nothing matches, posting a null id, and
            # spends an extra round-trip re-fetching what `chosen` already holds.
            #
            # No id guard here, unlike `do`: these come from
            # get_issue_transitions(), which builds every entry with
            # int(transition["id"]) and so cannot hand out one without an id.
            payload: dict = {"transition": {"id": str(chosen["id"])}}
            if fields:
                payload["fields"] = fields
            if update:
                payload["update"] = update
            client.post(f"rest/api/2/issue/{issue_key}/transitions", data=payload)

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
