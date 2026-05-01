"""Jira client initialization for CLI scripts."""

import re
from urllib.parse import urlparse

from atlassian import Jira
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import get_auth_mode, is_cloud_url, load_config, validate_config

# Default timeout for all Jira API requests (seconds)
JIRA_TIMEOUT = 30

# ═══════════════════════════════════════════════════════════════════════════════
# Account ID detection (Jira Cloud)
# ═══════════════════════════════════════════════════════════════════════════════

ACCOUNT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9:\-]+$")
LEGACY_ACCOUNT_ID_PATTERN = re.compile(r"^[a-f0-9]{24}$")


def is_account_id(s: str) -> bool:
    """Check if a string looks like a Jira Cloud account ID.

    Cloud account IDs come in two formats:
    - New format with colon: '557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a'
    - Legacy 24-char hex: '5b10ac8d82e05b22cc7d4ef5'
    """
    if not s:
        return False
    if ":" in s:
        return bool(ACCOUNT_ID_PATTERN.match(s))
    return bool(LEGACY_ACCOUNT_ID_PATTERN.match(s))


def resolve_assignee(client, identifier: str) -> dict:
    """Resolve an assignee identifier to a Jira-API-ready dict.

    Handles:
    - "me" (case-insensitive): resolves via client.myself()
    - Jira Cloud account IDs: returned as {"accountId": ...}
    - Usernames/emails: searched via user_find_by_user_string()

    Returns:
        dict with either {"accountId": ...} or {"name": ...}
    """
    if identifier.lower() == "me":
        user = client.myself()
        if "accountId" in user:
            return {"accountId": user["accountId"]}
        return {"name": user.get("name", user.get("key", ""))}

    if is_account_id(identifier):
        return {"accountId": identifier}

    users = client.user_find_by_user_string(query=identifier)
    if users and isinstance(users, list) and len(users) > 0:
        found = users[0]
        if isinstance(found, dict):
            if "accountId" in found:
                return {"accountId": found["accountId"]}
            return {"name": found.get("name", found.get("key", identifier))}
    # Fall back to raw identifier — let Jira validate
    return {"name": identifier}


def fetch_comments_paginated(client, issue_key: str, page_size: int = 100) -> tuple[list[dict], int | None]:
    """Fetch all comments for an issue, paginating through Jira's REST endpoint.

    The embedded ``fields.comment.comments`` block on an issue payload is
    truncated by Jira (default 50 entries on Server/DC). For long-running
    tickets that truncation silently drops comments. This helper hits
    ``/rest/api/2/issue/{key}/comment`` with explicit ``startAt`` /
    ``maxResults`` until the server signals it has returned everything.

    Returns ``(comments, total)`` where ``total`` is the Jira-reported total
    if available, or ``None`` if the server omits it.
    """
    comments: list[dict] = []
    start_at = 0
    total: int | None = None
    while True:
        payload = (
            client.get(
                f"rest/api/2/issue/{issue_key}/comment",
                params={"startAt": start_at, "maxResults": page_size},
            )
            or {}
        )
        values = payload.get("comments", []) or []
        if total is None:
            raw_total = payload.get("total")
            total = raw_total if isinstance(raw_total, int) else None
        comments.extend(values)
        if not values:
            break
        if total is not None and (start_at + len(values)) >= total:
            break
        start_at += len(values)
    return comments, total


def get_project_issue_types(client, project_key: str, subtask_only: bool | None = None) -> list[dict]:
    """Get available issue types for a project.

    Uses expand=issueTypes to ensure Server/DC includes type metadata.

    Args:
        client: Jira client instance
        project_key: Project key (e.g., "PROJ")
        subtask_only: If True, only subtask types. If False, only non-subtask. None = all.

    Returns:
        List of issue type dicts with at least 'id', 'name', 'subtask' keys.
    """
    project = client.project(project_key, expand="issueTypes")
    types = project.get("issueTypes", [])
    if subtask_only is True:
        return [t for t in types if t.get("subtask")]
    if subtask_only is False:
        return [t for t in types if not t.get("subtask")]
    return types


