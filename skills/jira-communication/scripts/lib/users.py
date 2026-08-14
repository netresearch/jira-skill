"""User lookup and [~username] mention verification helpers.

Mentions posted with an unverified username render as dead text in Jira —
the user is never notified. These helpers let write commands confirm every
mention inside the same CLI invocation (no separate lookup call needed) and
let read commands print technical usernames next to display names so agents
can mention ticket participants without any lookup at all.
"""

import re
import sys

from .config import is_cloud_url
from .errors import AuthenticationError, CaptchaError, _sanitize_error
from .output import error

# [~username] wiki-markup mention. Cloud emits [~accountid:<id>] instead.
# A leading backslash escapes the mention into literal text — skip those.
MENTION_PATTERN = re.compile(r"(?<!\\)\[~([^\]\s]+)\]")

_ACCOUNTID_PREFIX = "accountid:"

# {code}/{noformat} spans render their content literally, so a mention inside
# them never notifies anyone — quoting a log line must not trip the gate.
_LITERAL_BLOCK_RE = re.compile(r"\{(code|noformat)(?::[^}\n]*)?\}.*?\{\1\}", re.DOTALL | re.IGNORECASE)


def is_cloud_client(client) -> bool:
    """Mock-friendly Cloud detection via the URL (repo convention — the
    ``cloud`` attribute is easy to omit in mocks, see LazyJiraClient.jql)."""
    url = getattr(client, "url", "")
    return is_cloud_url(url) if isinstance(url, str) else False


def extract_mentions(text: str) -> list[str]:
    """Return unique [~...] mention identifiers in order of first appearance.

    Skips mentions inside {code}/{noformat} blocks (rendered literally) and
    backslash-escaped literals (``\\[~...]``).
    """
    stripped = _LITERAL_BLOCK_RE.sub("", text or "")
    seen: list[str] = []
    for match in MENTION_PATTERN.finditer(stripped):
        ident = match.group(1)
        if ident not in seen:
            seen.append(ident)
    return seen


def person_label(user: dict | None, fallback: str = "Unknown") -> str:
    """Render a user dict as 'Display Name (username)'.

    The parenthesized identifier is what mentions and --assignee need: the
    technical username on Server/DC, ``accountid:<id>`` on Cloud (whose user
    dicts carry no ``name``).
    """
    if not user:
        return fallback
    display = user.get("displayName") or user.get("name") or fallback
    name = user.get("name")
    if name and name != display:
        return f"{display} ({name})"
    if not name and user.get("accountId"):
        return f"{display} (accountid:{user['accountId']})"
    return display


def mention_token(user: dict) -> str | None:
    """The [~...] markup that actually notifies this user, or None."""
    name = user.get("name") or user.get("key")
    if name:
        return f"[~{name}]"
    account_id = user.get("accountId")
    if account_id:
        return f"[~{_ACCOUNTID_PREFIX}{account_id}]"
    return None


def find_users(client, query: str, limit: int = 10) -> list[dict]:
    """Search users by name/username/email fragment. Returns raw user dicts.

    atlassian-python-api v3 routes the fragment via ``query=`` only on Cloud;
    Server/DC requires ``username=`` (with ``query=`` the library returns an
    error string there, never results).
    """
    if is_cloud_client(client):
        users = client.user_find_by_user_string(query=query, limit=limit)
    else:
        users = client.user_find_by_user_string(username=query, limit=limit)
    if isinstance(users, list):
        return [u for u in users if isinstance(u, dict)]
    return []


def _infrastructure_error(exc: Exception) -> bool:
    """True for failures that mean 'the lookup could not run', never 'no such user':
    auth/CAPTCHA challenges and any HTTP status other than 404."""
    if isinstance(exc, (AuthenticationError, CaptchaError)):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return status is not None and status != 404


def verify_mentions(client, text: str) -> dict[str, list[dict]]:
    """Verify every [~username] mention in ``text`` against Jira.

    Returns a dict of unknown mention identifiers mapped to suggestion user
    dicts (may be empty). An empty return dict means every mention resolved.
    [~accountid:...] mentions are machine-generated identifiers and are
    skipped rather than guessed at. On Cloud a plain [~username] mention can
    never notify (Cloud requires the accountid form), so it is always
    reported, with [~accountid:...] suggestions. Auth/transport failures
    propagate — they are not evidence that a user does not exist.
    """
    unknown: dict[str, list[dict]] = {}
    cloud = is_cloud_client(client)
    for ident in extract_mentions(text):
        if ident.startswith(_ACCOUNTID_PREFIX):
            continue
        if not cloud:
            try:
                user = client.user(username=ident)
                if isinstance(user, dict) and (user.get("name") or user.get("key")):
                    continue
            except Exception as exc:
                if _infrastructure_error(exc):
                    raise
                # 404 on exact lookup — the mention is unknown; fall through
                # to the suggestion search below.
        try:
            suggestions = find_users(client, ident, limit=5)
        except Exception as exc:
            if _infrastructure_error(exc):
                raise
            # Suggestions are best-effort; report the mention as unknown
            # without candidates rather than failing the whole check.
            suggestions = []
        unknown[ident] = suggestions
    return unknown


def format_unknown_mentions(unknown: dict[str, list[dict]]) -> str:
    """Human-readable lines for an ``verify_mentions`` result, suggestion
    tokens rendered in the form that actually notifies ([~name] on Server/DC,
    [~accountid:...] on Cloud)."""
    lines = []
    for ident, suggestions in unknown.items():
        line = f"[~{ident}] does not match any notifiable Jira user"
        candidates = [
            f"{token} ({user.get('displayName', '?')})" for user in suggestions if (token := mention_token(user))
        ]
        if candidates:
            line += " — did you mean: " + ", ".join(candidates)
        lines.append(line)
    return "\n  ".join(lines)


def check_mentions_cli(client, text: str | None, skip: bool = False) -> None:
    """Shared CLI gate for every command that posts wiki-markup with mentions.

    No-op when ``skip`` is set or the text carries no ``[~`` (zero API calls).
    Exits 1 with suggestions on unknown mentions, and with the sanitized real
    error on auth/transport failures — never misreporting those as an
    unknown username.
    """
    if skip or not text or "[~" not in text:
        return
    try:
        unknown = verify_mentions(client, text)
    except Exception as exc:
        error(
            f"Mention verification failed ({_sanitize_error(str(exc))}) — a transport/auth problem, not an unknown username",
            suggestion="Fix credentials/connectivity, or re-run with --no-verify-mentions to post without the check.",
        )
        sys.exit(1)
    if not unknown:
        return
    error(
        "Unverified mention(s):\n  " + format_unknown_mentions(unknown),
        suggestion="Use an exact identifier from the suggestions, or re-run with --no-verify-mentions to post as-is.",
    )
    sys.exit(1)
