# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""A short state block for the ticket a command just read or changed.

A write that reports only ``✓ Added comment`` says nothing about the ticket it
landed on. An agent can comment, link and log time on a ticket that is still
Open and unassigned, or that belongs to someone else, and never see it: the
status field is the one signal colleagues read, and no output showed it.

``print_ticket_state`` appends status, assignee, resolution and time tracking,
plus a hint for each state that is likely wrong for the action. In text mode
it prints to stderr. With ``--json``, ``with_ticket_state`` adds the same facts
as a ``ticket_state`` field to an object output and leaves every existing key
alone. ``--quiet`` gets nothing. It never fails the command: a lookup error
costs one line or an ``error`` field. ``JIRA_TICKET_STATE=0`` turns it off.
"""

import os
import sys

from lib.config import load_status_sets

FIELDS = "status,assignee,resolution,timetracking,labels,issuetype,updated"

_OFF_VALUES = {"0", "false", "no", "off"}


def _enabled() -> bool:
    return os.environ.get("JIRA_TICKET_STATE", "").strip().lower() not in _OFF_VALUES


def _user_id(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return user.get("name") or user.get("accountId") or user.get("key")


def _user_label(user: dict | None) -> str:
    if not isinstance(user, dict):
        return "unassigned"
    return user.get("name") or user.get("displayName") or user.get("accountId") or "?"


def _duration(seconds) -> str:
    if not isinstance(seconds, int) or seconds <= 0:
        return "–"
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    return f"{hours}h" if hours else f"{minutes}m"


def _workflow_hints(fields: dict, me: str | None, writing: bool) -> list[str]:
    """Hints on status, assignee and resolution."""
    hints = []
    status = fields.get("status") or {}
    category = ((status.get("statusCategory") or {}).get("key") or "").lower()
    status_name = status.get("name", "?")
    assignee = _user_id(fields.get("assignee"))
    resolution = fields.get("resolution")
    done = category == "done"

    if writing and category == "new":
        hints.append(f'ticket is "{status_name}" while you work on it: claim it (assign + start work)')
    # Only In Progress: an unassigned ticket in a review status such as "QA" is
    # waiting for the team pool by design, and Open is covered by the claim hint.
    if writing and assignee is None and status_name.lower() == "in progress":
        hints.append("ticket is unassigned while you work on it: assign it")
    if writing and assignee and me and assignee != me and not done:
        hints.append(f"ticket is assigned to {_user_label(fields.get('assignee'))}, not to you")
    if writing and done:
        hints.append(f'ticket is already "{status_name}": reopen it if the work continues')
    if done and not resolution:
        hints.append(f'ticket is "{status_name}" without a resolution')
    if resolution and category and not done:
        hints.append(f'ticket carries resolution "{resolution.get("name", "?")}" but is "{status_name}"')
    return hints


def _time_hints(fields: dict) -> list[str]:
    """Hint when more time is logged than estimated."""
    tracking = fields.get("timetracking") or {}
    spent = tracking.get("timeSpentSeconds")
    estimate = tracking.get("originalEstimateSeconds")
    if isinstance(spent, int) and isinstance(estimate, int) and 0 < estimate < spent:
        return [f"logged time {_duration(spent)} exceeds the estimate {_duration(estimate)}"]
    return []


def ticket_hints(fields: dict, me: str | None, writing: bool) -> list[str]:
    """Hints for states that are likely wrong for the action just taken."""
    return _workflow_hints(fields, me, writing) + _time_hints(fields)


def render_ticket_state(key: str, fields: dict, me: str | None, writing: bool) -> list[str]:
    """The block as lines: two lines of state, then one line per hint."""
    status = (fields.get("status") or {}).get("name", "?")
    issuetype = (fields.get("issuetype") or {}).get("name", "?")
    assignee = fields.get("assignee")
    who = _user_label(assignee)
    if me and _user_id(assignee) == me:
        who += " (you)"
    resolution = (fields.get("resolution") or {}).get("name", "–")
    tracking = fields.get("timetracking") or {}
    labels = ", ".join(fields.get("labels") or []) or "–"
    lines = [
        f"── {key} · {issuetype} · {status} · resolution: {resolution} · assignee: {who}",
        "   time: logged {} / estimate {} / remaining {} · labels: {}".format(
            _duration(tracking.get("timeSpentSeconds")),
            _duration(tracking.get("originalEstimateSeconds")),
            _duration(tracking.get("remainingEstimateSeconds")),
            labels,
        ),
    ]
    lines.extend(f"(!) {hint}" for hint in ticket_hints(fields, me, writing))
    return lines


def _status_claim_reason(fields: dict, status_sets: dict | None) -> str | None:
    """Why the status says nobody is working on the ticket, or None.

    The status category decides, not ``working_status_names``: that set lists
    where rejected work lands and includes Open, To Do and Backlog.
    """
    sets = status_sets or {}
    status = fields.get("status") or {}
    name = status.get("name", "?")
    category = ((status.get("statusCategory") or {}).get("key") or "").lower()
    if category == "done" or name in sets.get("resolved", ()):
        return f'status "{name}" is resolved: reopen it'
    if category == "new":
        return f'status "{name}" is not started'
    if name in sets.get("qa", ()):
        return f'status "{name}" is a review status'
    return None


def _assignee_claim_reason(fields: dict, me: str | None) -> str | None:
    """Why the assignee is not the caller, or None (also when the caller is unknown)."""
    assignee = _user_id(fields.get("assignee"))
    if assignee is None:
        return "unassigned"
    if me and assignee != me:
        return f"assigned to {_user_label(fields.get('assignee'))}"
    return None


def claim_check(key: str, fields: dict, me: str | None, status_sets: dict | None) -> dict:
    """Whether the caller still has to take ``key`` before working on it.

    Returns ``{"needed", "reasons", "commands", "assignee", "status"}``;
    ``assignee`` and ``status`` hold the single reasons or None. The commands
    never name a transition: workflows differ, so the start or reopen
    transition is picked from ``jira-transition.py list``.
    """
    assignee = _assignee_claim_reason(fields, me)
    status = _status_claim_reason(fields, status_sets)
    commands = []
    if assignee:
        commands.append(f"jira-issue.py update {key} --assignee me")
    if status:
        commands.append(f"jira-transition.py list {key}")
        commands.append(f'jira-transition.py do {key} "<start or reopen transition from the list>"')
    reasons = [r for r in (assignee, status) if r]
    return {"needed": bool(reasons), "reasons": reasons, "commands": commands, "assignee": assignee, "status": status}


def claim_notice(key: str, check: dict) -> list[str]:
    """The claim check as text lines, empty when nothing is needed."""
    if not check["needed"]:
        return []
    lines = [f"!! CLAIM {key} before you comment, measure or edit: " + "; ".join(check["reasons"])]
    lines.extend(f"   {n}. {cmd}" for n, cmd in enumerate(check["commands"], 1))
    return lines


def claim_warning(key: str, check: dict) -> str | None:
    """One line for a comment on a ticket nobody works on, or None.

    Only when both hold: the caller is not the assignee and the status is not
    a working one. Commenting on someone else's ticket in progress is normal.
    """
    if not (check["assignee"] and check["status"]):
        return None
    return (
        f"{key} is not claimed ({check['assignee']}; {check['status']}). "
        f"If you are taking it: jira-issue.py update {key} --assignee me, "
        f"then the start transition from jira-transition.py list {key}"
    )


def print_ticket_state(
    client, key: str, ctx_obj: dict | None = None, writing: bool = True, me: str | None = None
) -> None:
    """Print the state block for ``key`` to stderr, unless output is machine-read.

    ``writing`` is True when the command wrote *to* the ticket (comment,
    worklog, link, update). A transition or a create produced the state it
    shows, so it passes False: the claim, foreign-assignee and reopen hints
    would describe its own result, while the resolution and time checks stay.

    ``ctx_obj`` is the Click context object of the calling script; its ``json``
    and ``quiet`` flags suppress the block. ``me`` is the caller's id when the
    command already looked it up, which saves the ``myself()`` call.
    """
    ctx_obj = ctx_obj or {}
    if ctx_obj.get("json") or ctx_obj.get("quiet") or not _enabled():
        return
    try:
        state = _fetch_state(client, key, me)
        if state is None:
            return
        lines = render_ticket_state(state[0], state[1], state[2], writing)
    except Exception as exc:
        print(f"── {key}: ticket state unavailable ({type(exc).__name__})", file=sys.stderr)
        return
    print("\n".join(lines), file=sys.stderr)


def caller_id(client) -> str | None:
    """The caller's user id, or None when ``myself()`` fails."""
    try:
        return _user_id(client.myself())
    except Exception:
        return None