def resolve_status(client, identifier: str) -> str:
    """Resolve a status identifier to a canonical Jira status name.

    Uses `GET /rest/api/2/status` and matches:
    1. Exact (case-insensitive) on status name → return canonical name
    2. Substring match (unambiguous — exactly one hit) → return canonical name
    3. Otherwise → raise ValueError with candidates

    The same status name may appear multiple times in the API response
    (same workflow status used across several workflows). Names are
    deduplicated before matching.

    Args:
        client: Jira client instance (must support `.get(path)`).
        identifier: User-supplied status string to resolve.

    Returns:
        Canonical status name with original casing from Jira.

    Raises:
        ValueError: No match, or substring match is ambiguous.
    """
    response = client.get("rest/api/2/status") or []
    if not isinstance(response, list):
        response = []
    names: set[str] = {s["name"] for s in response if isinstance(s, dict) and s.get("name")}
    if not names:
        raise ValueError("No statuses available from Jira")

    ident_lower = identifier.lower()

    # 1. Exact match (case-insensitive)
    for name in names:
        if name.lower() == ident_lower:
            return name

    # 2. Substring match (unambiguous)
    substring_matches = sorted(n for n in names if ident_lower in n.lower())
    if len(substring_matches) == 1:
        return substring_matches[0]
    if len(substring_matches) > 1:
        raise ValueError(f"Status '{identifier}' is ambiguous. Candidates: {', '.join(substring_matches)}")

    # 3. No match
    raise ValueError(f"Status '{identifier}' not found. Available: {', '.join(sorted(names))}")


def resolve_subtask_type(client, project_key: str, requested_type: str) -> str | None:
    """Resolve a requested issue type to a valid subtask type for the project.

    Resolution order:
    1. Exact match (case-insensitive) among subtask types
    2. Subtask type whose name contains the requested type (e.g., "Task" → "Sub: Task")
    3. Generic subtask keywords ("subtask", "sub-task") → first available subtask type
    4. Only one subtask type available → return it regardless of name
    5. No match / no subtask types → return None

    Args:
        client: Jira client instance
        project_key: Project key
        requested_type: The issue type name the user requested

    Returns:
        Resolved subtask type name, or None if no match or no subtask types.
    """
    subtask_types = get_project_issue_types(client, project_key, subtask_only=True)
    if not subtask_types:
        return None

    req_lower = requested_type.lower()

    # 1. Exact match (case-insensitive)
    for st in subtask_types:
        if st["name"].lower() == req_lower:
            return st["name"]

    # 2. Subtask type whose name contains the requested type (unambiguous only)
    #    e.g., "Task" matches "Sub: Task", "Bug" matches "Sub: Bug"
    substring_matches = [st for st in subtask_types if req_lower in st["name"].lower()]
    if len(substring_matches) == 1:
        return substring_matches[0]["name"]

    # 3. Generic subtask keywords → first available
    if req_lower in ("subtask", "sub-task", "sub task"):
        return subtask_types[0]["name"]

    # 4. Only one subtask type? Use it (unambiguous).
    if len(subtask_types) == 1:
        return subtask_types[0]["name"]

    return None


# === INLINE_START: client ===


class CaptchaError(Exception):
    """Error raised when Jira requires CAPTCHA resolution.

    This happens when Jira Server/DC detects suspicious login activity
    and requires the user to complete a CAPTCHA challenge in the web UI.
    """

    def __init__(self, message: str, login_url: str):
        super().__init__(message)
        self.login_url = login_url


class SessionExpiredError(Exception):
    """Raised when a 200 OK response carries an HTML session-expiry or login page.

    Jira Server/DC redirects expired sessions to a login page that returns
    200 OK with Content-Type: text/html and no Content-Disposition: attachment.
    Without this check the HTML body would be silently written to disk as if it
    were the requested file.
    """


class AuthenticationError(Exception):
    """Raised when Jira returns 401 or 403 on an authenticated request.

    Provides a typed alternative to inspecting raw HTTP status codes or
    string-matching error messages for authentication failures.
    """


