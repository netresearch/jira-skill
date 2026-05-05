"""JQL helper utilities.

Keep all escaping/quoting logic centralized so callers don't hand-roll
f-string JQL snippets.
"""


def jql_escape(value: str) -> str:
    """Escape a value for use inside a double-quoted JQL string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