def _fetch_state(client, key: str, me: str | None = None) -> tuple[str, dict, str | None] | None:
    """Return (key, fields, caller id) for ``key``, or None without usable data.

    Lookup errors of the issue read propagate; a failed ``myself()`` only
    leaves the caller unknown. A known ``me`` skips the ``myself()`` call.
    """
    issue = client.issue(key, fields=FIELDS)
    fields = issue.get("fields") if isinstance(issue, dict) else None
    if not isinstance(fields, dict):
        return None
    return issue.get("key") or key, fields, me or caller_id(client)


def ticket_state_data(key: str, fields: dict, me: str | None, writing: bool) -> dict:
    """The state as a JSON-ready dict: the same facts and hints as the text block."""
    status = fields.get("status") or {}
    assignee = _user_id(fields.get("assignee"))
    tracking = fields.get("timetracking") or {}
    return {
        "key": key,
        "status": status.get("name"),
        "status_category": (status.get("statusCategory") or {}).get("key"),
        "issuetype": (fields.get("issuetype") or {}).get("name"),
        "resolution": (fields.get("resolution") or {}).get("name"),
        "assignee": assignee,
        "assignee_is_you": None if me is None or assignee is None else assignee == me,
        "time_spent_seconds": tracking.get("timeSpentSeconds"),
        "original_estimate_seconds": tracking.get("originalEstimateSeconds"),
        "remaining_estimate_seconds": tracking.get("remainingEstimateSeconds"),
        "labels": list(fields.get("labels") or []),
        "hints": ticket_hints(fields, me, writing),
    }


