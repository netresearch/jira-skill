"""Helpers for Jira issue changelog / status-history analysis."""

from datetime import datetime, timedelta
from typing import Literal

TransitionKind = Literal["into_qa", "reject", "forward", "resolved", "out", "other"]


def parse_jira_datetime(s: str) -> datetime:
    """Parse a Jira ISO-8601 timestamp, including the ``+0000`` variant.

    Python 3.10's :func:`datetime.fromisoformat` rejects the compact
    ``+0000`` form Jira emits — normalise to ``+00:00`` first.
    """
    if len(s) >= 5 and s[-5] in "+-" and s[-4:].isdigit():
        s = s[:-2] + ":" + s[-2:]
    return datetime.fromisoformat(s)


def extract_status_transitions(issue: dict) -> list[dict]:
    """Extract status-change transitions from an expanded issue payload.

    Requires the issue to have been fetched with ``?expand=changelog``.
    Non-status field changes are ignored. Transitions are returned sorted
    by timestamp (oldest first) with the timestamp parsed to a timezone-aware
    :class:`datetime`.

    Returns:
        List of dicts ``{"created": datetime, "from": str, "to": str}``.
    """
    transitions: list[dict] = []
    histories = issue.get("changelog", {}).get("histories", [])
    for h in histories:
        created_raw = h.get("created")
        if not created_raw:
            continue
        try:
            created = parse_jira_datetime(created_raw)
        except ValueError:
            continue
        for item in h.get("items", []):
            if item.get("field") != "status":
                continue
            transitions.append(
                {
                    "created": created,
                    "from": item.get("fromString") or "",
                    "to": item.get("toString") or "",
                }
            )
    transitions.sort(key=lambda t: t["created"])
    return transitions


def compute_time_in_status(
    issue_created: datetime,
    transitions: list[dict],
    current_status: str,
    now: datetime,
) -> dict[str, timedelta]:
    """Sum the time an issue has spent in each status.

    Args:
        issue_created: When the issue was created (tz-aware datetime).
        transitions: Output of :func:`extract_status_transitions`,
            sorted oldest first.
        current_status: Status name at ``now`` — used for the final open
            segment (and as sole segment when the issue has no transitions).
        now: Reference "now" datetime.

    Returns:
        Mapping of status name → total :class:`timedelta` in that status.
    """
    result: dict[str, timedelta] = {}

    def _add(status: str, delta: timedelta) -> None:
        if delta.total_seconds() <= 0:
            delta = timedelta(0)
        result[status] = result.get(status, timedelta(0)) + delta

    if not transitions:
        _add(current_status, now - issue_created)
        return result

    # First segment: issue creation → first transition
    first = transitions[0]
    initial_status = first["from"] or current_status
    _add(initial_status, first["created"] - issue_created)

    # Middle segments: time spent in the status we were in *before* each later transition
    for i in range(1, len(transitions)):
        prev = transitions[i - 1]
        curr = transitions[i]
        # The status between prev and curr is prev["to"] (also curr["from"])
        status = prev["to"] or curr["from"] or current_status
        _add(status, curr["created"] - prev["created"])

    # Final open segment: last transition → now
    last = transitions[-1]
    _add(last["to"] or current_status, now - last["created"])

    return result


def extract_status_transitions_with_authors(issue: dict) -> list[dict]:
    """Like :func:`extract_status_transitions` but preserves transition author.

    Each entry adds ``author_name`` (display name) and ``author_key`` (the
    stable identifier — Server/DC ``name`` or Cloud ``accountId``).
    """
    transitions: list[dict] = []
    histories = issue.get("changelog", {}).get("histories", [])
    for h in histories:
        created_raw = h.get("created")
        if not created_raw:
            continue
        try:
            created = parse_jira_datetime(created_raw)
        except ValueError:
            continue
        author = h.get("author") or {}
        author_name = author.get("displayName", "")
        author_key = author.get("name") or author.get("accountId") or ""
        for item in h.get("items", []):
            if item.get("field") != "status":
                continue
            transitions.append(
                {
                    "created": created,
                    "from": item.get("fromString") or "",
                    "to": item.get("toString") or "",
                    "author_name": author_name,
                    "author_key": author_key,
                }
            )
    transitions.sort(key=lambda t: t["created"])
    return transitions


def classify_transition(transition: dict, status_sets: dict) -> "TransitionKind":
    """Classify a status transition against qa/working/resolved sets.

    Returns one of:
      * ``into_qa``  — moving from a non-QA state into a QA state (handover)
      * ``reject``   — moving from a QA state back to a working state (fail)
      * ``forward``  — moving between two distinct QA states (e.g. QA→QA2,
                       Review→UAT) — a multi-stage QA progression, NOT a fail
      * ``resolved`` — terminal success (any state → resolved set)
      * ``out``      — leaving QA into something not classified above
      * ``other``    — neither side touches QA
    """
    qa = status_sets["qa"]
    working = status_sets["working"]
    resolved = status_sets["resolved"]
    src = transition["from"]
    dst = transition["to"]
    if dst in resolved:
        return "resolved"
    src_in_qa = src in qa
    dst_in_qa = dst in qa
    if not src_in_qa and dst_in_qa:
        return "into_qa"
    if src_in_qa and dst in working:
        return "reject"
    if src_in_qa and dst_in_qa and src != dst:
        return "forward"
    if src_in_qa and not dst_in_qa:
        return "out"
    return "other"


def find_transition_window(transitions: list[dict], target_index: int) -> tuple[datetime | None, datetime | None]:
    """Return (T_prev, T_next) bracketing ``transitions[target_index]``.

    Both endpoints are *other* status changes, ignoring same-second duplicates.
    Either may be ``None`` if no bracketing transition exists.
    """
    if not (0 <= target_index < len(transitions)):
        return None, None
    target_t = transitions[target_index]["created"]
    t_prev = None
    for t in reversed(transitions[:target_index]):
        if t["created"] < target_t:
            t_prev = t["created"]
            break
    t_next = None
    for t in transitions[target_index + 1 :]:
        if t["created"] > target_t:
            t_next = t["created"]
            break
    return t_prev, t_next


def format_timedelta(delta: timedelta) -> str:
    """Format a :class:`timedelta` as a short human-readable string.

    Examples: ``3d 4h``, ``5h 30m``, ``42m``, ``0m``.
    Negative durations are clamped to ``0m``.
    """
    total = int(delta.total_seconds())
    if total <= 0:
        return "0m"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
