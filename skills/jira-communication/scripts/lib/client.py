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

ACCOUNT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9:\-]+$')
LEGACY_ACCOUNT_ID_PATTERN = re.compile(r'^[a-f0-9]{24}$')


def is_account_id(s: str) -> bool:
    """Check if a string looks like a Jira Cloud account ID.

    Cloud account IDs come in two formats:
    - New format with colon: '557058:d5765ebc-27de-4ce3-b520-a77a87e5e99a'
    - Legacy 24-char hex: '5b10ac8d82e05b22cc7d4ef5'
    """
    if not s:
        return False
    if ':' in s:
        return bool(ACCOUNT_ID_PATTERN.match(s))
    return bool(LEGACY_ACCOUNT_ID_PATTERN.match(s))

# === INLINE_START: client ===


class CaptchaError(Exception):
    """Error raised when Jira requires CAPTCHA resolution.

    This happens when Jira Server/DC detects suspicious login activity
    and requires the user to complete a CAPTCHA challenge in the web UI.
    """

    def __init__(self, message: str, login_url: str):
        super().__init__(message)
        self.login_url = login_url


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
        login_url=login_url
    )


def _patch_session_for_captcha(client: Jira, jira_url: str) -> None:
    """Patch the Jira client session to detect CAPTCHA challenges.

    The atlassian-python-api library doesn't check for CAPTCHA responses,
    so we patch the session's request method to add this check.

    Args:
        client: Jira client instance to patch
        jira_url: Base Jira URL for error messages
    """
    original_request = client._session.request

    def patched_request(method: str, url: str, **kwargs) -> Response:
        response = original_request(method, url, **kwargs)
        _check_captcha_challenge(response, jira_url)
        return response

    client._session.request = patched_request


class LazyJiraClient:
    """Deferred Jira client that supports issue-key/URL-based profile resolution.

    Stores connection parameters and creates the actual Jira client lazily on
    first attribute access. CLI subcommands can call with_context() to provide
    issue_key/url for automatic profile resolution before the first API call.

    Usage in CLI scripts::

        # Group callback — no connection made yet
        ctx.obj['client'] = LazyJiraClient(env_file=env_file, profile=profile)

        # Subcommand — provide issue_key context, then use normally
        ctx.obj['client'].with_context(issue_key=issue_key)
        client = ctx.obj['client']
        client.issue(issue_key)  # Client created here on first access
    """

    def __init__(self, env_file: str | None = None, profile: str | None = None):
        object.__setattr__(self, '_env_file', env_file)
        object.__setattr__(self, '_profile', profile)
        object.__setattr__(self, '_issue_key', None)
        object.__setattr__(self, '_url', None)
        object.__setattr__(self, '_client', None)

    def with_context(self, issue_key: str | None = None, url: str | None = None):
        """Set resolution context for automatic profile matching.

        Must be called before the first API call. Has no effect if the
        client is already initialized.

        If *issue_key* looks like a URL (starts with http(s)://), it is
        also used as *url* for host-based profile resolution.
        """
        if object.__getattribute__(self, '_client') is None:
            if issue_key is not None:
                object.__setattr__(self, '_issue_key', issue_key)
                # Detect URL passed as issue_key → enable host-based resolution
                if url is None and issue_key.startswith(('http://', 'https://')):
                    object.__setattr__(self, '_url', issue_key)
            if url is not None:
                object.__setattr__(self, '_url', url)
        return self

    def __getattr__(self, name):
        client = object.__getattribute__(self, '_client')
        if client is None:
            client = get_jira_client(
                env_file=object.__getattribute__(self, '_env_file'),
                profile=object.__getattribute__(self, '_profile'),
                issue_key=object.__getattribute__(self, '_issue_key'),
                url=object.__getattribute__(self, '_url'),
            )
            object.__setattr__(self, '_client', client)
        return getattr(client, name)


def get_jira_client(env_file: str | None = None, profile: str | None = None,
                    issue_key: str | None = None, url: str | None = None) -> Jira:
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

    jira_url = config['JIRA_URL']
    auth_mode = get_auth_mode(config)

    # Determine if Cloud or Server/DC
    is_cloud = config.get('JIRA_CLOUD', '').lower() == 'true'
    if 'JIRA_CLOUD' not in config:
        is_cloud = is_cloud_url(jira_url)

    try:
        if auth_mode == 'pat':
            # Server/DC with Personal Access Token
            client = Jira(
                url=jira_url,
                token=config['JIRA_PERSONAL_TOKEN'],
                cloud=is_cloud,
                timeout=JIRA_TIMEOUT,
            )
        else:
            # Cloud with username + API token
            client = Jira(
                url=jira_url,
                username=config['JIRA_USERNAME'],
                password=config['JIRA_API_TOKEN'],
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
        client._session.mount('https://', adapter)
        client._session.mount('http://', adapter)

        # Patch session to detect CAPTCHA challenges (primarily for Server/DC)
        _patch_session_for_captcha(client, jira_url)

        return client
    except CaptchaError:
        # Re-raise CAPTCHA errors with full context
        raise
    except Exception as e:
        # Sanitize error message to prevent credential leakage
        error_msg = _sanitize_error(str(e))
        if auth_mode == 'pat':
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
        r'(authorization:\s*)\S+(?:\s+\S+)?',
        r'\1***',
        message,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r'(bearer |basic |token=|password=|api_token=|api_key=|secret=|access_token=|private_token=|apikey=|auth_token=)\S+',
        r'\1***',
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized

# === INLINE_END: client ===