def _check_captcha_challenge(response: Response, jira_url: str) -> None:
    """Check response for CAPTCHA challenge and raise exception if found.

    Jira Server/DC may require CAPTCHA resolution after failed login attempts.
    This is indicated by the X-Authentication-Denied-Reason header containing
    'CAPTCHA_CHALLENGE'.

    Args:
        response: HTTP response to check
        jira_url: Base Jira URL for constructing login URL

    Raises:
        CaptchaError: If CAPTCHA challenge is detected
    """
    header_name = "X-Authentication-Denied-Reason"
    if header_name not in response.headers:
        return

    header_value = response.headers[header_name]
    if "CAPTCHA_CHALLENGE" not in header_value:
        return

    # Extract login URL if present in header, but validate it matches jira_url host
    login_url = f"{jira_url}/login.jsp"
    if "; login-url=" in header_value:
        candidate = header_value.split("; login-url=")[1].strip()
        # Only use the header URL if its host matches the configured Jira host
        candidate_host = urlparse(candidate).netloc.lower()
        jira_host = urlparse(jira_url).netloc.lower()
        if candidate_host == jira_host:
            login_url = candidate

    raise CaptchaError(
        f"CAPTCHA challenge detected!\n\n"
        f"  Jira requires you to solve a CAPTCHA before API access is allowed.\n\n"
        f"  To resolve:\n"
        f"    1. Open {login_url} in your web browser\n"
        f"    2. Log in and complete the CAPTCHA challenge\n"
        f"    3. Retry this command\n\n"
        f"  This typically happens after several failed login attempts.",
        login_url=login_url,
    )


def _check_session_expiry(response: Response, url: str) -> None:
    """Check whether a 200 OK response is actually an HTML session-expiry page.

    Jira Server/DC returns 200 OK with Content-Type: text/html when the session
    has expired and the request is redirected to a login page. Real HTML file
    attachments are distinguished by the presence of Content-Disposition: attachment.

    Args:
        response: HTTP response to check
        url: Effective URL of the response, used in the error message

    Raises:
        SessionExpiredError: If the response looks like a login/session-expiry page
    """
    if response.status_code != 200:
        return
    ct = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if not ct.startswith("text/html"):
        return
    cd = response.headers.get("Content-Disposition", "").lower()
    if "attachment" in cd:
        return
    raise SessionExpiredError(
        f"Request failed: response is HTML without an attachment disposition "
        f"(Content-Type: {ct}, URL: {url}). "
        "The session may have expired or the URL redirected to a login page."
    )


def _check_authentication(response: Response) -> None:
    """Check whether the response signals an authentication failure.

    Raises AuthenticationError for 401 and 403 responses. Must be called
    after _check_captcha_challenge so that CAPTCHA-flavoured 401s (which carry
    the X-Authentication-Denied-Reason header) are attributed to CaptchaError
    rather than the more generic AuthenticationError.

    Args:
        response: HTTP response to check

    Raises:
        AuthenticationError: If the response status is 401 or 403
    """
    if response.status_code in (401, 403):
        raise AuthenticationError(
            f"Authentication failed (HTTP {response.status_code}). Check your credentials or token."
        )


def _handle_response(response: Response, jira_url: str, url: str | None = None) -> None:
    """Run all response-level validation checks.

    Centralises CAPTCHA detection, authentication failure detection, and
    session-expiry detection so every request path benefits from the same
    guards regardless of whether it goes through the patched Jira session
    or a bare requests.get call.

    Call order matters:
    1. CAPTCHA — fires on 401 carrying X-Authentication-Denied-Reason header
    2. Authentication — fires on any remaining 401/403
    3. Session expiry — fires on 200 + text/html without attachment disposition

    Args:
        response: HTTP response to validate
        jira_url: Base Jira URL, used for CAPTCHA login URL construction
        url: Effective request URL for error messages; falls back to
             response.url when not supplied
    """
    _check_captcha_challenge(response, jira_url)
    _check_authentication(response)
    _check_session_expiry(response, url or getattr(response, "url", ""))