def with_ticket_state(client, key: str, data, writing: bool = True, ctx_obj: dict | None = None, me: str | None = None):
    """Return ``data`` with a ``ticket_state`` field for ``--json`` output.

    Only a dict gains the field, so every key a consumer already reads stays
    where it was; a list or any other shape is returned unchanged. A lookup
    error is recorded as ``{"key": ..., "error": "<ExceptionType>"}`` and
    never fails the command. ``JIRA_TICKET_STATE=0`` leaves ``data`` as is, and
    so does a ``quiet`` flag in ``ctx_obj``: some commands check ``--json``
    before ``--quiet``, and ``--quiet`` must not gain the field. ``me`` is as
    in :func:`print_ticket_state`.
    """
    if not isinstance(data, dict) or (ctx_obj or {}).get("quiet") or not _enabled():
        return data
    try:
        state = _fetch_state(client, key, me)
        if state is None:
            return data
        ticket_state = ticket_state_data(state[0], state[1], state[2], writing)
    except Exception as exc:
        ticket_state = {"key": key, "error": type(exc).__name__}
    return {**data, "ticket_state": ticket_state}


def warn_if_unclaimed(client, key: str, ctx_obj: dict | None = None) -> str | None:
    """Before a comment: warn on stderr when nobody works on ``key``.

    Prints :func:`claim_warning` and returns the caller's id, so the state
    block after the write needs no second ``myself()``. Silent under
    ``--quiet`` and ``JIRA_TICKET_STATE=0``; a lookup error is ignored, the
    write goes ahead either way. Costs one issue read. The QA and resolved
    status names come from the profile in ``ctx_obj`` or the issue key.
    """
    ctx_obj = ctx_obj or {}
    if ctx_obj.get("quiet") or not _enabled():
        return None
    me = caller_id(client)
    try:
        status_sets = load_status_sets(profile=ctx_obj.get("profile"), issue_key=key)
        issue = client.issue(key, fields="status,assignee")
        fields = issue.get("fields") if isinstance(issue, dict) else None
        if not isinstance(fields, dict):
            return me
        line = claim_warning(key, claim_check(key, fields, me, status_sets))
    except Exception:
        return me
    if line:
        print(f"⚠ {line}", file=sys.stderr)
    return me
