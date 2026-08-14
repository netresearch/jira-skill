"""Typed Jira transport errors and error-message sanitization.

Lives in its own module so that both ``lib.client`` (which raises these from
its patched session) and ``lib.users`` (which must let them propagate instead
of misreporting them as "unknown user") can import them without an import
cycle. ``lib.client`` re-exports every name for existing importers.
"""

import re


class CaptchaError(Exception):
    """Error raised when Jira requires CAPTCHA resolution.

    This happens when Jira Server/DC detects suspicious login activity
    and requires the user to complete a CAPTCHA challenge in the web UI.
    """

    def __init__(self, message: str, login_url: str):
        super().__init__(message)
        self.login_url = login_url


class AuthenticationError(Exception):
    """Raised when Jira returns 401 or 403 on an authenticated request.

    Provides a typed alternative to inspecting raw HTTP status codes or
    string-matching error messages for authentication failures.
    """


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