def _patch_session_for_response_validation(client: Jira, jira_url: str) -> None:
    """Patch the Jira client session to run response validation on every request.

    The atlassian-python-api library doesn't inspect responses for CAPTCHA
    challenges, authentication failures, or session-expiry HTML pages, so we
    wrap the session's request method to call _handle_response after each
    response is received.

    Args:
        client: Jira client instance to patch
        jira_url: Base Jira URL for error messages
    """
    original_request = client._session.request

    def patched_request(method: str, url: str, **kwargs) -> Response:
        response = original_request(method, url, **kwargs)
        _handle_response(response, jira_url, url=url)
        return response

    client._session.request = patched_request


class LazyJiraClient:
    """Deferred Jira client that supports issue-key/URL-based profile resolution.

    Stores connection parameters and creates the actual Jira client lazily on
    first attribute access. CLI subcommands can call with_context() to provide
    issue_key/url for automatic profile resolution before the first API call.

    Also overrides ``jql()`` to route Atlassian Cloud calls to the
    ``/rest/api/3/search/jql`` endpoint introduced by CHANGE-2046 — the library
    is pinned to api/2 which Atlassian removed from Cloud. Server/DC paths
    delegate to the library unchanged.

    Usage in CLI scripts::

        # Group callback — no connection made yet
        ctx.obj['client'] = LazyJiraClient(env_file=env_file, profile=profile)

        # Subcommand — provide issue_key context, then use normally
        ctx.obj['client'].with_context(issue_key=issue_key)
        client = ctx.obj['client']
        client.issue(issue_key)  # Client created here on first access
    """

    # Maximum issues to drain inside a single jql() call on Cloud before
    # bailing out, regardless of caller's start+limit. Prevents accidental
    # runaway pagination when a caller passes a very large start offset.
    _CLOUD_DRAIN_HARDCAP = 1000
    _CLOUD_SEARCH_ENDPOINT = "rest/api/3/search/jql"

    def __init__(self, env_file: str | None = None, profile: str | None = None):
        object.__setattr__(self, "_env_file", env_file)
        object.__setattr__(self, "_profile", profile)
        object.__setattr__(self, "_issue_key", None)
        object.__setattr__(self, "_url", None)
        object.__setattr__(self, "_client", None)

    def with_context(self, issue_key: str | None = None, url: str | None = None):
        """Set resolution context for automatic profile matching.

        Must be called before the first API call. Has no effect if the
        client is already initialized.

        If *issue_key* looks like a URL (starts with http(s)://), it is
        also used as *url* for host-based profile resolution.
        """
        if object.__getattribute__(self, "_client") is None:
            if issue_key is not None:
                object.__setattr__(self, "_issue_key", issue_key)
                # Detect URL passed as issue_key → enable host-based resolution
                if url is None and issue_key.startswith(("http://", "https://")):
                    object.__setattr__(self, "_url", issue_key)
            if url is not None:
                object.__setattr__(self, "_url", url)
        return self

    def _ensure_client(self) -> Jira:
        """Lazy-create the underlying Jira client on first use."""
        client = object.__getattribute__(self, "_client")
        if client is None:
            client = get_jira_client(
                env_file=object.__getattribute__(self, "_env_file"),
                profile=object.__getattribute__(self, "_profile"),
                issue_key=object.__getattribute__(self, "_issue_key"),
                url=object.__getattribute__(self, "_url"),
            )
            object.__setattr__(self, "_client", client)
        return client

    def __getattr__(self, name):
        return getattr(self._ensure_client(), name)

    def jql(self, jql: str, limit: int = 50, start: int = 0, fields=None, **kwargs) -> dict:
        """Execute a JQL search, routing Cloud to /rest/api/3/search/jql.

        On Atlassian Cloud the library's ``jql()`` hits ``/rest/api/2/search``
        which Atlassian removed (CHANGE-2046). This override calls the new
        cursor-paginated ``/rest/api/3/search/jql`` endpoint directly and
        translates the cursor-based response back to the offset/total shape
        the callers expect (``issues``, ``startAt``, ``maxResults``, ``total``,
        ``isLast``), so ``jira-search``, ``jira-qa-gather`` and
        ``jira-worklog-query`` keep working without changes.

        Synthesized ``total`` semantics:

        * On the final page (``isLast=True``): ``total == len(collected)`` —
          accurate count of the matching result set up to the drained window.
        * Otherwise: ``total == start + len(sliced) + 1`` — a sentinel that
          tells callers paginating via ``start_at`` that more pages exist.

        Inefficiency note: each call drains pages from index 0 up to
        ``start + limit`` because the new endpoint is cursor-based and we
        cannot resume from an offset. Callers that paginate over many pages
        incur quadratic total request cost. Acceptable as a workaround until
        ``atlassian-python-api`` ships Cloud-aware ``jql()``; see
        ``TODO(CHANGE-2046)`` below for the migration path.

        On Server/DC the library's ``jql()`` remains functional via api/2 and
        is called unchanged.
        """
        # TODO(CHANGE-2046): Remove this override once atlassian-python-api
        # supports Cloud /rest/api/3/search/jql natively (tracked upstream as
        # https://github.com/atlassian-api/atlassian-python-api/issues/1631).
        client = self._ensure_client()
        # URL-based Cloud detection is more robust than the library's ``cloud``
        # attribute, which has shifted across versions and is easy to omit in mocks.
        if not is_cloud_url(getattr(client, "url", "") or ""):
            return client.jql(jql, fields=fields, start=start, limit=limit, **kwargs)
        return self._jql_cloud(client, jql, start, limit, fields, expand=kwargs.get("expand"))

    @staticmethod
    def _normalize_jql_fields(fields) -> str:
        """Coerce a fields argument to the comma-separated string the endpoint expects."""
        if fields is None:
            return "*all"
        if isinstance(fields, (list, tuple, set)):
            return ",".join(fields)
        return fields

    def _jql_cloud(
        self,
        client,
        jql: str,
        start: int,
        limit: int,
        fields,
        *,
        expand=None,
    ) -> dict:
        """Cloud path: drain cursor-paginated pages until the window is filled."""
        fields_str = self._normalize_jql_fields(fields)
        target = start + limit
        hardcap = type(self)._CLOUD_DRAIN_HARDCAP
        collected: list = []
        next_token: str | None = None
        is_last = True  # defaults True so an empty initial response yields total=0

        while len(collected) < target and len(collected) < hardcap:
            page = self._fetch_jql_page(client, jql, fields_str, expand, target - len(collected), next_token)
            page_issues = page.get("issues", []) or []
            collected.extend(page_issues)
            is_last = bool(page.get("isLast", True))
            next_token = page.get("nextPageToken")
            if is_last or not next_token or not page_issues:
                break

        return self._synthesize_offset_response(collected, start, limit, is_last)

    def _fetch_jql_page(
        self,
        client,
        jql: str,
        fields: str,
        expand,
        remaining: int,
        next_token: str | None,
    ) -> dict:
        """Fetch a single page from /rest/api/3/search/jql, annotating errors with context."""
        params: dict = {
            "jql": jql,
            "maxResults": min(100, max(1, remaining)),
            "fields": fields,
        }
        if next_token is not None:
            params["nextPageToken"] = next_token
        if expand is not None:
            params["expand"] = expand
        try:
            return client.get(type(self)._CLOUD_SEARCH_ENDPOINT, params=params) or {}
        except Exception as exc:
            if hasattr(exc, "add_note"):  # Python 3.11+
                exc.add_note(f"Cloud override: {type(self)._CLOUD_SEARCH_ENDPOINT} (CHANGE-2046)")
            raise

    @staticmethod
    def _synthesize_offset_response(collected: list, start: int, limit: int, is_last: bool) -> dict:
        """Translate cursor-drained issues into the offset/total response shape callers expect."""
        target = start + limit
        sliced = collected[start:target]
        total = len(collected) if is_last else start + len(sliced) + 1
        return {
            "issues": sliced,
            "startAt": start,
            "maxResults": limit,
            "total": total,
            "isLast": is_last and len(collected) <= target,
        }


