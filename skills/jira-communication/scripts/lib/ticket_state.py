# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""A short state block for the ticket a command just read or changed.

A write that reports only ``✓ Added comment`` says nothing about the ticket it
landed on. An agent can comment, link and log time on a ticket that is still
Open and unassigned, or that belongs to someone else, and never see it: the
status field is the one signal colleagues read, and no output showed it.

``print_ticket_state`` appends status, assignee, resolution and time tracking,
plus a hint for each state that is likely wrong for the action. It prints to
stderr in text mode only, so ``--json`` and ``--quiet`` output stays exactly as
it was, and it never fails the command: a lookup error costs one line.
``JIRA_TICKET_STATE=0`` turns it off.
"""

import os
import sys

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


def print_ticket_state(client, key: str, ctx_obj: dict | None = None, writing: bool = True) -> None:
    """Print the state block for ``key`` to stderr, unless output is machine-read.

    ``writing`` is True when the command wrote *to* the ticket (comment,
    worklog, link, update). A transition or a create produced the state it
    shows, so it passes False: the claim, foreign-assignee and reopen hints
    would describe its own result, while the resolution and time checks stay.

    ``ctx_obj`` is the Click context object of the calling script; its ``json``
    and ``quiet`` flags suppress the block.
    """
    ctx_obj = ctx_obj or {}
    if ctx_obj.get("json") or ctx_obj.get("quiet") or not _enabled():
        return
    try:
        issue = client.issue(key, fields=FIELDS)
        fields = issue.get("fields") if isinstance(issue, dict) else None
        if not isinstance(fields, dict):
            return
        try:
            me = _user_id(client.myself())
        except Exception:
            me = None
        lines = render_ticket_state(issue.get("key") or key, fields, me, writing)
    except Exception as exc:
        print(f"── {key}: ticket state unavailable ({type(exc).__name__})", file=sys.stderr)
        return
    print("\n".join(lines), file=sys.stderr)
