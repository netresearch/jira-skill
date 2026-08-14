"""User lookup and [~username] mention verification helpers.

Mentions posted with an unverified username render as dead text in Jira —
the user is never notified. These helpers let write commands confirm every
mention inside the same CLI invocation (no separate lookup call needed) and
let read commands print technical usernames next to display names so agents
can mention ticket participants without any lookup at all.
"""

import re

# [~username] wiki-markup mention. Cloud emits [~accountid:<id>] instead.
MENTION_PATTERN = re.compile(r"\[~([^\]\s]+)\]")

_ACCOUNTID_PREFIX = "accountid:"


def extract_mentions(text: str) -> list[str]:
    """Return unique [~...] mention identifiers in order of first appearance."""
    seen: list[str] = []
    for match in MENTION_PATTERN.finditer(text or ""):
        ident = match.group(1)
        if ident not in seen:
            seen.append(ident)
    return seen


def person_label(user: dict | None, fallback: str = "Unknown") -> str:
    """Render a user dict as 'Display Name (username)'.

    The parenthesized technical username is what [~...] mentions and
    --assignee need; it only exists on Server/DC responses, so Cloud
    (accountId-only) users render as the bare display name.
    """
    if not user:
        return fallback
    display = user.get("displayName") or user.get("name") or fallback
    name = user.get("name")
    if name and name != display:
        return f"{display} ({name})"
    return display


def find_users(client, query: str, limit: int = 10) -> list[dict]:
    """Search users by name/username/email fragment. Returns raw user dicts.

    atlassian-python-api v3 routes the fragment via ``query=`` only on Cloud;
    Server/DC requires ``username=`` (with ``query=`` the library silently
    returns nothing there).
    """
    if getattr(client, "cloud", False):
        users = client.user_find_by_user_string(query=query, limit=limit)
    else:
        users = client.user_find_by_user_string(username=query, limit=limit)
    if isinstance(users, list):
        return [u for u in users if isinstance(u, dict)]
    return []


def verify_mentions(client, text: str) -> dict[str, list[dict]]:
    """Verify every [~username] mention in ``text`` against Jira.

    Returns a dict of unknown mention identifiers mapped to suggestion user
    dicts (may be empty). An empty return dict means every mention resolved.
    [~accountid:...] mentions (Jira Cloud) are machine-generated identifiers
    and are skipped rather than guessed at.
    """
    unknown: dict[str, list[dict]] = {}
    for ident in extract_mentions(text):
        if ident.startswith(_ACCOUNTID_PREFIX):
            continue
        try:
            user = client.user(username=ident)
            if isinstance(user, dict) and (user.get("name") or user.get("key")):
                continue
        except Exception:
            pass
        try:
            suggestions = find_users(client, ident, limit=5)
        except Exception:
            suggestions = []
        unknown[ident] = suggestions
    return unknown