def get_jira_client(
    env_file: str | None = None, profile: str | None = None, issue_key: str | None = None, url: str | None = None
) -> Jira:
    """Initialize and return a Jira client.

    Supports two authentication modes:
    - Cloud: JIRA_USERNAME + JIRA_API_TOKEN
    - Server/DC: JIRA_PERSONAL_TOKEN (Personal Access Token)

    When profiles.json exists and no env_file is specified, uses profile
    resolution to determine the correct Jira instance.

    Args:
        env_file: Optional path to environment file (takes precedence over profiles)
        profile: Optional profile name from ~/.jira/profiles.json
        issue_key: Optional issue key for automatic profile resolution
        url: Optional Jira URL for automatic profile resolution

    Returns:
        Configured Jira client instance

    Raises:
        FileNotFoundError: If env file doesn't exist
        ValueError: If configuration is invalid
        ConnectionError: If cannot connect to Jira
    """
    config = load_config(profile=profile, env_file=env_file, issue_key=issue_key, url=url)

    errors = validate_config(config)
    if errors:
        raise ValueError("Configuration errors:\n  " + "\n  ".join(errors))

    jira_url = config["JIRA_URL"]
    auth_mode = get_auth_mode(config)

    # Determine if Cloud or Server/DC
    is_cloud = config.get("JIRA_CLOUD", "").lower() == "true"
    if "JIRA_CLOUD" not in config:
        is_cloud = is_cloud_url(jira_url)

    try:
        if auth_mode == "pat":
            # Server/DC with Personal Access Token
            client = Jira(
                url=jira_url,
                token=config["JIRA_PERSONAL_TOKEN"],
                cloud=is_cloud,
                timeout=JIRA_TIMEOUT,
            )
        else:
            # Cloud with username + API token
            client = Jira(
                url=jira_url,
                username=config["JIRA_USERNAME"],
                password=config["JIRA_API_TOKEN"],
                cloud=is_cloud,
                timeout=JIRA_TIMEOUT,
            )

        # Mount retry adapter for rate limiting (HTTP 429) and transient errors
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        client._session.mount("https://", adapter)
        client._session.mount("http://", adapter)

        # Patch session to run response validation (CAPTCHA, authentication failures, session-expiry HTML pages)
        _patch_session_for_response_validation(client, jira_url)

        return client
    except CaptchaError:
        # Re-raise CAPTCHA errors with full context
        raise
    except Exception as e:
        # Sanitize error message to prevent credential leakage
        error_msg = _sanitize_error(str(e))
        if auth_mode == "pat":
            raise ConnectionError(
                f"Failed to connect to Jira at {jira_url}\n\n"
                f"  Error: {error_msg}\n\n"
                f"  Please verify:\n"
                f"    - JIRA_URL is correct\n"
                f"    - JIRA_PERSONAL_TOKEN is a valid Personal Access Token\n"
            ) from e
        else:
            raise ConnectionError(
                f"Failed to connect to Jira at {jira_url}\n\n"
                f"  Error: {error_msg}\n\n"
                f"  Please verify:\n"
                f"    - JIRA_URL is correct\n"
                f"    - JIRA_USERNAME is your email (Cloud) or username (Server/DC)\n"
                f"    - JIRA_API_TOKEN is valid\n"
            ) from e


def _sanitize_error(message: str) -> str:
    """Remove potential credential fragments from error messages.

    Uses regex to redact values after sensitive keys, rather than a simple
    denylist check that discards the entire message.
    """
    # Redact values following sensitive keys (e.g., "token=abc123" → "token=***")
    # First handle "Authorization: <scheme> <token>" as a single unit
    sanitized = re.sub(
        r"(authorization:\s*)\S+(?:\s+\S+)?",
        r"\1***",
        message,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"(bearer |basic |token=|password=|api_token=|api_key=|secret=|access_token=|private_token=|apikey=|auth_token=)\S+",
        r"\1***",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


# === INLINE_END: client ===
